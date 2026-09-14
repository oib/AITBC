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
    "apps/api-gateway/src/api_gateway/main.py": "api-gateway",
    "apps/blockchain-node/src/aitbc_chain/app.py": "blockchain-rpc",
    "apps/blockchain-node/src/aitbc_chain/main.py": "blockchain-node",
    "apps/coordinator-api/src/coordinator_api/main.py": "coordinator-api",
    "apps/governance/src/governance_service/main.py": "governance",
    "apps/gpu/src/gpu_service/main.py": "gpu",
    "apps/marketplace/src/marketplace_service/main.py": "marketplace",
    "apps/pool-hub/src/poolhub/app/main.py": "pool-hub",
    "apps/trading/src/trading_service/main.py": "trading",
    "apps/wallet/src/wallet_app/main.py": "wallet",
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
