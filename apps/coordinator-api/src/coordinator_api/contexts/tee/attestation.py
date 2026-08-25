"""TEE remote attestation domain and service for Agent B v0.14.1 B1."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import JSON, Boolean, Column, text
from sqlmodel import Field, Session, SQLModel, select

from aitbc.tee.attestation import AttestationQuote, AttestationVerifier


class TEEAttestationStatus(StrEnum):
    """Lifecycle status of a TEE attestation quote."""

    PENDING = "pending"
    VERIFIED = "verified"
    SELF_CONSISTENT = "self_consistent"
    REJECTED = "rejected"
    EXPIRED = "expired"


class EnclaveStatus(StrEnum):
    """Lifecycle status of a registered enclave."""

    PENDING = "pending"
    ACTIVE = "active"
    REVOKED = "revoked"


class EnclaveOwnershipError(Exception):
    """Raised when a caller tries to register/overwrite another agent's enclave identity.

    Security fix (2026-08-24): ``register_enclave`` used to upsert
    unconditionally, so any caller could re-register (and silently steal)
    any ``enclave_id`` someone else already claimed -- which would have
    defeated registry-pinned verification the moment it existed, since
    pinning is only as good as who is allowed to set the pin.
    """


@dataclass
class QuoteValidationResult:
    """Result of ``_validate_quote``."""

    valid: bool
    registered: bool
    reason: str | None = None


class TEEAttestation(SQLModel, table=True):
    """Stored result of a remote attestation verification."""

    __tablename__ = "tee_attestation"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"ta_{uuid4().hex[:10]}", max_length=32, primary_key=True)
    enclave_id: str = Field(default="", max_length=255, index=True)
    quote: str = Field(default="")
    measurement: str = Field(default="", max_length=255, index=True)
    status: str = Field(default=TEEAttestationStatus.PENDING.value, max_length=20, index=True)
    registered: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, server_default=text("false")))
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
    allowed_measurements: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False, server_default=text("'[]'")),
    )
    meta: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, server_default=text("'{}'")),
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)


class TEEAttestationService:
    """Service that records and verifies remote attestation quotes.

    v0.14.4: Quotes are verified against pre-registered ``EnclaveIdentity``
    rows when one exists for the enclave_id. The quote's embedded public key
    must match the registered public key, and the quote's measurement must be
    on the enclave's allowlist. Unregistered quotes are still recorded but are
    marked ``self_consistent`` rather than ``verified``; callers that need a
    real trust root (e.g. escrow release) must request ``require_registered``.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def _validate_quote(
        self,
        quote_b64: str,
        expected_measurement: str,
        expected_enclave_id: str,
        *,
        require_registered: bool = False,
    ) -> QuoteValidationResult:
        """Return a QuoteValidationResult for a quote.

        Expects ``quote_b64`` to be the base64-encoded JSON representation of
        an ``AttestationQuote``. Legacy raw quote blobs fail closed.
        """
        try:
            quote = AttestationQuote.from_base64(quote_b64)
        except (binascii.Error, ValueError, KeyError, TypeError):
            return QuoteValidationResult(False, False, "unparseable")

        if expected_enclave_id and quote.enclave_id != expected_enclave_id:
            return QuoteValidationResult(False, False, "enclave_id_mismatch")

        known_public_key: bytes | None = None
        allowed_measurements: set[str] | None = None
        identity = self.get_enclave(expected_enclave_id) if expected_enclave_id else None
        if identity is not None:
            if identity.status == EnclaveStatus.REVOKED.value:
                return QuoteValidationResult(False, False, "revoked")
            if identity.public_key:
                try:
                    known_public_key = base64.b64decode(identity.public_key)
                except (binascii.Error, ValueError):
                    return QuoteValidationResult(False, False, "invalid_registered_public_key")
            if identity.allowed_measurements:
                allowed_measurements = set(identity.allowed_measurements)
            else:
                # No explicit allowlist: the expected measurement itself is the
                # only allowed value, so a registered enclave cannot be reused
                # for a measurement the operator has not named.
                allowed_measurements = {expected_measurement} if expected_measurement else None

        expected = expected_measurement or expected_enclave_id
        verifier = AttestationVerifier(allowed_measurements=allowed_measurements, require_signature=True)
        passes = verifier.verify(
            quote,
            expected_measurement=expected or None,
            known_public_key=known_public_key,
        )
        if not passes:
            return QuoteValidationResult(False, False, "signature_or_measurement_failed")

        if identity is not None:
            return QuoteValidationResult(True, True, "registered")

        if require_registered:
            return QuoteValidationResult(False, False, "unregistered")

        return QuoteValidationResult(True, False, "self_consistent")

    def verify_and_store(
        self,
        enclave_id: str,
        quote: str,
        measurement: str = "",
        *,
        require_registered: bool = False,
    ) -> TEEAttestation:
        """Verify a quote and persist the result."""
        expected_measurement = measurement or enclave_id
        result = self._validate_quote(quote, expected_measurement, enclave_id, require_registered=require_registered)
        if result.valid and result.registered:
            status = TEEAttestationStatus.VERIFIED.value
        elif result.valid:
            status = TEEAttestationStatus.SELF_CONSISTENT.value
        else:
            status = TEEAttestationStatus.REJECTED.value
        attestation = TEEAttestation(
            enclave_id=enclave_id,
            quote=quote,
            measurement=expected_measurement,
            status=status,
            registered=result.registered,
            verified_at=datetime.now(UTC) if result.valid else None,
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
        *,
        allowed_measurements: list[str] | None = None,
    ) -> EnclaveIdentity:
        """Register or update an enclave identity.

        Registration is owner-locked: once an enclave_id has been registered
        with a given ``agent_id``, only that same ``agent_id`` may update it.
        The ``allowed_measurements`` list restricts which quote measurements
        this enclave may attest; if empty, the expected measurement passed at
        verification time is the only allowed value.
        """
        statement = select(EnclaveIdentity).where(EnclaveIdentity.enclave_id == enclave_id)
        identity = self.session.exec(statement).first()
        if identity is None:
            identity = EnclaveIdentity(enclave_id=enclave_id)
            self.session.add(identity)
        elif identity.agent_id and agent_id and identity.agent_id != agent_id:
            raise EnclaveOwnershipError(f"enclave_id {enclave_id!r} is already registered by a different agent")
        identity.public_key = public_key
        identity.agent_id = agent_id
        identity.status = status.value if isinstance(status, EnclaveStatus) else status
        if allowed_measurements is not None:
            identity.allowed_measurements = list(allowed_measurements)
        identity.updated_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(identity)
        return identity

    def get_enclave(self, enclave_id: str) -> EnclaveIdentity | None:
        """Fetch an enclave identity by enclave_id."""
        statement = select(EnclaveIdentity).where(EnclaveIdentity.enclave_id == enclave_id)
        return self.session.exec(statement).first()
