"""The chain node's escrow funding gate must reject self-attested energy quotes.

``POST /escrow/create`` on the blockchain node evaluates a protected energy
quote with ``evaluate_quote(quote, profile=quote.to_profile(),
rate=quote.to_rate())``. Those two arguments are derived from the quote itself,
so every profile/rate cross-check inside ``evaluate_quote`` is tautologically
satisfied and the energy floor is whatever ``tdp_watts`` and
``eur_per_kwh_scaled`` the caller embedded. Unlike the coordinator's funding
path, this route had no operator-signature check at all.

These tests cover the guard that closes that gap: the exact predicate
``escrow_routes.create_escrow`` applies before calling ``evaluate_quote``,

    operator = _energy_operator_address()
    if operator and not quote.verify_operator_signature(operator): reject

The guard is deliberately a no-op while ``ENERGY_OPERATOR_ADDRESS`` is unset,
which is the deployed state on every host today. Setting that one variable
arms this gate and the coordinator's ``settings.energy_operator_address``
check together.

Replacing ``to_profile()``/``to_rate()`` with an authoritative oracle read is a
separate change; a valid signature makes the embedded terms *attributable*, it
does not make them *correct*.
"""

from __future__ import annotations

import time

import pytest

from aitbc.crypto.crypto import derive_ethereum_address, sign_transaction_hash
from aitbc.marketplace.energy_pricing import (
    EnergyProfile,
    EnergyQuote,
    EnergyRate,
    SettlementRoute,
    build_minimum_quote,
)
from aitbc_chain.rpc.escrow_routes import _energy_operator_address

TARIFF_SCALED = 300_000_000_000_000_000  # 0.30 EUR/kWh * 10**18
RATE_SCALED = 4_000_000_000_000_000_000  # 4.00 AIT/EUR * 10**18
NATIVE_SCALE = 36_000_000

OPERATOR_KEY = "0x" + "11" * 32
ATTACKER_KEY = "0x" + "22" * 32


def _sign(quote: EnergyQuote, private_key: str) -> EnergyQuote:
    """Attach a real secp256k1 operator signature over the quote digest."""
    signature = sign_transaction_hash(quote.digest_sha256().hex(), private_key)
    return quote.with_operator_signature(
        operator_address=derive_ethereum_address(private_key),
        operator_signature=signature,
    )


@pytest.fixture
def unsigned_quote() -> EnergyQuote:
    now = int(time.time())
    profile = EnergyProfile(
        resource_id="gpu-rtx4060ti-node2-001",
        provider="0x" + "a" * 40,
        model_id="rtx-4060-ti",
        tdp_watts=165,
        eur_per_kwh_scaled=TARIFF_SCALED,
        enabled=True,
        revision=3,
    )
    rate = EnergyRate(
        ait_per_eur_scaled=RATE_SCALED,
        version=7,
        observed_at=now,
        submitted_at=now,
        source_kind="operator_reference",
        enabled=True,
    )
    return build_minimum_quote(
        profile=profile,
        rate=rate,
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
        operator_address=derive_ethereum_address(OPERATOR_KEY),
    )


def _gate_rejects(quote: EnergyQuote) -> bool:
    """Apply the guard's predicate exactly as ``create_escrow`` applies it."""
    operator = _energy_operator_address()
    return bool(operator) and not quote.verify_operator_signature(operator)


def test_address_unset_by_default(monkeypatch) -> None:
    """With no configured operator the accessor is empty, so the gate is off."""
    monkeypatch.delenv("ENERGY_OPERATOR_ADDRESS", raising=False)
    assert _energy_operator_address() == ""


def test_address_is_read_per_call(monkeypatch) -> None:
    """The accessor reads the environment per call, not once at import."""
    monkeypatch.setenv("ENERGY_OPERATOR_ADDRESS", "  0xAbCdEf  ")
    assert _energy_operator_address() == "0xAbCdEf"


def test_unsigned_quote_passes_when_gate_disabled(monkeypatch, unsigned_quote) -> None:
    """Unset address keeps today's behaviour: unsigned quotes still fund.

    This is what makes the change safe to deploy to hosts that do not yet set
    ``ENERGY_OPERATOR_ADDRESS`` -- it must not break existing escrow flows.
    """
    monkeypatch.delenv("ENERGY_OPERATOR_ADDRESS", raising=False)
    assert unsigned_quote.operator_signature is None
    assert not _gate_rejects(unsigned_quote)


def test_unsigned_quote_rejected_when_gate_enabled(monkeypatch, unsigned_quote) -> None:
    """A quote the caller minted with no operator signature is refused."""
    monkeypatch.setenv("ENERGY_OPERATOR_ADDRESS", derive_ethereum_address(OPERATOR_KEY))
    assert _gate_rejects(unsigned_quote)


def test_quote_signed_by_wrong_key_rejected(monkeypatch, unsigned_quote) -> None:
    """A signature from any key other than the configured operator is refused."""
    monkeypatch.setenv("ENERGY_OPERATOR_ADDRESS", derive_ethereum_address(OPERATOR_KEY))
    forged = _sign(unsigned_quote, ATTACKER_KEY)
    assert forged.operator_signature is not None
    assert _gate_rejects(forged)


def test_operator_signed_quote_accepted(monkeypatch, unsigned_quote) -> None:
    """A quote signed by the configured operator passes the gate."""
    monkeypatch.setenv("ENERGY_OPERATOR_ADDRESS", derive_ethereum_address(OPERATOR_KEY))
    signed = _sign(unsigned_quote, OPERATOR_KEY)
    assert not _gate_rejects(signed)


def test_tampering_after_signing_is_rejected(monkeypatch, unsigned_quote) -> None:
    """Lowering the energy floor after signing invalidates the signature.

    This is the attack the gate exists to stop: the signature covers the
    digest, and the digest covers ``tdp_watts`` and ``eur_per_kwh_scaled``.
    """
    monkeypatch.setenv("ENERGY_OPERATOR_ADDRESS", derive_ethereum_address(OPERATOR_KEY))
    signed = _sign(unsigned_quote, OPERATOR_KEY)
    assert not _gate_rejects(signed)

    from dataclasses import replace

    tampered = replace(signed, tdp_watts=1, net_energy_floor_units=1, principal_units=1)
    assert tampered.digest_sha256() != signed.digest_sha256()
    assert _gate_rejects(tampered)


def test_route_actually_applies_the_gate() -> None:
    """``create_escrow`` must call the guard, not just have it available.

    The tests above mirror the guard's predicate rather than driving the route,
    which needs a database, an RPC API key and a reachable hub. That mirror
    would keep passing if someone deleted the check from ``create_escrow``, so
    this asserts the call site itself is still there.
    """
    import inspect

    from aitbc_chain.rpc.escrow_routes import create_escrow

    source = inspect.getsource(create_escrow)
    assert "_energy_operator_address()" in source
    assert "verify_operator_signature" in source
    # The guard must run before the funding evaluation, not after it.
    assert source.index("verify_operator_signature") < source.index("evaluate_quote(")
