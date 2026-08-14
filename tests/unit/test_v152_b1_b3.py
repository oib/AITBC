"""Unit tests for v0.15.2 Agent B1 (containers/sub-networks) and B3 (middleware/CLI)."""

from __future__ import annotations

from aitbc.compliance.consent import ConsentTracker
from aitbc.compliance.errors import PolicyViolationError
from aitbc.compliance.policies import ComplianceFramework, DataClassification


def test_edge_compliance_subnet_allows_phi() -> None:
    from apps.edge.src.edge_app.compliance_subnets import ComplianceSubnet, SubnetRegistry

    subnet = ComplianceSubnet(
        subnet_id="hipaa-subnet-1",
        allowed_frameworks={ComplianceFramework.HIPAA},
        allowed_classifications={DataClassification.PHI},
    )
    registry = SubnetRegistry()
    registry.register(subnet)
    record = registry.assign("w-1", ComplianceFramework.HIPAA, "phi", "hipaa-subnet-1")
    assert record["status"] == "isolated"
    assert registry.is_isolated("hipaa-subnet-1", "w-1")


def test_edge_compliance_subnet_rejects_pci() -> None:
    from apps.edge.src.edge_app.compliance_subnets import ComplianceSubnet, SubnetRegistry

    subnet = ComplianceSubnet(
        subnet_id="hipaa-subnet-1",
        allowed_frameworks={ComplianceFramework.HIPAA},
        allowed_classifications={DataClassification.PHI},
    )
    registry = SubnetRegistry()
    registry.register(subnet)
    try:
        registry.assign("w-2", ComplianceFramework.PCI_DSS, "pci", "hipaa-subnet-1")
        assert False, "expected PolicyViolationError"
    except PolicyViolationError:
        pass


def test_gpu_compliance_enclave_requires_attestation() -> None:
    from apps.gpu.src.gpu_app.compliance_enclaves import ComplianceGPUEnclave

    enclave = ComplianceGPUEnclave(
        enclave_id="gpu-hipaa-1",
        policy_framework=ComplianceFramework.HIPAA,
        allowed_classifications={DataClassification.PHI},
    )
    try:
        enclave.run("w-1", "phi", {"x": 1})
        assert False, "expected PolicyViolationError"
    except PolicyViolationError:
        pass


def test_gpu_compliance_enclave_runs_after_attestation() -> None:
    from apps.gpu.src.gpu_app.compliance_enclaves import ComplianceGPUEnclave

    enclave = ComplianceGPUEnclave(
        enclave_id="gpu-hipaa-1",
        policy_framework=ComplianceFramework.HIPAA,
        allowed_classifications={DataClassification.PHI},
    )
    enclave.attest("measurement-1")
    result = enclave.run("w-1", "phi", {"x": 1})
    assert result["attested"] is True
    assert result["classification"] == "phi"


def test_consent_tracker() -> None:
    tracker = ConsentTracker()
    tracker.grant("patient-1", "treatment", classifications={"phi"})
    assert tracker.is_consented("patient-1", "treatment", "phi")
    tracker.revoke("patient-1", "treatment")
    assert not tracker.is_consented("patient-1", "treatment", "phi")


def _middleware_app(tracker: ConsentTracker | None = None):
    import sys
    from pathlib import Path

    from fastapi import FastAPI

    repo_root = Path(__file__).resolve().parents[2]
    coordinator_src = str(repo_root / "apps" / "coordinator-api" / "src")
    if coordinator_src not in sys.path:
        sys.path.insert(0, coordinator_src)
    from coordinator_api.middleware.compliance import ComplianceMiddleware

    app = FastAPI()
    app.add_middleware(ComplianceMiddleware, tracker=tracker)

    @app.get("/phi")
    def get_phi() -> dict[str, str]:
        return {"ok": "true"}

    return app


def _cli_runner():
    from click.testing import CliRunner
    from cli.aitbc_cli.core.main import cli

    return CliRunner(), cli
