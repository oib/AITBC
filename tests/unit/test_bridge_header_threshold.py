"""Fixture test for the bridge header threshold question (A34-2).

Four fake consensus attesters sign the canonical block-header message —
the exact shape ``_verify_header_threshold_signatures`` builds via
``build_verification_message`` and recovers with ``recover_all_signers``.
``check_threshold`` then decides, counting only signers that are members of
the registered active set (``aitbc/bridge/multisig.py``).

Shapes under test:
- (a) the planned pair {attester A, non-attester X} at threshold 2 — fails;
- (b) the current-shape pair {Y, X} with no attester — fails;
- (c) the four attesters — passes at threshold 2 and at 3.

Keys are fixture keys generated in the test; no real key material.
"""

from __future__ import annotations

import secrets

import pytest

from aitbc.bridge import build_verification_message, check_threshold, recover_all_signers
from aitbc.bridge.types import BridgeBlockHeader, ValidatorInfo, ValidatorSet
from aitbc.crypto.crypto import sign_transaction_data
from eth_keys import keys

CHAIN = "ait-hub.aitbc.bubuit.net"


def _key() -> tuple[str, str]:
    """Return (private_key_hex, address) for a fresh fixture key."""
    pk = keys.PrivateKey(secrets.token_bytes(32))
    return pk.to_hex(), str(pk.public_key.to_checksum_address())


@pytest.fixture(scope="module")
def cast() -> dict[str, tuple[str, str]]:
    return {
        "A": _key(),
        "B": _key(),
        "C": _key(),
        "D": _key(),
        "X": _key(),  # registered-looking but never attests
        "Y": _key(),  # retired attester stand-in
    }


def _header(proposer_addr: str) -> BridgeBlockHeader:
    return BridgeBlockHeader(
        chain_id=CHAIN,
        height=38109,
        hash="0xdeadbeef" * 8,
        parent_hash="0xfeedface" * 8,
        proposer=proposer_addr,
        state_root="0x1234" * 16,
        bridge_state_root="0x5678" * 16,
    )


def _vset(members: list[str], threshold: int = 2) -> ValidatorSet:
    infos = [ValidatorInfo(address=a, public_key="0x04", chain_id=CHAIN, epoch=1, is_active=True) for a in members]
    return ValidatorSet(chain_id=CHAIN, epoch=1, validators=infos, threshold=threshold, total=len(infos))


def _signed_header(cast: dict[str, tuple[str, str]], attesters: list[str]) -> tuple[dict, list[str], str]:
    """Header whose proposer is attester A; attestations over the canonical
    message from the named attesters; returns (message, all_sigs, proposer_sig)."""
    header = _header(cast["A"][1])
    message = build_verification_message(header)
    attestation_sigs = [sign_transaction_data(message, cast[name][0]) for name in attesters]
    proposer_sig = sign_transaction_data(message, cast["A"][0])
    return message, attestation_sigs, proposer_sig


def test_recovered_signers_are_the_attesters(cast) -> None:
    message, sigs, proposer_sig = _signed_header(cast, ["A", "B", "C", "D"])
    all_sigs = sigs + [proposer_sig]
    signers = {s.lower() for s in recover_all_signers(message, all_sigs)}
    expected = {cast[n][1].lower() for n in ("A", "B", "C", "D")}
    assert signers == expected


def test_planned_pair_cannot_meet_threshold(cast) -> None:
    """(a) {attester A, non-attester X} at t=2 — the planned shape."""
    message, sigs, proposer_sig = _signed_header(cast, ["A", "B", "C", "D"])
    signers = recover_all_signers(message, sigs + [proposer_sig])
    vset = _vset([cast["A"][1], cast["X"][1]], threshold=2)
    meets, count, valid = check_threshold(signers, vset, 2)
    assert not meets and count == 1


def test_current_shape_no_attester_fails(cast) -> None:
    """(b) {retired Y, non-attester X} — the live registered pair's shape."""
    message, sigs, proposer_sig = _signed_header(cast, ["A", "B", "C", "D"])
    signers = recover_all_signers(message, sigs + [proposer_sig])
    vset = _vset([cast["Y"][1], cast["X"][1]], threshold=2)
    meets, count, _ = check_threshold(signers, vset, 2)
    assert not meets and count == 0


def test_four_attesters_meets_threshold(cast) -> None:
    """(c) the four attesters at t=2 and t=3 — the working design."""
    message, sigs, proposer_sig = _signed_header(cast, ["A", "B", "C", "D"])
    signers = recover_all_signers(message, sigs + [proposer_sig])
    members = [cast[n][1] for n in ("A", "B", "C", "D")]
    meets2, count2, _ = check_threshold(signers, _vset(members, 2), 2)
    meets3, count3, _ = check_threshold(signers, _vset(members, 3), 3)
    assert meets2 and count2 >= 2
    assert meets3 and count3 >= 3


def test_four_attesters_two_of_four_boundary(cast) -> None:
    """Only two attestations available (one validator down) — t=2 still
    meets on a four-member set; t=3 does not."""
    message, sigs, proposer_sig = _signed_header(cast, ["A", "B"])
    signers = recover_all_signers(message, sigs + [proposer_sig])
    members = [cast[n][1] for n in ("A", "B", "C", "D")]
    meets2, count2, _ = check_threshold(signers, _vset(members, 2), 2)
    meets3, count3, _ = check_threshold(signers, _vset(members, 3), 3)
    # proposer sig of A dedupes with A's attestation — distinct signers are A,B
    assert meets2 and count2 == 2
    assert not meets3 and count3 == 2
