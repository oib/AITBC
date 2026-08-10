"""Unit tests for v0.14.2 Agent A TEE deliverables."""

from __future__ import annotations

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aitbc.agent_economics import (
    ConfidentialPayment,
    settle_payment,
    validate_payment,
)
from aitbc.tee import (
    AttestationQuote,
    AttestationVerifier,
    DualVerificationPolicy,
    QuoteGenerator,
    TEEBenchmark,
    VerificationMode,
    ZKProof,
    verify_quote,
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
    wallet.deposit("100")
    tx = wallet.send("recipient-1", "100", key)
    assert tx.verify() is True
    assert tx.sender_id == "owner-1"


def test_confidential_transaction_tampering_fails_verification() -> None:
    wallet = ConfidentialWallet(wallet_id="w-1", owner_id="owner-1")
    wallet.deposit("100")
    tx = wallet.send("recipient-1", "100", b"secret-key")
    tx.amount_commitment = b"tampered"
    assert tx.verify() is False


def test_confidential_payment_validates_and_settles() -> None:
    wallet = ConfidentialWallet(wallet_id="w-1", owner_id="owner-1")
    wallet.deposit("100")
    tx = wallet.send("recipient-1", "100", b"secret-key")
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
    wallet.deposit("100")
    tx = wallet.send("recipient-1", "100", b"secret-key")
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


def test_quote_signature_verification() -> None:
    generator = QuoteGenerator(enclave_id="enc-1", signing_key=b"tee-signing-key")
    quote = generator.generate(quote_id="q1", measurement="m-1")
    assert quote.signature != b""
    assert quote.public_key != b""
    assert AttestationVerifier({"m-1"}, require_signature=True).verify(quote) is True


def test_quote_tampering_fails_signature_verification() -> None:
    generator = QuoteGenerator(enclave_id="enc-1", signing_key=b"tee-signing-key")
    quote = generator.generate(quote_id="q1", measurement="m-1")
    quote.quote_blob = b"tampered"
    assert AttestationVerifier({"m-1"}, require_signature=True).verify(quote) is False


def test_quote_wrong_measurement_fails() -> None:
    quote = AttestationQuote(quote_blob=b"quote", measurement="m-1")
    assert verify_quote(quote, expected_measurement="m-2") is False


def test_zk_proof_signature_binding() -> None:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    context_id = "tx-1"
    public_inputs = b"public"
    bound_inputs = context_id.encode() + b"|" + public_inputs
    proof_data = private_key.sign(bound_inputs)
    zk = ZKProof(
        proof_id="zk-1",
        context_id=context_id,
        verifying_key=public_key,
        public_inputs=public_inputs,
        proof_data=proof_data,
    )
    assert zk.verify() is True


def test_zk_proof_wrong_context_fails() -> None:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    proof_data = private_key.sign(b"tx-1|public")
    zk = ZKProof(
        proof_id="zk-1",
        context_id="tx-2",
        verifying_key=public_key,
        public_inputs=b"public",
        proof_data=proof_data,
    )
    assert zk.verify() is False


def test_dual_verification_both_with_signed_evidence() -> None:
    generator = QuoteGenerator(enclave_id="enc-1", signing_key=b"tee-signing-key")
    quote = generator.generate(quote_id="q1", measurement="m-1")

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    public_inputs = b"inputs"
    bound_inputs = quote.quote_id.encode() + b"|" + public_inputs
    proof_data = private_key.sign(bound_inputs)
    zk = ZKProof(
        proof_id="zk-1",
        context_id=quote.quote_id,
        verifying_key=public_key,
        public_inputs=public_inputs,
        proof_data=proof_data,
    )

    policy = DualVerificationPolicy(
        mode=VerificationMode.BOTH,
        allowed_measurements={"m-1"},
    )
    assert verify_with_policy(policy, quote, zk) is True


def test_tee_benchmark_summary_includes_throughput_and_memory() -> None:
    benchmark = TEEBenchmark(name="test")
    benchmark.run("noop", lambda: None)
    summary = benchmark.summary()
    assert summary["count"] == 1.0
    assert summary["ops_per_sec"] > 0
    assert summary["peak_memory_bytes"] >= 0


def test_confidential_commitment_opens_correctly() -> None:
    wallet = ConfidentialWallet(wallet_id="w-1", owner_id="owner-1")
    wallet.deposit("100")
    tx = wallet.send("recipient-1", "100", b"secret-key")
    # The opening comes from the wallet, not from the envelope -- see V23-19a.
    opening = wallet.opening_for(tx.tx_id)
    assert opening is not None
    assert tx.opens_to(opening.amount, opening.blinding) is True


def test_confidential_payment_wrong_commitment_fails() -> None:
    wallet = ConfidentialWallet(wallet_id="w-1", owner_id="owner-1")
    wallet.deposit("100")
    tx = wallet.send("recipient-1", "100", b"secret-key")
    payment = ConfidentialPayment(
        payment_id=tx.tx_id,
        sender_id=tx.sender_id,
        recipient_id=tx.recipient_id,
        amount_commitment=b"wrong",
        tx=tx,
    )
    try:
        validate_payment(payment)
        assert False, "expected TEEError"
    except TEEError:
        pass


def test_confidential_wallet_balance_commitment_changes() -> None:
    wallet = ConfidentialWallet(wallet_id="w-1", owner_id="owner-1")
    wallet.deposit("100")
    balance_before = wallet.balance_commitment
    wallet.send("recipient-1", "50", b"secret-key")
    assert wallet.balance_commitment != balance_before
