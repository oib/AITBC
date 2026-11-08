"""#1206 pins: canonical slashing evidence (#1206 Option A).

Covers the determinism ruling: ``evidence_hash``/``evidence_bundle`` exclude
wall-clock timestamps and locally-mutated stake fields, equivocation hash
pairs are canonically ordered, re-observation dedups (no double-append,
no double-slash), legacy persisted records canonicalize on load, and
``draft_deactivation_txs`` only cites evidence sealed below the finality
depth.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal


from aitbc_chain.base_models import Block, Bond, ConsensusState
from aitbc_chain.config import settings
from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA, Validator, ValidatorRole
from aitbc_chain.consensus.slashing import SlashingCondition, SlashingManager
from aitbc_chain.database import session_scope

from .test_validator_deactivation_1198 import V2, _chain_db, _consensus

ADDR = "0x" + "d4" * 20
HA = "0x" + "aa" * 32
HB = "0x" + "bb" * 32
HC = "0x" + "cc" * 32


def _equivocation(mgr: SlashingManager, *, a: str = HA, b: str = HB, height: int = 11, round_number: int | None = 2):
    return mgr.record_attestation_equivocation(
        validator_address=ADDR, height=height, round_number=round_number, block_hash_a=a, block_hash_b=b, proposer=V2
    )


class TestCanonicalEvidenceHash:
    def test_hash_ignores_timestamp_and_local_stake(self):
        """Same logical evidence recorded at different times / after different
        local stake mutations must hash identically — the #1206 divergence."""
        m1 = SlashingManager()
        e1 = _equivocation(m1)
        e1.timestamp = 111.0
        e1.stake_before = Decimal("1000")
        e1.slashed_amount = Decimal("500")

        m2 = SlashingManager()
        e2 = _equivocation(m2)
        e2.timestamp = 999999.0
        e2.stake_before = Decimal("42")
        e2.slashed_amount = Decimal("1")

        assert m1.evidence_hash(ADDR) == m2.evidence_hash(ADDR)

    def test_bundle_excludes_local_fields(self):
        mgr = SlashingManager()
        _equivocation(mgr)
        bundle = mgr.evidence_bundle(ADDR)
        assert len(bundle["events"]) == 1
        ev = bundle["events"][0]
        assert "timestamp" not in ev
        assert "stake_before" not in ev
        assert "slashed_amount" not in ev
        assert ev["round_number"] == 2
        assert ev["hash_a"] == HA
        assert ev["hash_b"] == HB

    def test_equivocation_hash_pair_order_canonical(self):
        """(a,b) and (b,a) are the same offense — identical evidence + hash."""
        m1 = SlashingManager()
        _equivocation(m1, a=HA, b=HB)
        m2 = SlashingManager()
        _equivocation(m2, a=HB, b=HA)
        assert m1.evidence_hash(ADDR) == m2.evidence_hash(ADDR)
        # And inside the stored evidence JSON the pair is sorted.
        assert '"block_hash_a": "0x' + "aa" in m1.slashing_events[0].evidence

    def test_double_sign_evidence_order_canonical(self):
        m1 = SlashingManager()
        e1 = m1.detect_double_sign(ADDR, HA, HB, 7)
        m2 = SlashingManager()
        e2 = m2.detect_double_sign(ADDR, HB, HA, 7)
        assert e1 is not None and e2 is not None
        assert e1.evidence == e2.evidence
        assert (e1.hash_a, e1.hash_b) == (e2.hash_a, e2.hash_b) == (HA, HB)


class TestDedup:
    def test_equivocation_reobservation_dedups(self):
        mgr = SlashingManager()
        first = _equivocation(mgr)
        # Same offense observed again — reversed hash order, later wall-clock.
        second = _equivocation(mgr, a=HB, b=HA)
        assert second is first
        assert len(mgr.slashing_events) == 1

    def test_equivocation_different_round_not_deduped(self):
        mgr = SlashingManager()
        _equivocation(mgr, round_number=2)
        _equivocation(mgr, round_number=3)
        assert len(mgr.slashing_events) == 2

    def test_apply_slashing_dedup_no_double_slash(self):
        """Re-observed equivocation must not slash twice."""
        mgr = SlashingManager()
        validator = Validator(
            address=ADDR, stake=Decimal("1000"), reputation=1.0, role=ValidatorRole.VALIDATOR, last_proposed=0, is_active=True
        )
        e1 = mgr.detect_double_sign(ADDR, HA, HB, 7)
        assert mgr.apply_slashing(validator, e1) is True
        stake_after_first = validator.stake
        e2 = mgr.detect_double_sign(ADDR, HB, HA, 7)  # same offense, reversed order
        assert mgr.apply_slashing(validator, e2) is False
        assert validator.stake == stake_after_first
        assert len(mgr.slashing_events) == 1

    def test_dedup_key_survives_save_load(self):
        """A re-observation after restart (events reloaded from DB) still dedups."""
        chain_id = f"slash-det-{uuid.uuid4().hex[:8]}"
        _chain_db(chain_id)
        c = _consensus(chain_id, ADDR, V2)
        c.record_attestation_equivocation(ADDR, 11, 2, HA, HB, V2)
        assert len(c._slashing_manager.slashing_events) == 1
        c2 = MultiValidatorPoA(chain_id)
        c2.record_attestation_equivocation(ADDR, 11, 2, HB, HA, V2)
        assert len(c2._slashing_manager.slashing_events) == 1


class TestPersistenceCanonicalization:
    def test_legacy_equivocation_record_canonicalized_on_load(self):
        """Pre-#1206 rows stored hashes in observation order with no structured
        fields; load must canonicalize so the hash matches a fresh record."""
        chain_id = f"slash-leg-{uuid.uuid4().hex[:8]}"
        _chain_db(chain_id)
        legacy_evidence = json.dumps(
            {
                "kind": "attestation_equivocation",
                "height": 11,
                "round": 2,
                "block_hash_a": HB,  # unsorted: b before a
                "block_hash_b": HA,
                "proposer": V2,
            },
            sort_keys=True,
        )
        with session_scope(chain_id) as session:
            session.add(
                ConsensusState(
                    chain_id=chain_id,
                    current_view=0,
                    current_sequence=0,
                    current_epoch=0,
                    validator_set_json="{}",
                    slashing_events_json=json.dumps(
                        [
                            {
                                "validator_address": ADDR,
                                "condition": SlashingCondition.DOUBLE_SIGN.value,
                                "evidence": legacy_evidence,
                                "block_height": 11,
                                "timestamp": 123.0,
                                "slash_rate": 0.5,
                                "stake_before": None,
                                "slashed_amount": None,
                            }
                        ]
                    ),
                )
            )
            session.commit()
        c = MultiValidatorPoA(chain_id)
        loaded = c._slashing_manager.slashing_events[0]
        assert (loaded.hash_a, loaded.hash_b) == (HA, HB)
        assert loaded.round_number == 2

        fresh = SlashingManager()
        _equivocation(fresh)
        assert c._slashing_manager.evidence_hash(ADDR) == fresh.evidence_hash(ADDR)

    def test_save_load_hash_stable(self):
        chain_id = f"slash-rt-{uuid.uuid4().hex[:8]}"
        _chain_db(chain_id)
        c = _consensus(chain_id, ADDR, V2)
        c.record_attestation_equivocation(ADDR, 11, 2, HA, HB, V2)
        h1 = c._slashing_manager.evidence_hash(ADDR)
        c2 = MultiValidatorPoA(chain_id)
        assert c2._slashing_manager.evidence_hash(ADDR) == h1


class TestFinalityDepthFilter:
    def _add_block(self, chain_id: str, height: int) -> None:
        with session_scope(chain_id) as session:
            session.add(
                Block(
                    chain_id=chain_id,
                    height=height,
                    hash="0x" + f"{height:064x}",
                    parent_hash="0x" + f"{height - 1:064x}",
                    proposer=V2,
                    timestamp=datetime(2026, 11, 8, tzinfo=UTC),
                )
            )
            session.commit()

    def _bonded_consensus(self, chain_id: str):
        c = _consensus(chain_id, ADDR, V2)
        with session_scope(chain_id) as session:
            session.add(
                Bond(
                    chain_id=chain_id,
                    bond_id="bond-det-1",
                    provider=ADDR,
                    amount=1000,
                    status="active",
                    created_at=datetime(2026, 1, 1, tzinfo=UTC),
                    updated_at=datetime(2026, 1, 1, tzinfo=UTC),
                )
            )
            session.commit()
        return c

    def test_bundle_max_block_height(self):
        mgr = SlashingManager()
        _equivocation(mgr, height=5)
        _equivocation(mgr, height=20, round_number=4, a=HC, b=HA)
        assert len(mgr.evidence_bundle(ADDR)["events"]) == 2
        assert len(mgr.evidence_bundle(ADDR, max_block_height=10)["events"]) == 1
        assert mgr.evidence_hash(ADDR) != mgr.evidence_hash(ADDR, max_block_height=10)

    def test_draft_skips_unfinalized_evidence(self, monkeypatch):
        monkeypatch.setattr(settings, "consensus_chain_slashing_enabled", True)
        monkeypatch.setattr(settings, "consensus_slashing_evidence_finality_depth", 10)
        chain_id = f"slash-fin-{uuid.uuid4().hex[:8]}"
        _chain_db(chain_id)
        c = self._bonded_consensus(chain_id)
        c.record_attestation_equivocation(ADDR, 5, 2, HA, HB, V2)

        # Head at 12 → cutoff 2 → evidence at height 5 is not yet finalized.
        self._add_block(chain_id, 12)
        out = c.draft_deactivation_txs()
        assert out["drafts"] == []

        # Head at 20 → cutoff 10 → evidence at height 5 is finalized.
        self._add_block(chain_id, 20)
        out = c.draft_deactivation_txs()
        assert len(out["drafts"]) == 1
        draft = out["drafts"][0]
        assert draft["payload"]["evidence_hash"] == c._slashing_manager.evidence_hash(ADDR, max_block_height=10)

    def test_draft_no_head_falls_back_to_all_evidence(self, monkeypatch):
        """Unreadable head → no cutoff (availability over silent correctness)."""
        monkeypatch.setattr(settings, "consensus_chain_slashing_enabled", True)
        chain_id = f"slash-nohead-{uuid.uuid4().hex[:8]}"
        _chain_db(chain_id)
        c = self._bonded_consensus(chain_id)
        c.record_attestation_equivocation(ADDR, 5, 2, HA, HB, V2)
        out = c.draft_deactivation_txs()
        assert len(out["drafts"]) == 1
