"""#1311: replicated attestation-equivocation evidence — codec, ingest pipeline, handler, emit."""

from __future__ import annotations

import json

import pytest
from aitbc.crypto.consensus_signing import sign_consensus_message
from aitbc_chain.config import settings
from aitbc_chain.consensus import evidence_replication as er
from aitbc_chain.consensus import remote_attestation as ra_module
from aitbc_chain.consensus import vote_journal
from aitbc_chain.consensus.remote_attestation import RemoteAttestationService
from aitbc_chain.consensus.slashing import SlashingManager
from aitbc_chain.consensus.vote_journal import reset_vote_journals
from aitbc_chain.metrics import metrics_registry

CHAIN = "test-chain"
H = 100
HA, HB, HC, HD, HE = ("0x" + c * 64 for c in "abcde")


def _addr(key: str) -> str:
    from eth_keys import keys

    return keys.PrivateKey(bytes.fromhex(key[2:])).public_key.to_checksum_address()


OUR_KEY, VAL_KEY, OUT_KEY = "0x" + "11" * 32, "0x" + "22" * 32, "0x" + "44" * 32
OUR, VAL, OUT = _addr(OUR_KEY), _addr(VAL_KEY), _addr(OUT_KEY)


def _counter(name: str) -> float:
    return metrics_registry._counters.get(name, 0.0)


def _att(key: str, block_hash: str, *, round_: int | None, height: int = H, chain: str = CHAIN) -> dict:
    msg = {
        "chain_id": chain,
        "height": height,
        "hash": block_hash,
        "parent_hash": "0x" + "00" * 32,
        "proposer": OUR,
        "state_root": "0x" + "11" * 32,
        "bridge_state_root": "",
    }
    if round_ is not None:
        msg["round"] = round_
    return {
        "chain_id": chain,
        "height": height,
        "hash": block_hash,
        "parent_hash": msg["parent_hash"],
        "proposer": OUR,
        "state_root": msg["state_root"],
        "bridge_state_root": "",
        "round_in_payload": round_ is not None,
        "request_round": round_,
        "signature": sign_consensus_message(msg, key),
        "signer": _addr(key),
    }


def _record(key: str = VAL_KEY, hashes=(HA, HB), rounds=(1, 1), round_=1, height: int = H) -> dict:
    atts = [_att(key, hashes[0], round_=rounds[0], height=height), _att(key, hashes[1], round_=rounds[1], height=height)]
    return er.build_record(CHAIN, _addr(key), height, round_, hashes[0], hashes[1], atts)


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    metrics_registry.reset()
    er.reset_stores()
    reset_vote_journals()
    monkeypatch.setattr(vote_journal, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ra_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "equivocation_replication_enabled", True)
    monkeypatch.setattr(settings, "validator_set", json.dumps([{"address": OUR}, {"address": VAL}]))
    yield
    er.reset_stores()
    metrics_registry.reset()


VSET = {OUR, VAL}


def _ingest(payload, **kw):
    return er.ingest(CHAIN, payload, VSET, **kw)


class TestIngestPipeline:
    def test_same_round_signed_pair_is_stored_and_slashable(self):
        out = _ingest(_record())
        assert out.status == "stored" and out.slashable
        assert _counter("equivocation_ingest_stored_total") == 1

    def test_cross_round_pair_is_context_only(self):
        out = _ingest(_record(rounds=(1, 2), round_=1))
        assert out.status == "stored" and not out.slashable
        assert _counter("equivocation_ingest_context_only_total") == 1

    def test_legacy_round_absent_pair_is_context_only(self):
        out = _ingest(_record(rounds=(None, None), round_=None))
        assert out.status == "stored" and not out.slashable

    def test_mixed_format_pair_is_context_only(self):
        out = _ingest(_record(rounds=(1, None), round_=1))
        assert out.status == "stored" and not out.slashable

    def test_hash_only_record_is_dropped(self):
        rec = _record()
        rec["attestations"] = []
        assert _ingest(rec).status == "schema"

    def test_forged_signature_is_dropped_at_verify(self):
        rec = _record()
        rec["attestations"][0]["signature"] = rec["attestations"][1]["signature"]
        assert _ingest(rec).status == "verify"
        assert len(er.get_store(CHAIN)) == 0

    def test_signature_by_another_key_is_dropped(self):
        rec = _record(key=OUT_KEY)
        rec["validator"] = VAL  # claims to report VAL, signed by OUT
        assert _ingest(rec).status == "verify"

    def test_non_validator_is_dropped_before_verification(self):
        assert _ingest(_record(key=OUT_KEY)).status == "not_validator"
        assert len(er.get_store(CHAIN)) == 0

    def test_wrong_chain_is_dropped(self):
        assert er.ingest("other-chain", _record(), VSET).status == "chain"

    def test_attestation_height_must_match_record_height(self):
        rec = _record()
        rec["height"] = H + 1
        assert _ingest(rec).status in {"schema", "verify"}

    def test_oversize_is_dropped(self, monkeypatch):
        monkeypatch.setattr(settings, "equivocation_replication_max_record_bytes", 200)
        assert _ingest(_record()).status == "oversize"

    def test_sender_justification_field_is_not_stored(self):
        rec = _record()
        rec["justification"] = {"kind": "operator"}
        out = _ingest(rec)
        assert out.status == "stored" and "justification" not in (out.record or {})

    def test_unsorted_hash_pair_is_dropped(self):
        rec = _record()
        rec["block_hash_a"], rec["block_hash_b"] = rec["block_hash_b"], rec["block_hash_a"]
        assert _ingest(rec).status == "schema"


class TestDedupAndBounds:
    def test_duplicate_is_dropped_without_verification(self, monkeypatch):
        assert _ingest(_record()).status == "stored"
        calls = []
        monkeypatch.setattr(er, "_verify", lambda *a, **k: calls.append(a) or True)
        assert _ingest(_record()).status == "duplicate"
        assert calls == []  # read-only pre-filter skipped the crypto

    def test_prefilter_is_read_only(self):
        store = er.get_store(CHAIN)
        assert _ingest(_record(hashes=(HA, HB))).status == "stored"
        assert _ingest(_record(hashes=(HA, HC))).status == "stored"
        before = list(store._records)
        store.has(before[0])
        assert list(store._records) == before  # no reorder on read

    def test_atomic_insert_or_ignore(self):
        store = er.EvidenceStore()
        key = er.pair_key(CHAIN, VAL, H, 1, HA, HB)
        assert store.add_if_absent(key, {"n": 1}) is True
        assert store.add_if_absent(key, {"n": 2}) is False
        assert store.get(key) == {"n": 1}

    def test_distinct_hashes_per_slot_are_capped(self):
        # one Byzantine validator signing many hashes at one (height, round): HA-HB, HA-HC use 3 hashes,
        # HD pushes to 4, HE would be the 5th distinct hash
        assert _ingest(_record(hashes=(HA, HB))).status == "stored"
        assert _ingest(_record(hashes=(HA, HC))).status == "stored"
        assert _ingest(_record(hashes=(HA, HD))).status == "stored"
        assert _ingest(_record(hashes=(HA, HE))).status == "slot_cap"
        assert _counter("equivocation_ingest_dropped_slot_cap_total") == 1

    def test_slot_cap_is_per_round(self):
        for hs in ((HA, HB), (HA, HC), (HA, HD)):
            assert _ingest(_record(hashes=hs)).status == "stored"
        assert _ingest(_record(hashes=(HA, HE), rounds=(2, 2), round_=2)).status == "stored"

    def test_ring_evicts_fifo_and_releases_slot_counts(self, monkeypatch):
        monkeypatch.setattr(settings, "equivocation_replication_ring_cap", 2)
        for h in (HA, HC, HD):
            assert _ingest(_record(hashes=(HB, h))).status == "stored"
        store = er.get_store(CHAIN)
        assert len(store) == 2
        assert not store.has(er.pair_key(CHAIN, VAL, H, 1, HB, HA))
        assert _counter("equivocation_evidence_evicted_total") == 1

    def test_rate_cap_per_validator(self, monkeypatch):
        monkeypatch.setattr(settings, "equivocation_replication_rate_per_minute", 2)
        results = [_ingest(_record(hashes=(HA, h)), now=1.0).status for h in (HB, HC, HD)]
        assert results == ["stored", "stored", "rate"]
        assert _ingest(_record(hashes=(HA, HE)), now=100.0).status == "stored"  # window slid

    def test_publish_budget_is_bounded(self):
        store = er.EvidenceStore()
        key = er.pair_key(CHAIN, VAL, H, 1, HA, HB)
        assert [store.may_publish(key) for _ in range(5)] == [True, True, True, False, False]


class TestHandlerAndEmit:
    def _svc(self) -> RemoteAttestationService:
        return RemoteAttestationService(CHAIN, {OUR: OUR_KEY})

    def test_slashable_record_lands_in_the_recorder(self, monkeypatch):
        mgr = SlashingManager()
        svc = self._svc()
        monkeypatch.setattr(svc, "_equivocation_recorder", lambda: mgr)
        out = svc.handle_evidence(_record())
        assert out.slashable
        events = mgr.get_slashing_history(VAL)
        assert len(events) == 1 and events[0].round_number == 1
        assert json.loads(events[0].evidence)["attestations"]
        assert _counter("equivocation_ingest_recorded_total") == 1

    def test_context_only_record_is_not_recorded(self, monkeypatch):
        mgr = SlashingManager()
        svc = self._svc()
        monkeypatch.setattr(svc, "_equivocation_recorder", lambda: mgr)
        svc.handle_evidence(_record(rounds=(1, 2), round_=1))
        assert mgr.get_slashing_history(VAL) == []

    def test_replay_is_idempotent_in_the_recorder(self, monkeypatch):
        mgr = SlashingManager()
        svc = self._svc()
        monkeypatch.setattr(svc, "_equivocation_recorder", lambda: mgr)
        svc.handle_evidence(_record())
        svc.handle_evidence(_record())
        assert len(mgr.get_slashing_history(VAL)) == 1

    def test_ingested_record_is_never_re_emitted(self, monkeypatch):
        mgr = SlashingManager()
        svc = self._svc()
        monkeypatch.setattr(svc, "_equivocation_recorder", lambda: mgr)
        emitted = []
        monkeypatch.setattr(svc, "_emit_evidence", lambda *a, **k: emitted.append(a))
        svc.handle_evidence(_record())
        assert emitted == []

    def test_disabled_flag_is_inert(self, monkeypatch):
        monkeypatch.setattr(settings, "equivocation_replication_enabled", False)
        svc = self._svc()
        svc._emit_evidence(VAL, H, 1, HA, HB, _record()["attestations"])
        assert len(er.get_store(CHAIN)) == 0
        assert not er.enabled()

    @pytest.mark.asyncio
    async def test_local_same_round_pair_is_published_once_then_bounded(self, monkeypatch):
        published = []

        async def fake_publish(topic, payload):
            published.append((topic, payload))

        monkeypatch.setattr(ra_module.gossip_broker, "publish", fake_publish)
        svc = self._svc()
        atts = _record()["attestations"]
        for _ in range(5):
            svc._emit_evidence(VAL, H, 1, HA, HB, atts)
        import asyncio

        await asyncio.sleep(0)
        assert len(published) == 3  # max_publishes
        assert published[0][0] == er.equivocation_topic(CHAIN)
        assert _counter("equivocation_republish_suppressed_total") == 2

    @pytest.mark.asyncio
    async def test_cross_round_local_pair_is_not_published(self, monkeypatch):
        published = []

        async def fake_publish(topic, payload):
            published.append(payload)

        monkeypatch.setattr(ra_module.gossip_broker, "publish", fake_publish)
        svc = self._svc()
        atts = _record(rounds=(1, 2), round_=1)["attestations"]
        svc._emit_evidence(VAL, H, 1, HA, HB, atts)
        import asyncio

        await asyncio.sleep(0)
        assert published == []

    def test_topic_is_restricted(self):
        from aitbc_chain.gossip.gossip_auth import is_restricted_topic

        assert is_restricted_topic(er.equivocation_topic(CHAIN))
