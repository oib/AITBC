"""Unit tests for aitbc.tee TEE primitives (v0.14.1 §A1-A3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from aitbc.compute import TEEExecutionStatus, TEETask, TEETaskInput, TEETaskRunner
from aitbc.tee import (
    AttestationQuote,
    AttestationVerifier,
    ChannelState,
    Enclave,
    EnclaveConfig,
    EnclaveStatus,
    KeyProvisioningPolicy,
    QuoteGenerator,
    SealedBlob,
    SessionState,
    TEEChannel,
    TEEError,
    ChannelMessage,
    TEESession,
    load_or_create_signing_key,
    public_key_for_signing_key,
    seal,
    unseal,
    verify_quote,
)


# A1: attestation


def test_quote_generator_and_verifier() -> None:
    generator = QuoteGenerator()
    quote = generator.generate(
        quote_id="q1",
        enclave_id="enc-1",
        measurement="measurement-1",
    )
    assert quote.enclave_id == "enc-1"
    assert quote.measurement == "measurement-1"

    verifier = AttestationVerifier({"measurement-1"})
    assert verifier.verify(quote) is True
    assert verify_quote(quote, {"measurement-1"}) is True
    assert verify_quote(quote, {"measurement-2"}) is False
    assert AttestationVerifier({"measurement-1"}).verify(quote) is True


def test_quote_verifier_rejects_empty_quote() -> None:
    quote = AttestationQuote(
        quote_id="q1",
        enclave_id="enc-1",
        quote_blob=b"",
        measurement="measurement-1",
    )
    verifier = AttestationVerifier({"measurement-1"})
    assert verifier.verify(quote) is False


def test_quote_expires() -> None:
    quote = AttestationQuote(
        quote_id="q1",
        enclave_id="enc-1",
        quote_blob=b"report",
        measurement="measurement-1",
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    assert quote.is_expired() is True
    assert verify_quote(quote, {"measurement-1"}) is False


# A1: enclave


def test_enclave_lifecycle() -> None:
    config = EnclaveConfig(enclave_id="enc-1", image="test-image")
    enclave = Enclave(config=config)
    assert enclave.status == EnclaveStatus.PENDING

    enclave.build()
    assert enclave.status == EnclaveStatus.PENDING

    enclave.launch()
    assert enclave.status == EnclaveStatus.RUNNING

    enclave.teardown()
    assert enclave.status == EnclaveStatus.STOPPED


def test_enclave_launch_without_image_fails() -> None:
    config = EnclaveConfig(enclave_id="enc-1")
    enclave = Enclave(config=config)
    with pytest.raises(TEEError):
        enclave.launch()


# A1: identity


def test_key_provisioning_policy() -> None:
    policy = KeyProvisioningPolicy(
        enclave_id="enc-1",
        allowed_measurements=["measurement-1"],
    )
    assert policy.authorize("measurement-1") is True
    assert policy.authorize("measurement-2") is False


def test_key_provisioning_policy_allows_all_by_default() -> None:
    policy = KeyProvisioningPolicy(enclave_id="enc-1")
    assert policy.authorize("any-measurement") is True


# A2: session and channel


def _x25519_key_pair() -> tuple[bytes, bytes]:
    """Return a raw (private_key, public_key) X25519 pair."""
    private_key = X25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return private_bytes, public_key


def _established_pair() -> tuple[TEESession, TEESession]:
    """Create two sessions with matching X25519 shared secrets."""
    i_priv, i_pub = _x25519_key_pair()
    r_priv, r_pub = _x25519_key_pair()
    initiator = TEESession(
        session_id="s1",
        initiator_id="agent-a",
        responder_id="agent-b",
        initiator_public_key=i_pub,
        responder_public_key=r_pub,
        private_key=i_priv,
    )
    responder = TEESession(
        session_id="s1",
        initiator_id="agent-a",
        responder_id="agent-b",
        initiator_public_key=i_pub,
        responder_public_key=r_pub,
        private_key=r_priv,
    )
    initiator.establish()
    responder.establish()
    assert initiator.shared_secret == responder.shared_secret
    assert initiator.shared_secret != b""
    return initiator, responder


def test_tee_session_establish_and_rotate() -> None:
    initiator, _responder = _established_pair()
    assert initiator.state == SessionState.ESTABLISHED

    first_secret = initiator.shared_secret
    new_public = (
        X25519PrivateKey.generate()
        .public_key()
        .public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    )
    initiator.rotate_key(new_public)
    assert initiator.shared_secret != first_secret


def test_tee_session_replay_nonce() -> None:
    initiator, _responder = _established_pair()
    assert initiator.next_nonce() == 1
    assert initiator.next_nonce() == 2


def test_tee_channel_encode_and_decode() -> None:
    initiator, _responder = _established_pair()
    channel = TEEChannel(channel_id="ch-1", session=initiator, peer_id="agent-b")
    channel.open()
    assert channel.state == ChannelState.OPEN

    message = channel.encode(b"hello")
    assert isinstance(message, ChannelMessage)
    assert message.nonce == 1

    received = channel.decode(message)
    assert received == b"hello"


def test_tee_channel_round_trip_between_sides() -> None:
    """A message encoded by the initiator can be decoded by the responder."""
    initiator, responder = _established_pair()
    initiator_channel = TEEChannel(channel_id="ch-1", session=initiator, peer_id="agent-b")
    initiator_channel.open()
    message = initiator_channel.encode(b"secret payload")

    responder_channel = TEEChannel(channel_id="ch-1", session=responder, peer_id="agent-a")
    responder_channel.open()
    received = responder_channel.decode(message)
    assert received == b"secret payload"


# A3: sealed storage


def test_seal_and_unseal_round_trip() -> None:
    blob = seal(
        blob_id="b1",
        enclave_id="enc-1",
        measurement="measurement-1",
        plaintext=b"secret data",
        secret=b"test-sealing-key",
    )
    assert isinstance(blob, SealedBlob)
    assert blob.ciphertext != b"secret data"

    recovered = unseal(blob, secret=b"test-sealing-key")
    assert recovered == b"secret data"


def test_seal_requires_secret() -> None:
    with pytest.raises(ValueError, match="secret is required"):
        seal(
            blob_id="b1",
            enclave_id="enc-1",
            measurement="measurement-1",
            plaintext=b"secret data",
            secret=b"",
        )


def test_unseal_tampered_blob_fails() -> None:
    blob = seal(
        blob_id="b1",
        enclave_id="enc-1",
        measurement="measurement-1",
        plaintext=b"secret data",
        secret=b"test-sealing-key",
    )
    blob.tag = b"tampered"
    with pytest.raises(TEEError):
        unseal(blob, secret=b"test-sealing-key")


# A3: tee task


def test_tee_task_runner_success() -> None:
    generator = QuoteGenerator()
    quote = generator.generate(
        quote_id="q1",
        enclave_id="enc-1",
        measurement="measurement-1",
    )
    config = EnclaveConfig(enclave_id="enc-1", image="test-image")
    enclave = Enclave(config=config)
    enclave.launch()

    task_input = TEETaskInput(
        task_id="t1",
        agent_id="agent-a",
        payload={"x": 2},
        enclave_id="enc-1",
    )
    task = TEETask(input=task_input)
    task.attest(quote)
    task.bind_enclave(enclave)

    runner = TEETaskRunner()
    result = runner.run(task, lambda inp: {"double": inp.payload["x"] * 2})
    assert result.status == TEEExecutionStatus.COMPLETED
    assert result.output == {"double": 4}


def test_tee_task_runner_requires_attestation() -> None:
    config = EnclaveConfig(enclave_id="enc-1", image="test-image")
    enclave = Enclave(config=config)
    enclave.launch()
    task_input = TEETaskInput(
        task_id="t1",
        agent_id="agent-a",
        payload={},
        enclave_id="enc-1",
    )
    task = TEETask(input=task_input)
    task.bind_enclave(enclave)

    runner = TEETaskRunner()
    with pytest.raises(TEEError):
        runner.run(task, lambda inp: {})


def test_tee_task_runner_requires_running_enclave() -> None:
    generator = QuoteGenerator()
    quote = generator.generate(
        quote_id="q1",
        enclave_id="enc-1",
        measurement="measurement-1",
    )
    task_input = TEETaskInput(
        task_id="t1",
        agent_id="agent-a",
        payload={},
        enclave_id="enc-1",
    )
    task = TEETask(input=task_input)
    task.attest(quote)

    runner = TEETaskRunner()
    with pytest.raises(TEEError):
        runner.run(task, lambda inp: {})


def test_quote_serialization_and_signature() -> None:
    generator = QuoteGenerator("enc-1")
    quote = generator.generate(quote_id="q1", enclave_id="enc-1", measurement="measurement-1")
    assert quote.verify_signature() is True
    quote_b64 = quote.to_base64()
    restored = AttestationQuote.from_base64(quote_b64)
    assert restored.verify_signature() is True
    assert restored.enclave_id == "enc-1"
    assert restored.measurement == "measurement-1"
    assert AttestationVerifier({"measurement-1"}, require_signature=True).verify(restored)


def test_quote_verifier_rejects_tampered_measurement() -> None:
    generator = QuoteGenerator("enc-1")
    quote = generator.generate(quote_id="q1", enclave_id="enc-1", measurement="measurement-1")
    quote.measurement = "measurement-2"
    assert AttestationVerifier({"measurement-2"}, require_signature=True).verify(quote) is False


# Part 4 (2026-08-24): stable-key plumbing for aitbc tee attest / keygen and
# the miner's build_tee_quote, so a caller can give the coordinator a
# public key worth pinning verification to.


def test_load_or_create_signing_key_creates_a_32_byte_file(tmp_path) -> None:
    path = str(tmp_path / "enclave.key")
    key = load_or_create_signing_key(path)
    assert len(key) == 32
    with open(path, "rb") as f:
        assert f.read() == key


def test_load_or_create_signing_key_is_stable_across_calls(tmp_path) -> None:
    path = str(tmp_path / "enclave.key")
    first = load_or_create_signing_key(path)
    second = load_or_create_signing_key(path)
    assert first == second


def test_load_or_create_signing_key_creates_parent_directories(tmp_path) -> None:
    path = str(tmp_path / "nested" / "dir" / "enclave.key")
    key = load_or_create_signing_key(path)
    assert len(key) == 32


def test_load_or_create_signing_key_rejects_wrong_length_file(tmp_path) -> None:
    path = tmp_path / "bad.key"
    path.write_bytes(b"too short")
    with pytest.raises(ValueError):
        load_or_create_signing_key(str(path))


def test_stable_key_file_gives_quotes_a_stable_pinnable_identity(tmp_path) -> None:
    """The point of Part 4: a stable key file lets the *coordinator* pin a key."""
    path = str(tmp_path / "enclave.key")
    key_a = load_or_create_signing_key(path)
    key_b = load_or_create_signing_key(path)
    quote_a = QuoteGenerator("enc-x", signing_key=key_a).generate(quote_id="a", enclave_id="enc-x", measurement="m")
    quote_b = QuoteGenerator("enc-x", signing_key=key_b).generate(quote_id="b", enclave_id="enc-x", measurement="m")
    assert quote_a.public_key == quote_b.public_key


def test_public_key_for_signing_key_matches_what_a_quote_actually_signs_with() -> None:
    key = b"a fixed 32-byte secret only I hold"
    predicted = public_key_for_signing_key(key)
    quote = QuoteGenerator("enc-y", signing_key=key).generate(quote_id="q", enclave_id="enc-y", measurement="m")
    assert predicted == quote.public_key
