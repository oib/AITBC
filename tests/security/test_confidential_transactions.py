"""Security tests for AITBC confidential transactions.

Rewritten because the previous version had never executed. It imported ``ViewingKey`` from
``coordinator_api.models.confidential`` and ``ConfidentialTransactionService`` from
``coordinator_api.services.confidential_service``; neither name exists, so the module-level
``ImportError`` set ``CONFIDENTIAL_AVAILABLE = False`` and every one of its three test classes
was ``skipif``-ed away. 21 test functions, ~700 lines, zero of them run — for long enough that
four cryptographic defects accumulated in the code they nominally covered (see V23-19a).

Repairing the imports was not possible: of the ten methods those tests called on the service,
nine do not exist anywhere in the repository, and they also patched
``apps.coordinator_api.src.app.services.{hsm,mpc,pqc,aml,deniable,retention}_service`` — a
package path this repository has never had. The file described a system that was designed and
not built: HSM integration, multi-party computation, deniable encryption, post-quantum
signatures, viewing keys, regulatory reporting, retention policies.

What does exist is the X25519 + AES-256-GCM envelope encryption in
``coordinator_api.contexts.security.services``: ``EncryptionService``, ``KeyManager`` with
``FileKeyStorage``, and ``AccessController``. That is what these tests cover, end to end,
against real keys on a real temporary keystore rather than mocks.

Two things deliberately not asserted here, because they are not true and pretending otherwise
is how the previous file came to exist:

* **There is no forward secrecy.** Participant keys are long-lived X25519 keys held in the
  keystore; a compromised private key reads every past payload addressed to it. The old file
  had a ``test_forward_secrecy`` that generated its own ephemeral keys inline and asserted
  they round-tripped, which tests ``cryptography``, not this service.
* **Timing side channels are not covered.** The old file had three tests that measured
  wall-clock durations and asserted correlations below a threshold. Under load those measure
  the CI runner, not the code.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from coordinator_api.contexts.security.services.access_control import (
    AccessController,
    ParticipantRole,
    PolicyStore,
)
from coordinator_api.contexts.security.services.encryption import (
    DecryptionError,
    EncryptedData,
    EncryptionError,
    EncryptionService,
)
from coordinator_api.contexts.security.services.key_management import (
    FileKeyStorage,
    KeyManager,
    KeyManagementError,
)
from coordinator_api.schemas import ConfidentialAccessRequest

pytestmark = pytest.mark.security

SENSITIVE = {"amount": "1000000", "asset": "AIT", "settlement_details": {"iban": "DE89370400440532013000"}}


# --------------------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------------------


@pytest.fixture
async def key_manager(tmp_path):
    """A KeyManager over a real temporary keystore, with alice and bob enrolled."""
    manager = KeyManager(FileKeyStorage(str(tmp_path / "keys")))
    for participant in ("alice", "bob"):
        await manager.generate_key_pair(participant)
    return manager


@pytest.fixture
def service(key_manager):
    return EncryptionService(key_manager)


@pytest.fixture
def audit_secret(monkeypatch):
    """`create_audit_authorization` signs with settings.hmac_secret or settings.jwt_secret."""
    from coordinator_api.contexts.security.services import key_management

    monkeypatch.setattr(key_management.settings, "hmac_secret", "test-audit-hmac-secret", raising=False)
    return "test-audit-hmac-secret"


# --------------------------------------------------------------------------------------
# Confidentiality
# --------------------------------------------------------------------------------------


async def test_ciphertext_does_not_contain_the_plaintext(service):
    encrypted = service.encrypt(SENSITIVE, participants=["alice"])
    blob = encrypted.ciphertext + encrypted.tag + encrypted.nonce
    assert b"1000000" not in blob
    assert b"DE89370400440532013000" not in blob
    assert b"AIT" not in blob


async def test_participant_round_trip(service):
    encrypted = service.encrypt(SENSITIVE, participants=["alice"])
    assert service.decrypt(encrypted, "alice") == SENSITIVE


async def test_each_participant_decrypts_independently(service):
    encrypted = service.encrypt(SENSITIVE, participants=["alice", "bob"])
    assert service.decrypt(encrypted, "alice") == SENSITIVE
    assert service.decrypt(encrypted, "bob") == SENSITIVE
    assert encrypted.encrypted_keys["alice"] != encrypted.encrypted_keys["bob"]


async def test_non_participant_is_refused(service, key_manager):
    encrypted = service.encrypt(SENSITIVE, participants=["alice"])
    await key_manager.generate_key_pair("mallory")
    with pytest.raises(DecryptionError):
        service.decrypt(encrypted, "mallory")


async def test_two_encryptions_of_the_same_data_differ(service):
    """A fresh DEK and nonce per call, so identical plaintext is not recognisable."""
    a = service.encrypt(SENSITIVE, participants=["alice"])
    b = service.encrypt(SENSITIVE, participants=["alice"])
    assert a.ciphertext != b.ciphertext
    assert a.nonce != b.nonce


async def test_tampered_ciphertext_is_rejected(service):
    """AES-GCM is authenticated; a flipped byte must fail rather than decrypt to garbage."""
    encrypted = service.encrypt(SENSITIVE, participants=["alice"])
    flipped = bytearray(encrypted.ciphertext)
    flipped[0] ^= 0x01
    encrypted.ciphertext = bytes(flipped)
    with pytest.raises(DecryptionError):
        service.decrypt(encrypted, "alice")


async def test_tampered_tag_is_rejected(service):
    encrypted = service.encrypt(SENSITIVE, participants=["alice"])
    flipped = bytearray(encrypted.tag)
    flipped[-1] ^= 0xFF
    encrypted.tag = bytes(flipped)
    with pytest.raises(DecryptionError):
        service.decrypt(encrypted, "alice")


async def test_encrypting_for_nobody_is_refused(service):
    with pytest.raises(EncryptionError):
        service.encrypt(SENSITIVE, participants=[])


async def test_unknown_participant_is_refused_rather_than_silently_dropped(service):
    """Regression: this used to succeed.

    ``encrypt`` caught the missing-key error per participant, logged it and continued, so a
    call naming one unregistered participant returned a payload whose only usable key was the
    audit escrow's -- reported as success, unreadable by the person it was addressed to.
    """
    with pytest.raises(EncryptionError, match="No usable encryption key"):
        service.encrypt(SENSITIVE, participants=["nobody"])


async def test_one_unknown_participant_fails_the_whole_call(service):
    with pytest.raises(EncryptionError, match="nobody"):
        service.encrypt(SENSITIVE, participants=["alice", "nobody"])


# --------------------------------------------------------------------------------------
# Audit escrow
# --------------------------------------------------------------------------------------


async def test_audit_key_is_included_by_default(service):
    encrypted = service.encrypt(SENSITIVE, participants=["alice"])
    assert "audit" in encrypted.encrypted_keys


async def test_audit_key_can_be_omitted(service):
    encrypted = service.encrypt(SENSITIVE, participants=["alice"], include_audit=False)
    assert "audit" not in encrypted.encrypted_keys
    assert sorted(encrypted.encrypted_keys) == ["alice"]


async def test_audit_decrypt_with_valid_authorization(service, key_manager, audit_secret):
    encrypted = service.encrypt(SENSITIVE, participants=["alice"])
    auth = await key_manager.create_audit_authorization(issuer="regulator-1", purpose="audit")
    assert service.audit_decrypt(encrypted, auth) == SENSITIVE


async def test_audit_decrypt_rejects_a_forged_authorization(service, audit_secret):
    encrypted = service.encrypt(SENSITIVE, participants=["alice"])
    with pytest.raises(Exception):  # noqa: B017 - service raises DecryptionError or KeyManagementError
        service.audit_decrypt(encrypted, "bm90LWEtcmVhbC10b2tlbg==")


async def test_audit_decrypt_rejects_an_authorization_signed_with_another_secret(
    service, key_manager, audit_secret, monkeypatch
):
    """Re-signing the payload under a different secret must not be accepted."""
    encrypted = service.encrypt(SENSITIVE, participants=["alice"])
    auth = await key_manager.create_audit_authorization(issuer="regulator-1", purpose="audit")

    import base64
    import hmac

    payload = json.loads(base64.b64decode(auth))
    payload.pop("signature")
    payload["issuer"] = "attacker"
    payload["signature"] = hmac.new(b"a-different-secret", json.dumps(payload, sort_keys=True).encode(), "sha256").hexdigest()
    forged = base64.b64encode(json.dumps(payload, sort_keys=True).encode()).decode()

    with pytest.raises(Exception):  # noqa: B017
        service.audit_decrypt(encrypted, forged)


async def test_audit_authorization_requires_a_configured_secret(key_manager, monkeypatch):
    from coordinator_api.contexts.security.services import key_management

    monkeypatch.setattr(key_management.settings, "hmac_secret", "", raising=False)
    monkeypatch.setattr(key_management.settings, "jwt_secret", "", raising=False)
    with pytest.raises(KeyManagementError):
        await key_manager.create_audit_authorization(issuer="regulator-1", purpose="audit")


# --------------------------------------------------------------------------------------
# Key lifecycle
# --------------------------------------------------------------------------------------


async def test_generated_keys_are_distinct_per_participant(key_manager):
    assert key_manager.get_public_key("alice").public_bytes_raw() != key_manager.get_public_key("bob").public_bytes_raw()


async def test_rotation_raises_not_implemented(key_manager):
    """Rotation cannot currently succeed, and the test says so rather than assuming.

    ``_reencrypt_transactions`` raises ``NotImplementedError``. That now propagates: the
    router has an ``except NotImplementedError -> 501`` arm which could never fire while
    ``rotate_keys`` wrapped it as ``KeyManagementError``, so the endpoint answered 400 and
    put the internal message in ``detail``.
    """
    with pytest.raises(NotImplementedError):
        await key_manager.rotate_keys("alice")


async def test_failed_rotation_leaves_the_key_intact(service, key_manager):
    """Regression: a failed rotation used to destroy the key anyway.

    The rollback restored ``new_key_pair.version`` and then stored ``new_key_pair`` -- the
    version number went back, the key *material* did not. So a rotation that reported
    ``KeyManagementError`` to its caller had already replaced the participant's key and
    permanently orphaned every payload encrypted under the old one. Since re-encryption is
    unimplemented, this was the only path rotation ever took.
    """
    encrypted = service.encrypt(SENSITIVE, participants=["alice"])
    before = key_manager.get_public_key("alice").public_bytes_raw()

    with pytest.raises(NotImplementedError):
        await key_manager.rotate_keys("alice")

    assert key_manager.get_public_key("alice").public_bytes_raw() == before
    assert service.decrypt(encrypted, "alice") == SENSITIVE


async def test_revocation_removes_access(service, key_manager):
    encrypted = service.encrypt(SENSITIVE, participants=["alice"])
    assert await key_manager.revoke_keys("alice", reason="compromised") is True
    with pytest.raises(DecryptionError):
        service.decrypt(encrypted, "alice")


async def test_list_participants_reports_enrolled_keys(key_manager):
    assert set(await key_manager.list_participants()) >= {"alice", "bob"}


# --------------------------------------------------------------------------------------
# Serialisation
# --------------------------------------------------------------------------------------


async def test_encrypted_data_survives_a_dict_round_trip(service):
    encrypted = service.encrypt(SENSITIVE, participants=["alice"])
    restored = EncryptedData.from_dict(encrypted.to_dict())
    assert service.decrypt(restored, "alice") == SENSITIVE


async def test_to_dict_does_not_leak_plaintext(service):
    encrypted = service.encrypt(SENSITIVE, participants=["alice"])
    blob = json.dumps(encrypted.to_dict())
    assert "1000000" not in blob
    assert "DE89370400440532013000" not in blob


# --------------------------------------------------------------------------------------
# Access control
# --------------------------------------------------------------------------------------


@pytest.fixture
def controller():
    return AccessController(PolicyStore())


def _request(requester: str, transaction_id: str = "tx-1", purpose: str = "settlement"):
    return ConfidentialAccessRequest(transaction_id=transaction_id, requester=requester, purpose=purpose)


async def test_client_may_read_its_own_transaction(controller):
    assert controller.verify_access(_request("client-456")) is True


async def test_unknown_requester_is_denied(controller):
    """Participant roles are resolved from the id prefix; anything else has no role."""
    assert controller.verify_access(_request("somebody-else")) is False


async def test_unknown_transaction_is_denied(controller):
    assert controller.verify_access(_request("client-456", transaction_id="nope-1")) is False


async def test_miner_is_denied_a_purpose_its_role_does_not_grant(controller):
    assert controller.verify_access(_request("miner-789", purpose="audit")) is False


async def test_policy_store_exposes_the_default_policies(controller):
    policies = controller.policy_store.list_policies()
    assert {"client_own_data", "miner_assigned_data", "coordinator_full", "auditor_compliance"} <= set(policies)


async def test_roles_have_distinct_permission_sets(controller):
    client = controller.policy_store.get_role_permissions(ParticipantRole.CLIENT)
    auditor = controller.policy_store.get_role_permissions(ParticipantRole.AUDITOR)
    assert client != auditor


async def test_auditor_compliance_policy_carries_a_retention_window(controller):
    policy = controller.policy_store.get_policy("auditor_compliance")
    assert policy["time_restrictions"]["retention_days"] == 2555


async def test_retention_window_is_actually_enforced(controller):
    """Regression: this check could not fail.

    It read ``transaction["timestamp"]``, a key ``_get_transaction`` never sets, so the
    ``datetime.now(UTC)`` default fired on every call and the expiry was always
    ``now + retention``. Every role passed for every transaction, however old.
    """
    stale = {"created_at": (datetime.now(UTC) - timedelta(days=3000)).isoformat()}
    fresh = {"created_at": datetime.now(UTC).isoformat()}

    assert controller._check_retention_period(fresh, "auditor") is True
    assert controller._check_retention_period(stale, "auditor") is False  # 1825-day window
    assert controller._check_retention_period(stale, "regulator") is False  # 2555-day window
    assert controller._check_retention_period(stale, "coordinator") is True  # 3650-day window


async def test_retention_window_differs_by_role(controller):
    two_years_ago = {"created_at": (datetime.now(UTC) - timedelta(days=730)).isoformat()}
    assert controller._check_retention_period(two_years_ago, "auditor") is True
    assert controller._check_retention_period(two_years_ago, None) is False  # 365-day default
