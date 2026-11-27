"""#3068 AUDIT-PAY-EVM-UNITSCALE-1: EVM payments mis-converted units ~2.8e10x.

``units_to_ait`` hard-codes the native 36M-units/AIT scale, but quote
``*_units`` fields are denominated in ``quote.settlement_unit_scale`` —
1e18 for the EVM ERC-20 route. Every coordinator conversion of a quote
breakdown/principal to a token amount inflated EVM figures by ~27.8
billion, and a verified EVM payment landed in ``confirmed``, a state the
dispatch gate refuses forever with no settlement path (#3070).

Pins cover: the scale-aware ``units_to_token`` helper, the
``_evaluate_energy_quote`` conversion honoring ``settlement_unit_scale``,
and the deliberate EVM intake gate — new EVM-route funding is refused
while the lane has no completion/dispute path (env opt-in preserves the
dormant lane for operators who know).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from sqlmodel import Session

import pytest
from fastapi import HTTPException

from aitbc.market.energy_pricing import EnergyQuote, FeeModel, SettlementRoute
from aitbc.utils.units import UNITS_PER_AIT, units_to_ait, units_to_token
from coordinator_api.contexts.infrastructure.domain.job import Job
from coordinator_api.contexts.payments.services.payments import PaymentService
from coordinator_api.schemas import JobPaymentCreate

_SVC = "coordinator_api.contexts.payments.services.payments"
_FUNDING = "coordinator_api.contexts.payments.services.payments_funding"

EVM_SCALE = 10**18


def _quote(
    job_id: str = "job-1",
    *,
    route: SettlementRoute = SettlementRoute.EVM,
    scale: int = EVM_SCALE,
) -> EnergyQuote:
    now = 1_700_000_000
    return EnergyQuote(
        domain="aitbc-energy",
        chain_id="ait-test",
        settlement_asset="AIT",
        settlement_unit_scale=scale,
        buyer="0xBuyer0000000000000000000000000000000001",
        provider="0xProvider000000000000000000000000000001",
        job_id=job_id,
        quote_id="quote-1",
        settlement_route=route,
        resource_id="gpu-1",
        model_id="model-a",
        gpu_count=1,
        duration_seconds=3600,
        eur_per_kwh_scaled=10**18,
        tbp_watts=300,
        ait_per_eur_scaled=10**18,
        rate_version=1,
        rate_observed_at=now,
        rate_source_kind="test",
        profile_revision=1,
        evm_chain_id=11155111 if route == SettlementRoute.EVM else None,
        evm_contract="0xAIPowerRental00000000000000000000000001" if route == SettlementRoute.EVM else None,
        fee_model=FeeModel.BUYER_PAYS_ON_TOP,
        issued_at=now,
        expires_at=now + 300,
        principal_units=5 * scale,
        net_energy_floor_units=scale,
    )


def _job(session, job_id: str = "job-1") -> Job:
    job = Job(
        id=job_id,
        client_id="client-1",
        state="QUEUED",
        payload={"type": "inference", "model": "linear-1"},
        constraints={},
        payment_id=None,
        payment_status=None,
        requested_at=datetime.now(UTC) - timedelta(seconds=600),
        expires_at=datetime.now(UTC) + timedelta(seconds=600),
    )
    session.add(job)
    session.commit()
    return job


def _payment_data(quote: EnergyQuote) -> JobPaymentCreate:
    return JobPaymentCreate(
        job_id=quote.job_id,
        amount=Decimal("1"),
        currency="AITBC",
        payment_method="evm" if quote.settlement_route == SettlementRoute.EVM else "aitbc_token",
        protected=True,
        energy_quote=quote.to_dict(include_signature=True),
        evm_tx_hash="0xfeedface" if quote.settlement_route == SettlementRoute.EVM else None,
    )


# ---------------------------------------------------------------------------
# units_to_token
# ---------------------------------------------------------------------------


def test_units_to_token_respects_evm_scale() -> None:
    """5 whole tokens at 1e18 units/token is 5 — not 5e18/36e6 ≈ 1.39e11."""
    assert units_to_token(5 * EVM_SCALE, EVM_SCALE) == Decimal("5")


def test_units_to_token_native_scale_matches_units_to_ait() -> None:
    """The native route is unchanged: 36M units/token == units_to_ait."""
    units = 7 * UNITS_PER_AIT + 123
    assert units_to_token(units, UNITS_PER_AIT) == units_to_ait(units)


# ---------------------------------------------------------------------------
# _evaluate_energy_quote conversion
# ---------------------------------------------------------------------------


def _breakdown(buyer_charge_units: int):
    return SimpleNamespace(
        net_units=buyer_charge_units,
        principal_units=buyer_charge_units,
        provider_credit_units=buyer_charge_units,
        platform_fee_units=0,
        buyer_charge_units=buyer_charge_units,
    )


def _eval_result(buyer_charge_units: int):
    return SimpleNamespace(
        approved=True,
        breakdown=_breakdown(buyer_charge_units),
        refusal_code=None,
        refusal_reason=None,
    )


def test_evaluate_energy_quote_converts_by_quote_scale(db_engine) -> None:
    """An EVM-scale charge of 2.5 tokens must surface as 2.5 AIT, not the
    ~6.9e10 the native-scale conversion produced."""
    with Session(db_engine) as session:
        job = _job(session)
        service = PaymentService(session)
        quote = _quote(job.id, route=SettlementRoute.EVM, scale=EVM_SCALE)
        meta: dict = {}
        with (
            patch(f"{_FUNDING}.evaluate_quote", return_value=_eval_result(5 * EVM_SCALE // 2)),
            patch(f"{_FUNDING}._resolve_authoritative_inputs", return_value=(None, None)),
            patch(
                f"{_SVC}.settings",
                **{"energy_operator_address": "0xOp"},
            ),
            patch.object(EnergyQuote, "verify_operator_signature", return_value=True),
        ):
            amount = service._evaluate_energy_quote(quote, meta)
        assert amount == Decimal("2.5")


def test_evaluate_energy_quote_native_scale_unchanged(db_engine) -> None:
    """Native route: buyer_charge_units / 36M — identical to units_to_ait."""
    with Session(db_engine) as session:
        job = _job(session, job_id="job-native")
        service = PaymentService(session)
        quote = _quote(job.id, route=SettlementRoute.NATIVE, scale=UNITS_PER_AIT)
        meta: dict = {}
        charge_units = 3 * UNITS_PER_AIT + 36_000_000 // 2
        with (
            patch(f"{_FUNDING}.evaluate_quote", return_value=_eval_result(charge_units)),
            patch(f"{_FUNDING}._resolve_authoritative_inputs", return_value=(None, None)),
            patch(f"{_SVC}.settings", **{"energy_operator_address": "0xOp"}),
            patch.object(EnergyQuote, "verify_operator_signature", return_value=True),
        ):
            amount = service._evaluate_energy_quote(quote, meta)
        assert amount == units_to_ait(charge_units)


# ---------------------------------------------------------------------------
# EVM intake gate
# ---------------------------------------------------------------------------


def test_evm_route_payment_refused_while_lane_dormant(db_engine) -> None:
    """New EVM-route funding is refused: the payment would verify to
    'confirmed' — non-dispatchable, no settlement path — stranding buyer
    capital in AIPowerRental."""
    with Session(db_engine) as session:
        job = _job(session)
        service = PaymentService(session)
        quote = _quote(job.id, route=SettlementRoute.EVM, scale=EVM_SCALE)
        with pytest.raises(HTTPException) as exc:
            service._resolve_payment_quote(job, job.id, _payment_data(quote), {})
        assert exc.value.status_code == 422
        assert "EVM rental settlement is not enabled" in exc.value.detail


def test_evm_route_payment_allowed_with_opt_in(db_engine) -> None:
    """The env opt-in lifts the gate for operators running the lane knowingly."""
    with Session(db_engine) as session:
        job = _job(session, job_id="job-evm2")
        service = PaymentService(session)
        quote = _quote(job.id, route=SettlementRoute.EVM, scale=EVM_SCALE)
        with (
            patch(f"{_FUNDING}._EVM_RENTAL_ENABLED", True),
            patch.object(service, "_evaluate_energy_quote", return_value=Decimal("2.5")) as ev,
        ):
            amount, returned_quote = service._resolve_payment_quote(job, job.id, _payment_data(quote), {})
        assert amount == Decimal("2.5")
        assert returned_quote == quote
        ev.assert_called_once()


def test_native_route_payment_not_gated(db_engine) -> None:
    """The gate is EVM-route only — native protected rentals still resolve."""
    with Session(db_engine) as session:
        job = _job(session, job_id="job-native2")
        service = PaymentService(session)
        quote = _quote(job.id, route=SettlementRoute.NATIVE, scale=UNITS_PER_AIT)
        with patch.object(service, "_evaluate_energy_quote", return_value=Decimal("1.5")):
            amount, returned_quote = service._resolve_payment_quote(job, job.id, _payment_data(quote), {})
        assert amount == Decimal("1.5")
        assert returned_quote == quote


# ---------------------------------------------------------------------------
# market_gpu_purchase conversion site
# ---------------------------------------------------------------------------


def test_purchase_terms_convert_principal_by_quote_scale() -> None:
    """``_resolve_purchase_terms`` prices a quote-backed purchase from
    ``principal_units`` — at the quote's settlement_unit_scale, not the
    native 36M scale."""
    from coordinator_api.contexts.market.domain.gpu_market import GPURegistry
    from coordinator_api.contexts.market.routers.market_gpu import GPUBuyRequest
    from coordinator_api.contexts.market.routers.market_gpu_purchase import _resolve_purchase_terms

    quote = _quote("job-p", route=SettlementRoute.EVM, scale=EVM_SCALE)  # principal_units = 5 * 1e18
    request = GPUBuyRequest(
        buyer_id="buyer-1",
        gpu_id="gpu-1",
        duration_hours=1.0,
        energy_quote=quote.to_dict(include_signature=True),
    )
    gpu = GPURegistry(miner_id="m1", model="rtx", price_per_hour=Decimal("1.0"))

    async def _fake_price(**kwargs):
        return SimpleNamespace(recommended_price=Decimal("9.99"))

    engine = SimpleNamespace(calculate_dynamic_price=_fake_price)

    _, _, _, _, total_cost, _ = asyncio.run(_resolve_purchase_terms(request, gpu, engine))
    # 5 * 1e18 atomic units at the quote's 1e18 scale is 5 tokens — not the
    # ~1.39e11 the native-scale conversion produced.
    assert total_cost == Decimal("5")
