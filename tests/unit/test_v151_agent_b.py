"""Unit tests for v0.15.1 Agent B HIPAA compliance module."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

from sqlmodel import Session, SQLModel, create_engine

REPO_ROOT = Path(__file__).resolve().parents[2]


def _import_module(module_path: str, package_dir: Path) -> ModuleType:
    """Import a module by adding ``package_dir`` to ``sys.path``."""
    if str(package_dir) not in sys.path:
        sys.path.insert(0, str(package_dir))
    return __import__(module_path, fromlist=["__name__"])


def _hipaa_module() -> ModuleType:
    return _import_module(
        "coordinator_api.contexts.compliance.hipaa",
        REPO_ROOT / "apps/coordinator-api/src",
    )


def test_grant_and_check_consent() -> None:
    hipaa = _hipaa_module()
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        service = hipaa.HIPAAComplianceService(session)
        consent = service.grant_consent("patient-1", "treatment", expires_in_days=365)
        assert consent.is_active()
        assert service._check_consent("patient-1", "treatment")


def test_phi_access_requires_consent() -> None:
    hipaa = _hipaa_module()
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        service = hipaa.HIPAAComplianceService(session)
        try:
            service.access_phi("patient-2", "doctor-1", "record-1", "treatment")
            assert False, "expected PolicyViolationError"
        except Exception:
            pass
        service.grant_consent("patient-2", "treatment", expires_in_days=365)
        log = service.access_phi("patient-2", "doctor-1", "record-1", "treatment")
        assert log.outcome == "allowed"


def test_revoke_consent_denies_access() -> None:
    hipaa = _hipaa_module()
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        service = hipaa.HIPAAComplianceService(session)
        consent = service.grant_consent("patient-3", "treatment", expires_in_days=365)
        service.revoke_consent(consent.id)
        try:
            service.access_phi("patient-3", "doctor-1", "record-1", "treatment")
            assert False, "expected PolicyViolationError"
        except Exception:
            pass


def test_right_to_delete_revokes_consent_and_logs() -> None:
    hipaa = _hipaa_module()
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        service = hipaa.HIPAAComplianceService(session)
        service.grant_consent("patient-4", "treatment", expires_in_days=365)
        logs = service.right_to_delete("patient-4", "patient-4")
        assert len(logs) == 1
        assert logs[0].action == "delete"
        assert not service._check_consent("patient-4", "treatment")


def test_hipaa_example_policy_loaded() -> None:
    from aitbc.compliance.policies import ComplianceFramework, load_policy_template

    policy = load_policy_template(ComplianceFramework.HIPAA)
    assert policy.framework == ComplianceFramework.HIPAA
    assert policy.require_control("HIPAA-3")
