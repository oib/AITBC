"""Every long-running service must configure file logging, not just journal logging.

`configure_logging()` writes the traceback of a `logger.exception()` call only into
the rotating JSON file, never into the journal -- that split is deliberate and is
documented in `aitbc/aitbc_logging.py`. It is also conditional: the file handler is
created only when the caller passes both `service_name` and `to_file=True`.

Ten service entrypoints passed neither. The consequence was not "logs are less
detailed": it was that the 5xx handler in `aitbc/middleware/error_handler.py`
deliberately keeps the reason out of the HTTP response *because the reason goes to
the log* -- and the reason was reaching no log at all. Two of these services were
returning 500 with an empty body and nothing anywhere on the host explained why.

This is a source scan rather than a runtime check because these calls run at import
time in modules that pull in the whole service (database engines, settings that
require secrets); importing ten of them to read one keyword argument would make the
test heavier and less reliable than the thing it guards.

`service_name` doubles as the log directory name, so two entrypoints sharing a tree
must not share a name -- `aitbc_chain.app` (the RPC unit) and `aitbc_chain.main`
(the block producer) run as separate processes and would otherwise rotate the same
file out from under each other.

Two entries are not service `main.py` modules and are here deliberately.
`cli/aitbc_cli/commands/prometheus.py` is a CLI command module, but its `--watch`
branch is what `aitbc-prometheus-watch` runs as a long-lived unit; the call sits
inside that branch so a one-shot invocation by a human does not try to create a
service log directory as them. `aitbc_chain/gossip/relay.py` is the p2p unit's real
entrypoint -- its wrapper `exec`s into this module, so the wrapper's own logging
setup is replaced by this one.

What this test cannot see is the unit sandbox around the process.
`_get_log_file_path()` returns None rather than raising when the directory is
unwritable, so a `ProtectSystem=strict` unit with no `ReadWritePaths` entry for
`/var/log/aitbc` passes this scan and still writes nothing. Both units that were in
that position (`aitbc-blockchain-p2p`, `aitbc-prometheus-watch`) now carry the
entry; a new one needs it too.

The service *user* is the same kind of blind spot. `/var/log/aitbc` is `aitbc:aitbc
0755` on every host, so a unit running as anyone else cannot create its own
subdirectory there and degrades to journal-only just as silently.
`aitbc-hermes-agent` is the only one today (`User=aitbc-hermes`) and creates the
directory from a root `ExecStartPre=+` in its unit file.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# path -> the service_name it must register. The value is also the log directory,
# and matches the convention the wrapper scripts already use: the app directory
# name without the `aitbc-` prefix.
SERVICE_ENTRYPOINTS = {
    "apps/agent-coordinator/src/agent_app/main.py": "agent-coordinator",
    "apps/api-gateway/src/api_gateway/main.py": "api-gateway",
    "apps/blockchain-event-bridge/src/blockchain_event_bridge/main.py": "blockchain-event-bridge",
    "apps/blockchain-explorer/main.py": "blockchain-explorer",
    "apps/blockchain-node/src/aitbc_chain/app.py": "blockchain-rpc",
    "apps/blockchain-node/src/aitbc_chain/gossip/relay.py": "blockchain-p2p",
    "apps/blockchain-node/src/aitbc_chain/main.py": "blockchain-node",
    "apps/bridge-monitor/src/bridge_monitor/main.py": "bridge-monitor",
    "apps/coordinator-api/src/coordinator_api/main.py": "coordinator-api",
    "apps/edge/src/aitbc_edge/main.py": "edge",
    "apps/exchange/simple_exchange/server.py": "exchange",
    "apps/ffmpeg/main.py": "ffmpeg",
    "apps/governance/src/governance_service/main.py": "governance",
    "apps/gpu/src/gpu_service/main.py": "gpu",
    # The unit is aitbc-hermes-agent and every other name here is hyphenated; this
    # one read `hermes_agent` until the entry was added, which would have given it
    # the only log directory on the fleet that did not match its unit name.
    "apps/hermes_agent/main.py": "hermes-agent",
    "apps/ipfs/ipfs-daemon.py": "ipfs",
    "apps/ipfs/island_ipfs_daemon.py": "island-ipfs",
    "apps/marketplace/src/marketplace_service/main.py": "marketplace",
    "apps/pool-hub/src/poolhub/app/main.py": "pool-hub",
    "apps/trading/src/trading_service/main.py": "trading",
    "apps/wallet/src/wallet_app/main.py": "wallet",
    "apps/whisper/main.py": "whisper",
    "cli/aitbc_cli/commands/prometheus.py": "prometheus-watch",
}


def _configure_logging_calls(path: Path) -> list[ast.Call]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "configure_logging"
    ]


@pytest.mark.parametrize(("relpath", "expected_name"), sorted(SERVICE_ENTRYPOINTS.items()))
def test_entrypoint_enables_file_logging(relpath: str, expected_name: str) -> None:
    path = REPO / relpath
    assert path.exists(), f"{relpath} moved; update SERVICE_ENTRYPOINTS"

    calls = _configure_logging_calls(path)
    assert calls, f"{relpath} no longer calls configure_logging()"

    for call in calls:
        kwargs = {kw.arg: kw.value for kw in call.keywords}

        service_name = kwargs.get("service_name")
        assert isinstance(service_name, ast.Constant) and service_name.value == expected_name, (
            f"{relpath} must pass service_name={expected_name!r}; without it configure_logging() creates no file handler"
        )

        to_file = kwargs.get("to_file")
        assert isinstance(to_file, ast.Constant) and to_file.value is True, (
            f"{relpath} must pass to_file=True; without it the traceback of every logger.exception() call is discarded"
        )


def test_service_names_are_unique() -> None:
    """A shared name is a shared log file, and two processes rotating one file lose records."""
    names = list(SERVICE_ENTRYPOINTS.values())
    duplicates = {n for n in names if names.count(n) > 1}
    assert not duplicates, f"service_name collides across entrypoints: {sorted(duplicates)}"
