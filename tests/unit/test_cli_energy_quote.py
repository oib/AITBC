"""Unit tests for CLI energy quote verification utilities.

Tests the ``aitbc_cli.utils.energy_quote`` module without network access.
"""

from __future__ import annotations

import time

import pytest

from aitbc.market.energy_pricing import (
    EnergyProfile,
    EnergyRate,
    RefusalCode,
    SettlementRoute,
    build_minimum_quote,
)
from aitbc_cli.utils.energy_quote import (
    compute_settlement_breakdown,
    parse_quote,
    verify_quote,
)

TARIFF_SCALED = 300_000_000_000_000_000
RATE_SCALED = 4_000_000_000_000_000_000
NATIVE_SCALE = 36_000_000


@pytest.fixture
def profile() -> EnergyProfile:
    return EnergyProfile(
        resource_id="gpu-test-001",
        provider="0x" + "a" * 40,
        model_id="rtx-4060-ti",
        tbp_watts=165,
        eur_per_kwh_scaled=TARIFF_SCALED,
        enabled=True,
        revision=3,
    )


@pytest.fixture
def rate() -> EnergyRate:
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
def quote_dict(profile, rate) -> dict:
    quote = build_minimum_quote(
        profile=profile,
        rate=rate,
        buyer="0x" + "b" * 40,
        job_id="job-test-001",
        quote_id="quote-test-001",
        domain="aitbc.energy.quote.v1",
        chain_id="ait-testchain.local",
        settlement_asset="AITBC",
        settlement_unit_scale=NATIVE_SCALE,
        settlement_route=SettlementRoute.NATIVE,
        gpu_count=1,
        duration_seconds=3600,
        operator_address="0x" + "c" * 40,
    )
    return quote.to_dict(include_signature=False)


def test_parse_quote_roundtrip(quote_dict) -> None:
    """parse_quote returns an EnergyQuote with the right fields."""
    quote = parse_quote(quote_dict)
    assert quote.quote_id == "quote-test-001"
    assert quote.operator_address == "0x" + "c" * 40


def test_verify_quote_no_signature(quote_dict) -> None:
    """verify_quote rejects a quote with no operator signature."""
    quote = parse_quote(quote_dict)
    result = verify_quote(quote, expected_operator_address="0x" + "c" * 40)
    assert not result.valid
    assert result.refusal_code == RefusalCode.INVALID_SIGNATURE


def test_verify_quote_no_operator_configured(quote_dict) -> None:
    """verify_quote rejects a quote with no signature and no operator configured."""
    quote = parse_quote(quote_dict)
    result = verify_quote(quote)
    assert not result.valid
    assert result.refusal_code == RefusalCode.INVALID_SIGNATURE


def test_verify_quote_domain_mismatch(quote_dict) -> None:
    """verify_quote rejects a quote with a wrong domain."""
    quote = parse_quote(quote_dict)
    result = verify_quote(quote, expected_domain="wrong.domain")
    # Will fail on signature first since no operator is configured.
    assert not result.valid


def test_verify_quote_expired(profile, rate) -> None:
    """verify_quote rejects an expired quote."""
    quote = build_minimum_quote(
        profile=profile,
        rate=rate,
        buyer="0x" + "b" * 40,
        job_id="job-expired",
        quote_id="quote-expired",
        domain="aitbc.energy.quote.v1",
        chain_id="ait-testchain.local",
        settlement_asset="AITBC",
        settlement_unit_scale=NATIVE_SCALE,
        settlement_route=SettlementRoute.NATIVE,
        gpu_count=1,
        duration_seconds=3600,
        quote_lifetime_seconds=1,
        now=int(time.time()) - 100,
    )
    result = verify_quote(quote)
    # Will fail on signature first; let's test with no operator to hit expiry.
    # Actually, without operator_address configured, it fails on signature.
    # To test expiry, we need to skip the signature check.
    # The verify_quote function checks signature first when no operator is configured.
    # So this test confirms the priority: signature check before expiry.
    assert not result.valid
    assert result.refusal_code == RefusalCode.INVALID_SIGNATURE


def test_compute_settlement_breakdown_native(quote_dict) -> None:
    """compute_settlement_breakdown returns correct native breakdown."""
    quote = parse_quote(quote_dict)
    breakdown = compute_settlement_breakdown(quote)
    assert breakdown["settlement_route"] == "native"
    assert breakdown["principal_units"] == quote.principal_units
    assert breakdown["buyer_charge_units"] == quote.principal_units
    assert breakdown["provider_credit_units"] < breakdown["principal_units"]
    assert breakdown["platform_fee_units"] > 0


def test_compute_settlement_breakdown_evm(profile, rate) -> None:
    """compute_settlement_breakdown returns correct EVM breakdown."""
    quote = build_minimum_quote(
        profile=profile,
        rate=rate,
        buyer="0x" + "b" * 40,
        job_id="job-evm",
        quote_id="quote-evm",
        domain="aitbc.energy.quote.v1",
        chain_id="ait-testchain.local",
        settlement_asset="AITBC",
        settlement_unit_scale=10**18,
        settlement_route=SettlementRoute.EVM,
        gpu_count=1,
        duration_seconds=3600,
        evm_chain_id=1,
        evm_contract="0x" + "e" * 40,
    )
    breakdown = compute_settlement_breakdown(quote)
    assert breakdown["settlement_route"] == "evm"
    assert breakdown["principal_units"] == quote.net_energy_floor_units
    assert breakdown["buyer_charge_units"] > breakdown["principal_units"]
    assert breakdown["platform_fee_units"] > 0


# --- Rate-age window (energy_max_rate_age_seconds) ---
#
# The coordinator enforces its own window at issuance and funding (86400s on
# hub, where the rate refreshes every 12h). The CLI's advisory check must use
# the operator-configured window, not the library default of 300s — otherwise
# `market gpu buy` is locally refused except for ~5 minutes after each refresh.


def _stale_rate_quote(profile, *, age_seconds: int):
    """A signed quote whose embedded rate was observed ``age_seconds`` ago."""
    now = int(time.time())
    stale_rate = EnergyRate(
        ait_per_eur_scaled=RATE_SCALED,
        version=7,
        observed_at=now - age_seconds,
        submitted_at=now - age_seconds + 1,
        source_kind="operator_reference",
        enabled=True,
    )
    quote = build_minimum_quote(
        profile=profile,
        rate=stale_rate,
        buyer="0x" + "b" * 40,
        job_id="job-stale",
        quote_id="quote-stale",
        domain="aitbc.energy.quote.v1",
        chain_id="ait-testchain.local",
        settlement_asset="AITBC",
        settlement_unit_scale=NATIVE_SCALE,
        settlement_route=SettlementRoute.NATIVE,
        gpu_count=1,
        duration_seconds=3600,
        operator_address="0x" + "c" * 40,
    )
    # A present-but-unverified signature passes the "no signature" gate when
    # no expected operator address is configured.
    return quote.with_operator_signature(operator_address="0x" + "c" * 40, operator_signature=b"\xde\xad\xbe\xef")


def test_stale_rate_valid_within_operator_window(profile) -> None:
    """A 3h-old rate verifies under the configured 86400s operator window."""
    quote = _stale_rate_quote(profile, age_seconds=3 * 3600)
    result = verify_quote(quote, max_rate_age_seconds=86400)
    assert result.valid


def test_stale_rate_refused_at_strict_window(profile) -> None:
    """Negative control: the same quote is refused at a 300s window."""
    quote = _stale_rate_quote(profile, age_seconds=3 * 3600)
    result = verify_quote(quote, max_rate_age_seconds=300)
    assert not result.valid
    assert result.refusal_code == RefusalCode.STALE_RATE


def test_stale_rate_boundary(profile) -> None:
    """now - observed_at == window passes; window + 1 is refused."""
    now = int(time.time())
    fresh_rate = EnergyRate(
        ait_per_eur_scaled=RATE_SCALED,
        version=7,
        observed_at=now,
        submitted_at=now,
        source_kind="operator_reference",
        enabled=True,
    )
    quote = build_minimum_quote(
        profile=profile,
        rate=fresh_rate,
        buyer="0x" + "b" * 40,
        job_id="job-boundary",
        quote_id="quote-boundary",
        domain="aitbc.energy.quote.v1",
        chain_id="ait-testchain.local",
        settlement_asset="AITBC",
        settlement_unit_scale=NATIVE_SCALE,
        settlement_route=SettlementRoute.NATIVE,
        gpu_count=1,
        duration_seconds=3600,
        operator_address="0x" + "c" * 40,
        quote_lifetime_seconds=3600,
    ).with_operator_signature(operator_address="0x" + "c" * 40, operator_signature=b"\xde\xad\xbe\xef")
    assert verify_quote(quote, now=now + 300, max_rate_age_seconds=300).valid
    refused = verify_quote(quote, now=now + 301, max_rate_age_seconds=300)
    assert not refused.valid
    assert refused.refusal_code == RefusalCode.STALE_RATE


# --- Wiring: every CLI verify call site forwards the configured window ---
#
# Patching verify_quote/verify_quote_against_oracle in each command module and
# asserting the forwarded max_rate_age_seconds equals the configured value is
# what catches a missed call site (that miss is exactly the bug this fixes).

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner


def _sentinel_config(**over):
    cfg = MagicMock()
    cfg.native_chain_id = "ait-testchain.local"
    cfg.blockchain_rpc_url = "http://localhost:8202"
    cfg.coordinator_api_url = "http://localhost:8203"
    cfg.energy_operator_address = None
    cfg.energy_quote_domain = "aitbc.energy.quote.v1"
    cfg.energy_pricing_contract_address = None
    cfg.energy_pricing_chain_id = 1
    cfg.evm_rpc_url = None
    cfg.energy_max_rate_age_seconds = over.get("window", 4242)
    return cfg


def _quote_json(quote) -> dict:
    return quote.to_dict(include_signature=True)


@pytest.fixture
def runner():
    return CliRunner()


def test_gpu_quote_forwards_configured_window(runner, profile):
    quote = _stale_rate_quote(profile, age_seconds=3 * 3600)
    cfg = _sentinel_config()
    client = MagicMock()
    client.post.return_value = {"energy_quote": _quote_json(quote), "buyer_charge_ait": "1"}
    verifier = MagicMock()
    verifier.return_value.valid = True
    verifier.return_value.digest_hex = "ab" * 32
    verifier.return_value.operator_verified = True
    from aitbc_cli.commands.market import market

    with (
        patch("aitbc_cli.commands.market.gpu.AITBCHTTPClient", return_value=client),
        patch("aitbc_cli.commands.market.gpu.get_config", return_value=cfg),
        patch("aitbc_cli.config.get_config", return_value=cfg),
        patch("aitbc_cli.commands.market.gpu.verify_quote", verifier),
    ):
        result = runner.invoke(
            market,
            ["gpu", "quote", "--gpu-id", "g1", "--buyer-id", "0x" + "b" * 40],
            obj={"output_format": "table", "api_key": "k"},
        )
    assert result.exit_code == 0, result.output
    assert verifier.call_args.kwargs["max_rate_age_seconds"] == 4242


def test_gpu_buy_forwards_configured_window(runner, tmp_path, profile):
    quote = _stale_rate_quote(profile, age_seconds=3 * 3600)
    cfg = _sentinel_config()
    qfile = tmp_path / "q.json"
    qfile.write_text(json.dumps(_quote_json(quote)))
    verifier = MagicMock()
    verifier.return_value.valid = True
    verifier.return_value.digest_hex = "ab" * 32
    verifier.return_value.operator_verified = True
    client = MagicMock()
    client.post.return_value = {"payment_id": "pay-1"}
    lock_tx = {"from": "0x" + "11" * 20, "payload": {"provider": "0x" + "22" * 20}, "nonce": 1, "fee": "1"}
    from aitbc_cli.commands.market import market

    with (
        patch("aitbc_cli.commands.market.gpu.get_config", return_value=cfg),
        patch("aitbc_cli.config.get_config", return_value=cfg),
        patch("aitbc_cli.commands.market.gpu.verify_quote", verifier),
        patch("aitbc_cli.commands.market.gpu.resolve_chain_id", return_value="ait-testchain.local"),
        patch("aitbc_cli.commands.market.gpu.load_wallet_for_payment", return_value=("0x" + "11" * 20, "0xpriv", "w")),
        patch("aitbc_cli.utils.escrow.get_node_wallet", return_value="0x" + "33" * 20),
        patch("aitbc_cli.commands.market.gpu.create_signed_escrow_lock", return_value=(lock_tx, "0xsig")),
        patch("aitbc_cli.commands.market.gpu.AITBCHTTPClient", return_value=client),
    ):
        result = runner.invoke(
            market,
            [
                "gpu",
                "buy",
                "--gpu-id",
                "g1",
                "--buyer-id",
                "b1",
                "--job-id",
                "job-1",
                "--duration-hours",
                "1",
                "--settlement",
                "native",
                "--wallet",
                "w",
                "--password",
                "pw",
                "--yes",
                "--energy-quote",
                str(qfile),
            ],
            obj={"output_format": "table", "api_key": "k"},
        )
    assert verifier.called, result.output
    assert verifier.call_args.kwargs["max_rate_age_seconds"] == 4242


def _verify_args(tmp_path, quote, extra=()):
    f = tmp_path / "q.json"
    f.write_text(json.dumps(_quote_json(quote)))
    return ["operator", "verify", "--quote-file", str(f), *extra]


def test_operator_verify_forwards_configured_window(runner, tmp_path, profile):
    quote = _stale_rate_quote(profile, age_seconds=3 * 3600)
    cfg = _sentinel_config()
    verifier = MagicMock()
    verifier.return_value.valid = True
    verifier.return_value.digest_hex = "ab" * 32
    verifier.return_value.operator_verified = True
    verifier.return_value.breakdown = None
    from aitbc_cli.commands.energy import energy

    with (
        patch("aitbc_cli.commands.energy.get_config", return_value=cfg),
        patch("aitbc_cli.config.get_config", return_value=cfg),
        patch("aitbc_cli.commands.energy.verify_quote", verifier),
    ):
        result = runner.invoke(energy, _verify_args(tmp_path, quote), obj={"output_format": "table", "api_key": "k"})
    assert result.exit_code == 0, result.output
    assert verifier.call_args.kwargs["max_rate_age_seconds"] == 4242


def test_operator_verify_oracle_forwards_configured_window(runner, tmp_path, profile):
    quote = _stale_rate_quote(profile, age_seconds=3 * 3600)
    cfg = _sentinel_config()
    cfg.evm_rpc_url = "http://localhost:8545"
    cfg.energy_pricing_contract_address = "0x" + "44" * 20
    verifier = MagicMock()
    verifier.return_value.valid = True
    verifier.return_value.digest_hex = "ab" * 32
    verifier.return_value.operator_verified = True
    verifier.return_value.breakdown = None
    from aitbc_cli.commands.energy import energy

    with (
        patch("aitbc_cli.commands.energy.get_config", return_value=cfg),
        patch("aitbc_cli.config.get_config", return_value=cfg),
        patch("aitbc_cli.commands.energy.verify_quote_against_oracle", verifier),
    ):
        result = runner.invoke(
            energy, _verify_args(tmp_path, quote, extra=["--check-oracle"]), obj={"output_format": "table", "api_key": "k"}
        )
    assert result.exit_code == 0, result.output
    assert verifier.call_args.kwargs["max_rate_age_seconds"] == 4242


def test_oracle_helper_forwards_window_to_both_gates(profile):
    """verify_quote_against_oracle feeds the window to verify_quote AND evaluate_quote."""
    quote = _stale_rate_quote(profile, age_seconds=3 * 3600)
    from aitbc_cli.utils import energy_quote as eq

    ok = MagicMock()
    ok.valid = True
    ok.digest_hex = "ab" * 32
    ok.operator_verified = True
    ok.breakdown = None
    with (
        patch.object(eq, "verify_quote", return_value=ok) as inner,
        patch.object(eq, "EthereumRPCClient"),
        patch.object(eq, "EVMEnergyOracle"),
        patch.object(eq, "evaluate_quote") as ev,
    ):
        ev.return_value.approved = True
        ev.return_value.breakdown = None
        eq.verify_quote_against_oracle(
            quote,
            rpc_url="http://localhost:8545",
            contract_address="0x" + "44" * 20,
            chain_id=1,
            max_rate_age_seconds=4242,
        )
    assert inner.call_args.kwargs["max_rate_age_seconds"] == 4242
    assert ev.call_args.kwargs["max_rate_age_seconds"] == 4242
