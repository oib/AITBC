"""V23-92 leftovers — shop/follower nodes must not treat hub-only services as local.

``aitbc-exchange`` (8106) and ``aitbc-agent-coordinator`` (8107) are in
``setup.sh``'s ``hub_services`` list. A shop or follower node is correct not to
run them. Defaults and monitors that still name ``localhost:8106`` / ``:8107``
report a missing unit as an outage — the same shape as the coin-request
notification bug V23-92 already fixed in the CLI.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HEALTH_CHECK_SH = REPO_ROOT / "scripts" / "monitoring" / "health_check.sh"
SETUP_SH = REPO_ROOT / "scripts" / "deployment" / "setup.sh"


def _hub_services() -> set[str]:
    text = SETUP_SH.read_text(encoding="utf-8")
    match = re.search(r"local hub_services=\((.*?)\)", text, re.DOTALL)
    assert match, "setup.sh no longer declares hub_services"
    return set(re.findall(r"aitbc-[a-z0-9-]+", match.group(1)))


def test_exchange_and_agent_coordinator_are_hub_services() -> None:
    hub = _hub_services()
    assert "aitbc-exchange" in hub
    assert "aitbc-agent-coordinator" in hub


def _health_endpoints_for(*, blockchain_mode: str, market_role: str, hardware_profile: str) -> set[str]:
    import os
    import subprocess

    env = os.environ.copy()
    env.update(
        {
            "BLOCKCHAIN_MODE": blockchain_mode,
            "MARKET_ROLE": market_role,
            "HARDWARE_PROFILE": hardware_profile,
        }
    )
    script = f"""
    source {HEALTH_CHECK_SH}
    printf '%s\\n' "${{!SERVICE_ENDPOINTS[@]}}"
    """
    result = subprocess.run(["bash", "-c", script], env=env, check=True, capture_output=True, text=True)
    return {line for line in result.stdout.splitlines() if line}


def test_health_check_probes_hub_only_ports_only_on_a_hub() -> None:
    hub = _health_endpoints_for(blockchain_mode="hub", market_role="customer", hardware_profile="nogpu")
    shop = _health_endpoints_for(blockchain_mode="follower", market_role="shop", hardware_profile="gpu")
    follower = _health_endpoints_for(blockchain_mode="follower", market_role="customer", hardware_profile="nogpu")
    customer = _health_endpoints_for(blockchain_mode="follower", market_role="customer", hardware_profile="nogpu")

    assert "aitbc-exchange" in hub
    assert "aitbc-agent-coordinator" in hub
    assert "aitbc-pool-hub" not in hub

    assert "aitbc-exchange" not in shop
    assert "aitbc-agent-coordinator" not in shop
    assert "aitbc-pool-hub" in shop
    assert "aitbc-gpu" in shop
    assert "aitbc-edge" in shop

    assert "aitbc-exchange" not in follower
    assert "aitbc-agent-coordinator" not in follower
    assert "aitbc-pool-hub" not in follower
    assert "aitbc-wallet" in follower

    assert customer == follower


def test_cli_defaults_do_not_point_at_local_hub_only_ports() -> None:
    from aitbc_cli.config import CLIConfig

    agent = CLIConfig.model_fields["agent_coordinator_url"].default
    exchange = CLIConfig.model_fields["exchange_service_url"].default
    assert agent == ""
    assert exchange == ""


def test_pool_hub_does_not_default_to_local_agent_coordinator() -> None:
    settings_src = (REPO_ROOT / "apps" / "pool-hub" / "src" / "poolhub" / "settings.py").read_text(
        encoding="utf-8"
    )
    client_src = (REPO_ROOT / "apps" / "pool-hub" / "src" / "poolhub" / "clients" / "blockchain.py").read_text(
        encoding="utf-8"
    )
    assert "localhost:8107" not in settings_src
    assert "localhost:8107" not in client_src


def test_coin_request_notifications_still_refuse_a_local_default() -> None:
    """The original V23-92 fix must keep working."""
    tree = ast.parse((REPO_ROOT / "cli" / "aitbc_cli" / "commands" / "coin_requests.py").read_text())
    defaults = [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)]
    assert "http://localhost:8107" not in defaults
