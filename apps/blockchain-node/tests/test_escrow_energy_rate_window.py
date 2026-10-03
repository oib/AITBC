"""The node RPC must apply the operator's rate window when funding a protected escrow.

``POST /escrow/create`` evaluates an embedded energy quote with
``evaluate_quote``. Until this change the call passed no
``max_rate_age_seconds``, so the library default of 300 s applied while the
coordinator's issuance and funding gates accepted the operator-configured
window (hub: 86400 s). A coordinator-funded protected buy therefore failed
at the node — the final gate — unless it landed within 300 s of a rate
POST, and the refusal surfaced as a silent pending payment
(``_create_token_escrow`` swallows the 422 into a warning).

The route now reads ``ENERGY_MAX_RATE_AGE_SECONDS`` per call — the same
variable the coordinator honours — and falls back to 86400 s on unset,
non-integer, or non-positive values. These tests drive the real
``create_escrow`` coroutine with its collaborators (escrow manager,
session scope, lock submission) mocked, so the only variable under test is
the rate window.
"""

from __future__ import annotations

import inspect
import time
from datetime import UTC
from datetime import datetime as _real_datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

import aitbc_chain.rpc.escrow_routes as escrow_routes
from aitbc.market.energy_pricing import (
    EnergyProfile,
    EnergyQuote,
    EnergyRate,
    SettlementRoute,
    build_minimum_quote,
)
from aitbc.utils import units_to_ait

TARIFF_SCALED = 300_000_000_000_000_000  # 0.30 EUR/kWh * 10**18
RATE_SCALED = 4_000_000_000_000_000_000  # 4.00 AIT/EUR * 10**18
NATIVE_SCALE = 36_000_000

NODE_WALLET = "0x" + "c" * 40
BUYER = "0x" + "b" * 40
PROVIDER = "0x" + "a" * 40
JOB_ID = "job-ratewin-001"


def _quote(rate_observed_at: int) -> EnergyQuote:
    """A quote whose embedded rate was observed at the given epoch."""
    profile = EnergyProfile(
        resource_id="gpu-rtx4060ti-node2-001",
        provider=PROVIDER,
        model_id="rtx-4060-ti",
        tbp_watts=165,
        eur_per_kwh_scaled=TARIFF_SCALED,
        enabled=True,
        revision=3,
    )
    rate = EnergyRate(
        ait_per_eur_scaled=RATE_SCALED,
        version=5,
        observed_at=rate_observed_at,
        submitted_at=rate_observed_at,
        source_kind="operator_reference",
        enabled=True,
    )
    return build_minimum_quote(
        profile=profile,
        rate=rate,
        buyer=BUYER,
        job_id=JOB_ID,
        quote_id="quote-ratewin-001",
        domain="aitbc.energy.quote.v1",
        chain_id="ait-testchain.local",
        settlement_asset="AITBC",
        settlement_unit_scale=NATIVE_SCALE,
        settlement_route=SettlementRoute.NATIVE,
        gpu_count=1,
        duration_seconds=3600,
    )


def _body(quote: EnergyQuote) -> dict:
    """A valid /escrow/create request carrying the quote and its lock tx."""
    amount_dec = units_to_ait(quote.principal_units)
    lock_tx, _ = escrow_routes._build_lock_tx(
        JOB_ID,
        BUYER,
        PROVIDER,
        amount_dec,
        nonce=0,
        energy_quote_id=quote.quote_id,
        energy_quote_digest=quote.digest_sha256().hex(),
        settlement_route=quote.settlement_route.value,
        settlement_asset=quote.settlement_asset,
        settlement_unit_scale=quote.settlement_unit_scale,
    )
    lock_tx["signature"] = "0x" + "ab" * 65
    return {
        "job_id": JOB_ID,
        "buyer": BUYER,
        "provider": PROVIDER,
        "amount": str(amount_dec),
        "energy_quote": quote.to_dict(include_signature=True),
        "lock_tx": lock_tx,
    }


def _session_scope() -> MagicMock:
    """A session_scope() stand-in whose session.get() finds nothing."""
    cm = MagicMock()
    session = cm.__enter__.return_value
    session.get.return_value = None
    return cm


@pytest.fixture
def route(monkeypatch):
    """Patch every collaborator create_escrow touches except the energy gate."""
    monkeypatch.delenv("ENERGY_OPERATOR_ADDRESS", raising=False)
    monkeypatch.setattr(escrow_routes, "_NODE_WALLET", NODE_WALLET)
    mgr = MagicMock()
    mgr.escrow_contracts = {}
    mgr.active_contracts = set()
    mgr.disputed_contracts = set()
    mgr._validate_contract_inputs.return_value = True
    mgr.create_contract = AsyncMock(return_value=(True, "ok", "contract-1"))
    mgr.fund_contract = AsyncMock()
    monkeypatch.setattr(escrow_routes, "get_escrow_manager", lambda: mgr)
    monkeypatch.setattr(escrow_routes, "_find_existing_lock", AsyncMock(return_value=None))
    monkeypatch.setattr(escrow_routes, "_submit_lock_tx", AsyncMock(return_value="0x" + "cd" * 32))
    monkeypatch.setattr(escrow_routes, "session_scope", _session_scope)
    return escrow_routes


def _freeze_now(route, monkeypatch, now_ts: int) -> None:
    """Pin the module's datetime.now() so rate ages are exact."""

    class FrozenDatetime:
        @staticmethod
        def now(tz=None):
            return _real_datetime.fromtimestamp(now_ts, tz or UTC)

    monkeypatch.setattr(route, "datetime", FrozenDatetime)


@pytest.mark.asyncio
async def test_rate_within_fallback_window_funds(route, monkeypatch) -> None:
    """A 3 h old rate funds under the 86400 s fallback.

    The coordinator accepted exactly this quote at issuance and funding; the
    unpatched node refused it at the 300 s library default.
    """
    monkeypatch.delenv("ENERGY_MAX_RATE_AGE_SECONDS", raising=False)
    quote = _quote(int(time.time()) - 3 * 3600)
    result = await route.create_escrow(_body(quote))
    assert result["success"] is True


@pytest.mark.asyncio
async def test_rate_exactly_at_window_funds(route, monkeypatch) -> None:
    """Boundary: age == window still funds (the library refuses only past it)."""
    monkeypatch.delenv("ENERGY_MAX_RATE_AGE_SECONDS", raising=False)
    now = int(time.time())
    _freeze_now(route, monkeypatch, now)
    quote = _quote(now - 86400)
    result = await route.create_escrow(_body(quote))
    assert result["success"] is True


@pytest.mark.asyncio
async def test_rate_one_second_past_window_refused(route, monkeypatch) -> None:
    """Boundary: age == window + 1 is refused with STALE_RATE at 422."""
    monkeypatch.delenv("ENERGY_MAX_RATE_AGE_SECONDS", raising=False)
    now = int(time.time())
    _freeze_now(route, monkeypatch, now)
    quote = _quote(now - 86401)
    with pytest.raises(HTTPException) as excinfo:
        await route.create_escrow(_body(quote))
    assert excinfo.value.status_code == 422
    assert "stale_rate" in excinfo.value.detail


@pytest.mark.asyncio
async def test_env_override_honoured(route, monkeypatch) -> None:
    """ENERGY_MAX_RATE_AGE_SECONDS=60 refuses a rate observed 61 s ago."""
    monkeypatch.setenv("ENERGY_MAX_RATE_AGE_SECONDS", "60")
    quote = _quote(int(time.time()) - 61)
    with pytest.raises(HTTPException) as excinfo:
        await route.create_escrow(_body(quote))
    assert excinfo.value.status_code == 422
    assert "stale_rate" in excinfo.value.detail


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["abc", "0", "-5"])
async def test_invalid_env_falls_back_to_86400(route, monkeypatch, bad) -> None:
    """Non-integer and non-positive overrides fall back to 86400 s."""
    monkeypatch.setenv("ENERGY_MAX_RATE_AGE_SECONDS", bad)
    quote = _quote(int(time.time()) - 3 * 3600)
    result = await route.create_escrow(_body(quote))
    assert result["success"] is True


def test_window_accessor_defaults(monkeypatch) -> None:
    monkeypatch.delenv("ENERGY_MAX_RATE_AGE_SECONDS", raising=False)
    assert escrow_routes._energy_max_rate_age_seconds() == 86400


def test_window_accessor_reads_env_per_call(monkeypatch) -> None:
    monkeypatch.setenv("ENERGY_MAX_RATE_AGE_SECONDS", "3600")
    assert escrow_routes._energy_max_rate_age_seconds() == 3600
    monkeypatch.setenv("ENERGY_MAX_RATE_AGE_SECONDS", "120")
    assert escrow_routes._energy_max_rate_age_seconds() == 120


@pytest.mark.parametrize("bad", ["", "abc", "0", "-1"])
def test_window_accessor_invalid_values_fall_back(monkeypatch, bad) -> None:
    monkeypatch.setenv("ENERGY_MAX_RATE_AGE_SECONDS", bad)
    assert escrow_routes._energy_max_rate_age_seconds() == 86400


def test_route_passes_the_window_to_evaluate_quote() -> None:
    """The call site must keep forwarding the configured window.

    The accessor tests above would still pass if someone dropped the
    ``max_rate_age_seconds=`` argument and returned to the 300 s library
    default, so assert the wiring itself is present.
    """
    source = inspect.getsource(escrow_routes.create_escrow)
    assert "max_rate_age_seconds=_energy_max_rate_age_seconds()" in source
