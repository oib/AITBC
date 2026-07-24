"""Unit tests for aitbc.tee TEE primitives (v0.14.1 §A1-A3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

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
    TEEMessage,
    TEESession,
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


def test_tee_session_establish_and_rotate() -> None:
    session = TEESession(
        session_id="s1",
        initiator_id="agent-a",
        responder_id="agent-b",
        initiator_public_key=b"initiator-pubkey",
        responder_public_key=b"responder-pubkey",
    )
    assert session.state == SessionState.PENDING

    session.establish()
    assert session.state == SessionState.ESTABLISHED
    assert session.shared_secret != b""

    first_secret = session.shared_secret
    session.rotate_key(b"new-ephemeral")
    assert session.shared_secret != first_secret


def test_tee_session_replay_nonce() -> None:
    session = TEESession(
        session_id="s1",
        initiator_id="agent-a",
        responder_id="agent-b",
        initiator_public_key=b"initiator-pubkey",
        responder_public_key=b"responder-pubkey",
    )
    session.establish()
    assert session.next_nonce() == 1
    assert session.next_nonce() == 2


def test_tee_channel_send_and_receive() -> None:
    session = TEESession(
        session_id="s1",
        initiator_id="agent-a",
        responder_id="agent-b",
        initiator_public_key=b"initiator-pubkey",
        responder_public_key=b"responder-pubkey",
    )
    session.establish()
    channel = TEEChannel(channel_id="ch-1", session=session, peer_id="agent-b")
    channel.open()
    assert channel.state == ChannelState.OPEN

    message = channel.send(b"hello")
    assert isinstance(message, TEEMessage)
    assert message.nonce == 1

    received = channel.receive(message)
    assert received == b"hello"


# A3: sealed storage


def test_seal_and_unseal_round_trip() -> None:
    blob = seal(
        blob_id="b1",
        enclave_id="enc-1",
        measurement="measurement-1",
        plaintext=b"secret data",
    )
    assert isinstance(blob, SealedBlob)
    assert blob.ciphertext != b"secret data"

    recovered = unseal(blob)
    assert recovered == b"secret data"


def test_unseal_tampered_blob_fails() -> None:
    blob = seal(
        blob_id="b1",
        enclave_id="enc-1",
        measurement="measurement-1",
        plaintext=b"secret data",
    )
    blob.tag = b"tampered"
    with pytest.raises(TEEError):
        unseal(blob)


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
