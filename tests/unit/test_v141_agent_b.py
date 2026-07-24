"""Unit tests for v0.14.1 Agent B TEE deliverables."""

from __future__ import annotations

import base64
import sys
import urllib.error
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

from sqlmodel import Session, SQLModel, create_engine

REPO_ROOT = Path(__file__).resolve().parents[2]


def _import_module(module_path: str, package_dir: Path) -> ModuleType:
    """Import a module by adding ``package_dir`` to ``sys.path``."""
    if str(package_dir) not in sys.path:
        sys.path.insert(0, str(package_dir))
    return __import__(module_path, fromlist=["__name__"])


def test_tee_attestation_service_valid_quote() -> None:
    """A valid base64 quote is verified and stored."""
    att_mod = _import_module(
        "coordinator_api.contexts.tee.attestation",
        REPO_ROOT / "apps/coordinator-api/src",
    )
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        service = att_mod.TEEAttestationService(session)
        quote = base64.b64encode(b"x" * 64).decode("ascii")
        att = service.verify_and_store("enclave-1", quote, "measurement-1")
        assert att.status == att_mod.TEEAttestationStatus.VERIFIED.value
        fetched = service.get_attestation(att.id)
        assert fetched is not None
        assert fetched.enclave_id == "enclave-1"


def test_tee_attestation_service_invalid_quote() -> None:
    """A non-base64 quote is rejected."""
    att_mod = _import_module(
        "coordinator_api.contexts.tee.attestation",
        REPO_ROOT / "apps/coordinator-api/src",
    )
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        service = att_mod.TEEAttestationService(session)
        att = service.verify_and_store("enclave-2", "not-base64!!!", "measurement-2")
        assert att.status == att_mod.TEEAttestationStatus.REJECTED.value


def test_enclave_identity_lifecycle() -> None:
    """Enclaves can be registered and retrieved."""
    att_mod = _import_module(
        "coordinator_api.contexts.tee.attestation",
        REPO_ROOT / "apps/coordinator-api/src",
    )
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        service = att_mod.TEEAttestationService(session)
        identity = service.register_enclave("enc-1", "pubkey-1", "agent-1")
        assert identity.status == att_mod.EnclaveStatus.ACTIVE.value
        fetched = service.get_enclave("enc-1")
        assert fetched is not None
        assert fetched.public_key == "pubkey-1"


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
    proxy.register_channel("ch-1", "peer-1")
    proxy.open_channel("ch-1")
    result = proxy.route_to_channel("ch-1", {"data": "hello"})
    assert result["delivered"] is True
    assert proxy.channels["ch-1"].messages[0]["payload"]["data"] == "hello"


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
