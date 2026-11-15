"""#1940 F3-A pins: dormant cross-view COMMIT equivocation evidence.

Once ``pbft_cross_view_commit_lock_height`` is armed, a validator that
COMMITs two different ``block_hash`` values at the same ``sequence_number``
(chain height) in different PBFT ``view_number``s produces canonical,
verifiable, slashable evidence — kind ``pbft_cross_view_vote_equivocation``
— without changing which votes are legal (that is the unarmed F3-B lock)
and without touching prepare-phase rotation, which stays non-slashable
across views by design.

On-chain, ``VALIDATOR_DEACTIVATE`` v2 evidence carrying the new kind
verifies only when the ``validator_deactivation_pbft_cross_view_evidence_height``
chain parameter is armed at the apply height and the evidenced sequence
sits inside ``[activation, apply_height]`` — unset/malformed/pre-activation
claims fail closed. Everything here is dormant by default: ``None`` gates
keep behavior byte-identical.

Real secp256k1 keys and signatures throughout, in the style of
``test_pbft_certificate_1940.py`` / ``test_deactivation_evidence_1263.py``.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from sqlmodel import Session, select

from aitbc_chain.base_models import Bond, Block, ChainParameter, ValidatorDeactivation
from aitbc_chain.config import settings
from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA, Validator, ValidatorRole
from aitbc_chain.consensus.pbft_cross_view import cross_view_commit_lock_active
from aitbc_chain.consensus.slashing import (
    PBFT_CROSS_VIEW_VOTE_EQUIVOCATION,
    SlashingManager,
    event_is_equivocation_claim,
    event_signature_evidence,
    slashing_event_record,
)
from aitbc.crypto.consensus_signing import sign_consensus_message
from aitbc.crypto.signature_recovery import canonical_address
from aitbc_chain.database import session_scope
from aitbc_chain.state.deactivation_evidence import verify_deactivation_evidence
from aitbc_chain.state.state_transition import StateTransition

from ..test_apply_parity import CHAIN, PROVIDER, PROVIDER_KEY, _seed_bond
from .test_validator_deactivation_1198 import (
    BLOCK_TIME,
    V2,
    _chain_db,
    _consensus,
    _deactivation_tx,
    _engine,
    _seed_authority,
)

CHAIN_ID = "cross-view-1940"
SEQ = 10
HA = "0x" + "aa" * 32
HB = "0x" + "bb" * 32
HC = "0x" + "cc" * 32


def _key(byte: str) -> tuple[str, str]:
    from eth_keys import keys

    priv = "0x" + byte * 32
    return keys.PrivateKey(bytes.fromhex(priv[2:])).public_key.to_checksum_address(), priv


ADDR, ADDR_KEY = _key("77")
ADDR2, ADDR2_KEY = _key("88")
OUTSIDER, _OUTSIDER_KEY = _key("99")


def _digest(block_hash: str, seq: int, view: int) -> str:
    return hashlib.sha256(f"{block_hash}:{seq}:{view}".encode()).hexdigest()


def _signed_fields(
    sender: str,
    key: str,
    *,
    block_hash: str,
    seq: int,
    view: int,
    phase: str = "commit",
    digest: str | None = None,
    signature_key: str | None = None,
) -> dict[str, Any]:
    """One signed PBFT message record — the ``_VOTE_EVIDENCE_FIELDS`` subset."""
    digest = digest if digest is not None else _digest(block_hash, seq, view)
    signed = {
        "message_type": phase,
        "sender": sender,
        "view_number": view,
        "sequence_number": seq,
        "digest": digest,
    }
    return {
        "message_type": phase,
        "sender": sender,
        "view_number": view,
        "sequence_number": seq,
        "digest": digest,
        "block_hash": block_hash,
        "signature": sign_consensus_message(signed, signature_key or key),
    }


class _PBFTMsg:
    """Attribute-style PBFTMessage stand-in for ``record_commit(message=...)``."""

    def __init__(self, phase: str, sender: str, view: int, seq: int, block_hash: str, key: str):
        digest = _digest(block_hash, seq, view)
        signed = {
            "message_type": phase,
            "sender": sender,
            "view_number": view,
            "sequence_number": seq,
            "digest": digest,
        }
        self.message_type = SimpleNamespace(value=phase)
        self.sender = sender
        self.view_number = view
        self.sequence_number = seq
        self.digest = digest
        self.block_hash = block_hash
        self.signature = sign_consensus_message(signed, key)


def _poa(*addresses: str) -> MultiValidatorPoA:
    c = MultiValidatorPoA(CHAIN_ID, load_state=False)
    for a in addresses:
        c.add_validator(a, 1000.0)
        c.validators[a].role = ValidatorRole.VALIDATOR
        c.validators[a].is_active = True
    return c


@pytest.fixture
def armed(monkeypatch):
    monkeypatch.setattr(settings, "pbft_cross_view_commit_lock_height", SEQ)
    yield


def _v2_payload(mgr: SlashingManager, validator: str) -> dict:
    """Assemble the payload exactly the way _deactivation_payload does."""
    canon = canonical_address(validator)
    bundle_mgr = SlashingManager()
    bundle_mgr.slashing_events = list(mgr.slashing_events)
    return {
        "validator_address": canon,
        "evidence_hash": bundle_mgr.evidence_hash(canon),
        "bond_id": "bond-x",
        "evidence_version": 2,
        "evidence": [slashing_event_record(e) for e in mgr.slashing_events],
    }


def _cross_view_event(
    validator: str = ADDR,
    key: str = ADDR_KEY,
    *,
    seq: int = SEQ,
    view_a: int = 0,
    view_b: int = 1,
    hash_a: str = HA,
    hash_b: str = HB,
    phase: str = "commit",
) -> Any:
    """A real two-signature cross-view event on a fresh manager."""
    mgr = SlashingManager()
    m_a = _signed_fields(validator, key, block_hash=hash_a, seq=seq, view=view_a, phase=phase)
    m_b = _signed_fields(validator, key, block_hash=hash_b, seq=seq, view=view_b, phase=phase)
    event = mgr.cross_view_vote_equivocation_event(validator, seq, phase, m_b, m_a)  # reversed on purpose
    mgr.slashing_events.append(event)
    return event


def _seed_param(session: Session, chain_id: str, name: str, value: str, applied_height: int = 0) -> None:
    session.add(
        ChainParameter(
            chain_id=chain_id,
            parameter=name,
            value=value,
            applied_height=applied_height,
        )
    )


# ---------------------------------------------------------------------------
# Gate helper
# ---------------------------------------------------------------------------


class TestGate:
    def test_unset_is_inactive(self):
        assert settings.pbft_cross_view_commit_lock_height is None
        assert cross_view_commit_lock_active(SEQ) is False
        assert cross_view_commit_lock_active(0) is False

    def test_armed_boundaries(self, monkeypatch):
        monkeypatch.setattr(settings, "pbft_cross_view_commit_lock_height", 10)
        assert cross_view_commit_lock_active(9) is False
        assert cross_view_commit_lock_active(10) is True
        assert cross_view_commit_lock_active(11) is True
        assert cross_view_commit_lock_active(None) is False
        assert cross_view_commit_lock_active(True) is False  # bool is not a strict int
        assert cross_view_commit_lock_active("10") is False

    def test_malformed_threshold_inactive(self, monkeypatch):
        for bad in ("x", -1, True, 1.5):
            monkeypatch.setattr(settings, "pbft_cross_view_commit_lock_height", bad)
            assert cross_view_commit_lock_active(10**9) is False


# ---------------------------------------------------------------------------
# slashing.py unit pins
# ---------------------------------------------------------------------------


class TestCrossViewEvent:
    def test_event_shape_and_canonical_evidence(self):
        mgr = SlashingManager()
        m_a = _signed_fields(ADDR, ADDR_KEY, block_hash=HB, seq=SEQ, view=1)  # higher view first
        m_b = _signed_fields(ADDR, ADDR_KEY, block_hash=HA, seq=SEQ, view=0)
        event = mgr.cross_view_vote_equivocation_event(ADDR, SEQ, "commit", m_a, m_b)

        assert event.condition.value == "double_sign"
        assert event.block_height == SEQ  # chain height, NOT the view
        assert event.round_number is None
        assert (event.hash_a, event.hash_b) == tuple(sorted([HA, HB], key=str.lower))
        assert event_is_equivocation_claim(event)
        assert event_signature_evidence(event) is not None

        ep = json.loads(event.evidence)
        assert ep["kind"] == PBFT_CROSS_VIEW_VOTE_EQUIVOCATION
        assert ep["sequence"] == SEQ
        assert ep["phase"] == "commit"
        assert ep["views"] == [0, 1]
        # messages ordered by (view_number, block_hash.lower(), signature)
        assert [m["view_number"] for m in ep["messages"]] == [0, 1]
        assert [m["block_hash"] for m in ep["messages"]] == [HA, HB]
        assert all(m["message_type"] == "commit" for m in ep["messages"])

    def test_observation_order_does_not_change_evidence(self):
        mgr = SlashingManager()
        m_a = _signed_fields(ADDR, ADDR_KEY, block_hash=HA, seq=SEQ, view=0)
        m_b = _signed_fields(ADDR, ADDR_KEY, block_hash=HB, seq=SEQ, view=1)
        e1 = mgr.cross_view_vote_equivocation_event(ADDR, SEQ, "commit", m_a, m_b)
        e2 = mgr.cross_view_vote_equivocation_event(ADDR, SEQ, "commit", m_b, m_a)
        assert e1.evidence == e2.evidence
        assert (e1.hash_a, e1.hash_b) == (e2.hash_a, e2.hash_b)

    def test_dedup_distinguishes_view_pairs_with_same_hash_pair(self):
        """(v0,v1) and (v0,v2) conflicts over the same two hashes are TWO offenses."""
        mgr = SlashingManager()
        validator = Validator(
            address=ADDR,
            stake=Decimal("1000"),
            reputation=1.0,
            role=ValidatorRole.VALIDATOR,
            last_proposed=0,
            is_active=True,
        )
        e1 = _cross_view_event(view_a=0, view_b=1)
        e2 = _cross_view_event(view_a=0, view_b=2)
        # Same block-hash pair, different view pairs — the dedup key must tell
        # them apart (this is what the phase/sequence/views key fields buy).
        assert (e1.hash_a, e1.hash_b) == (e2.hash_a, e2.hash_b)
        assert json.loads(e1.evidence)["views"] == [0, 1]
        assert json.loads(e2.evidence)["views"] == [0, 2]
        # rebuild both on the same manager so dedup sees both
        mgr.slashing_events = []
        mgr.slashing_events.append(e1)
        assert mgr.apply_slashing(validator, e2) is True
        assert len(mgr.slashing_events) == 2
        # re-observing e1 must dedup, not double-slash
        stake_before = validator.stake
        assert mgr.apply_slashing(validator, e1) is False
        assert validator.stake == stake_before
        assert len(mgr.slashing_events) == 2

    def test_dedup_upgrades_unsigned_evidence_in_place(self):
        """Same (sequence, view pair, hash pair) recorded without signatures
        first is upgraded by the signed observation — one event, better evidence."""
        mgr = SlashingManager()
        validator = Validator(
            address=ADDR,
            stake=Decimal("1000"),
            reputation=1.0,
            role=ValidatorRole.VALIDATOR,
            last_proposed=0,
            is_active=True,
        )
        signed = _cross_view_event()
        # Craft the unsigned twin: identical dedup-key fields, no messages.
        unsigned_ep = {
            "kind": PBFT_CROSS_VIEW_VOTE_EQUIVOCATION,
            "sequence": SEQ,
            "phase": "commit",
            "views": [0, 1],
        }
        unsigned = type(signed)(
            validator_address=ADDR,
            condition=signed.condition,
            evidence=json.dumps(unsigned_ep, sort_keys=True),
            block_height=SEQ,
            timestamp=signed.timestamp,
            slash_rate=signed.slash_rate,
            hash_a=signed.hash_a,
            hash_b=signed.hash_b,
        )
        mgr.slashing_events = [unsigned]
        assert mgr.apply_slashing(validator, signed) is False  # dedup hit
        assert len(mgr.slashing_events) == 1
        assert event_signature_evidence(mgr.slashing_events[0]) is not None
        assert json.loads(mgr.slashing_events[0].evidence)["messages"]


# ---------------------------------------------------------------------------
# multi_validator_poa detection
# ---------------------------------------------------------------------------


class TestDetection:
    def test_cross_view_commit_pair_slashable_when_armed(self, armed):
        c = _poa(ADDR, ADDR2)
        stake_before = c.validators[ADDR].stake
        m_a = _PBFTMsg("commit", ADDR, 0, SEQ, HA, ADDR_KEY)
        m_b = _PBFTMsg("commit", ADDR, 1, SEQ, HB, ADDR_KEY)
        assert c.record_commit(ADDR, HA, 0, message=m_a) is True
        assert c.record_commit(ADDR, HB, 1, message=m_b) is True

        events = [e for e in c._slashing_manager.slashing_events if event_is_equivocation_claim(e)]
        assert len(events) == 1
        ev = events[0]
        ep = json.loads(ev.evidence)
        assert ep["kind"] == PBFT_CROSS_VIEW_VOTE_EQUIVOCATION
        assert ep["phase"] == "commit"
        assert ep["sequence"] == SEQ
        assert ev.block_height == SEQ
        assert ev.is_applied
        assert c.validators[ADDR].stake < stake_before
        assert event_signature_evidence(ev) is not None

    def test_same_hash_across_views_is_not_equivocation(self, armed):
        c = _poa(ADDR, ADDR2)
        m_a = _PBFTMsg("commit", ADDR, 0, SEQ, HA, ADDR_KEY)
        m_b = _PBFTMsg("commit", ADDR, 1, SEQ, HA, ADDR_KEY)
        assert c.record_commit(ADDR, HA, 0, message=m_a) is True
        assert c.record_commit(ADDR, HA, 1, message=m_b) is True
        assert c._slashing_manager.slashing_events == []

    def test_prepare_cross_view_conflict_never_scanned(self, armed):
        """Prepare votes legitimately rotate across views — no cross-view event."""
        c = _poa(ADDR, ADDR2)
        m_a = _PBFTMsg("prepare", ADDR, 0, SEQ, HA, ADDR_KEY)
        m_b = _PBFTMsg("prepare", ADDR, 1, SEQ, HB, ADDR_KEY)
        assert c.record_prepare(ADDR, HA, 0, message=m_a) is True
        assert c.record_prepare(ADDR, HB, 1, message=m_b) is True
        assert c._slashing_manager.slashing_events == []

    def test_unsigned_cross_view_commit_produces_no_event(self, armed):
        c = _poa(ADDR, ADDR2)
        assert c.record_commit(ADDR, HA, 0) is True  # no message= capture
        assert c.record_commit(ADDR, HB, 1) is True
        assert c._slashing_manager.slashing_events == []

    def test_missing_signature_fields_produce_no_event(self, armed):
        c = _poa(ADDR, ADDR2)
        m_a = _PBFTMsg("commit", ADDR, 0, SEQ, HA, ADDR_KEY)
        m_b = _PBFTMsg("commit", ADDR, 1, SEQ, HB, ADDR_KEY)
        m_b.signature = ""  # captured but unsigned — can never satisfy the gate
        assert c.record_commit(ADDR, HA, 0, message=m_a) is True
        assert c.record_commit(ADDR, HB, 1, message=m_b) is True
        assert c._slashing_manager.slashing_events == []

    def test_same_view_conflict_still_uses_vote_equivocation(self, armed):
        c = _poa(ADDR, ADDR2)
        m_a = _PBFTMsg("commit", ADDR, 2, SEQ, HA, ADDR_KEY)
        m_b = _PBFTMsg("commit", ADDR, 2, SEQ, HB, ADDR_KEY)
        assert c.record_commit(ADDR, HA, 2, message=m_a) is True
        assert c.record_commit(ADDR, HB, 2, message=m_b) is False  # same-round reject
        events = [e for e in c._slashing_manager.slashing_events if event_is_equivocation_claim(e)]
        assert len(events) == 1
        ep = json.loads(events[0].evidence)
        assert ep["kind"] == "vote_equivocation"  # unchanged legacy path
        assert events[0].block_height == 2  # legacy shape: height holds the view

    def test_dormant_when_gate_unset(self):
        assert settings.pbft_cross_view_commit_lock_height is None
        c = _poa(ADDR, ADDR2)
        m_a = _PBFTMsg("commit", ADDR, 0, SEQ, HA, ADDR_KEY)
        m_b = _PBFTMsg("commit", ADDR, 1, SEQ, HB, ADDR_KEY)
        assert c.record_commit(ADDR, HA, 0, message=m_a) is True
        assert c.record_commit(ADDR, HB, 1, message=m_b) is True
        assert c._slashing_manager.slashing_events == []

    def test_pre_threshold_sequence_not_scanned(self, armed):
        c = _poa(ADDR, ADDR2)
        m_a = _PBFTMsg("commit", ADDR, 0, SEQ - 1, HA, ADDR_KEY)
        m_b = _PBFTMsg("commit", ADDR, 1, SEQ - 1, HB, ADDR_KEY)
        assert c.record_commit(ADDR, HA, 0, message=m_a) is True
        assert c.record_commit(ADDR, HB, 1, message=m_b) is True
        assert c._slashing_manager.slashing_events == []

    def test_inner_sequence_gate_filters_when_detect_runs_unarmed(self, armed):
        """``detect_byzantine_behavior`` reached via the same-round path must
        still honor the per-record ``cross_view_commit_lock_active`` filter:
        a cross-view commit pair on an UNARMED sequence produces no
        cross-view event even though detection ran."""
        c = _poa(ADDR, ADDR2)
        # Gate armed at SEQ=10; every record below it.
        m_a = _PBFTMsg("commit", ADDR, 0, 5, HA, ADDR_KEY)
        m_c = _PBFTMsg("commit", ADDR, 1, 5, HC, ADDR_KEY)  # cross-view pair member
        m_b = _PBFTMsg("commit", ADDR, 0, 5, HB, ADDR_KEY)  # same-view conflict → triggers detect
        assert c.record_commit(ADDR, HA, 0, message=m_a) is True
        assert c.record_commit(ADDR, HC, 1, message=m_c) is True
        assert c.record_commit(ADDR, HB, 0, message=m_b) is False
        kinds = [json.loads(e.evidence).get("kind") for e in c._slashing_manager.slashing_events]
        assert PBFT_CROSS_VIEW_VOTE_EQUIVOCATION not in kinds
        # the same-round offense at view 0 is still recorded via the old path
        assert "vote_equivocation" in kinds

    def test_reobservation_dedups_to_one_event(self, armed):
        c = _poa(ADDR, ADDR2)
        m_a = _PBFTMsg("commit", ADDR, 0, SEQ, HA, ADDR_KEY)
        m_b = _PBFTMsg("commit", ADDR, 1, SEQ, HB, ADDR_KEY)
        c.record_commit(ADDR, HA, 0, message=m_a)
        c.record_commit(ADDR, HB, 1, message=m_b)
        # replay both votes — detection re-runs, dedup must hold
        c.record_commit(ADDR, HA, 0, message=m_a)
        c.record_commit(ADDR, HB, 1, message=m_b)
        equiv = [e for e in c._slashing_manager.slashing_events if event_is_equivocation_claim(e)]
        assert len(equiv) == 1

    def test_three_way_conflict_evidences_one_canonical_pair(self, armed):
        c = _poa(ADDR, ADDR2)
        for view, h in ((0, HA), (1, HB), (2, HC)):
            c.record_commit(ADDR, h, view, message=_PBFTMsg("commit", ADDR, view, SEQ, h, ADDR_KEY))
        equiv = [e for e in c._slashing_manager.slashing_events if event_is_equivocation_claim(e)]
        assert len(equiv) == 1
        ep = json.loads(equiv[0].evidence)
        assert ep["kind"] == PBFT_CROSS_VIEW_VOTE_EQUIVOCATION
        assert ep["views"] == [0, 1]  # lowest-view pair wins canonically


# ---------------------------------------------------------------------------
# deactivation_evidence verify matrix
# ---------------------------------------------------------------------------


class TestCrossViewVerify:
    APPLY = 20

    def _payload(self, **kwargs):
        event = _cross_view_event(**kwargs)
        mgr = SlashingManager()
        mgr.slashing_events = [event]
        return _v2_payload(mgr, kwargs.get("validator", ADDR))

    def _session(self, tmp_path, param_value: str | None, name: str = "cross.db"):
        session = Session(_engine(tmp_path, name=name))
        if param_value is not None:
            _seed_param(session, "test-chain", "validator_deactivation_pbft_cross_view_evidence_height", param_value)
        session.commit()
        return session

    @staticmethod
    def _rebind(payload: dict) -> dict:
        """Recompute evidence_hash over (possibly tampered) evidence records
        so the bundle binding still holds and the targeted check is what fires."""
        from aitbc_chain.consensus.slashing import SlashingCondition, SlashingEvent

        mgr = SlashingManager()
        mgr.slashing_events = [
            SlashingEvent(
                validator_address=r["validator_address"],
                condition=SlashingCondition(r["condition"]),
                evidence=r["evidence"],
                block_height=r["block_height"],
                timestamp=r["timestamp"],
                slash_rate=r["slash_rate"],
                round_number=r["round_number"],
                hash_a=r["hash_a"],
                hash_b=r["hash_b"],
            )
            for r in payload["evidence"]
        ]
        payload["evidence_hash"] = mgr.evidence_hash(payload["validator_address"])
        return payload

    def _verify(self, payload, session=None, block_height=APPLY):
        return verify_deactivation_evidence(
            payload,
            chain_id="test-chain",
            validator_addr=payload["validator_address"],
            evidence_hash=payload["evidence_hash"],
            session=session,
            block_height=block_height,
        )

    def test_armed_in_window_verifies(self, tmp_path):
        payload = self._payload()
        with self._session(tmp_path, "10") as session:
            assert self._verify(payload, session=session) is None

    def test_unset_param_fails_closed(self, tmp_path):
        payload = self._payload()
        with self._session(tmp_path, None) as session:
            reason = self._verify(payload, session=session)
        assert "not armed" in (reason or "")

    def test_malformed_param_fails_closed(self, tmp_path):
        payload = self._payload()
        with self._session(tmp_path, "not-a-height") as session:
            reason = self._verify(payload, session=session)
        assert "not armed" in (reason or "")

    def test_no_session_fails_closed(self):
        payload = self._payload()
        reason = self._verify(payload, session=None)
        assert "not armed" in (reason or "")

    def test_pre_activation_sequence_rejected(self, tmp_path):
        payload = self._payload(seq=5)  # below activation 10
        with self._session(tmp_path, "10") as session:
            reason = self._verify(payload, session=session)
        assert "outside the armed evidence window" in (reason or "")

    def test_sequence_above_apply_height_rejected(self, tmp_path):
        payload = self._payload(seq=30)  # above apply height 20; activation 10
        with self._session(tmp_path, "10") as session:
            reason = self._verify(payload, session=session, block_height=20)
        assert "outside the armed evidence window" in (reason or "")

    def test_apply_height_none_fails_closed(self, tmp_path):
        payload = self._payload()
        with self._session(tmp_path, "10") as session:
            reason = self._verify(payload, session=session, block_height=None)
        assert "outside the armed evidence window" in (reason or "")

    def test_prepare_phase_rejected(self, tmp_path):
        payload = self._payload(phase="prepare")
        with self._session(tmp_path, "10") as session:
            reason = self._verify(payload, session=session)
        assert "not commit-phase" in (reason or "")

    def test_same_view_pair_rejected(self, tmp_path):
        payload = self._payload(view_a=3, view_b=3)
        with self._session(tmp_path, "10") as session:
            reason = self._verify(payload, session=session)
        assert "not a cross-view commit pair" in (reason or "")

    def test_same_hash_pair_rejected(self, tmp_path):
        payload = self._payload(hash_a=HA, hash_b=HA)
        with self._session(tmp_path, "10") as session:
            reason = self._verify(payload, session=session)
        assert "not a cross-view commit pair" in (reason or "")

    def test_sequence_mismatch_rejected(self, tmp_path):
        payload = self._payload(seq=SEQ)
        # Tamper: message records claim a different sequence than the payload.
        for rec in payload["evidence"]:
            ep = json.loads(rec["evidence"])
            for m in ep["messages"]:
                m["sequence_number"] = SEQ + 1
            rec["evidence"] = json.dumps(ep, sort_keys=True)
        # Rebuild the hash over the tampered records so binding still holds
        # and the sequence check is what fires.
        mgr = SlashingManager()
        from aitbc_chain.consensus.slashing import SlashingEvent, SlashingCondition

        mgr.slashing_events = [
            SlashingEvent(
                validator_address=r["validator_address"],
                condition=SlashingCondition(r["condition"]),
                evidence=r["evidence"],
                block_height=r["block_height"],
                timestamp=r["timestamp"],
                slash_rate=r["slash_rate"],
                round_number=r["round_number"],
                hash_a=r["hash_a"],
                hash_b=r["hash_b"],
            )
            for r in payload["evidence"]
        ]
        payload["evidence_hash"] = mgr.evidence_hash(payload["validator_address"])
        with self._session(tmp_path, "10") as session:
            reason = self._verify(payload, session=session)
        assert "do not match the evidence sequence" in (reason or "")

    def test_event_height_mismatch_rejected(self, tmp_path):
        event = _cross_view_event(seq=SEQ)
        event.block_height = SEQ + 5  # evidence sequence no longer equals block_height
        mgr = SlashingManager()
        mgr.slashing_events = [event]
        payload = _v2_payload(mgr, ADDR)
        with self._session(tmp_path, "10") as session:
            reason = self._verify(payload, session=session)
        assert "does not match event block_height" in (reason or "")

    def test_bad_digest_rejected(self, tmp_path):
        payload = self._payload()
        for rec in payload["evidence"]:
            ep = json.loads(rec["evidence"])
            ep["messages"][1]["digest"] = "0x" + "00" * 32
            rec["evidence"] = json.dumps(ep, sort_keys=True)
        # rebind hash over tampered records
        from aitbc_chain.consensus.slashing import SlashingCondition, SlashingEvent

        mgr = SlashingManager()
        mgr.slashing_events = [
            SlashingEvent(
                validator_address=r["validator_address"],
                condition=SlashingCondition(r["condition"]),
                evidence=r["evidence"],
                block_height=r["block_height"],
                timestamp=r["timestamp"],
                slash_rate=r["slash_rate"],
                round_number=r["round_number"],
                hash_a=r["hash_a"],
                hash_b=r["hash_b"],
            )
            for r in payload["evidence"]
        ]
        payload["evidence_hash"] = mgr.evidence_hash(payload["validator_address"])
        with self._session(tmp_path, "10") as session:
            reason = self._verify(payload, session=session)
        assert "digest does not match" in (reason or "")

    def test_bad_signature_rejected(self, tmp_path):
        # Second commit signed by a different key than the sender claims.
        event = _cross_view_event()
        ep = json.loads(event.evidence)
        m_b = ep["messages"][1]
        wrong = _signed_fields(
            ep["messages"][0]["sender"], ADDR2_KEY, block_hash=m_b["block_hash"], seq=SEQ, view=m_b["view_number"]
        )
        ep["messages"][1] = wrong
        event.evidence = json.dumps(ep, sort_keys=True)
        mgr = SlashingManager()
        mgr.slashing_events = [event]
        payload = _v2_payload(mgr, ADDR)
        with self._session(tmp_path, "10") as session:
            reason = self._verify(payload, session=session)
        assert "signature verification failed" in (reason or "")

    def test_outsider_sender_rejected(self, tmp_path):
        event = _cross_view_event()
        ep = json.loads(event.evidence)
        m = dict(ep["messages"][0])
        m["sender"] = OUTSIDER  # claims a different sender entirely
        ep["messages"][0] = m
        event.evidence = json.dumps(ep, sort_keys=True)
        mgr = SlashingManager()
        mgr.slashing_events = [event]
        payload = _v2_payload(mgr, ADDR)
        with self._session(tmp_path, "10") as session:
            reason = self._verify(payload, session=session)
        assert "sender does not match" in (reason or "")

    def test_declared_views_mismatch_rejected(self, tmp_path):
        """``views`` is canonical evidence: a declared list that disagrees
        with the sorted message-record views must fail verification."""
        payload = self._payload()
        for rec in payload["evidence"]:
            ep = json.loads(rec["evidence"])
            ep["views"] = [0, 2]  # messages actually carry views [0, 1]
            rec["evidence"] = json.dumps(ep, sort_keys=True)
        payload = self._rebind(payload)
        with self._session(tmp_path, "10") as session:
            reason = self._verify(payload, session=session)
        assert "views do not match" in (reason or "")

    def test_evidence_hash_binding_still_enforced(self, tmp_path):
        payload = self._payload()
        payload["evidence_hash"] = "0x" + "ff" * 32
        with self._session(tmp_path, "10") as session:
            reason = self._verify(payload, session=session)
        assert "evidence_hash does not match" in (reason or "")


# ---------------------------------------------------------------------------
# Apply-path / replay gating
# ---------------------------------------------------------------------------


class TestApplyGate:
    @staticmethod
    def _markers(session: Session):
        return list(session.exec(select(ValidatorDeactivation).where(ValidatorDeactivation.chain_id == CHAIN)).all())

    @staticmethod
    def _provider_payload(seq: int = SEQ) -> dict:
        event = _cross_view_event(validator=PROVIDER, key=PROVIDER_KEY, seq=seq)
        mgr = SlashingManager()
        mgr.slashing_events = [event]
        payload = _v2_payload(mgr, PROVIDER)
        payload["bond_id"] = "bond-par-1"
        return payload

    def test_armed_apply_writes_marker(self, tmp_path):
        st = StateTransition()
        payload = self._provider_payload(seq=10)
        with Session(_engine(tmp_path)) as session:
            _seed_bond(session)
            _seed_authority(session)
            _seed_param(session, CHAIN, "validator_deactivation_evidence_required", "true")
            _seed_param(session, CHAIN, "validator_deactivation_pbft_cross_view_evidence_height", "10")
            session.commit()
            ok, msg = st.apply_transaction(
                session,
                CHAIN,
                _deactivation_tx(payload),
                tx_hash="cv-ok",
                block_version=22,
                block_height=20,
                block_time=BLOCK_TIME,
            )
            assert ok, msg
            markers = self._markers(session)
            assert len(markers) == 1
            assert markers[0].validator_address == canonical_address(PROVIDER)

    def test_replay_below_param_activation_rejected(self, tmp_path):
        """Param armed at height 10 but the block applies at height 5: the
        value is not yet in force for that height, so the claim is
        unverifiable — a marker that could never verify stays rejected."""
        st = StateTransition()
        payload = self._provider_payload(seq=10)
        with Session(_engine(tmp_path)) as session:
            _seed_bond(session)
            _seed_authority(session)
            _seed_param(session, CHAIN, "validator_deactivation_evidence_required", "true")
            _seed_param(
                session,
                CHAIN,
                "validator_deactivation_pbft_cross_view_evidence_height",
                "10",
                applied_height=10,
            )
            session.commit()
            ok, _msg = st.apply_transaction(
                session,
                CHAIN,
                _deactivation_tx(payload),
                tx_hash="cv-replay",
                block_version=22,
                block_height=5,
                block_time=BLOCK_TIME,
            )
            assert ok  # fee/nonce still apply; the marker is what is gated
            assert self._markers(session) == []

    def test_sequence_above_apply_height_rejected(self, tmp_path):
        st = StateTransition()
        payload = self._provider_payload(seq=10)
        with Session(_engine(tmp_path)) as session:
            _seed_bond(session)
            _seed_authority(session)
            _seed_param(session, CHAIN, "validator_deactivation_evidence_required", "true")
            _seed_param(session, CHAIN, "validator_deactivation_pbft_cross_view_evidence_height", "3")
            session.commit()
            # seq 10 >= activation 3 but > apply height 5 → outside window
            ok, _msg = st.apply_transaction(
                session,
                CHAIN,
                _deactivation_tx(payload),
                tx_hash="cv-future",
                block_version=22,
                block_height=5,
                block_time=BLOCK_TIME,
            )
            assert ok
            assert self._markers(session) == []

    def test_gate_disarmed_keeps_legacy_accept(self, tmp_path):
        """Without validator_deactivation_evidence_required the v1-style path
        is untouched — audit-only markers still apply (pre-#1263 semantics)."""
        st = StateTransition()
        with Session(_engine(tmp_path)) as session:
            _seed_bond(session)
            _seed_authority(session)
            session.commit()
            ok, msg = st.apply_transaction(
                session, CHAIN, _deactivation_tx(), tx_hash="cv-off", block_version=22, block_height=5, block_time=BLOCK_TIME
            )
            assert ok, msg
            assert len(self._markers(session)) == 1


# ---------------------------------------------------------------------------
# Persistence round-trip
# ---------------------------------------------------------------------------


class TestPersistenceRoundTrip:
    def test_cross_view_event_survives_save_load_byte_identical(self):
        event = _cross_view_event(view_a=2, view_b=5, seq=42)
        mgr = SlashingManager()
        mgr.slashing_events = [event]

        records = [slashing_event_record(e) for e in mgr.slashing_events]
        blob = json.loads(json.dumps(records))  # simulate slashing_events_json
        parsed = MultiValidatorPoA._parse_slashing_events(blob)
        assert len(parsed) == 1
        back = parsed[0]
        assert back.evidence == event.evidence  # byte-identical canonical JSON
        assert back.hash_a == event.hash_a and back.hash_b == event.hash_b
        assert back.round_number is None
        assert back.block_height == 42

        mgr2 = SlashingManager()
        mgr2.slashing_events = parsed
        assert mgr2.evidence_hash(ADDR) == mgr.evidence_hash(ADDR)

    def test_canonical_fields_populated_for_draft_bundle(self):
        """_canonical_evidence_fields must extract hash_a/hash_b from
        messages[] for the new kind so drafts stay canonical."""
        event = _cross_view_event()
        record = slashing_event_record(event)
        evidence, round_number, hash_a, hash_b = MultiValidatorPoA._canonical_evidence_fields(record)
        assert round_number is None
        assert hash_a == event.hash_a and hash_b == event.hash_b
        ep = json.loads(evidence)
        assert ep["kind"] == PBFT_CROSS_VIEW_VOTE_EQUIVOCATION
        assert [m["view_number"] for m in ep["messages"]] == sorted(m["view_number"] for m in ep["messages"])


# ---------------------------------------------------------------------------
# Draft-path exclusion: uncitable cross-view claims never enter v2 bundles
# ---------------------------------------------------------------------------


class TestDraftExclusion:
    """``draft_deactivation_txs``/``_deactivation_payload`` must not cite a
    cross-view equivocation claim the apply gate could never verify — an
    unverifiable equivocation claim fails the WHOLE marker."""

    HEAD = 30
    CUTOFF_SEQ = 5  # <= head - finality_depth(10) = 20, so it reaches the draft

    def _setup(self, monkeypatch, chain_id: str):
        monkeypatch.setattr(settings, "consensus_chain_slashing_enabled", True)
        _chain_db(chain_id)
        c = _consensus(chain_id, ADDR, V2)
        with session_scope(chain_id) as session:
            session.add(
                Block(
                    chain_id=chain_id,
                    height=self.HEAD,
                    hash="0x" + "dd" * 32,
                    parent_hash="0x" + "00" * 32,
                    proposer=V2,
                    timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                    tx_count=0,
                )
            )
            session.add(
                Bond(
                    chain_id=chain_id,
                    bond_id="bond-cv",
                    provider=ADDR,
                    amount=1000,
                    status="active",
                    created_at=datetime(2026, 1, 1, tzinfo=UTC),
                    updated_at=datetime(2026, 1, 1, tzinfo=UTC),
                )
            )
            session.commit()
        # A signed same-view vote equivocation guarantees a v2 draft regardless
        # of the cross-view claim's fate, so exclusion is observable in
        # payload["evidence"] rather than collapsing to v1.
        m1 = _signed_fields(ADDR, ADDR_KEY, block_hash=HA, seq=9, view=4)
        m2 = _signed_fields(ADDR, ADDR_KEY, block_hash=HB, seq=9, view=4)
        c._slashing_manager.slashing_events.append(c._slashing_manager.vote_equivocation_event(ADDR, 4, "commit", m1, m2))
        # The cross-view claim under test (sequence 5, views 0/1).
        c._slashing_manager.slashing_events.append(_cross_view_event(validator=ADDR, key=ADDR_KEY, seq=self.CUTOFF_SEQ))
        return c

    @staticmethod
    def _kinds(payload: dict) -> list:
        return [json.loads(e["evidence"]).get("kind") for e in payload.get("evidence", [])]

    def test_below_activation_excluded_from_v2(self, monkeypatch):
        chain_id = f"cv-draft-below-{uuid.uuid4().hex[:8]}"
        c = self._setup(monkeypatch, chain_id)
        with session_scope(chain_id) as session:
            _seed_param(session, chain_id, "validator_deactivation_pbft_cross_view_evidence_height", "10")
            session.commit()
        out = c.draft_deactivation_txs()
        assert len(out["drafts"]) == 1
        payload = out["drafts"][0]["payload"]
        assert payload["evidence_version"] == 2
        assert self._kinds(payload) == ["vote_equivocation"]

    def test_at_or_above_activation_included_in_v2(self, monkeypatch):
        chain_id = f"cv-draft-above-{uuid.uuid4().hex[:8]}"
        c = self._setup(monkeypatch, chain_id)
        with session_scope(chain_id) as session:
            _seed_param(session, chain_id, "validator_deactivation_pbft_cross_view_evidence_height", "5")
            session.commit()
        out = c.draft_deactivation_txs()
        assert len(out["drafts"]) == 1
        payload = out["drafts"][0]["payload"]
        assert payload["evidence_version"] == 2
        assert PBFT_CROSS_VIEW_VOTE_EQUIVOCATION in self._kinds(payload)

    def test_unset_param_excludes_cross_view_claim(self, monkeypatch):
        chain_id = f"cv-draft-unset-{uuid.uuid4().hex[:8]}"
        c = self._setup(monkeypatch, chain_id)
        out = c.draft_deactivation_txs()
        assert len(out["drafts"]) == 1
        payload = out["drafts"][0]["payload"]
        assert payload["evidence_version"] == 2
        assert self._kinds(payload) == ["vote_equivocation"]
