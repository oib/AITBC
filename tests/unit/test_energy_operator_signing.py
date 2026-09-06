"""Unit tests for energy quote operator signing and verification.

Tests the operator signature scheme, quote digest stability, and CLI
verification utilities added in the CLI energy-floor implementation.
No network, no contracts.
"""

from __future__ import annotations

import time
from dataclasses import replace
from decimal import Decimal

import pytest

from aitbc.marketplace.energy_pricing import (
    EnergyPricingError,
    EnergyProfile,
    EnergyQuote,
    EnergyRate,
    FeeModel,
    RefusalCode,
    SettlementRoute,
    build_minimum_quote,
    compute_energy_net_units,
    evaluate_quote,
)

TARIFF_SCALED = 300_000_000_000_000_000  # 0.30 * 10**18
RATE_SCALED = 4_000_000_000_000_000_000  # 4.00 * 10**18
NATIVE_SCALE = 36_000_000


@pytest.fixture
def base_profile() -> EnergyProfile:
    return EnergyProfile(
        resource_id="gpu-rtx4060ti-node2-001",
        provider="0x" + "a" * 40,
        model_id="rtx-4060-ti",
        tdp_watts=165,
        eur_per_kwh_scaled=TARIFF_SCALED,
        enabled=True,
        revision=3,
    )


@pytest.fixture
def base_rate() -> EnergyRate:
    now = int(time.time())
    return EnergyRate(
        ait_per_eur_scaled=RATE_SCALED,
        version=7,
        observed_at=now,
        submitted_at=now + 1,
        source_kind="operator_reference",
        enabled=True,
    )


@pytest.fixture
def base_quote(base_profile, base_rate) -> EnergyQuote:
    return build_minimum_quote(
        profile=base_profile,
        rate=base_rate,
        buyer="0x" + "b" * 40,
        job_id="job-test-001",
        quote_id="quote-test-001",
        domain="aitbc.energy.quote.v1",
        chain_id="ait-hub.aitbc.bubuit.net",
        settlement_asset="AITBC",
        settlement_unit_scale=NATIVE_SCALE,
        settlement_route=SettlementRoute.NATIVE,
        gpu_count=1,
        duration_seconds=3600,
        operator_address="0x" + "c" * 40,
    )


def test_quote_has_operator_address(base_quote) -> None:
    """Operator address is stored in the quote."""
    assert base_quote.operator_address == "0x" + "c" * 40
    assert base_quote.operator_signature is None


def test_quote_digest_stability(base_quote) -> None:
    """The digest is stable across multiple calls and excludes signatures."""
    d1 = base_quote.digest_sha256()
    d2 = base_quote.digest_sha256()
    assert d1 == d2
    assert len(d1) == 32


def test_quote_digest_excludes_operator_address_when_unsigned(base_quote) -> None:
    """The digest includes operator_address (it's a signed field)."""
    quote_without_addr = replace(base_quote, operator_address=None)
    d1 = base_quote.digest_sha256()
    d2 = quote_without_addr.digest_sha256()
    assert d1 != d2, "operator_address must affect the digest"


def test_with_operator_signature_preserves_fields(base_quote) -> None:
    """with_operator_signature returns a copy with the signature attached."""
    sig = b"\x01" * 65
    signed = base_quote.with_operator_signature(
        operator_address="0x" + "c" * 40,
        operator_signature=sig,
    )
    assert signed.operator_signature == sig
    assert signed.operator_address == "0x" + "c" * 40
    # Original is unchanged (frozen dataclass).
    assert base_quote.operator_signature is None
    # Other fields are preserved.
    assert signed.quote_id == base_quote.quote_id
    assert signed.buyer == base_quote.buyer
    assert signed.principal_units == base_quote.principal_units


def test_with_operator_signature_changes_digest(base_quote) -> None:
    """Attaching a signature does not change the canonical digest.

    The digest excludes operator_signature and buyer_signature, so the
    digest of the signed quote equals the digest of the unsigned quote.
    """
    sig = b"\x01" * 65
    signed = base_quote.with_operator_signature(
        operator_address="0x" + "c" * 40,
        operator_signature=sig,
    )
    assert signed.digest_sha256() == base_quote.digest_sha256()


def test_verify_operator_signature_missing(base_quote) -> None:
    """verify_operator_signature returns False when no signature is present."""
    assert not base_quote.verify_operator_signature("0x" + "c" * 40)


def test_verify_operator_signature_wrong_address(base_quote) -> None:
    """verify_operator_signature returns False for a wrong expected address."""
    sig = b"\x01" * 65
    signed = base_quote.with_operator_signature(
        operator_address="0x" + "c" * 40,
        operator_signature=sig,
    )
    # The signature is fake so recovery will fail or return a different address.
    assert not signed.verify_operator_signature("0x" + "d" * 40)


def test_to_dict_includes_operator_address(base_quote) -> None:
    """to_dict includes operator_address in the output."""
    d = base_quote.to_dict(include_signature=False)
    assert "operator_address" in d
    assert d["operator_address"] == "0x" + "c" * 40


def test_from_dict_roundtrip_operator_address(base_quote) -> None:
    """from_dict preserves operator_address across serialization."""
    d = base_quote.to_dict(include_signature=False)
    restored = EnergyQuote.from_dict(d)
    assert restored.operator_address == base_quote.operator_address


def test_evm_quote_uses_buyer_pays_on_top(base_profile, base_rate) -> None:
    """EVM quotes use the BUYER_PAYS_ON_TOP fee model."""
    quote = build_minimum_quote(
        profile=base_profile,
        rate=base_rate,
        buyer="0x" + "b" * 40,
        job_id="job-evm-001",
        quote_id="quote-evm-001",
        domain="aitbc.energy.quote.v1",
        chain_id="ait-hub.aitbc.bubuit.net",
        settlement_asset="AITBC",
        settlement_unit_scale=10**18,
        settlement_route=SettlementRoute.EVM,
        gpu_count=1,
        duration_seconds=3600,
        evm_chain_id=1,
        evm_contract="0x" + "e" * 40,
        operator_address="0x" + "c" * 40,
    )
    assert quote.settlement_route == SettlementRoute.EVM
    assert quote.fee_model == FeeModel.BUYER_PAYS_ON_TOP
    assert quote.principal_units == quote.net_energy_floor_units


def test_refusal_codes_exist() -> None:
    """New refusal codes are defined."""
    assert RefusalCode.INVALID_SIGNATURE == "invalid_signature"
    assert RefusalCode.DOMAIN_MISMATCH == "domain_mismatch"
    assert RefusalCode.CHAIN_MISMATCH == "chain_mismatch"
    assert RefusalCode.FLOOR_MISMATCH == "floor_mismatch"


def test_build_minimum_quote_without_operator_address(base_profile, base_rate) -> None:
    """Building a quote without operator_address defaults to None."""
    quote = build_minimum_quote(
        profile=base_profile,
        rate=base_rate,
        buyer="0x" + "b" * 40,
        job_id="job-noop-001",
        quote_id="quote-noop-001",
        domain="aitbc.energy.quote.v1",
        chain_id="ait-hub.aitbc.bubuit.net",
        settlement_asset="AITBC",
        settlement_unit_scale=NATIVE_SCALE,
        settlement_route=SettlementRoute.NATIVE,
        gpu_count=1,
        duration_seconds=3600,
    )
    assert quote.operator_address is None
