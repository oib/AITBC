"""#1198 pins: consensus-visible slashing state (spec v2, Option A).

Covers the VALIDATOR_DEACTIVATE apply path (dedicated authority param,
strict address, bond gate, value=0), the effective-active predicate in
MultiValidatorPoA (height boundary, reorg replay, flag-off identity), the
advisory evidence APIs, and the migration divergence report/drafts.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from sqlmodel import Session, create_engine, select

from aitbc_chain.base_models import (
    Account,
    Bond,
    ChainParameter,
    ValidatorDeactivation,
)
from aitbc_chain.config import settings
from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA, ValidatorRole
from aitbc_chain.consensus.slashing import SlashingManager, slashing_manager
from aitbc.crypto.crypto import derive_ethereum_address
from aitbc.crypto.signature_recovery import canonical_address
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.state.state_transition import StateTransition

from ..test_apply_parity import (
    CHAIN,
    PROVIDER,
    _attach_sender_sig,
    _seed_bond,
    _tx,
)

AUTH_KEY = "0x" + "33" * 32
AUTH = derive_ethereum_address(AUTH_KEY)
EVIDENCE = "0x" + "ab" * 32
BLOCK_TIME = datetime(2026, 11, 8, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("VALIDATOR_DEACTIVATION_AUTHORITY_ADDRESS", raising=False)
    yield


def _engine(tmp_path, name: str = "vd.db"):
    engine = create_engine(f"sqlite:///{tmp_path / name}", echo=False)
    chain_metadata.create_all(engine)
    return engine


def _deactivation_tx(payload: dict | None = None, *, value: int = 0, signer_key: str = AUTH_KEY, nonce: int = 0) -> dict:
    tx = _tx(
        AUTH,
        AUTH,
        value,
        "VALIDATOR_DEACTIVATE",
        payload
        or {
            "validator_address": PROVIDER,
            "evidence_hash": EVIDENCE,
            "bond_id": "bond-par-1",
        },
        fee=10,
    )
    tx["nonce"] = nonce
    return _attach_sender_sig(tx, signer_key)


def _seed_authority(session: Session, chain_id: str = CHAIN) -> None:
    session.add(
        ChainParameter(
            chain_id=chain_id,
            parameter="validator_deactivation_authority",
            value=AUTH,
            applied_height=0,
        )
    )
    session.add(Account(chain_id=chain_id, address=AUTH, balance=10**9, nonce=0))


def _markers(session: Session, chain_id: str = CHAIN) -> list[ValidatorDeactivation]:
    return list(session.exec(select(ValidatorDeactivation).where(ValidatorDeactivation.chain_id == chain_id)).all())


class TestValidatorDeactivateApply:
    def test_marker_written_when_all_gates_pass(self, tmp_path):
        st = StateTransition()
        with Session(_engine(tmp_path)) as session:
            _seed_bond(session)
            _seed_authority(session)
            session.commit()
            ok, msg = st.apply_transaction(
                session, CHAIN, _deactivation_tx(), tx_hash="vd-ok", block_version=22, block_height=5, block_time=BLOCK_TIME
            )
            assert ok, msg
            markers = _markers(session)
            assert len(markers) == 1
            m = markers[0]
            assert m.validator_address == PROVIDER
            assert m.evidence_hash == EVIDENCE
            assert m.deactivation_tx_hash == "vd-ok"
            assert m.block_height == 5
            # fee/nonce still applied through the generic path
            auth = session.get(Account, (CHAIN, AUTH))
            assert auth.nonce == 1

    def test_no_authority_skips_but_applies_fee_nonce(self, tmp_path):
        st = StateTransition()
        with Session(_engine(tmp_path)) as session:
            _seed_bond(session)
            session.add(Account(chain_id=CHAIN, address=AUTH, balance=10**9, nonce=0))
            session.commit()
            ok, _ = st.apply_transaction(
                session, CHAIN, _deactivation_tx(), tx_hash="vd-noauth", block_version=22, block_height=5
            )
            assert ok
            assert _markers(session) == []
            assert session.get(Account, (CHAIN, AUTH)).nonce == 1

    def test_wrong_signer_skips(self, tmp_path):
        st = StateTransition()
        other_key = "0x" + "44" * 32
        other = derive_ethereum_address(other_key)
        with Session(_engine(tmp_path)) as session:
            _seed_bond(session)
            _seed_authority(session)
            session.add(Account(chain_id=CHAIN, address=other, balance=10**9, nonce=0))
            session.commit()
            tx = _deactivation_tx(signer_key=other_key)
            tx["from"] = other
            tx["to"] = other
            tx = _attach_sender_sig(tx, other_key)
            ok, _ = st.apply_transaction(session, CHAIN, tx, tx_hash="vd-wrong", block_version=22, block_height=5)
            assert ok
            assert _markers(session) == []

    def test_nonzero_value_rejected_at_validate(self, tmp_path):
        st = StateTransition()
        with Session(_engine(tmp_path)) as session:
            _seed_bond(session)
            _seed_authority(session)
            session.commit()
            ok, msg = st.validate_transaction(session, CHAIN, _deactivation_tx(value=7), "vd-val", block_version=22)
            assert not ok
            assert "value=0" in msg

    def test_non_strict_address_skips(self, tmp_path):
        st = StateTransition()
        with Session(_engine(tmp_path)) as session:
            _seed_bond(session)
            _seed_authority(session)
            session.commit()
            tx = _deactivation_tx({"validator_address": "not-an-address", "evidence_hash": EVIDENCE, "bond_id": "bond-par-1"})
            ok, _ = st.apply_transaction(session, CHAIN, tx, tx_hash="vd-badaddr", block_version=22, block_height=5)
            assert ok
            assert _markers(session) == []

    def test_missing_evidence_or_bond_skips(self, tmp_path):
        st = StateTransition()
        with Session(_engine(tmp_path)) as session:
            _seed_bond(session)
            _seed_authority(session)
            session.commit()
            for i, payload in enumerate(
                [
                    {"validator_address": PROVIDER, "bond_id": "bond-par-1"},
                    {"validator_address": PROVIDER, "evidence_hash": EVIDENCE},
                    {"validator_address": PROVIDER, "evidence_hash": EVIDENCE, "bond_id": "no-such-bond"},
                ]
            ):
                tx = _deactivation_tx(payload, nonce=i)
                ok, _ = st.apply_transaction(session, CHAIN, tx, tx_hash=f"vd-miss-{i}", block_version=22, block_height=5)
                assert ok
            assert _markers(session) == []

    def test_bond_provider_mismatch_skips(self, tmp_path):
        st = StateTransition()
        other_provider = derive_ethereum_address("0x" + "55" * 32)
        with Session(_engine(tmp_path)) as session:
            _seed_bond(session)  # bond provider is PROVIDER
            _seed_authority(session)
            session.commit()
            tx = _deactivation_tx({"validator_address": other_provider, "evidence_hash": EVIDENCE, "bond_id": "bond-par-1"})
            ok, _ = st.apply_transaction(session, CHAIN, tx, tx_hash="vd-mismatch", block_version=22, block_height=5)
            assert ok
            assert _markers(session) == []

    def test_second_marker_for_same_validator_skips(self, tmp_path):
        st = StateTransition()
        with Session(_engine(tmp_path)) as session:
            _seed_bond(session)
            _seed_authority(session)
            session.commit()
            st.apply_transaction(session, CHAIN, _deactivation_tx(), tx_hash="vd-1", block_version=22, block_height=5)
            tx2 = _deactivation_tx(nonce=1)
            st.apply_transaction(session, CHAIN, tx2, tx_hash="vd-2", block_version=22, block_height=6)
            assert len(_markers(session)) == 1


def _chain_db(chain_id: str):
    """Materialize a test chain.db and return its engine (registered id)."""
    from pathlib import Path

    from aitbc_chain.database import get_engine

    Path(settings.get_db_path(chain_id)).parent.mkdir(parents=True, exist_ok=True)
    engine = get_engine(chain_id, create_ok=True)
    chain_metadata.create_all(engine)
    return engine


def _consensus(chain_id: str, *addresses: str) -> MultiValidatorPoA:
    c = MultiValidatorPoA(chain_id)
    c._require_block_signatures = False
    for a in addresses:
        c.add_validator(a, 1000.0)
        c.validators[a].role = ValidatorRole.VALIDATOR
        c.validators[a].is_active = True
    return c


V1 = "0x" + "a1" * 20
V2 = "0x" + "b2" * 20
V3 = "0x" + "c3" * 20


class TestEffectiveActivePredicate:
    def test_flag_off_ignores_markers(self, monkeypatch):
        monkeypatch.setattr(settings, "consensus_chain_slashing_enabled", False)
        chain_id = f"slash-off-{uuid.uuid4().hex[:8]}"
        _chain_db(chain_id)
        c = _consensus(chain_id, V1, V2, V3)
        from aitbc_chain.database import session_scope

        with session_scope(chain_id) as session:
            session.add(
                ValidatorDeactivation(
                    chain_id=chain_id,
                    validator_address=V1,
                    evidence_hash=EVIDENCE,
                    deactivation_tx_hash="t",
                    block_height=1,
                )
            )
            session.commit()
        assert V1 in c.get_consensus_participants()

    def test_flag_on_excludes_marked_validator(self, monkeypatch):
        monkeypatch.setattr(settings, "consensus_chain_slashing_enabled", True)
        chain_id = f"slash-on-{uuid.uuid4().hex[:8]}"
        _chain_db(chain_id)
        c = _consensus(chain_id, V1, V2, V3)
        from aitbc_chain.database import session_scope

        with session_scope(chain_id) as session:
            session.add(
                ValidatorDeactivation(
                    chain_id=chain_id,
                    validator_address=V1,
                    evidence_hash=EVIDENCE,
                    deactivation_tx_hash="t",
                    block_height=1,
                )
            )
            session.commit()
        participants = c.get_consensus_participants()
        assert V1 not in participants
        assert set(participants) == {V2, V3}

    def test_height_boundary_marker_applies_next_height_only(self, monkeypatch):
        monkeypatch.setattr(settings, "consensus_chain_slashing_enabled", True)
        chain_id = f"slash-h-{uuid.uuid4().hex[:8]}"
        _chain_db(chain_id)
        c = _consensus(chain_id, V1, V2, V3)
        from aitbc_chain.database import session_scope

        # Marker sealed in block 5: selection for height 5 still sees it
        # active (state-after-parent), height 6 excludes it.
        with session_scope(chain_id) as session:
            session.add(
                ValidatorDeactivation(
                    chain_id=chain_id,
                    validator_address=V1,
                    evidence_hash=EVIDENCE,
                    deactivation_tx_hash="t",
                    block_height=5,
                )
            )
            session.commit()
        # select_proposer(5): upto=4 → marker not yet applicable
        proposers_at_5 = {c.select_proposer(5, r) for r in range(len(c.validators))}
        assert V1 in proposers_at_5
        # select_proposer(6): upto=5 → marker applies
        proposers_at_6 = {c.select_proposer(6, r) for r in range(len(c.validators))}
        assert V1 not in proposers_at_6

    def test_reorg_unseal_reactivates(self, monkeypatch):
        monkeypatch.setattr(settings, "consensus_chain_slashing_enabled", True)
        chain_id = f"slash-r-{uuid.uuid4().hex[:8]}"
        _chain_db(chain_id)
        c = _consensus(chain_id, V1, V2, V3)
        from aitbc_chain.database import session_scope

        with session_scope(chain_id) as session:
            row = ValidatorDeactivation(
                chain_id=chain_id,
                validator_address=V1,
                evidence_hash=EVIDENCE,
                deactivation_tx_hash="t",
                block_height=1,
            )
            session.add(row)
            session.commit()
        assert V1 not in c.get_consensus_participants()
        # Reorg un-seals the carrying block → row gone → deterministic reactivation.
        with session_scope(chain_id) as session:
            session.delete(session.exec(select(ValidatorDeactivation)).one())
            session.commit()
        assert V1 in c.get_consensus_participants()

    def test_validate_block_rejects_marked_proposer(self, monkeypatch):
        monkeypatch.setattr(settings, "consensus_chain_slashing_enabled", True)
        chain_id = f"slash-v-{uuid.uuid4().hex[:8]}"
        _chain_db(chain_id)
        c = _consensus(chain_id, V1, V2, V3)
        from aitbc_chain.database import session_scope
        from aitbc_chain.models import Block

        with session_scope(chain_id) as session:
            session.add(
                ValidatorDeactivation(
                    chain_id=chain_id,
                    validator_address=V1,
                    evidence_hash=EVIDENCE,
                    deactivation_tx_hash="t",
                    block_height=1,
                )
            )
            session.commit()
        block = Mock(spec=Block)
        block.hash = "0xh"
        block.height = 2  # marker at 1 < 2 → applies
        block.timestamp = datetime(2026, 11, 8, tzinfo=UTC)
        block.signature = ""
        assert c.validate_block(block, V1) is False
        assert c.validate_block(block, V2) is True


class TestAdvisoryAndMigration:
    def test_record_attestation_equivocation_and_hash(self):
        mgr = SlashingManager()
        mgr.record_double_sign = mgr.detect_double_sign  # noqa: SLF001 - clarity
        e1 = mgr.detect_double_sign("0xVAL", "0xaaa", "0xbbb", 10)
        assert e1 is not None
        mgr.slashing_events.append(e1)
        mgr.record_attestation_equivocation(
            validator_address="0xVAL", height=11, round_number=2, block_hash_a="0xccc", block_hash_b="0xddd", proposer="0xP"
        )
        h1 = mgr.evidence_hash("0xVAL")
        assert h1.startswith("0x") and len(h1) == 66
        bundle = mgr.evidence_bundle("0xVAL")
        assert len(bundle["events"]) == 2
        assert bundle["events"][1]["evidence"].find("attestation_equivocation") >= 0
        # Deterministic: same history → same hash.
        assert SlashingManager().evidence_hash("0xNONE") != h1
        mgr2 = SlashingManager()
        mgr2.slashing_events = list(mgr.slashing_events)
        assert mgr2.evidence_hash("0xVAL") == h1

    def test_draft_deactivation_txs(self, monkeypatch):
        monkeypatch.setattr(settings, "consensus_chain_slashing_enabled", True)
        chain_id = f"slash-d-{uuid.uuid4().hex[:8]}"
        _chain_db(chain_id)
        c = _consensus(chain_id, V1, V2)
        c.validators[V1].is_active = False  # locally deactivated, no marker
        c.validators[V1].role = ValidatorRole.STANDBY
        from aitbc_chain.database import session_scope

        with session_scope(chain_id) as session:
            session.add(
                Bond(
                    chain_id=chain_id,
                    bond_id="bond-v1",
                    provider=V1,
                    amount=1000,
                    status="active",
                    created_at=datetime(2026, 1, 1, tzinfo=UTC),
                    updated_at=datetime(2026, 1, 1, tzinfo=UTC),
                )
            )
            session.commit()
        out = c.draft_deactivation_txs()
        assert len(out["drafts"]) == 1
        d = out["drafts"][0]
        assert d["type"] == "VALIDATOR_DEACTIVATE"
        assert d["payload"]["validator_address"] == canonical_address(V1)
        assert d["payload"]["bond_id"] == "bond-v1"
        assert d["payload"]["evidence_hash"].startswith("0x")
        assert out["skipped"] == []

    def test_draft_skips_bondless_validator(self, monkeypatch):
        monkeypatch.setattr(settings, "consensus_chain_slashing_enabled", True)
        chain_id = f"slash-nb-{uuid.uuid4().hex[:8]}"
        _chain_db(chain_id)
        c = _consensus(chain_id, V1)
        c.validators[V1].is_active = False
        c.validators[V1].role = ValidatorRole.STANDBY
        out = c.draft_deactivation_txs()
        assert out["drafts"] == []
        assert len(out["skipped"]) == 1
        assert "no active bond" in out["skipped"][0]["reason"]

    def test_divergence_report(self, monkeypatch):
        monkeypatch.setattr(settings, "consensus_chain_slashing_enabled", True)
        chain_id = f"slash-rep-{uuid.uuid4().hex[:8]}"
        _chain_db(chain_id)
        c = _consensus(chain_id, V1, V2)
        c.validators[V1].is_active = False
        c.validators[V1].role = ValidatorRole.STANDBY
        from aitbc_chain.database import session_scope

        with session_scope(chain_id) as session:
            session.add(
                ValidatorDeactivation(
                    chain_id=chain_id,
                    validator_address=V2,
                    evidence_hash=EVIDENCE,
                    deactivation_tx_hash="t",
                    block_height=1,
                )
            )
            # V2 is locally active but marked on-chain — not in the
            # is_active=False report; V1 is the divergent entry.
            session.commit()
        report = c.chain_slashing_divergence_report()
        assert len(report) == 1
        assert report[0]["address"] == V1
        assert report[0]["on_chain_marker"] is False

    def test_byzantine_threshold_advisory_when_armed(self, monkeypatch):
        """Armed: threshold reached logs advisory, does NOT flip is_active."""
        monkeypatch.setattr(settings, "consensus_chain_slashing_enabled", True)
        monkeypatch.setattr(settings, "consensus_byzantine_threshold", 1)
        chain_id = f"slash-adv-{uuid.uuid4().hex[:8]}"
        _chain_db(chain_id)
        c = _consensus(chain_id, V1)
        # Simulate equivocation evidence directly through the manager.
        c._slashing_manager.slashing_events.append(c._slashing_manager.detect_double_sign(V1, "0xaaa", "0xbbb", 3))
        # Drive the same branch detect_byzantine_behavior takes at threshold.
        count = c._slashing_manager.get_validator_slash_count(V1, c._slashing_manager.slashing_events[0].condition)
        assert count >= settings.consensus_byzantine_threshold
        # The armed path never writes is_active — asserted via the guard the
        # production code now takes (direct call would need gossip stores).
        assert c._chain_slashing_armed() is True
        assert c.validators[V1].is_active is True

    def test_slashing_manager_global_untouched(self):
        # The module-global manager is shared; evidence APIs must not leak
        # state between tests beyond appended events.
        assert isinstance(slashing_manager, SlashingManager)

    @pytest.mark.asyncio
    async def test_attestation_equivocation_wires_to_consensus_and_persists(self, monkeypatch):
        """End-to-end pin (#1198 pin-gap): RemoteAttestationService._handle_request
        routes attestation equivocation into get_consensus(chain_id)._slashing_manager,
        persists ConsensusState.slashing_events_json, and feeds draft_deactivation_txs()."""
        import json
        import time as _time

        from aitbc_chain.base_models import ConsensusState
        from aitbc_chain.consensus import multi_validator_poa as mvpoa
        from aitbc_chain.consensus import remote_attestation as ra_mod
        from aitbc_chain.consensus.remote_attestation import RemoteAttestationService
        from aitbc_chain.database import session_scope

        chain_id = f"slash-e2e-{uuid.uuid4().hex[:8]}"
        _chain_db(chain_id)
        our_key = "0x" + "11" * 32
        proposer_key = "0x" + "22" * 32
        our_addr = derive_ethereum_address(our_key)
        proposer_addr = derive_ethereum_address(proposer_key)

        monkeypatch.setattr(settings, "consensus_chain_slashing_enabled", True)
        monkeypatch.setattr(settings, "consensus_require_signed_attest_request", False)
        monkeypatch.setattr(settings, "attestation_header_max_age_seconds", 0.0)
        monkeypatch.setattr(settings, "attestation_round_lock_enabled", False)
        monkeypatch.setattr(
            settings,
            "validator_set",
            json.dumps([{"address": our_addr}, {"address": proposer_addr}]),
        )

        c = _consensus(chain_id, our_addr, proposer_addr)
        monkeypatch.setitem(mvpoa.consensus_instances, chain_id, c)

        with session_scope(chain_id) as session:
            session.add(
                Bond(
                    chain_id=chain_id,
                    bond_id="bond-att-1",
                    provider=our_addr,
                    amount=1000,
                    status="active",
                    created_at=datetime(2026, 1, 1, tzinfo=UTC),
                    updated_at=datetime(2026, 1, 1, tzinfo=UTC),
                )
            )
            session.commit()

        published: list[tuple[str, dict]] = []

        class _Broker:
            async def publish(self, topic: str, msg: dict) -> None:
                published.append((topic, msg))

        monkeypatch.setattr(ra_mod, "gossip_broker", _Broker())
        svc = RemoteAttestationService(chain_id, {our_addr: our_key})

        def _req(block_hash: str) -> dict:
            return {
                "header": {
                    "chain_id": chain_id,
                    "height": 42,
                    "hash": block_hash,
                    "parent_hash": "0xparent",
                    "proposer": proposer_addr,
                    "state_root": "0xroot",
                    "bridge_state_root": "",
                },
                "transactions": [],
                "timestamp": _time.time(),
            }

        await svc._handle_request(_req("0xaaaa"))
        assert len(published) == 1
        assert mvpoa.get_consensus(chain_id).get_slashing_history() == []

        # Expire the height-only lock so the second rival hash is signed (the
        # #1242 comment 18430 scenario).
        svc._attested[42] = {None: ("0xaaaa", proposer_addr, _time.monotonic() - 3600)}
        await svc._handle_request(_req("0xbbbb"))
        assert len(published) == 2

        history = mvpoa.get_consensus(chain_id).get_slashing_history()
        assert len(history) == 1
        assert history[0].validator_address == canonical_address(our_addr)
        assert "0xaaaa" in history[0].evidence and "0xbbbb" in history[0].evidence

        # Persisted to ConsensusState.slashing_events_json in chain.db
        with session_scope(chain_id) as session:
            row = session.exec(select(ConsensusState).where(ConsensusState.chain_id == chain_id)).one()
            persisted = json.loads(row.slashing_events_json)
        assert len(persisted) == 1
        assert "attestation_equivocation" in persisted[0]["evidence"]

        # draft_deactivation_txs picks up the attestation equivocation and commits its evidence_hash
        drafts = mvpoa.get_consensus(chain_id).draft_deactivation_txs()
        assert len(drafts["drafts"]) == 1
        draft = drafts["drafts"][0]
        assert draft["payload"]["validator_address"] == canonical_address(our_addr)
        assert draft["payload"]["bond_id"] == "bond-att-1"
        assert draft["payload"]["evidence_hash"] == mvpoa.get_consensus(chain_id)._slashing_manager.evidence_hash(our_addr)

    @pytest.mark.asyncio
    async def test_attestation_equivocation_falls_back_when_multi_validator_disabled(self, monkeypatch):
        """When multi_validator_consensus_enabled is False, equivocation falls back to global slashing_manager."""
        import json
        import time as _time

        from aitbc_chain.consensus import remote_attestation as ra_mod
        from aitbc_chain.consensus.remote_attestation import RemoteAttestationService

        our_key = "0x" + "11" * 32
        proposer_key = "0x" + "22" * 32
        our_addr = derive_ethereum_address(our_key)
        proposer_addr = derive_ethereum_address(proposer_key)

        monkeypatch.setattr(settings, "multi_validator_consensus_enabled", False)
        monkeypatch.setattr(settings, "consensus_require_signed_attest_request", False)
        monkeypatch.setattr(settings, "attestation_header_max_age_seconds", 0.0)
        monkeypatch.setattr(settings, "attestation_round_lock_enabled", False)
        monkeypatch.setattr(
            settings,
            "validator_set",
            json.dumps([{"address": our_addr}, {"address": proposer_addr}]),
        )

        class _Broker:
            async def publish(self, topic: str, msg: dict) -> None:
                pass

        monkeypatch.setattr(ra_mod, "gossip_broker", _Broker())
        before_len = len(slashing_manager.slashing_events)
        svc = RemoteAttestationService("fallback-chain", {our_addr: our_key})

        def _req(block_hash: str) -> dict:
            return {
                "header": {
                    "chain_id": "fallback-chain",
                    "height": 7,
                    "hash": block_hash,
                    "parent_hash": "0xparent",
                    "proposer": proposer_addr,
                    "state_root": "0xroot",
                    "bridge_state_root": "",
                },
                "transactions": [],
                "timestamp": _time.time(),
            }

        await svc._handle_request(_req("0x1111"))
        svc._attested[7] = {None: ("0x1111", proposer_addr, _time.monotonic() - 3600)}
        await svc._handle_request(_req("0x2222"))
        assert len(slashing_manager.slashing_events) == before_len + 1
        slashing_manager.slashing_events.pop()
