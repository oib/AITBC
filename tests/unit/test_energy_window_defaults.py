"""The energy-rate freshness window has exactly one default: 86400s.

SD-7 follow-up: the same window used to live in four places that had
drifted apart — the coordinator's ``Settings`` field defaulted to 300s
while the node RPC fallback, the CLI config field, and hub's env file all
used 86400s. The fleet converged on 86400 because the refresher
(``aitbc-native-energy-rate-refresh.timer``) re-attests the stored rate
every 12h: a 300s window would invalidate every quote after a single
missed run, while 86400 tolerates two missed runs with slack.

All four code defaults now bind ``DEFAULT_MAX_RATE_AGE_SECONDS`` in
``aitbc.market.energy_pricing`` so they cannot drift. This module fails
if any of them is re-hardcoded to something else, or if the shared
constant is changed away from the documented 24h operator policy.
"""

from __future__ import annotations

from aitbc.market.energy_pricing import DEFAULT_MAX_RATE_AGE_SECONDS


def test_shared_constant_is_the_documented_window() -> None:
    """24h: the refresher's 12h cadence needs the window to outlast two
    missed runs. Changing this number is a fleet-wide decision — the
    coordinator, node fallback, CLI, and alert rules all assume it."""
    assert DEFAULT_MAX_RATE_AGE_SECONDS == 86400


def test_coordinator_default_binds_the_shared_constant() -> None:
    from coordinator_api.config import Settings

    default = Settings.model_fields["energy_max_rate_age_seconds"].default
    assert default == DEFAULT_MAX_RATE_AGE_SECONDS


def test_node_rpc_fallback_binds_the_shared_constant(monkeypatch) -> None:
    from aitbc_chain.rpc import escrow_routes

    assert escrow_routes._FALLBACK_MAX_RATE_AGE_SECONDS == DEFAULT_MAX_RATE_AGE_SECONDS
    monkeypatch.delenv("ENERGY_MAX_RATE_AGE_SECONDS", raising=False)
    assert escrow_routes._energy_max_rate_age_seconds() == DEFAULT_MAX_RATE_AGE_SECONDS


def test_cli_default_binds_the_shared_constant(monkeypatch) -> None:
    from aitbc_cli.config import CLIConfig

    monkeypatch.delenv("ENERGY_MAX_RATE_AGE_SECONDS", raising=False)
    assert CLIConfig().energy_max_rate_age_seconds == DEFAULT_MAX_RATE_AGE_SECONDS
    assert CLIConfig.model_fields["energy_max_rate_age_seconds"].default == DEFAULT_MAX_RATE_AGE_SECONDS
