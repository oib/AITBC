"""V23-04: a wrong signature and an unreadable one must not look the same.

The finding: "A node rejecting every honestly-signed block and a node under attack produce
the same log line and the same metric." The log halves were separated when the recovery
paths were centralised. These cover the metric half.

The distinction decides what an operator does. A rising `unparseable` rate is an encoding
mismatch on our side — which is exactly what V23-01 was, and it stayed invisible precisely
because nothing counted it apart from ordinary rejections.
"""

import hashlib

import pytest
from eth_account import Account

from aitbc.crypto.consensus_signing import sign_block_hash, verify_block_signature
from aitbc.crypto.crypto import derive_ethereum_address
from aitbc.crypto.signature_metrics import (
    MISMATCH,
    SIGNATURE_VERIFICATION_FAILURES,
    SIGNATURE_VERIFICATIONS,
    UNPARSEABLE,
)

PRIVATE_KEY = "4c0883a69102937d6231471b5dbb6204fe512961708279fc6a0d1f2d3a0b1c2d"
BLOCK_HASH = "0x" + hashlib.sha256(b"block").hexdigest()


def _failures(context: str, outcome: str) -> float:
    value = SIGNATURE_VERIFICATION_FAILURES.labels(context=context, outcome=outcome)._value.get()
    return float(value)


def _attempts(context: str) -> float:
    return float(SIGNATURE_VERIFICATIONS.labels(context=context)._value.get())


def test_a_valid_signature_counts_an_attempt_and_no_failure() -> None:
    before_attempts = _attempts("block")
    before_mismatch = _failures("block", MISMATCH)
    before_unparseable = _failures("block", UNPARSEABLE)

    signature = sign_block_hash(BLOCK_HASH, PRIVATE_KEY)
    assert verify_block_signature(BLOCK_HASH, signature, derive_ethereum_address(PRIVATE_KEY)) is True

    assert _attempts("block") == before_attempts + 1
    assert _failures("block", MISMATCH) == before_mismatch
    assert _failures("block", UNPARSEABLE) == before_unparseable


def test_a_signature_from_the_wrong_key_counts_as_mismatch_not_unparseable() -> None:
    """Someone else's valid signature. Parses fine, recovers to the wrong address."""
    before_mismatch = _failures("block", MISMATCH)
    before_unparseable = _failures("block", UNPARSEABLE)

    signature = sign_block_hash(BLOCK_HASH, PRIVATE_KEY)
    someone_else = Account.from_key("0x" + "11" * 32).address

    assert verify_block_signature(BLOCK_HASH, signature, someone_else) is False

    assert _failures("block", MISMATCH) == before_mismatch + 1
    assert _failures("block", UNPARSEABLE) == before_unparseable, "a wrong signer is not an encoding problem"


@pytest.mark.parametrize(
    "signature",
    [
        "0x" + "ab" * 64,  # 64 bytes -- one short of a signature
        "0x" + "ab" * 65,  # right length, recovery id 0xab is not 0/1/27/28
        "",  # nothing at all
    ],
    ids=["too-short", "bad-recovery-id", "empty"],
)
def test_unreadable_signatures_count_as_unparseable_not_mismatch(signature: str) -> None:
    """This is the class that V23-01 fell into: our own encoding, not an attacker's."""
    before_mismatch = _failures("block", MISMATCH)
    before_unparseable = _failures("block", UNPARSEABLE)

    assert verify_block_signature(BLOCK_HASH, signature, derive_ethereum_address(PRIVATE_KEY)) is False

    assert _failures("block", UNPARSEABLE) == before_unparseable + 1
    assert _failures("block", MISMATCH) == before_mismatch, "an unreadable signature is not a wrong signer"


def test_the_v2301_regression_would_now_be_visible() -> None:
    """The concrete scenario the finding describes.

    V23-01 rejected every signature carrying an Ethereum recovery id (27/28) — that is, from
    every standard wallet. Had it recurred, it would show as a pure `unparseable` spike with
    no `mismatch` movement, which is a deployment fault rather than an attack.
    """
    before_mismatch = _failures("block", MISMATCH)
    before_unparseable = _failures("block", UNPARSEABLE)

    # Ten distinct signatures, each rejected for an encoding reason: r and s vary, the
    # recovery byte is 0xff throughout. (Varying the whole signature by hand does not work
    # here -- byte patterns 0x00 and 0x01 are *valid* recovery ids, so those recover to some
    # address and count as mismatches, which is the distinction this test exists to make.)
    for i in range(10):
        malformed = "0x" + f"{i:02x}" * 64 + "ff"
        verify_block_signature(BLOCK_HASH, malformed, derive_ethereum_address(PRIVATE_KEY))

    assert _failures("block", UNPARSEABLE) == before_unparseable + 10
    assert _failures("block", MISMATCH) == before_mismatch, (
        "the two outcomes must move independently -- if a deployment fault raised the same "
        "counter as an attack, the operator learns nothing from either"
    )


def test_a_mismatch_names_the_key_that_actually_signed(caplog) -> None:
    """V23-52: the log half of the same distinction.

    A mismatch has two very different causes: someone forged a block, or a proposer is
    signing with a key that is not the identity it declares. The metric cannot tell them
    apart and neither could the message -- it said "Invalid proposer signature" and stopped.

    That is not hypothetical. The deployed hub signed 12,000+ blocks with an unregistered
    key while declaring the genesis proposer, so every block was well-formed, correctly
    signed, and rejected by every follower. Identifying it meant fetching a block and
    recovering the address by hand. Both addresses are public; naming them makes the next
    occurrence one line of log.
    """
    signer = Account.create()
    impostor = Account.create()
    signature = sign_block_hash(BLOCK_HASH, signer.key.hex())

    with caplog.at_level("WARNING"):
        assert verify_block_signature(BLOCK_HASH, signature, impostor.address) is False

    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert signer.address in logged, "the recovered key must be named -- it is the whole diagnosis"
    assert impostor.address in logged, "and the expected one, or there is nothing to compare against"


def test_an_unparseable_signature_still_logs_without_raising(caplog) -> None:
    """The mismatch branch re-recovers to report; that must not turn a rejection into a crash."""
    with caplog.at_level("WARNING"):
        assert verify_block_signature(BLOCK_HASH, "0x" + "00" * 64 + "ff", Account.create().address) is False
