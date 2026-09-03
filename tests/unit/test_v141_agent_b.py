"""Unit tests for v0.14.1 Agent B TEE deliverables."""

from __future__ import annotations

import json
import sys
import urllib.error
from pathlib import Path
from types import ModuleType
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]


def _import_module(module_path: str, package_dir: Path) -> ModuleType:
    """Import a module by adding ``package_dir`` to ``sys.path``."""
    if str(package_dir) not in sys.path:
        sys.path.insert(0, str(package_dir))
    return __import__(module_path, fromlist=["__name__"])


def test_tee_task_runner_submits_successfully() -> None:
    """The GPU TEE runner executes a task and best-effort reports to coordinator."""
    runner = _import_module("gpu_app.tee_runner", REPO_ROOT / "apps/gpu/src")
    with patch("urllib.request.urlopen") as mock_urlopen:
        task = runner.run_tee_task(
            task_id="task-1",
            agent_id="agent-1",
            payload={"data": "secret"},
            coordinator_url="http://localhost:8000",
        )
        assert task.status == runner.TEEExecutionStatus.COMPLETED
        assert task.result["executed"] is True
        assert mock_urlopen.called


def test_tee_task_runner_handles_network_errors() -> None:
    """The runner tolerates an unreachable coordinator."""
    runner = _import_module("gpu_app.tee_runner", REPO_ROOT / "apps/gpu/src")
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("unreachable")):
        task = runner.run_tee_task("task-2", "agent-1")
        assert task.status == runner.TEEExecutionStatus.COMPLETED
        assert any("failed" in log.lower() for log in task.logs)


def test_tee_proxy_routes_messages() -> None:
    """The edge TEE proxy registers channels and routes payloads."""
    proxy_mod = _import_module("edge_app.tee_proxy", REPO_ROOT / "apps/edge/src")
    proxy = proxy_mod.TEEProxy()
    proxy.register_channel("ch-1", "peer-1", peer_public_key=b"x" * 32)
    proxy.open_channel("ch-1")
    result = proxy.route_to_channel("ch-1", {"data": "hello"})
    assert result["delivered"] is True
    channel = proxy.channels["ch-1"].channel
    message = channel.messages[0]
    decoded = json.loads(channel.decode(message).decode("utf-8"))
    assert decoded["data"] == "hello"


def test_tee_proxy_rejects_unregistered_or_closed() -> None:
    """The proxy refuses to route to unregistered or closed channels."""
    proxy_mod = _import_module("edge_app.tee_proxy", REPO_ROOT / "apps/edge/src")
    proxy = proxy_mod.TEEProxy()
    try:
        proxy.route_to_channel("missing", {})
        assert False, "expected KeyError"
    except KeyError:
        pass
    proxy.register_channel("ch-2", "peer-2")
    try:
        proxy.route_to_channel("ch-2", {})
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass
