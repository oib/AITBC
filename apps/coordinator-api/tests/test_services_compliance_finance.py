"""Tests for coordinator_api.contexts.compliance.finance (#1289 residual coverage)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from aitbc.compliance.errors import PolicyViolationError
from aitbc.compliance.policies import ComplianceFramework
from coordinator_api.contexts.compliance.finance import (
    FinancialComplianceService,
    NonRepudiationProof,
    TransactionAuditRecord,
    TransactionStatus,
    _hash_payload,
    _sign_payload,
    _verify_signature,
)

SIGNING_KEY = b"test-signing-key"
PUBLIC_KEY = b"test-signing-key"
WRONG_KEY = b"attacker-key"


@pytest.fixture
def service(db_session: Session) -> FinancialComplianceService:
    return FinancialComplianceService(db_session)


def _create(service: FinancialComplianceService, **overrides: object) -> TransactionAuditRecord:
    kwargs: dict[str, object] = {
        "transaction_id": "tx_1",
        "actor_id": "actor_1",
        "counterparty_id": "cp_1",
        "amount": Decimal("10.50"),
        "asset": "USDC",
        "classification": "pci",
    }
    kwargs.update(overrides)
    return service.create_transaction(**kwargs)  # type: ignore[arg-type]


class TestTransactionStatus:
    def test_enum_values(self) -> None:
        assert TransactionStatus.PENDING.value == "pending"
        assert TransactionStatus.APPROVED.value == "approved"
        assert TransactionStatus.DENIED.value == "denied"


class TestHashAndSignatureHelpers:
    def test_hash_payload_is_deterministic(self) -> None:
        record = TransactionAuditRecord(
            transaction_id="tx",
            actor_id="a",
            counterparty_id="c",
            amount=Decimal("1.5"),
            asset="AIT",
        )
        assert _hash_payload(record) == _hash_payload(record)
        assert len(_hash_payload(record)) == 64

    def test_hash_payload_changes_with_fields(self) -> None:
        base = TransactionAuditRecord(transaction_id="tx", actor_id="a", amount=Decimal("1"))
        other = TransactionAuditRecord(transaction_id="tx2", actor_id="a", amount=Decimal("1"))
        assert _hash_payload(base) != _hash_payload(other)

    def test_sign_and_verify_roundtrip(self) -> None:
        signature = _sign_payload("deadbeef", SIGNING_KEY)
        assert signature.startswith(SIGNING_KEY + b":")
        assert _verify_signature("deadbeef", signature, PUBLIC_KEY) is True

    def test_verify_signature_rejects_empty(self) -> None:
        assert _verify_signature("h", b"", PUBLIC_KEY) is False

    def test_verify_signature_rejects_missing_colon(self) -> None:
        assert _verify_signature("h", b"nocolonhere", PUBLIC_KEY) is False

    def test_verify_signature_rejects_wrong_key(self) -> None:
        signature = _sign_payload("h", SIGNING_KEY)
        assert _verify_signature("h", signature, WRONG_KEY) is False


class TestCreateTransaction:
    def test_creates_pending_record_with_proof_hash(self, service: FinancialComplianceService) -> None:
        record = _create(service)

        assert record.id.startswith("far_")
        assert record.status == TransactionStatus.PENDING.value
        assert record.transaction_id == "tx_1"
        assert record.amount == Decimal("10.50")
        assert record.policy_framework == ComplianceFramework.PCI_DSS.value
        assert record.proof_hash
        assert record.created_at is not None
        assert record.finalized_at is None

    def test_record_is_persisted(self, service: FinancialComplianceService, db_session: Session) -> None:
        record = _create(service)
        fetched = db_session.exec(
            select(TransactionAuditRecord).where(TransactionAuditRecord.transaction_id == "tx_1")
        ).first()
        assert fetched is not None
        assert fetched.id == record.id

    def test_negative_amount_raises_policy_violation(self, service: FinancialComplianceService) -> None:
        with pytest.raises(PolicyViolationError, match="negative"):
            _create(service, amount=Decimal("-1"))

    def test_unique_transaction_id_enforced(self, service: FinancialComplianceService) -> None:
        _create(service)
        with pytest.raises(IntegrityError):
            _create(service, actor_id="actor_2")


class TestAuthorize:
    def test_unknown_transaction_raises_value_error(self, service: FinancialComplianceService) -> None:
        with pytest.raises(ValueError, match="transaction not found"):
            service.authorize("tx_missing", SIGNING_KEY, PUBLIC_KEY)

    def test_authorize_approves_and_creates_proof(self, service: FinancialComplianceService, db_session: Session) -> None:
        record = _create(service)

        authorized = service.authorize(record.transaction_id, SIGNING_KEY, PUBLIC_KEY)

        assert authorized.status == TransactionStatus.APPROVED.value
        assert authorized.finalized_at is not None

        proofs = db_session.exec(
            select(NonRepudiationProof).where(NonRepudiationProof.transaction_id == record.transaction_id)
        ).all()
        assert len(proofs) == 1
        proof = proofs[0]
        assert proof.id.startswith("nrp_")
        assert proof.signer_id == record.actor_id
        assert proof.payload_hash == record.proof_hash
        assert proof.signature.startswith(SIGNING_KEY + b":")

    def test_verify_non_repudiation_with_correct_key(self, service: FinancialComplianceService) -> None:
        record = _create(service)
        service.authorize(record.transaction_id, SIGNING_KEY, PUBLIC_KEY)

        assert service.verify_non_repudiation(record.transaction_id, PUBLIC_KEY) is True

    def test_verify_non_repudiation_with_wrong_key(self, service: FinancialComplianceService) -> None:
        record = _create(service)
        service.authorize(record.transaction_id, SIGNING_KEY, PUBLIC_KEY)

        assert service.verify_non_repudiation(record.transaction_id, WRONG_KEY) is False

    def test_verify_non_repudiation_without_proof(self, service: FinancialComplianceService) -> None:
        _create(service)
        assert service.verify_non_repudiation("tx_1", PUBLIC_KEY) is False

    def test_consent_required_without_consent_id_denies(self, service: FinancialComplianceService) -> None:
        record = _create(service, consent_required=True, consent_id=None)

        with pytest.raises(PolicyViolationError, match="requires consent"):
            service.authorize(record.transaction_id, SIGNING_KEY, PUBLIC_KEY)

        db_session_record = service.session.get(TransactionAuditRecord, record.id)
        assert db_session_record is not None
        assert db_session_record.status == TransactionStatus.DENIED.value

    def test_consent_required_with_consent_id_approves(self, service: FinancialComplianceService) -> None:
        record = _create(service, consent_required=True, consent_id="consent_1")

        authorized = service.authorize(record.transaction_id, SIGNING_KEY, PUBLIC_KEY)

        assert authorized.status == TransactionStatus.APPROVED.value

    def test_denied_transaction_cannot_be_reauthorized(self, service: FinancialComplianceService) -> None:
        record = _create(service, consent_required=True, consent_id=None)
        with pytest.raises(PolicyViolationError):
            service.authorize(record.transaction_id, SIGNING_KEY, PUBLIC_KEY)

        # Supplying consent cannot resurrect the denied record: consent_id is
        # immutable on the stored row, so authorize keeps raising.
        with pytest.raises(PolicyViolationError):
            service.authorize(record.transaction_id, SIGNING_KEY, PUBLIC_KEY)


class TestAuditTrail:
    def test_audit_trail_returns_record(self, service: FinancialComplianceService) -> None:
        record = _create(service)

        trail = service.audit_trail("tx_1")

        assert len(trail) == 1
        assert trail[0].id == record.id

    def test_audit_trail_empty_for_unknown(self, service: FinancialComplianceService) -> None:
        assert service.audit_trail("tx_nope") == []


class TestGlbaFramework:
    def test_glba_service_loads_glba_policy(self, db_session: Session) -> None:
        service = FinancialComplianceService(db_session, framework=ComplianceFramework.GLBA)

        assert service.framework == ComplianceFramework.GLBA
        assert service.policy.framework == ComplianceFramework.GLBA
        # GLBA-1 (Customer Information Safeguards) is required -> consent gate applies.
        assert service._require_control("GLBA-1") is True
        assert service._require_control("PCI-1") is False

    def test_glba_consent_gate_denies(self, db_session: Session) -> None:
        service = FinancialComplianceService(db_session, framework=ComplianceFramework.GLBA)
        record = service.create_transaction(
            transaction_id="tx_glba",
            actor_id="actor_g",
            counterparty_id="cp_g",
            amount=Decimal("5"),
            asset="USD",
            classification="pii",
            consent_required=True,
        )

        with pytest.raises(PolicyViolationError, match="requires consent"):
            service.authorize(record.transaction_id, SIGNING_KEY, PUBLIC_KEY)

    def test_glba_authorize_happy_path(self, db_session: Session) -> None:
        service = FinancialComplianceService(db_session, framework=ComplianceFramework.GLBA)
        record = service.create_transaction(
            transaction_id="tx_glba2",
            actor_id="actor_g",
            counterparty_id="cp_g",
            amount=Decimal("5"),
            asset="USD",
            classification="pii",
        )

        authorized = service.authorize(record.transaction_id, SIGNING_KEY, PUBLIC_KEY)

        assert authorized.status == TransactionStatus.APPROVED.value
        assert authorized.policy_framework == ComplianceFramework.GLBA.value
        assert service.verify_non_repudiation("tx_glba2", PUBLIC_KEY) is True


class TestModelDefaults:
    def test_transaction_audit_record_defaults(self) -> None:
        record = TransactionAuditRecord()
        assert record.id.startswith("far_")
        assert record.status == TransactionStatus.PENDING.value
        assert record.classification == "pci"
        assert record.policy_framework == "pci_dss"
        assert record.amount == Decimal("0")

    def test_non_repudiation_proof_defaults(self) -> None:
        proof = NonRepudiationProof()
        assert proof.id.startswith("nrp_")
        assert proof.signature == b""
        assert proof.timestamp is not None
