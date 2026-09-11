"""Unit tests for aitbc.marketplace.energy_pricing.

Tests the pure arithmetic and quote evaluation described in the energy-floor
plan. No network, no contracts, no float money.
"""

from __future__ import annotations

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
    compute_evm_buyer_charge,
    compute_energy_net_units,
    compute_funding_breakdown,
    compute_native_gross_units,
    compute_provider_credit_native,
    evaluate_quote,
    to_scaled,
)

# Reference vector from the plan:
# 165 W, EUR 0.30/kWh, 1 GPU, 3600 s, EUR 0.25/AIT (AIT/EUR = 4)
TARIFF_EUR_PER_KWH = Decimal("0.30")
AIT_PER_EUR = Decimal("4.00")
TARIFF_SCALED = 300_000_000_000_000_000  # 0.30 * 10**18
RATE_SCALED = 4_000_000_000_000_000_000  # 4.00 * 10**18


def _reference_kwargs() -> dict:
    return {
        "tdp_watts": 165,
        "eur_per_kwh_scaled": TARIFF_SCALED,
        "ait_per_eur_scaled": RATE_SCALED,
        "gpu_count": 1,
        "duration_seconds": 3600,
    }


@pytest.fixture
def base_profile() -> EnergyProfile:
    return EnergyProfile(
        resource_id="gpu-rtx4060ti-node2-001",
        provider="0xProviderAddress",
        model_id="rtx-4060-ti",
        tdp_watts=165,
        eur_per_kwh_scaled=TARIFF_SCALED,
        enabled=True,
        revision=3,
    )


@pytest.fixture
def base_rate() -> EnergyRate:
    return EnergyRate(
        ait_per_eur_scaled=RATE_SCALED,
        version=7,
        observed_at=1_700_000_000,
        submitted_at=1_700_000_010,
        source_kind="operator_reference",
        enabled=True,
    )


def test_reference_vector_native_energy_net() -> None:
    net = compute_energy_net_units(
        **_reference_kwargs(),
        settlement_unit_scale=36_000_000,
    )
    assert net == 7_128_000


def test_reference_vector_native_gross_and_provider_credit() -> None:
    net = 7_128_000
    gross = compute_native_gross_units(net, 250)
    assert gross == 7_310_770
    provider = compute_provider_credit_native(gross, 250)
    assert provider >= net
    # The conservative gross should leave the provider with at least the floor.
    assert provider == 7_128_001


def test_reference_vector_evm_buyer_charge() -> None:
    net = compute_energy_net_units(
        **_reference_kwargs(),
        settlement_unit_scale=10**18,
    )
    assert net == 198_000_000_000_000_000
    buyer_charge = compute_evm_buyer_charge(net, 250)
    assert buyer_charge == net + (net * 250 // 10_000)
    assert buyer_charge == 202_950_000_000_000_000


def test_compute_energy_net_units_multiple_gpus() -> None:
    net_one = compute_energy_net_units(
        **_reference_kwargs(),
        settlement_unit_scale=36_000_000,
    )
    net_two = compute_energy_net_units(
        **dict(_reference_kwargs(), gpu_count=2),
        settlement_unit_scale=36_000_000,
    )
    assert net_two == 2 * net_one


def test_compute_energy_net_units_fractional_duration() -> None:
    net_one_hour = compute_energy_net_units(
        **_reference_kwargs(),
        settlement_unit_scale=36_000_000,
    )
    net_half_hour = compute_energy_net_units(
        **dict(_reference_kwargs(), duration_seconds=1800),
        settlement_unit_scale=36_000_000,
    )
    assert net_half_hour == net_one_hour // 2


def test_compute_energy_net_units_zero_or_negative_rejected() -> None:
    with pytest.raises(EnergyPricingError):
        compute_energy_net_units(
            **dict(_reference_kwargs(), gpu_count=0),
            settlement_unit_scale=36_000_000,
        )
    with pytest.raises(EnergyPricingError):
        compute_energy_net_units(
            **dict(_reference_kwargs(), duration_seconds=-1),
            settlement_unit_scale=36_000_000,
        )


def test_to_scaled_decimal_and_string() -> None:
    assert to_scaled(Decimal("0.30")) == TARIFF_SCALED
    assert to_scaled("0.30") == TARIFF_SCALED
    assert to_scaled(Decimal("4.00")) == RATE_SCALED


def test_to_scaled_rejects_float_and_invalid() -> None:
    with pytest.raises(EnergyPricingError):
        to_scaled(0.30)
    with pytest.raises(EnergyPricingError):
        to_scaled(Decimal("NaN"))
    with pytest.raises(EnergyPricingError):
        to_scaled(Decimal("-0.1"))
    with pytest.raises(EnergyPricingError):
        to_scaled("not-a-number")


def test_to_scaled_rejects_over_precision_by_default() -> None:
    with pytest.raises(EnergyPricingError):
        to_scaled(Decimal("0.3333333333333333334"))  # 19 decimal places


def test_to_scaled_allows_quantization() -> None:
    # Rounds 0.333...3334 with 19 places to 18 places half-up.
    scaled = to_scaled(Decimal("0.3333333333333333334"), allow_quantize=True)
    assert scaled == 333_333_333_333_333_333


def test_native_gross_rounding_properties() -> None:
    # Small net and 1% fee: the gross must leave provider with at least net.
    net = 1
    gross = compute_native_gross_units(net, 100)
    provider = compute_provider_credit_native(gross, 100)
    assert provider >= net
    # 100 units at 2.5% fee.
    net = 100
    gross = compute_native_gross_units(net, 250)
    provider = compute_provider_credit_native(gross, 250)
    assert provider >= net
    assert gross == 103


def test_funding_breakdown_native_matches_escrow_semantics() -> None:
    net = 7_128_000
    gross = compute_native_gross_units(net, 250)
    breakdown = compute_funding_breakdown(
        principal_units=gross,
        fee_basis_points=250,
        fee_model=FeeModel.PROVIDER_DEDUCTED,
        net_energy_floor_units=net,
    )
    assert breakdown.net_units == net
    assert breakdown.buyer_charge_units == gross
    assert breakdown.provider_credit_units >= net
    assert breakdown.evm_principal_units is None


def test_funding_breakdown_evm_matches_aipowerrental_semantics() -> None:
    principal = 198_000_000_000_000_000
    breakdown = compute_funding_breakdown(
        principal_units=principal,
        fee_basis_points=250,
        fee_model=FeeModel.BUYER_PAYS_ON_TOP,
        net_energy_floor_units=principal,
    )
    assert breakdown.net_units == principal
    assert breakdown.provider_credit_units == principal
    assert breakdown.evm_principal_units == principal
    assert breakdown.buyer_charge_units == 202_950_000_000_000_000
    assert breakdown.platform_fee_units == 4_950_000_000_000_000


def test_funding_breakdown_below_floor_raises() -> None:
    with pytest.raises(EnergyPricingError) as exc:
        compute_funding_breakdown(
            principal_units=100,
            fee_basis_points=250,
            fee_model=FeeModel.PROVIDER_DEDUCTED,
            net_energy_floor_units=200,
        )
    assert exc.value.code == RefusalCode.BELOW_FLOOR.value


def test_build_minimum_quote_native(base_profile: EnergyProfile, base_rate: EnergyRate) -> None:
    quote = build_minimum_quote(
        profile=base_profile,
        rate=base_rate,
        buyer="0xBuyerAddress",
        job_id="job-001",
        quote_id="quote-001",
        domain="aitbc-energy-quote-v1",
        chain_id="ait-hub.aitbc.bubuit.net",
        settlement_asset="AIT",
        settlement_unit_scale=36_000_000,
        settlement_route=SettlementRoute.NATIVE,
        gpu_count=1,
        duration_seconds=3600,
        now=1_700_000_100,
    )
    assert quote.net_energy_floor_units == 7_128_000
    assert quote.principal_units == 7_310_770
    assert quote.fee_model == FeeModel.PROVIDER_DEDUCTED


def test_build_minimum_quote_evm(base_profile: EnergyProfile, base_rate: EnergyRate) -> None:
    quote = build_minimum_quote(
        profile=base_profile,
        rate=base_rate,
        buyer="0xBuyerAddress",
        job_id="job-002",
        quote_id="quote-002",
        domain="aitbc-energy-quote-v1",
        chain_id="1",
        settlement_asset="AIT",
        settlement_unit_scale=10**18,
        settlement_route=SettlementRoute.EVM,
        gpu_count=1,
        duration_seconds=3600,
        now=1_700_000_100,
    )
    assert quote.net_energy_floor_units == 198_000_000_000_000_000
    assert quote.principal_units == quote.net_energy_floor_units
    assert quote.fee_model == FeeModel.BUYER_PAYS_ON_TOP


def test_evaluate_quote_approved(base_profile: EnergyProfile, base_rate: EnergyRate) -> None:
    quote = build_minimum_quote(
        profile=base_profile,
        rate=base_rate,
        buyer="0xBuyerAddress",
        job_id="job-003",
        quote_id="quote-003",
        domain="aitbc-energy-quote-v1",
        chain_id="ait-hub.aitbc.bubuit.net",
        settlement_asset="AIT",
        settlement_unit_scale=36_000_000,
        settlement_route=SettlementRoute.NATIVE,
        gpu_count=1,
        duration_seconds=3600,
        buyer_cap_units=10_000_000,
        now=1_700_000_100,
    )
    result = evaluate_quote(
        quote=quote,
        profile=base_profile,
        rate=base_rate,
        now=1_700_000_110,
    )
    assert result.approved is True
    assert result.breakdown is not None
    assert result.breakdown.buyer_charge_units == 7_310_770
    assert result.breakdown.provider_credit_units >= quote.net_energy_floor_units


def test_evaluate_quote_buyer_cap_conflict(base_profile: EnergyProfile, base_rate: EnergyRate) -> None:
    quote = build_minimum_quote(
        profile=base_profile,
        rate=base_rate,
        buyer="0xBuyerAddress",
        job_id="job-004",
        quote_id="quote-004",
        domain="aitbc-energy-quote-v1",
        chain_id="ait-hub.aitbc.bubuit.net",
        settlement_asset="AIT",
        settlement_unit_scale=36_000_000,
        settlement_route=SettlementRoute.NATIVE,
        gpu_count=1,
        duration_seconds=3600,
        buyer_cap_units=7_000_000,  # below gross
        now=1_700_000_100,
    )
    result = evaluate_quote(
        quote=quote,
        profile=base_profile,
        rate=base_rate,
        now=1_700_000_110,
    )
    assert result.approved is False
    assert result.refusal_code == RefusalCode.BUYER_CAP_CONFLICT


def test_evaluate_quote_hard_cap_conflict(base_profile: EnergyProfile, base_rate: EnergyRate) -> None:
    quote = build_minimum_quote(
        profile=base_profile,
        rate=base_rate,
        buyer="0xBuyerAddress",
        job_id="job-005",
        quote_id="quote-005",
        domain="aitbc-energy-quote-v1",
        chain_id="ait-hub.aitbc.bubuit.net",
        settlement_asset="AIT",
        settlement_unit_scale=36_000_000,
        settlement_route=SettlementRoute.NATIVE,
        gpu_count=1,
        duration_seconds=3600,
        now=1_700_000_100,
    )
    result = evaluate_quote(
        quote=quote,
        profile=base_profile,
        rate=base_rate,
        now=1_700_000_110,
        hard_cap_units=7_100_000,
    )
    assert result.approved is False
    assert result.refusal_code == RefusalCode.HARD_CAP_CONFLICT


def test_evaluate_quote_expired(base_profile: EnergyProfile, base_rate: EnergyRate) -> None:
    quote = build_minimum_quote(
        profile=base_profile,
        rate=base_rate,
        buyer="0xBuyerAddress",
        job_id="job-006",
        quote_id="quote-006",
        domain="aitbc-energy-quote-v1",
        chain_id="ait-hub.aitbc.bubuit.net",
        settlement_asset="AIT",
        settlement_unit_scale=36_000_000,
        settlement_route=SettlementRoute.NATIVE,
        gpu_count=1,
        duration_seconds=3600,
        quote_lifetime_seconds=60,
        now=1_700_000_100,
    )
    result = evaluate_quote(
        quote=quote,
        profile=base_profile,
        rate=base_rate,
        now=1_700_000_200,
    )
    assert result.approved is False
    assert result.refusal_code == RefusalCode.EXPIRED


def test_evaluate_quote_stale_rate(base_profile: EnergyProfile, base_rate: EnergyRate) -> None:
    quote = build_minimum_quote(
        profile=base_profile,
        rate=base_rate,
        buyer="0xBuyerAddress",
        job_id="job-007",
        quote_id="quote-007",
        domain="aitbc-energy-quote-v1",
        chain_id="ait-hub.aitbc.bubuit.net",
        settlement_asset="AIT",
        settlement_unit_scale=36_000_000,
        settlement_route=SettlementRoute.NATIVE,
        gpu_count=1,
        duration_seconds=3600,
        now=1_700_000_100,
    )
    # Rate was observed at 1.7B, but the system thinks the max age is 10 seconds.
    result = evaluate_quote(
        quote=quote,
        profile=base_profile,
        rate=base_rate,
        now=1_700_000_200,
        max_rate_age_seconds=10,
    )
    assert result.approved is False
    assert result.refusal_code == RefusalCode.STALE_RATE


def test_evaluate_quote_profile_revision_mismatch(base_profile: EnergyProfile, base_rate: EnergyRate) -> None:
    quote = build_minimum_quote(
        profile=base_profile,
        rate=base_rate,
        buyer="0xBuyerAddress",
        job_id="job-008",
        quote_id="quote-008",
        domain="aitbc-energy-quote-v1",
        chain_id="ait-hub.aitbc.bubuit.net",
        settlement_asset="AIT",
        settlement_unit_scale=36_000_000,
        settlement_route=SettlementRoute.NATIVE,
        gpu_count=1,
        duration_seconds=3600,
        now=1_700_000_100,
    )
    new_profile = EnergyProfile(
        resource_id=base_profile.resource_id,
        provider=base_profile.provider,
        model_id=base_profile.model_id,
        tdp_watts=base_profile.tdp_watts,
        eur_per_kwh_scaled=base_profile.eur_per_kwh_scaled,
        enabled=True,
        revision=base_profile.revision + 1,
    )
    result = evaluate_quote(
        quote=quote,
        profile=new_profile,
        rate=base_rate,
        now=1_700_000_110,
    )
    assert result.approved is False
    assert result.refusal_code == RefusalCode.PROFILE_MISMATCH


def test_evaluate_quote_below_floor(base_profile: EnergyProfile, base_rate: EnergyRate) -> None:
    quote = build_minimum_quote(
        profile=base_profile,
        rate=base_rate,
        buyer="0xBuyerAddress",
        job_id="job-009",
        quote_id="quote-009",
        domain="aitbc-energy-quote-v1",
        chain_id="ait-hub.aitbc.bubuit.net",
        settlement_asset="AIT",
        settlement_unit_scale=36_000_000,
        settlement_route=SettlementRoute.NATIVE,
        gpu_count=1,
        duration_seconds=3600,
        now=1_700_000_100,
    )
    # Manually lower principal to simulate tampering.
    tampered = replace(quote, principal_units=quote.net_energy_floor_units - 1)
    result = evaluate_quote(
        quote=tampered,
        profile=base_profile,
        rate=base_rate,
        now=1_700_000_110,
    )
    assert result.approved is False
    assert result.refusal_code == RefusalCode.BELOW_FLOOR


def test_canonical_json_deterministic_and_signature_independent(base_profile: EnergyProfile, base_rate: EnergyRate) -> None:
    quote = build_minimum_quote(
        profile=base_profile,
        rate=base_rate,
        buyer="0xBuyerAddress",
        job_id="job-010",
        quote_id="quote-010",
        domain="aitbc-energy-quote-v1",
        chain_id="ait-hub.aitbc.bubuit.net",
        settlement_asset="AIT",
        settlement_unit_scale=36_000_000,
        settlement_route=SettlementRoute.NATIVE,
        gpu_count=1,
        duration_seconds=3600,
        now=1_700_000_100,
    )
    quote_signed = EnergyQuote(
        **quote.to_canonical_dict(),
        operator_signature=b"fake-signature",
    )
    assert quote.canonical_json() == quote_signed.canonical_json()
    assert quote.digest_sha256() == quote_signed.digest_sha256()


def test_quote_digest_changes_with_field(base_profile: EnergyProfile, base_rate: EnergyRate) -> None:
    quote1 = build_minimum_quote(
        profile=base_profile,
        rate=base_rate,
        buyer="0xBuyerAddress",
        job_id="job-011",
        quote_id="quote-011",
        domain="aitbc-energy-quote-v1",
        chain_id="ait-hub.aitbc.bubuit.net",
        settlement_asset="AIT",
        settlement_unit_scale=36_000_000,
        settlement_route=SettlementRoute.NATIVE,
        gpu_count=1,
        duration_seconds=3600,
        now=1_700_000_100,
    )
    quote2 = replace(quote1, quote_id="quote-011-modified")
    assert quote1.digest_sha256() != quote2.digest_sha256()


def test_quote_to_dict_round_trip(base_profile: EnergyProfile, base_rate: EnergyRate) -> None:
    """Quote dict serialization must be reversible and preserve the floor."""
    quote = build_minimum_quote(
        profile=base_profile,
        rate=base_rate,
        buyer="0xBuyerAddress",
        job_id="job-012",
        quote_id="quote-012",
        domain="aitbc-energy-quote-v1",
        chain_id="ait-hub.aitbc.bubuit.net",
        settlement_asset="AIT",
        settlement_unit_scale=36_000_000,
        settlement_route=SettlementRoute.NATIVE,
        gpu_count=1,
        duration_seconds=3600,
        now=1_700_000_100,
    )
    signed = EnergyQuote(**quote.to_canonical_dict(), operator_signature=b"\x01" * 65)
    payload = signed.to_dict(include_signature=True)
    restored = EnergyQuote.from_dict(payload)
    assert restored == signed
    assert restored.net_energy_floor_units == quote.net_energy_floor_units
    assert restored.principal_units == quote.principal_units


def test_quote_to_profile_and_rate(base_profile: EnergyProfile, base_rate: EnergyRate) -> None:
    """Reconstructed profile/rate from the quote satisfy evaluate_quote."""
    quote = build_minimum_quote(
        profile=base_profile,
        rate=base_rate,
        buyer="0xBuyerAddress",
        job_id="job-013",
        quote_id="quote-013",
        domain="aitbc-energy-quote-v1",
        chain_id="ait-hub.aitbc.bubuit.net",
        settlement_asset="AIT",
        settlement_unit_scale=36_000_000,
        settlement_route=SettlementRoute.NATIVE,
        gpu_count=1,
        duration_seconds=3600,
        now=1_700_000_100,
    )
    result = evaluate_quote(
        quote=quote,
        profile=quote.to_profile(),
        rate=quote.to_rate(),
        now=1_700_000_110,
    )
    assert result.approved is True
    assert result.breakdown is not None
    assert result.breakdown.net_units == quote.net_energy_floor_units
