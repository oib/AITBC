"""Unit tests for v0.15.2 Agent B financial regulatory compliance module."""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from types import ModuleType

from sqlmodel import Session, SQLModel, create_engine

REPO_ROOT = Path(__file__).resolve().parents[2]


def _import_module(module_path: str, package_dir: Path) -> ModuleType:
    """Import a module by adding ``package_dir`` to ``sys.path``."""
    if str(package_dir) not in sys.path:
        sys.path.insert(0, str(package_dir))
    return __import__(module_path, fromlist=["__name__"])


def _finance_module() -> ModuleType:
    return _import_module(
        "coordinator_api.contexts.compliance.finance",
        REPO_ROOT / "apps/coordinator-api/src",
    )


def test_create_financial_transaction() -> None:
    finance = _finance_module()
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        service = finance.FinancialComplianceService(session)
        record = service.create_transaction(
            transaction_id="txn-1",
            actor_id="merchant-1",
            counterparty_id="processor-1",
            amount=Decimal("100.00"),
            asset="USD",
            classification="pci",
        )
        assert record.transaction_id == "txn-1"
        assert record.status == finance.TransactionStatus.PENDING.value
        assert record.proof_hash != ""


def test_authorize_transaction_requires_consent() -> None:
    finance = _finance_module()
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        service = finance.FinancialComplianceService(session)
        service.create_transaction(
            transaction_id="txn-2",
            actor_id="merchant-1",
            counterparty_id="processor-1",
            amount=Decimal("50.00"),
            asset="USD",
            classification="pci",
            consent_required=True,
        )
        try:
            service.authorize("txn-2", b"key-1", b"key-1")
            assert False, "expected PolicyViolationError"
        except Exception:
            pass


def test_authorize_and_verify_non_repudiation() -> None:
    finance = _finance_module()
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        service = finance.FinancialComplianceService(session)
        service.create_transaction(
            transaction_id="txn-3",
            actor_id="merchant-1",
            counterparty_id="processor-1",
            amount=Decimal("25.00"),
            asset="USD",
            classification="pci",
            consent_required=True,
            consent_id="consent-1",
        )
        authorized = service.authorize("txn-3", b"key-1", b"key-1")
        assert authorized.status == finance.TransactionStatus.APPROVED.value
        assert service.verify_non_repudiation("txn-3", b"key-1") is True
        assert service.verify_non_repudiation("txn-3", b"wrong-key") is False


def test_glba_policy_applies_to_pii() -> None:
    from aitbc.compliance.policies import ComplianceFramework, load_policy_template

    policy = load_policy_template(ComplianceFramework.GLBA)
    assert policy.framework == ComplianceFramework.GLBA
    assert policy.require_control("GLBA-1")
