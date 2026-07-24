"""Unit tests for v0.14.2 Agent A TEE deliverables."""

from __future__ import annotations

from aitbc.agent_economics import (
    ConfidentialPayment,
    settle_payment,
    validate_payment,
)
from aitbc.tee import (
    AttestationQuote,
    DualVerificationPolicy,
    TEEBenchmark,
    VerificationMode,
    ZKProof,
    verify_with_policy,
    verify_with_result,
)
from aitbc.tee.errors import TEEError
from aitbc.wallet import ConfidentialWallet


def test_dual_verification_tee_only() -> None:
    quote = AttestationQuote(
        quote_id="q1",
        enclave_id="enc-1",
        quote_blob=b"quote",
        measurement="m-1",
    )
    policy = DualVerificationPolicy(
        mode=VerificationMode.TEE_ONLY,
        allowed_measurements={"m-1"},
    )
    assert verify_with_policy(policy, quote, None) is True


def test_dual_verification_zk_only() -> None:
    zk = ZKProof(proof_id="zk-1", verified=True)
    policy = DualVerificationPolicy(mode=VerificationMode.ZK_ONLY)
    assert verify_with_policy(policy, None, zk) is True


def test_dual_verification_both_requires_both() -> None:
    quote = AttestationQuote(
        quote_id="q1",
        enclave_id="enc-1",
        quote_blob=b"quote",
        measurement="m-1",
    )
    zk = ZKProof(proof_id="zk-1", verified=True)
    policy = DualVerificationPolicy(
        mode=VerificationMode.BOTH,
        allowed_measurements={"m-1"},
    )
    assert verify_with_policy(policy, quote, zk) is True


def test_dual_verification_both_fails_missing_zk() -> None:
    quote = AttestationQuote(
        quote_id="q1",
        enclave_id="enc-1",
        quote_blob=b"quote",
        measurement="m-1",
    )
    policy = DualVerificationPolicy(
        mode=VerificationMode.BOTH,
        allowed_measurements={"m-1"},
    )
    assert verify_with_policy(policy, quote, None) is False


def test_dual_verification_result_details() -> None:
    quote = AttestationQuote(
        quote_id="q1",
        enclave_id="enc-1",
        quote_blob=b"quote",
        measurement="m-1",
    )
    policy = DualVerificationPolicy(mode=VerificationMode.TEE_ONLY)
    result = verify_with_result(policy, quote, None)
    assert result.verified is True
    assert result.tee_ok is True
    assert result.zk_ok is False


def test_dual_verification_zk_only_missing_proof_raises() -> None:
    policy = DualVerificationPolicy(mode=VerificationMode.ZK_ONLY)
    try:
        policy.verify(None, None)
        assert False, "expected TEEError"
    except TEEError:
        pass


def test_tee_benchmark_runs_and_summarizes() -> None:
    benchmark = TEEBenchmark(name="test")
    result = benchmark.run("noop", lambda: None)
    assert result.name == "noop"
    assert result.latency_ms >= 0
    summary = benchmark.summary()
    assert summary["count"] == 1.0
    assert summary["avg_ms"] == result.latency_ms


def test_confidential_wallet_signs_and_verifies() -> None:
    wallet = ConfidentialWallet(wallet_id="w-1", owner_id="owner-1")
    key = b"secret-key"
    tx = wallet.send("recipient-1", "commitment-100", key)
    assert tx.verify() is True
    assert tx.sender_id == "owner-1"


def test_confidential_transaction_tampering_fails_verification() -> None:
    wallet = ConfidentialWallet(wallet_id="w-1", owner_id="owner-1")
    tx = wallet.send("recipient-1", "commitment-100", b"secret-key")
    tx.amount_commitment = "tampered"
    assert tx.verify() is False


def test_confidential_payment_validates_and_settles() -> None:
    wallet = ConfidentialWallet(wallet_id="w-1", owner_id="owner-1")
    tx = wallet.send("recipient-1", "commitment-100", b"secret-key")
    payment = ConfidentialPayment(
        payment_id=tx.tx_id,
        sender_id=tx.sender_id,
        recipient_id=tx.recipient_id,
        amount_commitment=tx.amount_commitment,
        tx=tx,
    )
    assert validate_payment(payment) is True
    receipt = settle_payment(payment)
    assert receipt["settled"] is True


def test_confidential_payment_invalid_signature_fails() -> None:
    wallet = ConfidentialWallet(wallet_id="w-1", owner_id="owner-1")
    tx = wallet.send("recipient-1", "commitment-100", b"secret-key")
    tx.signature = b"invalid"
    payment = ConfidentialPayment(
        payment_id=tx.tx_id,
        sender_id=tx.sender_id,
        recipient_id=tx.recipient_id,
        amount_commitment=tx.amount_commitment,
        tx=tx,
    )
    try:
        validate_payment(payment)
        assert False, "expected TEEError"
    except TEEError:
        pass
