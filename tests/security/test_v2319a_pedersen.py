"""V23-19a — the confidential-transaction commitments must actually commit.

Each test here corresponds to a defect that was present and is demonstrated, not asserted:
the forgery test constructs the attack the old construction permitted and requires it to fail
now. The homomorphism tests would have failed against the previous code because the committed
value was ``sha256(amount)``.
"""

from __future__ import annotations

import hashlib
from dataclasses import fields
from decimal import Decimal

import pytest
from ecdsa import NIST256p

from aitbc.agent_economics.confidential_payments import ConfidentialPayment, validate_payment
from aitbc.tee.errors import TEEError
from aitbc.wallet.confidential import (
    ConfidentialTransaction,
    ConfidentialWallet,
    Opening,
    _blinding_scalar,
    _commit,
    _G,
    _H,
    add_blindings,
    add_commitments,
    amount_to_units,
    commit,
    subtract_blindings,
    subtract_commitments,
    verify_commitment,
)

_N = NIST256p.order


# --------------------------------------------------------------------------------------
# Binding: nobody may know log_G(H)
# --------------------------------------------------------------------------------------


def test_h_is_not_a_known_multiple_of_g() -> None:
    """The old H was sha256(seed)*G, so its discrete log was public."""
    old_h = int.from_bytes(hashlib.sha256(b"aitbc-pedersen-h").digest(), "big") % _N
    assert _G * old_h != _H


def test_h_is_on_the_curve_and_not_infinity() -> None:
    assert NIST256p.curve.contains_point(_H.x(), _H.y())
    assert _H.x() is not None


def test_commitment_cannot_be_opened_to_a_second_amount() -> None:
    """The forgery the old construction allowed.

    With H = h*G for a known h, C = v*G + r*H collapses to (v + r*h)*G, and any amount v' can
    be opened by choosing r' = (v + r*h - v')/h. That attack is reproduced verbatim below
    against the seed the old code used; it must no longer produce a valid opening.
    """
    amount, blinding = "100", b"\x11" * 32
    c = commit(amount, blinding)
    assert verify_commitment(c, amount, blinding) is True

    h = int.from_bytes(hashlib.sha256(b"aitbc-pedersen-h").digest(), "big") % _N
    v = amount_to_units(amount)
    r = _blinding_scalar(blinding)
    forged_v = amount_to_units("1")
    forged_r = ((v + r * h - forged_v) * pow(h, -1, _N)) % _N

    assert verify_commitment(c, "1", forged_r.to_bytes(32, "big")) is False


# --------------------------------------------------------------------------------------
# Homomorphism: the committed value must be the amount, not a hash of it
# --------------------------------------------------------------------------------------


def test_commitments_add_to_the_sum_of_the_amounts() -> None:
    r1, r2 = b"\x01" * 32, b"\x02" * 32
    summed = add_commitments(commit("2", r1), commit("3", r2))
    assert verify_commitment(summed, "5", add_blindings(r1, r2)) is True


def test_commitments_subtract_to_the_difference_of_the_amounts() -> None:
    r1, r2 = b"\x03" * 32, b"\x04" * 32
    diff = subtract_commitments(commit("10", r1), commit("4", r2))
    assert verify_commitment(diff, "6", subtract_blindings(r1, r2)) is True


def test_sum_does_not_open_to_the_wrong_total() -> None:
    r1, r2 = b"\x05" * 32, b"\x06" * 32
    summed = add_commitments(commit("2", r1), commit("3", r2))
    assert verify_commitment(summed, "6", add_blindings(r1, r2)) is False


def test_fractional_amounts_are_homomorphic() -> None:
    r1, r2 = b"\x0a" * 32, b"\x0b" * 32
    summed = add_commitments(commit("0.1", r1), commit("0.2", r2))
    assert verify_commitment(summed, "0.3", add_blindings(r1, r2)) is True


# --------------------------------------------------------------------------------------
# Amounts are numbers
# --------------------------------------------------------------------------------------


def test_non_numeric_amounts_are_rejected() -> None:
    """The old tests and the CLI both passed strings like this as amounts."""
    with pytest.raises(ValueError):
        amount_to_units("commitment-100")


def test_equal_amounts_written_differently_commit_identically() -> None:
    r = b"\x07" * 32
    assert commit("1", r) == commit("1.0", r) == commit("01", r) == commit(Decimal("1.00"), r)


def test_negative_amounts_are_rejected() -> None:
    with pytest.raises(ValueError):
        amount_to_units("-1")


def test_amounts_beyond_the_bound_are_rejected() -> None:
    with pytest.raises(ValueError):
        amount_to_units(Decimal(2**64))


def test_excess_precision_is_rejected_not_rounded() -> None:
    with pytest.raises(ValueError):
        amount_to_units("0.000000001")


# --------------------------------------------------------------------------------------
# The envelope must not carry its own opening
# --------------------------------------------------------------------------------------


def test_envelope_has_no_amount_or_blinding_field() -> None:
    names = {f.name for f in fields(ConfidentialTransaction)}
    assert "amount_label" not in names
    assert "blinding" not in names


def test_envelope_cannot_self_verify_its_amount() -> None:
    assert not hasattr(ConfidentialTransaction, "verify_commitment")


def test_opening_must_be_supplied_to_check_the_amount() -> None:
    wallet = ConfidentialWallet(wallet_id="w-1", owner_id="alice")
    wallet.deposit("100")
    tx = wallet.send("bob", "40", b"key")

    opening = wallet.opening_for(tx.tx_id)
    assert opening is not None
    assert tx.opens_to(opening.amount, opening.blinding) is True
    assert tx.opens_to("41", opening.blinding) is False


# --------------------------------------------------------------------------------------
# The wallet balance must be openable
# --------------------------------------------------------------------------------------


def test_balance_commitment_opens_to_the_balance() -> None:
    wallet = ConfidentialWallet(wallet_id="w-1", owner_id="alice")
    wallet.deposit("5")
    wallet.deposit("5")
    opening = wallet.open_balance()
    assert opening.amount == Decimal("10")
    assert opening.opens(wallet.balance_commitment) is True


def test_balance_commitment_tracks_sends() -> None:
    wallet = ConfidentialWallet(wallet_id="w-1", owner_id="alice")
    wallet.deposit("10")
    wallet.send("bob", "4", b"key")
    assert wallet.balance() == Decimal("6")
    assert wallet.open_balance().opens(wallet.balance_commitment) is True


def test_sending_more_than_the_balance_is_refused() -> None:
    wallet = ConfidentialWallet(wallet_id="w-1", owner_id="alice")
    wallet.deposit("1")
    with pytest.raises(ValueError, match="insufficient"):
        wallet.send("bob", "2", b"key")


def test_balance_proof_admits_it_has_no_range_proof() -> None:
    wallet = ConfidentialWallet(wallet_id="w-1", owner_id="alice")
    assert wallet.balance_proof()["has_range_proof"] is False


# --------------------------------------------------------------------------------------
# Payment validation must not claim more than it checked
# --------------------------------------------------------------------------------------


def _payment(wallet: ConfidentialWallet, tx: ConfidentialTransaction) -> ConfidentialPayment:
    return ConfidentialPayment(
        payment_id=tx.tx_id,
        sender_id=tx.sender_id,
        recipient_id=tx.recipient_id,
        amount_commitment=tx.amount_commitment,
        tx=tx,
    )


def test_validation_succeeds_without_any_amount_claim() -> None:
    wallet = ConfidentialWallet(wallet_id="w-1", owner_id="alice")
    wallet.deposit("10")
    tx = wallet.send("bob", "3", b"key")
    assert validate_payment(_payment(wallet, tx)) is True


def test_validation_checks_a_supplied_opening() -> None:
    wallet = ConfidentialWallet(wallet_id="w-1", owner_id="alice")
    wallet.deposit("10")
    tx = wallet.send("bob", "3", b"key")
    good = wallet.opening_for(tx.tx_id)
    assert good is not None
    assert validate_payment(_payment(wallet, tx), opening=good) is True

    bad = Opening(amount=Decimal("9"), blinding=good.blinding)
    with pytest.raises(TEEError, match="opening does not match"):
        validate_payment(_payment(wallet, tx), opening=bad)


def test_validation_still_rejects_a_bad_signature() -> None:
    wallet = ConfidentialWallet(wallet_id="w-1", owner_id="alice")
    wallet.deposit("10")
    tx = wallet.send("bob", "3", b"key")
    tx.signature = b"\x00" * 64
    with pytest.raises(TEEError, match="signature is invalid"):
        validate_payment(_payment(wallet, tx))


def test_signature_covers_the_commitment() -> None:
    wallet = ConfidentialWallet(wallet_id="w-1", owner_id="alice")
    wallet.deposit("10")
    tx = wallet.send("bob", "3", b"key")
    tx.amount_commitment = commit("9", b"\x0c" * 32)
    assert tx.verify() is False


def test_commit_helper_matches_internal_construction() -> None:
    r = b"\x0d" * 32
    from aitbc.wallet.confidential import _encode

    assert commit("7", r) == _encode(_commit("7", r))
