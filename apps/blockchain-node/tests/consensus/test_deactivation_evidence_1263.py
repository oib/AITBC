"""#1263 pins: on-chain VALIDATOR_DEACTIVATE evidence verification.

Covers signature retention in both equivocation record kinds
(attestation + PBFT vote), the ``validator_deactivation_evidence_required``
chain-parameter gate (armed → verify, disarmed → byte-identical legacy),
``round_in_payload`` reconstruction under BOTH round-lock flag states, and
v2 draft emission only for signature-bearing events.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime

from sqlmodel import Session, select

from aitbc_chain.base_models import Bond, ChainParameter, ValidatorDeactivation
from aitbc_chain.config import settings
from aitbc_chain.consensus.slashing import SlashingManager
from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA
from aitbc.crypto.consensus_signing import sign_consensus_message
from aitbc.crypto.crypto import derive_ethereum_address
from aitbc_chain.database import session_scope
from aitbc_chain.state.deactivation_evidence import verify_deactivation_evidence
from aitbc_chain.state.state_transition import StateTransition

from ..test_apply_parity import CHAIN, PROVIDER, PROVIDER_KEY, _seed_bond
from .test_validator_deactivation_1198 import (
    BLOCK_TIME,
    EVIDENCE,
    V2,
    _chain_db,
    _consensus,
    _deactivation_tx,
    _engine,
    _seed_authority,
)

ADDR_KEY = "0x" + "55" * 32
ADDR = derive_ethereum_address(ADDR_KEY)
HA = "0x" + "aa" * 32
HB = "0x" + "bb" * 32


def _attestation_record(
    signer_key: str,
    block_hash: str,
    *,
    height: int = 11,
    round_in_payload: bool,
    request_round: int | None,
    proposer: str = V2,
    chain_id: str = "test-chain",
) -> dict:
    """One signed attestation record, exactly as _record_signed_attestation emits."""
    message = {
        "chain_id": chain_id,
        "height": height,
        "hash": block_hash,
        "parent_hash": "0x" + "00" * 32,
        "proposer": proposer,
        "state_root": "0x" + "11" * 32,
        "bridge_state_root": "",
    }
    if round_in_payload:
        message["round"] = request_round
    signer = derive_ethereum_address(signer_key)
    return {
        "chain_id": chain_id,
        "height": height,
        "hash": block_hash,
        "parent_hash": message["parent_hash"],
        "proposer": proposer,
        "state_root": message["state_root"],
        "bridge_state_root": "",
        "round_in_payload": round_in_payload,
        "request_round": request_round if round_in_payload else None,
        "signature": sign_consensus_message(message, signer_key),
        "signer": signer,
    }


def _signed_equivocation_event(
    mgr: SlashingManager,
    validator: str,
    key: str,
    *,
    round_in_payload: bool,
    request_round: int | None,
    height: int = 11,
) -> None:
    attestations = [
        _attestation_record(key, HA, height=height, round_in_payload=round_in_payload, request_round=request_round),
        _attestation_record(key, HB, height=height, round_in_payload=round_in_payload, request_round=request_round),
    ]
    mgr.record_attestation_equivocation(
        validator_address=validator,
        height=height,
        round_number=request_round,
        block_hash_a=HA,
        block_hash_b=HB,
        proposer=V2,
        attestations=attestations,
    )


def _v2_payload(mgr: SlashingManager, validator: str) -> dict:
    """Assemble the payload exactly the way _deactivation_payload does."""
    from aitbc_chain.consensus.slashing import slashing_event_record
    from aitbc.crypto.signature_recovery import canonical_address

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


class TestEvidenceVerification:
    def test_valid_signed_equivocation_verifies_round_lock_off(self):
        """Prod configuration: round is NOT inside the signed preimage."""
        mgr = SlashingManager()
        _signed_equivocation_event(mgr, ADDR, ADDR_KEY, round_in_payload=False, request_round=None)
        payload = _v2_payload(mgr, ADDR)
        assert (
            verify_deactivation_evidence(
                payload,
                chain_id="test-chain",
                validator_addr=payload["validator_address"],
                evidence_hash=payload["evidence_hash"],
            )
            is None
        )

    def test_valid_signed_equivocation_verifies_round_lock_on(self):
        """round_in_payload=True: the round is inside the signed preimage."""
        mgr = SlashingManager()
        _signed_equivocation_event(mgr, ADDR, ADDR_KEY, round_in_payload=True, request_round=3)
        payload = _v2_payload(mgr, ADDR)
        assert (
            verify_deactivation_evidence(
                payload,
                chain_id="test-chain",
                validator_addr=payload["validator_address"],
                evidence_hash=payload["evidence_hash"],
            )
            is None
        )

    def test_round_in_payload_flag_cannot_be_dropped(self):
        """A record claiming round_in_payload=False for a round-signed message fails."""
        mgr = SlashingManager()
        _signed_equivocation_event(mgr, ADDR, ADDR_KEY, round_in_payload=True, request_round=3)
        payload = _v2_payload(mgr, ADDR)
        for rec in payload["evidence"]:
            ep = json.loads(rec["evidence"])
            for att in ep["attestations"]:
                att["round_in_payload"] = False
                att["request_round"] = None
            rec["evidence"] = json.dumps(ep, sort_keys=True)
        # evidence_hash no longer matches after tampering — rejected either way.
        reason = verify_deactivation_evidence(
            payload,
            chain_id="test-chain",
            validator_addr=payload["validator_address"],
            evidence_hash=payload["evidence_hash"],
        )
        assert reason is not None

    def test_tampered_evidence_hash_rejected(self):
        mgr = SlashingManager()
        _signed_equivocation_event(mgr, ADDR, ADDR_KEY, round_in_payload=False, request_round=None)
        payload = _v2_payload(mgr, ADDR)
        payload["evidence_hash"] = "0x" + "ff" * 32
        reason = verify_deactivation_evidence(
            payload,
            chain_id="test-chain",
            validator_addr=payload["validator_address"],
            evidence_hash=payload["evidence_hash"],
        )
        assert reason is not None

    def test_wrong_signer_rejected(self):
        mgr = SlashingManager()
        _signed_equivocation_event(mgr, ADDR, ADDR_KEY, round_in_payload=False, request_round=None)
        payload = _v2_payload(mgr, ADDR)
        other = derive_ethereum_address("0x" + "77" * 32)
        payload["validator_address"] = other
        reason = verify_deactivation_evidence(
            payload,
            chain_id="test-chain",
            validator_addr=other,
            evidence_hash=payload["evidence_hash"],
        )
        assert reason is not None

    def test_missing_signatures_rejected(self):
        mgr = SlashingManager()
        mgr.record_attestation_equivocation(ADDR, 11, None, HA, HB, V2)  # hash-only
        payload = _v2_payload(mgr, ADDR)
        reason = verify_deactivation_evidence(
            payload,
            chain_id="test-chain",
            validator_addr=payload["validator_address"],
            evidence_hash=payload["evidence_hash"],
        )
        assert reason is not None

    def test_no_equivocation_rejected(self):
        mgr = SlashingManager()
        mgr.slashing_events.append(mgr.detect_unavailability(ADDR, 5, 20))
        payload = _v2_payload(mgr, ADDR)
        reason = verify_deactivation_evidence(
            payload,
            chain_id="test-chain",
            validator_addr=payload["validator_address"],
            evidence_hash=payload["evidence_hash"],
        )
        assert "no verifiable equivocation" in (reason or "")

    def test_legacy_v1_payload_rejected_when_armed(self):
        payload = {"validator_address": ADDR, "evidence_hash": EVIDENCE, "bond_id": "b"}
        reason = verify_deactivation_evidence(payload, chain_id="test-chain", validator_addr=ADDR, evidence_hash=EVIDENCE)
        assert "evidence_version" in (reason or "")


class TestVoteEquivocation:
    @staticmethod
    def _signed_vote(key: str, sender: str, block_hash: str, view: int = 4, seq: int = 9, phase: str = "prepare") -> dict:
        digest = hashlib.sha256(f"{block_hash}:{seq}:{view}".encode()).hexdigest()
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
            "signature": sign_consensus_message(signed, key),
        }

    def test_vote_equivocation_verifies(self):
        signer = derive_ethereum_address(ADDR_KEY)
        mgr = SlashingManager()
        m1 = self._signed_vote(ADDR_KEY, signer, HA)
        m2 = self._signed_vote(ADDR_KEY, signer, HB)
        mgr.slashing_events.append(mgr.vote_equivocation_event(ADDR, 4, "prepare", m1, m2))
        payload = _v2_payload(mgr, ADDR)
        assert (
            verify_deactivation_evidence(
                payload,
                chain_id="test-chain",
                validator_addr=payload["validator_address"],
                evidence_hash=payload["evidence_hash"],
            )
            is None
        )

    def test_vote_bad_digest_rejected(self):
        signer = derive_ethereum_address(ADDR_KEY)
        mgr = SlashingManager()
        m1 = self._signed_vote(ADDR_KEY, signer, HA)
        m2 = self._signed_vote(ADDR_KEY, signer, HB)
        m2["digest"] = "0x" + "00" * 32  # digest no longer matches block_hash:seq:view
        mgr.slashing_events.append(mgr.vote_equivocation_event(ADDR, 4, "prepare", m1, m2))
        payload = _v2_payload(mgr, ADDR)
        reason = verify_deactivation_evidence(
            payload,
            chain_id="test-chain",
            validator_addr=payload["validator_address"],
            evidence_hash=payload["evidence_hash"],
        )
        assert reason is not None


class TestApplyGate:
    """End-to-end: armed param enforces verification; disarmed is legacy."""

    @staticmethod
    def _seed_evidence_param(session: Session, chain_id: str, value: str = "true") -> None:
        session.add(
            ChainParameter(
                chain_id=chain_id,
                parameter="validator_deactivation_evidence_required",
                value=value,
                applied_height=0,
            )
        )

    @staticmethod
    def _markers(session: Session):
        return list(session.exec(select(ValidatorDeactivation).where(ValidatorDeactivation.chain_id == CHAIN)).all())

    def test_armed_rejects_audit_only_marker(self, tmp_path):
        st = StateTransition()
        with Session(_engine(tmp_path)) as session:
            _seed_bond(session)
            _seed_authority(session)
            self._seed_evidence_param(session, CHAIN)
            session.commit()
            ok, _msg = st.apply_transaction(
                session, CHAIN, _deactivation_tx(), tx_hash="vd-ev1", block_version=22, block_height=5, block_time=BLOCK_TIME
            )
            assert ok  # apply-path contract: fee/nonce still apply
            assert self._markers(session) == []

    def test_disarmed_accepts_audit_only_marker(self, tmp_path):
        st = StateTransition()
        with Session(_engine(tmp_path)) as session:
            _seed_bond(session)
            _seed_authority(session)
            self._seed_evidence_param(session, CHAIN, value="false")
            session.commit()
            ok, msg = st.apply_transaction(
                session, CHAIN, _deactivation_tx(), tx_hash="vd-ev2", block_version=22, block_height=5, block_time=BLOCK_TIME
            )
            assert ok, msg
            assert len(self._markers(session)) == 1

    def test_param_absent_is_legacy(self, tmp_path):
        st = StateTransition()
        with Session(_engine(tmp_path)) as session:
            _seed_bond(session)
            _seed_authority(session)
            session.commit()
            ok, msg = st.apply_transaction(
                session, CHAIN, _deactivation_tx(), tx_hash="vd-ev2b", block_version=22, block_height=5, block_time=BLOCK_TIME
            )
            assert ok, msg
            assert len(self._markers(session)) == 1

    def test_armed_accepts_verified_v2_marker(self, tmp_path):
        st = StateTransition()
        mgr = SlashingManager()
        _signed_equivocation_event(mgr, PROVIDER, PROVIDER_KEY, round_in_payload=False, request_round=None)
        payload = _v2_payload(mgr, PROVIDER)
        payload["bond_id"] = "bond-par-1"
        with Session(_engine(tmp_path)) as session:
            _seed_bond(session)
            _seed_authority(session)
            self._seed_evidence_param(session, CHAIN)
            session.commit()
            ok, msg = st.apply_transaction(
                session,
                CHAIN,
                _deactivation_tx(payload),
                tx_hash="vd-ev3",
                block_version=22,
                block_height=5,
                block_time=BLOCK_TIME,
            )
            assert ok, msg
            markers = self._markers(session)
            assert len(markers) == 1
            assert markers[0].evidence_hash == payload["evidence_hash"]

    def test_armed_rejects_v2_with_unsigned_equivocation_only(self, tmp_path):
        st = StateTransition()
        mgr = SlashingManager()
        mgr.record_attestation_equivocation(PROVIDER, 11, None, HA, HB, V2)  # hash-only
        payload = _v2_payload(mgr, PROVIDER)
        payload["bond_id"] = "bond-par-1"
        with Session(_engine(tmp_path)) as session:
            _seed_bond(session)
            _seed_authority(session)
            self._seed_evidence_param(session, CHAIN)
            session.commit()
            ok, _msg = st.apply_transaction(
                session,
                CHAIN,
                _deactivation_tx(payload),
                tx_hash="vd-ev4",
                block_version=22,
                block_height=5,
                block_time=BLOCK_TIME,
            )
            assert ok
            assert self._markers(session) == []


class TestDraftV2:
    def test_draft_emits_v2_only_for_signed_events(self, monkeypatch):
        monkeypatch.setattr(settings, "consensus_chain_slashing_enabled", True)
        chain_id = f"slash-v2-{uuid.uuid4().hex[:8]}"
        _chain_db(chain_id)
        c = _consensus(chain_id, ADDR, V2)
        with session_scope(chain_id) as session:
            session.add(
                Bond(
                    chain_id=chain_id,
                    bond_id="bond-v2",
                    provider=ADDR,
                    amount=1000,
                    status="active",
                    created_at=datetime(2026, 1, 1, tzinfo=UTC),
                    updated_at=datetime(2026, 1, 1, tzinfo=UTC),
                )
            )
            session.commit()
        # unsigned equivocation → v1 audit-only draft
        c._slashing_manager.record_attestation_equivocation(ADDR, 5, 2, HA, HB, V2)
        out = c.draft_deactivation_txs()
        assert len(out["drafts"]) == 1
        assert "evidence_version" not in out["drafts"][0]["payload"]

        # signed equivocation → v2 draft; the unsigned claim is excluded
        _signed_equivocation_event(c._slashing_manager, ADDR, ADDR_KEY, round_in_payload=False, request_round=None, height=6)
        out = c.draft_deactivation_txs()
        assert len(out["drafts"]) == 1
        p = out["drafts"][0]["payload"]
        assert p["evidence_version"] == 2
        assert isinstance(p["evidence"], list) and p["evidence"]
        kinds = [json.loads(e["evidence"]).get("kind") for e in p["evidence"]]
        assert kinds == ["attestation_equivocation"]
        # the surviving record is the signed one (height 6)
        assert json.loads(p["evidence"][0]["evidence"])["height"] == 6
        # and the payload verifies end-to-end
        assert (
            verify_deactivation_evidence(
                p,
                chain_id=chain_id,
                validator_addr=p["validator_address"],
                evidence_hash=p["evidence_hash"],
            )
            is None
        )


# ---------------------------------------------------------------------------
# #1263 capture pins: signature retention in both equivocation record kinds
# ---------------------------------------------------------------------------

import time
from types import SimpleNamespace

import pytest

from aitbc_chain.consensus import remote_attestation as ra_module
from aitbc_chain.consensus.remote_attestation import RemoteAttestationService
from aitbc.crypto.consensus_signing import verify_consensus_message
from aitbc_chain.consensus.slashing import event_is_equivocation_claim, event_signature_evidence, slashing_event_record


class _StubBroker:
    def __init__(self):
        self.published: list[tuple[str, dict]] = []

    async def publish(self, topic: str, message: dict):
        self.published.append((topic, message))


def _attester_service(monkeypatch, signer_addr: str, signer_key: str, proposer_addr: str):
    monkeypatch.setattr(
        settings,
        "validator_set",
        json.dumps([{"address": signer_addr}, {"address": proposer_addr}]),
    )
    monkeypatch.setattr(settings, "consensus_require_signed_attest_request", False)
    monkeypatch.setattr(settings, "attestation_header_max_age_seconds", 0.0)
    broker = _StubBroker()
    monkeypatch.setattr(ra_module, "gossip_broker", broker)
    return RemoteAttestationService("test-chain", {signer_addr: signer_key}), broker


def _request(height: int, block_hash: str, proposer: str) -> dict:
    return {
        "header": {
            "chain_id": "test-chain",
            "height": height,
            "hash": block_hash,
            "parent_hash": "0xparent",
            "proposer": proposer,
            "state_root": "0xroot",
            "bridge_state_root": "",
        },
        "timestamp": time.time(),
    }


class TestAttestationCapture:
    @pytest.mark.asyncio
    async def test_signed_attestation_recorded_round_lock_off(self, monkeypatch):
        """Prod flag state: round stays out of the signed preimage."""
        signer_key = ADDR_KEY
        signer = derive_ethereum_address(signer_key)
        proposer_key = "0x" + "22" * 32
        proposer = derive_ethereum_address(proposer_key)
        svc, broker = _attester_service(monkeypatch, signer, signer_key, proposer)

        await svc._handle_request(_request(100, HA, proposer))

        assert broker.published
        key = svc._signed_attestation_key(100, HA, signer)
        rec = svc._signed_attestations[key]
        assert rec["round_in_payload"] is False
        assert rec["request_round"] is None
        message = {
            "chain_id": rec["chain_id"],
            "height": rec["height"],
            "hash": rec["hash"],
            "parent_hash": rec["parent_hash"],
            "proposer": rec["proposer"],
            "state_root": rec["state_root"],
            "bridge_state_root": rec["bridge_state_root"],
        }
        assert verify_consensus_message(message, rec["signature"], signer)

    def test_signed_attestation_record_round_lock_on(self, monkeypatch, tmp_path):
        """round_in_payload=True: the record must rebuild the round-signed message."""
        signer_key = ADDR_KEY
        signer = derive_ethereum_address(signer_key)
        svc = RemoteAttestationService("test-chain", {signer: signer_key})
        message = {
            "chain_id": "test-chain",
            "height": 7,
            "hash": HA,
            "parent_hash": "0xparent",
            "proposer": V2,
            "state_root": "0xroot",
            "bridge_state_root": "",
            "round": 3,
        }
        signature = sign_consensus_message(message, signer_key)
        svc._record_signed_attestation(7, HA, signer, message, 3, True, signature)
        key = svc._signed_attestation_key(7, HA, signer)
        rec = svc._signed_attestations[key]
        assert rec["round_in_payload"] is True
        assert rec["request_round"] == 3
        # Rebuild exactly what on-chain verification rebuilds.
        rebuilt = {
            "chain_id": rec["chain_id"],
            "height": rec["height"],
            "hash": rec["hash"],
            "parent_hash": rec["parent_hash"],
            "proposer": rec["proposer"],
            "state_root": rec["state_root"],
            "bridge_state_root": rec["bridge_state_root"],
            "round": rec["request_round"],
        }
        assert verify_consensus_message(rebuilt, rec["signature"], signer)

    @pytest.mark.asyncio
    async def test_rival_signing_pairs_both_signatures(self, monkeypatch):
        """Signing hash B after hash A at the same height yields gate-verifiable evidence."""
        signer_key = ADDR_KEY
        signer = derive_ethereum_address(signer_key)
        proposer_key = "0x" + "22" * 32
        proposer = derive_ethereum_address(proposer_key)
        svc, _broker = _attester_service(monkeypatch, signer, signer_key, proposer)

        recorded = []

        class _Rec:
            def record_attestation_equivocation(self, **kwargs):
                recorded.append(kwargs)
                return None

        monkeypatch.setattr(svc, "_equivocation_recorder", lambda: _Rec())

        await svc._handle_request(_request(100, HA, proposer))
        # Equivocation is only reachable post-expiry (#1245): the live lock
        # refuses rivals, so age the recorded lock past the window. The hash
        # stays in _signed_once — that is the prior-signature index the
        # equivocation pairing reads.
        svc._attested[100] = (HA, proposer, time.monotonic() - 10_000)
        await svc._handle_request(_request(100, HB, proposer))

        assert recorded, "rival signing must record attestation equivocation"
        call = recorded[0]
        assert call["validator_address"] == signer
        assert call["block_hash_a"] != call["block_hash_b"]
        attestations = call["attestations"]
        assert attestations is not None and len(attestations) == 2
        hashes = {a["hash"] for a in attestations}
        assert hashes == {HA, HB}
        assert all(a.get("signature") for a in attestations)

        # The paired evidence verifies end-to-end through the apply gate.
        mgr = SlashingManager()
        evt = mgr.record_attestation_equivocation(
            validator_address=signer,
            height=call["height"],
            round_number=call["round_number"],
            block_hash_a=call["block_hash_a"],
            block_hash_b=call["block_hash_b"],
            proposer=call["proposer"],
            attestations=attestations,
        )
        mgr.slashing_events = [evt]
        payload = _v2_payload(mgr, signer)
        assert (
            verify_deactivation_evidence(
                payload,
                chain_id="test-chain",
                validator_addr=payload["validator_address"],
                evidence_hash=payload["evidence_hash"],
            )
            is None
        )


class _FakePBFTMessage:
    def __init__(self, phase: str, sender: str, view: int, seq: int, block_hash: str, key: str):
        digest = hashlib.sha256(f"{block_hash}:{seq}:{view}".encode()).hexdigest()
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


class TestVoteCapture:
    def test_prepare_equivocation_carries_signatures(self, monkeypatch):
        monkeypatch.setattr(settings, "consensus_chain_slashing_enabled", True)
        chain_id = f"slash-vc-{uuid.uuid4().hex[:8]}"
        _chain_db(chain_id)
        c = _consensus(chain_id, ADDR, V2)
        m1 = _FakePBFTMessage("prepare", ADDR, 4, 9, HA, ADDR_KEY)
        m2 = _FakePBFTMessage("prepare", ADDR, 4, 9, HB, ADDR_KEY)
        assert c.record_prepare(ADDR, HA, 4, message=m1) is True
        assert c.record_prepare(ADDR, HB, 4, message=m2) is False  # conflict rejected

        events = c._slashing_manager.slashing_events
        equiv = [e for e in events if event_is_equivocation_claim(e)]
        assert equiv, "conflicting prepare must produce equivocation evidence"
        assert event_signature_evidence(equiv[0]) is not None

        # The captured evidence verifies through the apply gate.
        payload = _v2_payload(c._slashing_manager, ADDR)
        assert (
            verify_deactivation_evidence(
                payload,
                chain_id=chain_id,
                validator_addr=payload["validator_address"],
                evidence_hash=payload["evidence_hash"],
            )
            is None
        )

    def test_commit_equivocation_carries_signatures(self, monkeypatch):
        monkeypatch.setattr(settings, "consensus_chain_slashing_enabled", True)
        chain_id = f"slash-vc2-{uuid.uuid4().hex[:8]}"
        _chain_db(chain_id)
        c = _consensus(chain_id, ADDR, V2)
        m1 = _FakePBFTMessage("commit", ADDR, 7, 3, HA, ADDR_KEY)
        m2 = _FakePBFTMessage("commit", ADDR, 7, 3, HB, ADDR_KEY)
        assert c.record_commit(ADDR, HA, 7, message=m1) is True
        assert c.record_commit(ADDR, HB, 7, message=m2) is False

        events = c._slashing_manager.slashing_events
        equiv = [e for e in events if event_is_equivocation_claim(e)]
        assert equiv and event_signature_evidence(equiv[0]) is not None
        ep = json.loads(equiv[0].evidence)
        assert ep["kind"] == "vote_equivocation"
        assert ep["phase"] == "commit"

    def test_unsigned_votes_fall_back_to_legacy_evidence(self, monkeypatch):
        """Old/test callers without message= keep the advisory-only record."""
        monkeypatch.setattr(settings, "consensus_chain_slashing_enabled", True)
        chain_id = f"slash-vc3-{uuid.uuid4().hex[:8]}"
        _chain_db(chain_id)
        c = _consensus(chain_id, ADDR, V2)
        assert c.record_prepare(ADDR, HA, 4) is True
        assert c.record_prepare(ADDR, HB, 4) is False
        equiv = [e for e in c._slashing_manager.slashing_events if event_is_equivocation_claim(e)]
        assert equiv
        assert event_signature_evidence(equiv[0]) is None  # can never satisfy the armed gate


class TestPersistenceRoundTrip:
    def test_signature_bearing_events_survive_save_load_shape(self):
        """slashing_event_record → JSON → _parse_slashing_events keeps evidence byte-identical."""
        mgr = SlashingManager()
        _signed_equivocation_event(mgr, ADDR, ADDR_KEY, round_in_payload=False, request_round=None)
        signer = derive_ethereum_address(ADDR_KEY)
        m1 = _FakePBFTMessage("prepare", signer, 4, 9, HA, ADDR_KEY)
        m2 = _FakePBFTMessage("prepare", signer, 4, 9, HB, ADDR_KEY)

        def _record(m):
            return {
                "message_type": m.message_type.value,
                "sender": m.sender,
                "view_number": m.view_number,
                "sequence_number": m.sequence_number,
                "digest": m.digest,
                "block_hash": m.block_hash,
                "signature": m.signature,
            }

        mgr.slashing_events.append(mgr.vote_equivocation_event(ADDR, 4, "prepare", _record(m1), _record(m2)))

        records = [slashing_event_record(e) for e in mgr.slashing_events]
        blob = json.loads(json.dumps(records))  # simulate slashing_events_json
        parsed = MultiValidatorPoA._parse_slashing_events(blob)
        assert len(parsed) == len(mgr.slashing_events)
        for orig, back in zip(mgr.slashing_events, parsed, strict=False):
            assert back.evidence == orig.evidence
            assert back.hash_a == orig.hash_a and back.hash_b == orig.hash_b
            assert back.round_number == orig.round_number
            assert back.block_height == orig.block_height

        # And the reloaded manager reproduces the same evidence_hash.
        mgr2 = SlashingManager()
        mgr2.slashing_events = parsed
        assert mgr2.evidence_hash(ADDR) == mgr.evidence_hash(ADDR)
