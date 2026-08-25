"""V24: what the TEE attestation path is willing to trust.

Two problems, one enclosing the other -- the same shape as V23-24 on the ZK
side.

First, ``QuoteGenerator._resolve_signing_key`` derived its Ed25519 seed from
``enclave_id`` alone when no explicit key was supplied -- and ``enclave_id``
is data the caller controls (it travels in job constraints, and in the quote
itself). Anyone who knew or guessed an enclave_id could compute the exact
signing key a legitimate quote for it would use, and sign their own.

Second, and independent of the first: ``AttestationVerifier.verify()`` never
checked a quote's public key against anything external. It only checked that
the signature matched the public key carried in the quote itself, which is
true for *any* keypair -- deterministic or freshly random, legitimate or
forged. The already-built ``EnclaveIdentity`` registry (``POST
/v1/tee/enclaves``) existed to pin a quote's key to a previously-registered
one, but ``_validate_quote`` never consulted it, and registration itself had
no ownership check -- any authenticated caller could overwrite anyone's
registration.

Fixing the key derivation alone would not have closed the hole: a forger
does not need to guess a key when nothing checks whether it is the right key
at all.
"""

from __future__ import annotations

import base64

from coordinator_api.contexts.tee.attestation import (
    EnclaveOwnershipError,
    EnclaveStatus,
    TEEAttestationService,
    TEEAttestationStatus,
)

from aitbc.tee import AttestationVerifier, QuoteGenerator


class TestSigningKeyIsNotDerivable:
    """V24 part one: the signing key must not be computable from public data."""

    def test_two_generators_same_enclave_id_get_different_keys(self):
        quote_a = QuoteGenerator("shared-enclave").generate(quote_id="a", enclave_id="shared-enclave", measurement="m")
        quote_b = QuoteGenerator("shared-enclave").generate(quote_id="b", enclave_id="shared-enclave", measurement="m")
        assert quote_a.public_key != quote_b.public_key

    def test_explicit_signing_key_still_gives_a_stable_identity(self):
        key = b"a fixed 32-byte secret only I hold"
        quote_a = QuoteGenerator("enc-1", signing_key=key).generate(quote_id="a", enclave_id="enc-1", measurement="m")
        quote_b = QuoteGenerator("enc-1", signing_key=key).generate(quote_id="b", enclave_id="enc-1", measurement="m")
        assert quote_a.public_key == quote_b.public_key


class TestVerifierPinsToKnownKey:
    """V24 part two: verification must be able to pin to a registered key, not just self-consistency."""

    def test_self_consistent_forged_quote_passes_without_pinning(self):
        # The honest residual baseline: an enclave_id with no registration is
        # still only as trustworthy as it always was.
        forged = QuoteGenerator("victim-enclave", signing_key=b"attacker-controlled-key-material").generate(
            quote_id="q", enclave_id="victim-enclave", measurement="m"
        )
        assert AttestationVerifier(require_signature=True).verify(forged) is True

    def test_same_forged_quote_fails_against_a_pinned_key(self):
        real_key = b"the-legitimate-enclave-owner-key"
        real_pub = (
            QuoteGenerator(signing_key=real_key)
            .generate(quote_id="r", enclave_id="victim-enclave", measurement="m")
            .public_key
        )
        forged = QuoteGenerator("victim-enclave", signing_key=b"attacker-controlled-key-material").generate(
            quote_id="q", enclave_id="victim-enclave", measurement="m"
        )
        assert AttestationVerifier(require_signature=True).verify(forged, known_public_key=real_pub) is False


class TestCoordinatorPinsToRegisteredIdentity:
    """V24: the coordinator service wires the registry into _validate_quote."""

    def test_unregistered_enclave_is_self_consistent_not_verified(self, db_session):
        service = TEEAttestationService(db_session)
        quote = QuoteGenerator("no-registration").generate(
            quote_id="q", enclave_id="no-registration", measurement="no-registration"
        )
        attestation = service.verify_and_store("no-registration", quote.to_base64(), measurement="no-registration")
        assert attestation.status == TEEAttestationStatus.SELF_CONSISTENT.value
        assert attestation.registered is False

    def test_unregistered_enclave_rejected_when_require_registered(self, db_session):
        service = TEEAttestationService(db_session)
        quote = QuoteGenerator("no-registration").generate(
            quote_id="q", enclave_id="no-registration", measurement="no-registration"
        )
        attestation = service.verify_and_store(
            "no-registration",
            quote.to_base64(),
            measurement="no-registration",
            require_registered=True,
        )
        assert attestation.status == TEEAttestationStatus.REJECTED.value
        assert attestation.registered is False

    def test_registered_enclave_rejects_a_quote_from_a_different_key(self, db_session):
        service = TEEAttestationService(db_session)
        real_key = b"the-real-enclave-owner-signing-key"
        real_pub = (
            QuoteGenerator(signing_key=real_key)
            .generate(quote_id="setup", enclave_id="pinned-enclave", measurement="pinned-enclave")
            .public_key
        )
        service.register_enclave("pinned-enclave", base64.b64encode(real_pub).decode("ascii"), "owner-1")

        impostor = QuoteGenerator("pinned-enclave", signing_key=b"someone-elses-key-entirely").generate(
            quote_id="q", enclave_id="pinned-enclave", measurement="pinned-enclave"
        )
        attestation = service.verify_and_store("pinned-enclave", impostor.to_base64(), measurement="pinned-enclave")
        assert attestation.status == TEEAttestationStatus.REJECTED.value

    def test_registered_enclave_accepts_a_quote_from_the_registered_key(self, db_session):
        service = TEEAttestationService(db_session)
        real_key = b"the-real-enclave-owner-signing-key-2"
        real_pub = (
            QuoteGenerator(signing_key=real_key)
            .generate(quote_id="setup", enclave_id="pinned-enclave-2", measurement="pinned-enclave-2")
            .public_key
        )
        service.register_enclave("pinned-enclave-2", base64.b64encode(real_pub).decode("ascii"), "owner-1")

        genuine = QuoteGenerator("pinned-enclave-2", signing_key=real_key).generate(
            quote_id="q", enclave_id="pinned-enclave-2", measurement="pinned-enclave-2"
        )
        attestation = service.verify_and_store("pinned-enclave-2", genuine.to_base64(), measurement="pinned-enclave-2")
        assert attestation.status == TEEAttestationStatus.VERIFIED.value
        assert attestation.registered is True

    def test_revoked_enclave_rejects_even_a_correctly_signed_quote(self, db_session):
        service = TEEAttestationService(db_session)
        real_key = b"another-real-enclave-owner-key"
        real_pub = (
            QuoteGenerator(signing_key=real_key)
            .generate(quote_id="setup", enclave_id="revoked-enclave", measurement="revoked-enclave")
            .public_key
        )
        service.register_enclave(
            "revoked-enclave", base64.b64encode(real_pub).decode("ascii"), "owner-1", status=EnclaveStatus.REVOKED
        )
        genuine = QuoteGenerator("revoked-enclave", signing_key=real_key).generate(
            quote_id="q", enclave_id="revoked-enclave", measurement="revoked-enclave"
        )
        attestation = service.verify_and_store("revoked-enclave", genuine.to_base64(), measurement="revoked-enclave")
        assert attestation.status == TEEAttestationStatus.REJECTED.value

    def test_allowed_measurements_reject_unlisted_measurement(self, db_session):
        service = TEEAttestationService(db_session)
        real_key = b"measurement-guarded-key"
        real_pub = (
            QuoteGenerator(signing_key=real_key)
            .generate(quote_id="setup", enclave_id="measured-enclave", measurement="allowed-measurement")
            .public_key
        )
        service.register_enclave(
            "measured-enclave",
            base64.b64encode(real_pub).decode("ascii"),
            "owner-1",
            allowed_measurements=["allowed-measurement"],
        )

        genuine_wrong_measurement = QuoteGenerator("measured-enclave", signing_key=real_key).generate(
            quote_id="q", enclave_id="measured-enclave", measurement="forbidden-measurement"
        )
        attestation = service.verify_and_store(
            "measured-enclave",
            genuine_wrong_measurement.to_base64(),
            measurement="forbidden-measurement",
        )
        assert attestation.status == TEEAttestationStatus.REJECTED.value


class TestEnclaveRegistrationIsOwnerLocked:
    """V24: registering an enclave_id someone else already owns must fail, not overwrite."""

    def test_second_agent_cannot_overwrite_an_existing_registration(self, db_session):
        service = TEEAttestationService(db_session)
        service.register_enclave("contested-enclave", "cGxhY2Vob2xkZXI=", "owner-1")
        try:
            service.register_enclave("contested-enclave", "YXR0YWNrZXI=", "owner-2")
            raised = False
        except EnclaveOwnershipError:
            raised = True
        assert raised is True

    def test_same_agent_can_update_their_own_registration(self, db_session):
        service = TEEAttestationService(db_session)
        service.register_enclave("owned-enclave", "b2xk", "owner-1")
        updated = service.register_enclave("owned-enclave", "bmV3", "owner-1")
        assert updated.public_key == "bmV3"
