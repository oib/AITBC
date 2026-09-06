"""CLI utilities for parsing, verifying, and settling energy quotes.

This module provides reusable helpers for the ``aitbc market gpu`` and
``aitbc energy`` command groups. It wraps the canonical
``aitbc.marketplace.energy_pricing`` types with CLI-friendly parsing,
operator-signature verification, freshness checks, and settlement
breakdown computation so command modules stay thin.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from aitbc.marketplace.energy_pricing import (
    DEFAULT_MAX_RATE_AGE_SECONDS,
    DEFAULT_QUOTE_LIFETIME_SECONDS,
    EnergyQuote,
    RefusalCode,
    SettlementRoute,
    compute_evm_buyer_charge,
    compute_energy_net_units,
    compute_native_gross_units,
    evaluate_quote,
)
from aitbc.marketplace.energy_oracle import EVMEnergyOracle
from aitbc.ethereum_rpc import EthereumConfig, EthereumRPCClient


@dataclass(frozen=True)
class QuoteVerification:
    """Result of verifying an energy quote in the CLI."""

    valid: bool
    quote: EnergyQuote
    refusal_code: RefusalCode | None = None
    refusal_reason: str | None = None
    digest_hex: str = ""
    operator_verified: bool = False
    breakdown: dict[str, Any] | None = None


def parse_quote(data: dict[str, Any]) -> EnergyQuote:
    """Parse a quote dict from an API response into an ``EnergyQuote``."""
    return EnergyQuote.from_dict(data)


def verify_quote(
    quote: EnergyQuote,
    *,
    expected_operator_address: str | None = None,
    expected_domain: str | None = None,
    expected_chain_id: str | None = None,
    now: int | None = None,
    max_rate_age_seconds: int = DEFAULT_MAX_RATE_AGE_SECONDS,
) -> QuoteVerification:
    """Verify a quote's signature, freshness, and internal consistency.

    Returns a ``QuoteVerification`` with the digest, operator check result,
    and a refusal code/reason when the quote is not usable.
    """
    now = now if now is not None else int(time.time())
    digest_hex = quote.digest_sha256().hex()

    operator_verified = False
    if expected_operator_address:
        operator_verified = quote.verify_operator_signature(expected_operator_address)
        if not operator_verified:
            return QuoteVerification(
                valid=False,
                quote=quote,
                refusal_code=RefusalCode.INVALID_SIGNATURE,
                refusal_reason="Operator signature is missing or does not recover to the configured address",
                digest_hex=digest_hex,
                operator_verified=False,
            )
    elif quote.operator_signature is None:
        return QuoteVerification(
            valid=False,
            quote=quote,
            refusal_code=RefusalCode.INVALID_SIGNATURE,
            refusal_reason="Quote has no operator signature and no operator address was configured",
            digest_hex=digest_hex,
            operator_verified=False,
        )

    if expected_domain and quote.domain != expected_domain:
        return QuoteVerification(
            valid=False,
            quote=quote,
            refusal_code=RefusalCode.DOMAIN_MISMATCH,
            refusal_reason=f"Quote domain {quote.domain} does not match expected {expected_domain}",
            digest_hex=digest_hex,
            operator_verified=operator_verified,
        )

    if expected_chain_id and quote.chain_id != expected_chain_id:
        return QuoteVerification(
            valid=False,
            quote=quote,
            refusal_code=RefusalCode.CHAIN_MISMATCH,
            refusal_reason=f"Quote chain_id {quote.chain_id} does not match expected {expected_chain_id}",
            digest_hex=digest_hex,
            operator_verified=operator_verified,
        )

    if quote.expires_at <= now:
        return QuoteVerification(
            valid=False,
            quote=quote,
            refusal_code=RefusalCode.EXPIRED,
            refusal_reason=f"Quote expired at {quote.expires_at}",
            digest_hex=digest_hex,
            operator_verified=operator_verified,
        )

    if now - quote.rate_observed_at > max_rate_age_seconds:
        return QuoteVerification(
            valid=False,
            quote=quote,
            refusal_code=RefusalCode.STALE_RATE,
            refusal_reason=f"Rate observed at {quote.rate_observed_at} is older than {max_rate_age_seconds}s",
            digest_hex=digest_hex,
            operator_verified=operator_verified,
        )

    # Recompute the energy floor from the quote's own inputs and check it
    # matches the stored value. This catches tampering with the floor field.
    recomputed = compute_energy_net_units(
        tdp_watts=quote.tdp_watts,
        eur_per_kwh_scaled=quote.eur_per_kwh_scaled,
        ait_per_eur_scaled=quote.ait_per_eur_scaled,
        gpu_count=quote.gpu_count,
        duration_seconds=quote.duration_seconds,
        settlement_unit_scale=quote.settlement_unit_scale,
    )
    if recomputed != quote.net_energy_floor_units:
        return QuoteVerification(
            valid=False,
            quote=quote,
            refusal_code=RefusalCode.FLOOR_MISMATCH,
            refusal_reason=f"Recomputed floor {recomputed} does not match quote floor {quote.net_energy_floor_units}",
            digest_hex=digest_hex,
            operator_verified=operator_verified,
        )

    return QuoteVerification(
        valid=True,
        quote=quote,
        digest_hex=digest_hex,
        operator_verified=operator_verified,
    )


def compute_settlement_breakdown(quote: EnergyQuote) -> dict[str, Any]:
    """Compute the native gross or EVM buyer charge for a quote.

    Returns a dict with ``principal_units``, ``buyer_charge_units``,
    ``provider_credit_units``, ``platform_fee_units``, and ``net_floor_units``
    keyed to the quote's settlement route.
    """
    net = quote.net_energy_floor_units
    if quote.settlement_route == SettlementRoute.NATIVE:
        gross = compute_native_gross_units(net, quote.fee_basis_points)
        fee = gross - net
        return {
            "settlement_route": "native",
            "principal_units": gross,
            "buyer_charge_units": gross,
            "provider_credit_units": gross - fee,
            "platform_fee_units": fee,
            "net_floor_units": net,
        }
    elif quote.settlement_route == SettlementRoute.EVM:
        buyer_charge = compute_evm_buyer_charge(net, quote.fee_basis_points)
        fee = buyer_charge - net
        return {
            "settlement_route": "evm",
            "principal_units": net,
            "buyer_charge_units": buyer_charge,
            "provider_credit_units": net,
            "platform_fee_units": fee,
            "net_floor_units": net,
        }
    else:
        raise ValueError(f"Unsupported settlement route: {quote.settlement_route}")


def verify_quote_against_oracle(
    quote: EnergyQuote,
    *,
    rpc_url: str,
    contract_address: str,
    chain_id: int,
    operator_address: str | None = None,
    now: int | None = None,
) -> QuoteVerification:
    """Verify a quote against the on-chain IEnergyPricing oracle.

    Reads the authoritative profile and rate from the contract at the
    quote's pinned block (or latest) and runs the full ``evaluate_quote``
    gate so the CLI can refuse a quote whose terms no longer match the
    on-chain state.
    """
    now = now if now is not None else int(time.time())
    base = verify_quote(quote, expected_operator_address=operator_address, now=now)
    if not base.valid:
        return base

    rpc = EthereumRPCClient(EthereumConfig(rpc_url=rpc_url, network=str(chain_id)))
    oracle = EVMEnergyOracle(rpc, contract_address, chain_id)
    block = quote.evm_block_number if quote.evm_block_number is not None else "latest"
    profile = oracle.get_profile(quote.resource_id, block_identifier=block)
    rate = oracle.get_rate(block_identifier=block)

    result = evaluate_quote(quote=quote, profile=profile, rate=rate, now=now)
    if not result.approved:
        return QuoteVerification(
            valid=False,
            quote=quote,
            refusal_code=result.refusal_code,
            refusal_reason=result.refusal_reason,
            digest_hex=base.digest_hex,
            operator_verified=base.operator_verified,
        )

    breakdown = compute_settlement_breakdown(quote)
    return QuoteVerification(
        valid=True,
        quote=quote,
        digest_hex=base.digest_hex,
        operator_verified=base.operator_verified,
        breakdown=breakdown,
    )
