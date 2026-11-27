"""#3070 AUDIT-EVM-RENTAL-ACTIVATION-1 HIGH-1: quote ``evm_contract`` binding.

``_build_energy_quote`` embedded ``energy_pricing_contract_address`` (the
IEnergyPricing oracle) as the quote's ``evm_contract``, but receipt
validation binds ``receipt.to`` against ``energy_rental_contract_address``
(the AIPowerRental contract the buyer actually funds). A correctly
configured operator therefore produced quotes that deterministically
failed their own receipt validation.

Pins cover: the quote embeds the rental contract address, the oracle
pricing address is not leaked into ``evm_contract``, and the EVM route
fails closed when no rental contract is configured.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from aitbc.market.energy_pricing import (
    FIXED_POINT_SCALE,
    EnergyProfile,
    EnergyRate,
    SettlementRoute,
)

import importlib

import coordinator_api.contexts.market.routers.market_gpu  # noqa: F401
from coordinator_api.config import settings

market_gpu = importlib.import_module("coordinator_api.contexts.market.routers.market_gpu")

PRICING_CONTRACT = "0xPricingOracle00000000000000000000000001"
RENTAL_CONTRACT = "0xAIPowerRental00000000000000000000000002"
PROVIDER = "0x4A5b3bf95aa06072c568Cfcb7392b4e86608B5D2"


@pytest.fixture
def evm_settings(monkeypatch):
    monkeypatch.setattr(settings, "energy_pricing_contract_address", PRICING_CONTRACT)
    monkeypatch.setattr(settings, "energy_rental_contract_address", RENTAL_CONTRACT)
    monkeypatch.setattr(settings, "native_chain_id", "aitbc-mainnet")
    monkeypatch.setattr(settings, "energy_operator_key", None)
    monkeypatch.setattr(settings, "energy_operator_address", None)
    return settings


def _stub_oracle() -> SimpleNamespace:
    def get_profile(resource_id: str) -> EnergyProfile:
        return EnergyProfile(
            resource_id=resource_id,
            provider=PROVIDER,
            model_id="m",
            tbp_watts=165,
            eur_per_kwh_scaled=int(Decimal("0.30") * FIXED_POINT_SCALE),
            enabled=True,
            revision=1,
        )

    def get_rate() -> EnergyRate:
        return EnergyRate(
            ait_per_eur_scaled=int(Decimal("1.5") * FIXED_POINT_SCALE),
            version=1,
            observed_at=1_700_000_000,
            submitted_at=1_700_000_000,
            source_kind="native_operator",
            enabled=True,
        )

    return SimpleNamespace(get_profile=get_profile, get_rate=get_rate)


def _gpu() -> SimpleNamespace:
    return SimpleNamespace(resource_id="node2-rtx4060ti")


@pytest.mark.unit
def test_evm_quote_embeds_rental_contract_not_pricing_contract(evm_settings, monkeypatch):
    """HIGH-1: quote.evm_contract must be the AIPowerRental address — the
    address receipt validation compares ``receipt.to`` against."""
    monkeypatch.setattr(market_gpu, "_get_energy_oracle", lambda session: _stub_oracle())

    quote = market_gpu._build_energy_quote(
        session=None,
        gpu=_gpu(),
        buyer=PROVIDER,
        job_id="job-1",
        duration_hours=1.0,
        gpu_count=1,
        settlement_route=SettlementRoute.EVM,
        settlement_unit_scale=10**18,
    )

    assert quote["settlement_route"] == SettlementRoute.EVM.value
    assert quote["evm_contract"] == RENTAL_CONTRACT
    assert quote["evm_contract"] != PRICING_CONTRACT


@pytest.mark.unit
def test_native_quote_never_embeds_oracle_contract(evm_settings, monkeypatch):
    """Native-route quotes are inert for receipt binding, but must still
    never carry the oracle/pricing contract address."""
    monkeypatch.setattr(market_gpu, "_get_energy_oracle", lambda session: _stub_oracle())

    quote = market_gpu._build_energy_quote(
        session=None,
        gpu=_gpu(),
        buyer=PROVIDER,
        job_id="job-1",
        duration_hours=1.0,
        gpu_count=1,
        settlement_route=SettlementRoute.NATIVE,
    )

    assert quote["settlement_route"] == SettlementRoute.NATIVE.value
    assert quote["evm_contract"] != PRICING_CONTRACT


@pytest.mark.unit
def test_evm_quote_fails_closed_without_rental_contract(evm_settings, monkeypatch):
    """An EVM quote with no rental contract configured must refuse — a
    contract-less quote cannot be validated against a receipt ``to``."""
    monkeypatch.setattr(settings, "energy_rental_contract_address", None)
    monkeypatch.setattr(market_gpu, "_get_energy_oracle", lambda session: _stub_oracle())

    with pytest.raises(HTTPException) as excinfo:
        market_gpu._build_energy_quote(
            session=None,
            gpu=_gpu(),
            buyer=PROVIDER,
            job_id="job-1",
            duration_hours=1.0,
            gpu_count=1,
            settlement_route=SettlementRoute.EVM,
            settlement_unit_scale=10**18,
        )
    assert excinfo.value.status_code == 503
