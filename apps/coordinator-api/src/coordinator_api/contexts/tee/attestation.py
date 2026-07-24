"""TEE remote attestation domain and service for Agent B v0.14.1 B1."""

from __future__ import annotations

import base64
import binascii
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import JSON, Column, text
from sqlmodel import Field, Session, SQLModel, select


class TEEAttestationStatus(StrEnum):
    """Lifecycle status of a TEE attestation quote."""

    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    EXPIRED = "expired"


class EnclaveStatus(StrEnum):
    """Lifecycle status of a registered enclave."""

    PENDING = "pending"
    ACTIVE = "active"
    REVOKED = "revoked"


class TEEAttestation(SQLModel, table=True):
    """Stored result of a remote attestation verification."""

    __tablename__ = "tee_attestation"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"ta_{uuid4().hex[:10]}", max_length=32, primary_key=True)
    enclave_id: str = Field(default="", max_length=255, index=True)
    quote: str = Field(default="")
    measurement: str = Field(default="", max_length=255, index=True)
    status: str = Field(default=TEEAttestationStatus.PENDING.value, max_length=20, index=True)
    meta: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, server_default=text("'{}'")),
    )
    verified_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)


class EnclaveIdentity(SQLModel, table=True):
    """Registered identity for a TEE enclave."""

    __tablename__ = "enclave_identity"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"ei_{uuid4().hex[:10]}", max_length=32, primary_key=True)
    enclave_id: str = Field(default="", max_length=255, index=True)
    public_key: str = Field(default="", max_length=1024)
    agent_id: str = Field(default="", max_length=255, index=True)
    status: str = Field(default=EnclaveStatus.PENDING.value, max_length=20, index=True)
    meta: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, server_default=text("'{}'")),
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)


class TEEAttestationService:
    """Service that records and verifies remote attestation quotes.

    ponytail: This is a skeleton verifier. Real TEE verification needs a
    platform-specific quote library (SGX/V2/TDX) and a policy engine.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def _validate_quote(self, quote: str) -> bool:
        """Return True for a well-formed base64-encoded quote."""
        try:
            decoded = base64.b64decode(quote, validate=True)
        except (binascii.Error, ValueError):
            return False
        return len(decoded) >= 32

    def verify_and_store(self, enclave_id: str, quote: str, measurement: str = "") -> TEEAttestation:
        """Verify a quote and persist the result."""
        is_valid = self._validate_quote(quote)
        attestation = TEEAttestation(
            enclave_id=enclave_id,
            quote=quote,
            measurement=measurement,
            status=TEEAttestationStatus.VERIFIED.value if is_valid else TEEAttestationStatus.REJECTED.value,
            verified_at=datetime.now(UTC) if is_valid else None,
        )
        self.session.add(attestation)
        self.session.commit()
        self.session.refresh(attestation)
        return attestation

    def get_attestation(self, attestation_id: str) -> TEEAttestation | None:
        """Fetch a stored attestation by id."""
        return self.session.get(TEEAttestation, attestation_id)

    def register_enclave(
        self,
        enclave_id: str,
        public_key: str,
        agent_id: str = "",
        status: EnclaveStatus = EnclaveStatus.ACTIVE,
    ) -> EnclaveIdentity:
        """Register or update an enclave identity."""
        statement = select(EnclaveIdentity).where(EnclaveIdentity.enclave_id == enclave_id)
        identity = self.session.exec(statement).first()
        if identity is None:
            identity = EnclaveIdentity(enclave_id=enclave_id)
            self.session.add(identity)
        identity.public_key = public_key
        identity.agent_id = agent_id
        identity.status = status.value if isinstance(status, EnclaveStatus) else status
        identity.updated_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(identity)
        return identity

    def get_enclave(self, enclave_id: str) -> EnclaveIdentity | None:
        """Fetch an enclave identity by enclave_id."""
        statement = select(EnclaveIdentity).where(EnclaveIdentity.enclave_id == enclave_id)
        return self.session.exec(statement).first()
