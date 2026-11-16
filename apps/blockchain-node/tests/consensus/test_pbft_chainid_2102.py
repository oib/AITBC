"""#2102 pins: PBFT vote signatures bind ``chain_id``.

PBFT prepare/commit/pre-prepare signatures previously covered only
``{message_type, sender, view_number, sequence_number, digest}`` — a
signature made on one chain verified on any other chain sharing the
validator key, so an equivocation pair recorded on chain X replayed as
slashable evidence on armed chain Y.

New signatures add ``chain_id`` to the preimage; every verifier tries the
chain-bound preimage first and falls back to the legacy preimage so
in-flight gossip and historical signatures still verify (pre-#2102
signatures are already chain-agnostic and cannot be re-bound — that
residual ages out with the evidence TTL / intake windows).

Real secp256k1 keys and signatures throughout, in the style of
``test_pbft_certificate_1940.py``.
"""

from __future__ import annotations

import hashlib
from typing import Any

from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA, ValidatorRole
from aitbc_chain.consensus.pbft import PBFTConsensus, PBFTMessage, PBFTMessageType
from aitbc_chain.consensus.pbft_certificate import validate_commit_certificate
from aitbc_chain.consensus.pbft_vote_signature import pbft_vote_preimage, verify_pbft_vote_signature
from aitbc_chain.consensus.slashing import SlashingManager, slashing_event_record
from aitbc_chain.state.deactivation_evidence import (
    _cross_view_message_crypto_ok,
    _verify_vote_equivocation,
    verify_deactivation_evidence,
)
from aitbc.crypto.consensus_signing import sign_consensus_message
from aitbc.crypto.signature_recovery import canonical_address

CHAIN_A = "chain-a-2102"
CHAIN_B = "chain-b-2102"
BH = "0x" + "ab" * 32
BH2 = "0x" + "cd" * 32
SEQ = 10
VIEW = 3


def _key(byte: str) -> tuple[str, str]:
    from eth_keys import keys

    priv = "0x" + byte * 32
    return keys.PrivateKey(bytes.fromhex(priv[2:])).public_key.to_checksum_address(), priv


ADDR, KEY = _key("21")
ADDR2, KEY2 = _key("22")
ADDR3, KEY3 = _key("23")
MEMBERS = [ADDR, ADDR2, ADDR3]
SIGNS = {ADDR: KEY, ADDR2: KEY2, ADDR3: KEY3}


def _digest(block_hash: str, seq: int, view: int) -> str:
    return hashlib.sha256(f"{block_hash}:{seq}:{view}".encode()).hexdigest()


def _record(sender: str, *, block_hash: str = BH, seq: int = SEQ, view: int = VIEW, phase: str = "commit") -> dict[str, Any]:
    return {
        "message_type": phase,
        "sender": sender,
        "view_number": view,
        "sequence_number": seq,
        "digest": _digest(block_hash, seq, view),
        "block_hash": block_hash,
    }


def _sign(record: dict[str, Any], key: str, chain_id: str | None) -> str:
    return sign_consensus_message(pbft_vote_preimage(record, chain_id), key)


def _commit(sender: str, key: str, *, chain_id: str | None, block_hash: str = BH) -> dict[str, Any]:
    rec = _record(sender, block_hash=block_hash)
    return {**rec, "signature": _sign(rec, key, chain_id), "timestamp": 0.0}


def _quorum(chain_id: str | None, block_hash: str = BH) -> list[dict[str, Any]]:
    return [_commit(a, SIGNS[a], chain_id=chain_id, block_hash=block_hash) for a in MEMBERS]


def _make_pbft(chain_id: str = CHAIN_A, priv: str = "") -> PBFTConsensus:
    consensus = MultiValidatorPoA(chain_id)
    for addr in MEMBERS:
        consensus.add_validator(addr, 1000.0)
        consensus.validators[addr].role = ValidatorRole.PROPOSER
    return PBFTConsensus(consensus, private_key=priv, chain_id=chain_id, local_validator=MEMBERS[0])


# ---------------------------------------------------------------------------
# pbft_vote_signature helpers
# ---------------------------------------------------------------------------


class TestVoteSignatureHelper:
    def test_same_chain_verifies(self):
        rec = _record(ADDR)
        sig = _sign(rec, KEY, CHAIN_A)
        assert verify_pbft_vote_signature(rec, sig, ADDR, CHAIN_A)

    def test_cross_chain_rejected(self):
        rec = _record(ADDR)
        sig = _sign(rec, KEY, CHAIN_A)
        assert not verify_pbft_vote_signature(rec, sig, ADDR, CHAIN_B)

    def test_legacy_signature_falls_back(self):
        rec = _record(ADDR)
        sig = _sign(rec, KEY, None)
        assert verify_pbft_vote_signature(rec, sig, ADDR, CHAIN_A)
        assert verify_pbft_vote_signature(rec, sig, ADDR, CHAIN_B)

    def test_foreign_key_rejected(self):
        rec = _record(ADDR)
        sig = _sign(rec, KEY2, CHAIN_A)
        assert not verify_pbft_vote_signature(rec, sig, ADDR, CHAIN_A)

    def test_malformed_signature_never_raises(self):
        rec = _record(ADDR)
        assert not verify_pbft_vote_signature(rec, "not-a-signature", ADDR, CHAIN_A)


# ---------------------------------------------------------------------------
# PBFTConsensus sign/verify round-trip
# ---------------------------------------------------------------------------


class TestConsensusMessageSignVerify:
    def _msg(self) -> PBFTMessage:
        return PBFTMessage(
            message_type=PBFTMessageType.COMMIT,
            sender=ADDR,
            view_number=VIEW,
            sequence_number=SEQ,
            digest=_digest(BH, SEQ, VIEW),
            signature="",
            timestamp=0.0,
            block_hash=BH,
        )

    def test_signed_message_verifies_on_same_chain(self):
        pbft = _make_pbft(CHAIN_A, priv=KEY)
        msg = self._msg()
        pbft._sign_message(msg)
        assert msg.signature
        assert pbft._verify_message_signature(msg)

    def test_signature_does_not_verify_on_foreign_chain(self):
        signer = _make_pbft(CHAIN_A, priv=KEY)
        msg = self._msg()
        signer._sign_message(msg)
        foreign = _make_pbft(CHAIN_B)
        assert not foreign._verify_message_signature(msg)

    def test_unsigned_message_still_gated_by_config(self, monkeypatch):
        from aitbc_chain.config import settings

        pbft = _make_pbft(CHAIN_A)
        msg = self._msg()
        monkeypatch.setattr(settings, "pbft_require_signatures", True)
        assert not pbft._verify_message_signature(msg)


# ---------------------------------------------------------------------------
# validate_commit_certificate — chain-bound quorum
# ---------------------------------------------------------------------------


class TestCertificateChainBinding:
    def test_bound_quorum_accepts_on_own_chain(self):
        ok, reason = validate_commit_certificate(_quorum(CHAIN_A), BH, MEMBERS, height=SEQ, view=VIEW, chain_id=CHAIN_A)
        assert ok, reason

    def test_bound_quorum_rejected_on_foreign_chain(self):
        ok, reason = validate_commit_certificate(_quorum(CHAIN_A), BH, MEMBERS, height=SEQ, view=VIEW, chain_id=CHAIN_B)
        assert not ok
        assert "quorum" in reason or "commit" in reason

    def test_legacy_signed_quorum_still_accepts(self):
        """Transitional: pre-#2102 signatures carry no chain binding and keep
        verifying under the legacy fallback on any chain."""
        ok, reason = validate_commit_certificate(_quorum(None), BH, MEMBERS, height=SEQ, view=VIEW, chain_id=CHAIN_B)
        assert ok, reason


# ---------------------------------------------------------------------------
# Equivocation evidence — apply-side chain binding
# ---------------------------------------------------------------------------


def _equivocation_payload(chain_id: str | None) -> dict[str, Any]:
    """Two COMMITs, same seq/view, different block_hash — the slashable pair."""
    msgs = []
    for h in (BH, BH2):
        rec = _record(ADDR, block_hash=h)
        msgs.append({**rec, "signature": _sign(rec, KEY, chain_id)})
    return {"messages": msgs}


class TestEquivocationEvidenceChainBinding:
    def test_bound_pair_verifies_on_own_chain(self):
        assert _verify_vote_equivocation(_equivocation_payload(CHAIN_A), ADDR, CHAIN_A)

    def test_bound_pair_rejected_on_foreign_chain(self):
        assert not _verify_vote_equivocation(_equivocation_payload(CHAIN_A), ADDR, CHAIN_B)

    def test_legacy_pair_still_verifies(self):
        assert _verify_vote_equivocation(_equivocation_payload(None), ADDR, CHAIN_B)

    def test_cross_view_message_crypto_chain_bound(self):
        rec = _record(ADDR, block_hash=BH2)
        fields = {**rec, "signature": _sign(rec, KEY, CHAIN_A)}
        assert _cross_view_message_crypto_ok(fields, ADDR, CHAIN_A) is None
        reason = _cross_view_message_crypto_ok(fields, ADDR, CHAIN_B)
        assert reason is not None and "signature" in reason


# ---------------------------------------------------------------------------
# Empty chain_id — sign/verify symmetry (#2102 respin)
# ---------------------------------------------------------------------------


class TestEmptyChainId:
    """``settings.chain_id`` defaults to ``""``: an empty chain must sign the
    legacy preimage, or ``_sign_message``/``_verify_message_signature``
    diverge and the node cannot verify its own votes (self-DoS)."""

    def test_empty_chain_id_preimage_is_legacy(self):
        rec = _record(ADDR)
        assert pbft_vote_preimage(rec, "") == pbft_vote_preimage(rec, None)
        assert "chain_id" not in pbft_vote_preimage(rec, "")

    def test_empty_chain_id_signature_verifies(self):
        rec = _record(ADDR)
        sig = _sign(rec, KEY, "")
        assert verify_pbft_vote_signature(rec, sig, ADDR, "")
        assert verify_pbft_vote_signature(rec, sig, ADDR, None)
        assert verify_pbft_vote_signature(rec, sig, ADDR, CHAIN_A)

    def test_empty_chain_id_consensus_roundtrip(self):
        pbft = _make_pbft("", priv=KEY)
        msg = PBFTMessage(
            message_type=PBFTMessageType.COMMIT,
            sender=ADDR,
            view_number=VIEW,
            sequence_number=SEQ,
            digest=_digest(BH, SEQ, VIEW),
            signature="",
            timestamp=0.0,
            block_hash=BH,
        )
        pbft._sign_message(msg)
        assert msg.signature
        assert pbft._verify_message_signature(msg)


# ---------------------------------------------------------------------------
# verify_deactivation_evidence — end-to-end chain_id forwarding (#2102 respin)
# ---------------------------------------------------------------------------


def _v2_bundle(chain_id: str | None) -> dict[str, Any]:
    """A v2 evidence bundle whose vote_equivocation messages are signed under
    ``chain_id`` — the same shape ``_deactivation_payload`` emits."""
    mgr = SlashingManager()
    msgs = []
    for h in (BH, BH2):
        rec = _record(ADDR, block_hash=h)
        msgs.append({**rec, "signature": _sign(rec, KEY, chain_id)})
    mgr.slashing_events.append(mgr.vote_equivocation_event(ADDR, VIEW, "commit", msgs[0], msgs[1]))
    canon = canonical_address(ADDR)
    bundle_mgr = SlashingManager()
    bundle_mgr.slashing_events = list(mgr.slashing_events)
    return {
        "validator_address": canon,
        "evidence_hash": bundle_mgr.evidence_hash(canon),
        "evidence_version": 2,
        "evidence": [slashing_event_record(e) for e in mgr.slashing_events],
    }


class TestDeactivationEvidenceChainForwarding:
    """Pin the public entry point: ``verify_deactivation_evidence`` must pass
    its ``chain_id`` argument through to the leaf PBFT signature checks —
    a ``chain_id=None`` forwarding mutation must fail these tests."""

    def test_bound_bundle_verifies_on_own_chain(self):
        payload = _v2_bundle(CHAIN_A)
        assert (
            verify_deactivation_evidence(
                payload,
                chain_id=CHAIN_A,
                validator_addr=payload["validator_address"],
                evidence_hash=payload["evidence_hash"],
            )
            is None
        )

    def test_bound_bundle_rejected_on_foreign_chain(self):
        payload = _v2_bundle(CHAIN_A)
        reason = verify_deactivation_evidence(
            payload,
            chain_id=CHAIN_B,
            validator_addr=payload["validator_address"],
            evidence_hash=payload["evidence_hash"],
        )
        assert reason is not None

    def test_legacy_bundle_still_verifies(self):
        payload = _v2_bundle(None)
        assert (
            verify_deactivation_evidence(
                payload,
                chain_id=CHAIN_B,
                validator_addr=payload["validator_address"],
                evidence_hash=payload["evidence_hash"],
            )
            is None
        )
