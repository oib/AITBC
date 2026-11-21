"""#2357: energy CLI honesty defects found during S56 replay.

1. ``aitbc energy suggest --register`` printed ``Applied via --register;
   next:`` BEFORE the register call ran, so a failed leg still showed the
   success banner. The banner must only appear after registration succeeds.
2. ``aitbc energy operator verify`` on a malformed quote (e.g. ``{}``)
   crashed with an unhandled ``TypeError`` traceback instead of a clean
   ``CLIError``. ``parse_quote`` now validates the payload shape.
"""

from __future__ import annotations

import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from aitbc_cli.commands.energy import energy
from aitbc_cli.utils.error_handling import CLIError, ValidationError
from aitbc_cli.utils.http_client import NetworkError


@pytest.fixture
def runner():
    return CliRunner()


def _config():
    c = MagicMock()
    c.native_chain_id = ""
    c.blockchain_rpc_url = "http://localhost:8202"
    c.coordinator_api_url = "http://localhost:8203"
    c.native_coordinator_url = None
    c.energy_operator_address = None
    c.energy_quote_domain = "aitbc.energy.quote.v1"
    c.energy_max_rate_age_seconds = 86400
    c.energy_pricing_contract_address = None
    c.evm_rpc_url = None
    c.energy_eur_per_kwh = None
    c.shop_region = None
    c.api_key = None
    return c


def _est():
    return SimpleNamespace(
        register_watts=300,
        gpu_tbp_w=300,
        gpu_w_source="test",
        cpu_watts=100,
        cpu_w_source="test",
        platform_watts=100,
        node_gpu_count=1,
        node_wall_watts=500,
    )


def _suggest_patches(config, native_side_effect=None):
    return (
        patch("aitbc_cli.commands.energy.get_config", return_value=config),
        patch("aitbc_cli.config.get_config", return_value=config),
        patch(
            "aitbc_cli.commands.energy._suggest_hardware",
            return_value=(_est(), "test-gpu", "test-cpu", None),
        ),
        patch(
            "aitbc_cli.commands.energy._resolve_tariff",
            return_value=(Decimal("0.30"), "manual"),
        ),
        patch(
            "aitbc_cli.commands.energy._resolve_ait_rate",
            return_value=(Decimal("4"), "test"),
        ),
        patch("aitbc.market.hardware_catalog.compute_multiplier", return_value=None),
        patch("aitbc.market.energy_pricing.compute_energy_net_units", return_value=123),
        patch(
            "aitbc_cli.commands.energy._native_energy_request",
            side_effect=native_side_effect,
        ),
    )


SUGGEST_ARGS = [
    "suggest",
    "--resource-id",
    "res-1",
    "--provider-address",
    "0x" + "22" * 20,
    "--gpu-count",
    "1",
    "--duration-seconds",
    "3600",
    "--register",
]


def test_suggest_register_failure_has_no_applied_banner(runner):
    """A failed --register leg must not print the 'Applied' success text."""
    config = _config()
    patches = _suggest_patches(config, native_side_effect=NetworkError("boom"))
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7]:
        result = runner.invoke(energy, SUGGEST_ARGS, obj={"output_format": "table"})
    assert result.exit_code != 0
    assert "Native profile registration failed" in result.output
    assert "Applied via --register" not in result.output


def test_suggest_register_success_prints_applied_banner(runner):
    """On success the banner still appears, after the register output."""
    config = _config()
    patches = _suggest_patches(config, native_side_effect={"ok": True})
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7]:
        result = runner.invoke(energy, SUGGEST_ARGS, obj={"output_format": "table"})
    assert result.exit_code == 0, result.output
    assert "Native energy profile registered" in result.output
    assert "Applied via --register; next:" in result.output


def test_operator_verify_malformed_quote_is_clean_clierror(runner, tmp_path):
    """``{}`` must produce a CLIError, not a TypeError traceback."""
    quote_file = tmp_path / "quote.json"
    quote_file.write_text("{}")
    config = _config()
    with (
        patch("aitbc_cli.commands.energy.get_config", return_value=config),
        patch("aitbc_cli.config.get_config", return_value=config),
    ):
        result = runner.invoke(
            energy,
            ["operator", "verify", "--quote-file", str(quote_file)],
            obj={"output_format": "table"},
        )
    assert result.exit_code != 0
    assert "missing required field" in result.output
    assert not isinstance(result.exception, TypeError)


def test_parse_quote_empty_dict_raises_validation_error():
    """parse_quote({}) raises CLIError (ValidationError), not TypeError."""
    from aitbc_cli.utils.energy_quote import parse_quote

    with pytest.raises(CLIError) as excinfo:
        parse_quote({})
    assert isinstance(excinfo.value, ValidationError)
    assert "missing required field" in str(excinfo.value)


def test_parse_quote_non_object_raises_validation_error():
    from aitbc_cli.utils.energy_quote import parse_quote

    with pytest.raises(ValidationError):
        parse_quote(["not", "a", "dict"])


def test_parse_quote_valid_unsigned_quote_still_verifies(runner, tmp_path):
    """Regression: a structurally valid unsigned quote still reaches
    verification and fails with invalid_signature, not a parse error."""
    import time

    from aitbc.market.energy_pricing import EnergyQuote, SettlementRoute
    from aitbc_cli.utils.address import to_canonical
    from aitbc_cli.utils.energy_quote import compute_energy_net_units

    now = int(time.time())
    floor = compute_energy_net_units(
        tbp_watts=100,
        eur_per_kwh_scaled=30 * 10**16,
        ait_per_eur_scaled=10**18,
        gpu_count=1,
        duration_seconds=3600,
        settlement_unit_scale=10**18,
    )
    q = EnergyQuote(
        domain="aitbc.energy.quote.v1",
        chain_id="ait-hub.aitbc.bubuit.net",
        settlement_asset="AITBC",
        settlement_unit_scale=10**18,
        buyer=to_canonical("0x" + "11" * 20),
        provider="0x" + "22" * 20,
        job_id="job-1",
        quote_id="q-1",
        settlement_route=SettlementRoute.NATIVE,
        resource_id="res-1",
        model_id="m-1",
        gpu_count=1,
        duration_seconds=3600,
        eur_per_kwh_scaled=30 * 10**16,
        tbp_watts=100,
        ait_per_eur_scaled=10**18,
        rate_version=1,
        rate_observed_at=now,
        rate_source_kind="manual",
        profile_revision=1,
        net_energy_floor_units=floor,
        principal_units=floor * 2,
        issued_at=now,
        expires_at=now + 300,
    )
    quote_file = tmp_path / "quote.json"
    quote_file.write_text(json.dumps(q.to_dict(include_signature=True)))

    config = _config()
    config.native_chain_id = "ait-hub.aitbc.bubuit.net"
    config.energy_operator_address = "0x" + "33" * 20
    with (
        patch("aitbc_cli.commands.energy.get_config", return_value=config),
        patch("aitbc_cli.config.get_config", return_value=config),
    ):
        result = runner.invoke(
            energy,
            ["operator", "verify", "--quote-file", str(quote_file)],
            obj={"output_format": "table"},
        )
    assert result.exit_code != 0
    assert "invalid_signature" in result.output
