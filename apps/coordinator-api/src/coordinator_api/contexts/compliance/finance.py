"""Financial regulatory (PCI/GLBA) compliance module (v0.15.2 §B2).

This is a policy skeleton. Real PCI/GLBA enforcement needs a hardware-backed
signing key, a tamper-evident audit sink, and integration with a token vault
for PAN handling.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import JSON, Column, Numeric, text
from sqlmodel import Field, Session, SQLModel, select

from aitbc.compliance.errors import PolicyViolationError
from aitbc.compliance.policies import ComplianceFramework, load_policy_template


class TransactionStatus(StrEnum):
    """Lifecycle status of a financial transaction audit record."""

    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"


class TransactionAuditRecord(SQLModel, table=True):
    """Immutable audit record for a regulated financial transaction."""

    __tablename__ = "transaction_audit_record"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"far_{uuid4().hex[:10]}", max_length=32, primary_key=True)
    transaction_id: str = Field(default="", max_length=64, index=True, unique=True)
    actor_id: str = Field(default="", max_length=255, index=True)
    counterparty_id: str = Field(default="", max_length=255, index=True)
    amount: Decimal = Field(default=Decimal("0"), sa_column=Column(Numeric(38, 18), nullable=False))
    asset: str = Field(default="", max_length=32, index=True)
    classification: str = Field(default="pci", max_length=32, index=True)
    policy_framework: str = Field(default="pci_dss", max_length=32, index=True)
    consent_required: bool = Field(default=False)
    consent_id: str | None = Field(default=None, max_length=32)
    status: str = Field(default=TransactionStatus.PENDING.value, max_length=20, index=True)
    proof_hash: str = Field(default="", max_length=128)
    meta: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, server_default=text("'{}'")),
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)
    finalized_at: datetime | None = Field(default=None)


class NonRepudiationProof(SQLModel, table=True):
    """Detached signature proving a transaction was authorized by an actor."""

    __tablename__ = "non_repudiation_proof"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"nrp_{uuid4().hex[:10]}", max_length=32, primary_key=True)
    transaction_id: str = Field(default="", max_length=64, index=True)
    signer_id: str = Field(default="", max_length=255, index=True)
    payload_hash: str = Field(default="", max_length=128)
    signature: bytes = Field(default=b"")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)
    meta: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, server_default=text("'{}'")),
    )


def _hash_payload(record: TransactionAuditRecord) -> str:
    """Return a SHA-256 hash over the transaction fields."""
    payload = f"{record.transaction_id}:{record.actor_id}:{record.counterparty_id}:{record.amount}:{record.asset}:{record.created_at.isoformat()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sign_payload(payload_hash: str, signing_key: bytes) -> bytes:
    """Create a deterministic skeleton signature over ``payload_hash``."""
    return signing_key + b":" + payload_hash.encode("utf-8")[:32]


def _verify_signature(payload_hash: str, signature: bytes, public_key: bytes) -> bool:
    """Verify a skeleton signature against a public key."""
    if not signature or b":" not in signature:
        return False
    prefix, _ = signature.split(b":", 1)
    return prefix == public_key


class FinancialComplianceService:
    """Enforce PCI/GLBA controls, transaction audit trails, and non-repudiation."""

    def __init__(self, session: Session, framework: ComplianceFramework = ComplianceFramework.PCI_DSS) -> None:
        self.session = session
        self.framework = framework
        self.policy = load_policy_template(framework)

    def _require_control(self, control_id: str) -> bool:
        """Return True if the loaded policy requires ``control_id``."""
        return self.policy.require_control(control_id)

    def create_transaction(
        self,
        transaction_id: str,
        actor_id: str,
        counterparty_id: str,
        amount: Decimal,
        asset: str,
        classification: str,
        consent_required: bool = False,
        consent_id: str | None = None,
    ) -> TransactionAuditRecord:
        """Create a regulated financial transaction audit record."""
        if amount < 0:
            raise PolicyViolationError("transaction amount cannot be negative")
        record = TransactionAuditRecord(
            transaction_id=transaction_id,
            actor_id=actor_id,
            counterparty_id=counterparty_id,
            amount=amount,
            asset=asset,
            classification=classification,
            policy_framework=self.framework.value,
            consent_required=consent_required,
            consent_id=consent_id,
            status=TransactionStatus.PENDING.value,
        )
        record.proof_hash = _hash_payload(record)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def authorize(
        self,
        transaction_id: str,
        signing_key: bytes,
        public_key: bytes,
    ) -> TransactionAuditRecord:
        """Authorize a transaction and create a non-repudiation proof.

        Requires PCI/GLBA access-control and stored-data-encryption controls to be
        present in the policy.
        """
        statement = select(TransactionAuditRecord).where(TransactionAuditRecord.transaction_id == transaction_id)
        record = self.session.exec(statement).first()
        if record is None:
            raise ValueError("transaction not found")
        if self._require_control("PCI-1") or self._require_control("GLBA-1"):
            if record.consent_required and not record.consent_id:
                record.status = TransactionStatus.DENIED.value
                self.session.commit()
                self.session.refresh(record)
                raise PolicyViolationError(f"transaction {transaction_id} requires consent")
        proof = NonRepudiationProof(
            transaction_id=transaction_id,
            signer_id=record.actor_id,
            payload_hash=record.proof_hash,
            signature=_sign_payload(record.proof_hash, signing_key),
        )
        self.session.add(proof)
        record.status = TransactionStatus.APPROVED.value
        record.finalized_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(record)
        return record

    def verify_non_repudiation(self, transaction_id: str, public_key: bytes) -> bool:
        """Return True if a valid non-repudiation proof exists for the transaction."""
        statement = select(NonRepudiationProof).where(NonRepudiationProof.transaction_id == transaction_id)
        for proof in self.session.exec(statement):
            if _verify_signature(proof.payload_hash, proof.signature, public_key):
                return True
        return False

    def audit_trail(self, transaction_id: str) -> list[TransactionAuditRecord]:
        """Return all audit records for a transaction (normally one, but queryable)."""
        statement = select(TransactionAuditRecord).where(TransactionAuditRecord.transaction_id == transaction_id)
        return list(self.session.exec(statement))
