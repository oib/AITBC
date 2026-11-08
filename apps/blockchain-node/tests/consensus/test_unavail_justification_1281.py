"""#1281 Phase 2: verifiable-justification barrier (Unavailability Certificate
+ GossipObservationIndex evidence valve).

Pins the armed-mode contract:

* ``verify_unavailability_cert`` is the one pure verifier — every field
  binding, signature, threshold, freshness, and replay/tag check;
* the combined predicate ``unfetchable_persists AND index_clean AND
  uc_valid`` is the only release path — no time-only escape;
* gate wiring: armed valve release stores the justification on the
  journal vote, the gossip response, and (proposer side) block metadata;
* flag off is byte-identical Phase-1 behavior.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from aitbc_chain.config import settings
from aitbc_chain.consensus import poa as poa_module
from aitbc_chain.consensus import remote_attestation as ra_module
from aitbc_chain.consensus import unavail, vote_fetch, vote_journal
from aitbc_chain.consensus.poa import PoAProposer
from aitbc_chain.consensus.remote_attestation import RemoteAttestationService
from aitbc_chain.consensus.slashing import SlashingManager
from aitbc_chain.consensus.unavail import (
    GossipObservationIndex,
    UnavailabilityCertificate,
    collect_unavailability_cert,
    unlock_justification,
    unfetchable_persists,
    verify_unavailability_cert,
)
from aitbc_chain.consensus.vote_journal import KIND_ATTEST, get_vote_journal, reset_vote_journals
from aitbc.crypto.signature_recovery import canonical_address
from aitbc_chain.metrics import metrics_registry

T0 = 1_800_000_000.0
CHAIN = "test-chain"
H = "0xvoted"
RIVAL = "0xrival"


def _key(byte: str) -> tuple[str, str]:
    from eth_keys import keys

    priv = "0x" + byte * 32
    addr = keys.PrivateKey(bytes.fromhex(priv[2:])).public_key.to_checksum_address()
    return addr, priv


ADDR1, KEY1 = _key("11")
ADDR2, KEY2 = _key("22")
ADDR3, KEY3 = _key("33")
PROPOSER, _ = _key("44")
VSET = {a.lower() for a in (ADDR1, ADDR2, ADDR3, PROPOSER)}


def _vset_json() -> str:
    return json.dumps([{"address": a} for a in (ADDR1, ADDR2, ADDR3, PROPOSER)])


def _ts(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, UTC).replace(tzinfo=None).isoformat()


def _request(height: int, block_hash: str, proposer: str, clock_now: float, **extra) -> dict:
    req = {
        "header": {
            "chain_id": CHAIN,
            "height": height,
            "hash": block_hash,
            "parent_hash": "0xparent",
            "proposer": proposer,
            "state_root": "0xroot",
            "bridge_state_root": "",
            "timestamp": _ts(clock_now),
        },
        "timestamp": clock_now,
    }
    req.update(extra)
    return req


def _cert(height: int = 100, block_hash: str = H, epoch: int | None = None, n: int = 2) -> UnavailabilityCertificate:
    epoch = int(__import__("time").time()) if epoch is None else epoch
    keys = [(ADDR1, KEY1), (ADDR2, KEY2), (ADDR3, KEY3)][:n]
    responses = tuple(
        {"validator": a, "signature": unavail.build_unavail_response(CHAIN, height, block_hash, epoch, a, k)["signature"]}
        for a, k in keys
    )
    return UnavailabilityCertificate(chain_id=CHAIN, height=height, hash=block_hash, epoch=epoch, responses=responses)


class _Sub:
    def __init__(self, items: list | None = None) -> None:
        self._q: asyncio.Queue = asyncio.Queue()
        for i in items or []:
            self._q.put_nowait(i)
        self.closed = False

    async def get(self):
        return await self._q.get()

    def close(self) -> None:
        self.closed = True


class _Broker:
    """Fake gossip broker. ``responders`` auto-answer UNAVAIL_QUERY on the
    resp topic with correctly-epoch-bound signatures (the epoch only exists
    inside the query, so responses cannot be pre-built)."""

    def __init__(self, responders: list[tuple[str, str]] | None = None) -> None:
        self.published: list[tuple[str, dict]] = []
        self._resp_sub: _Sub | None = None
        self._responders = responders if responders is not None else [(ADDR2, KEY2), (ADDR3, KEY3)]

    async def publish(self, topic: str, message: dict) -> None:
        self.published.append((topic, message))
        if "unavail_query" in topic and isinstance(message, dict) and self._resp_sub is not None:
            for addr, key in self._responders:
                resp = unavail.build_unavail_response(
                    message["chain_id"],
                    int(message["height"]),
                    str(message["hash"]),
                    int(message["epoch"]),
                    addr,
                    key,
                )
                self._resp_sub._q.put_nowait(resp)

    async def subscribe(self, topic: str, max_queue_size: int = 100):
        if "unavail_resp" in topic:
            if self._resp_sub is None:
                self._resp_sub = _Sub()
            return self._resp_sub
        return _Sub()


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    metrics_registry.reset()
    reset_vote_journals()
    vote_fetch.reset_throttle()
    monkeypatch.setattr(vote_journal, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ra_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "consensus_require_signed_attest_request", False)
    monkeypatch.setattr(settings, "consensus_proposer_round_seconds", 60)
    monkeypatch.setattr(settings, "attestation_lock_enabled", True)
    monkeypatch.setattr(settings, "attestation_header_max_age_seconds", 0.0)
    monkeypatch.setattr(settings, "attestation_round_lock_enabled", False)
    monkeypatch.setattr(settings, "chain_id", CHAIN)
    monkeypatch.setattr(settings, "vote_journal_enabled", True)
    monkeypatch.setattr(settings, "vote_journal_unlock_seconds", 300.0)
    monkeypatch.setattr(settings, "vote_journal_justification_enabled", False)
    monkeypatch.setattr(settings, "unavail_collect_seconds", 0.3)
    monkeypatch.setattr(settings, "unavail_cert_max_age_seconds", 120.0)
    monkeypatch.setattr(settings, "unavail_evidence_seconds", 0.25)
    monkeypatch.setattr(settings, "unavail_sample_seconds", 0.05)
    monkeypatch.setattr(settings, "multi_validator_min_attestations", 2)
    monkeypatch.setattr(settings, "validator_set", _vset_json())
    yield
    reset_vote_journals()
    metrics_registry.reset()


class TestCertVerifier:
    def test_valid_cert_passes(self):
        cert = _cert()
        ok, reason = verify_unavailability_cert(cert, chain_id=CHAIN, height=100, block_hash=H)
        assert ok, reason

    def test_dict_form(self):
        cert = _cert()
        ok, _ = verify_unavailability_cert(cert.to_dict(), chain_id=CHAIN, height=100, block_hash=H)
        assert ok

    @pytest.mark.parametrize(
        "field,value",
        [("chain_id", "other"), ("height", 99), ("hash", "0xother"), ("epoch", 1)],
    )
    def test_field_binding_rejects(self, field, value):
        raw = _cert().to_dict()
        raw[field] = value
        ok, reason = verify_unavailability_cert(raw, chain_id=CHAIN, height=100, block_hash=H)
        assert not ok
        assert reason

    def test_below_threshold_rejected(self):
        cert = _cert(n=1)
        ok, reason = verify_unavailability_cert(cert, chain_id=CHAIN, height=100, block_hash=H)
        assert not ok and reason == "below_threshold"

    def test_duplicate_signer_rejected(self):
        base = _cert(n=1)
        cert = UnavailabilityCertificate(
            chain_id=CHAIN,
            height=100,
            hash=H,
            epoch=base.epoch,
            responses=base.responses + base.responses,
        )
        ok, reason = verify_unavailability_cert(cert, chain_id=CHAIN, height=100, block_hash=H)
        assert not ok and reason == "duplicate_signer"

    def test_non_validator_signer_rejected(self):
        outsider, okey = _key("99")
        epoch = int(__import__("time").time())
        cert = UnavailabilityCertificate(
            chain_id=CHAIN,
            height=100,
            hash=H,
            epoch=epoch,
            responses=(
                {
                    "validator": outsider,
                    "signature": unavail.build_unavail_response(CHAIN, 100, H, epoch, outsider, okey)["signature"],
                },
                {
                    "validator": ADDR1,
                    "signature": unavail.build_unavail_response(CHAIN, 100, H, epoch, ADDR1, KEY1)["signature"],
                },
            ),
        )
        ok, reason = verify_unavailability_cert(cert, chain_id=CHAIN, height=100, block_hash=H)
        assert not ok and reason == "signer_not_validator"

    def test_attestation_signature_cannot_replay_as_unavail(self):
        """Domain separation: a signature over the attestation payload must
        not verify under the unavail-v1 tag."""
        from aitbc.crypto.consensus_signing import sign_consensus_message

        epoch = int(__import__("time").time())
        msg = {"chain_id": CHAIN, "height": 100, "hash": H}
        sig = sign_consensus_message(msg, KEY1)
        cert = UnavailabilityCertificate(
            chain_id=CHAIN,
            height=100,
            hash=H,
            epoch=epoch,
            responses=(
                {"validator": ADDR1, "signature": sig},
                {
                    "validator": ADDR2,
                    "signature": unavail.build_unavail_response(CHAIN, 100, H, epoch, ADDR2, KEY2)["signature"],
                },
            ),
        )
        ok, reason = verify_unavailability_cert(cert, chain_id=CHAIN, height=100, block_hash=H)
        assert not ok and reason == "bad_signature"


class TestObservationIndex:
    def test_clean_when_quiet_and_mesh_visible(self):
        idx = GossipObservationIndex()
        ignore = {canonical_address(ADDR1)}
        # Two foreign validators active at the height (requests for the
        # RIVAL hash — mesh is alive, voted hash stays quiet).
        idx.note_request(100, RIVAL, ADDR2)
        idx.note_response(100, RIVAL, ADDR3)
        v = idx.clean_verdict(100, H, ignore=ignore, window=60.0)
        assert v["clean"] is True
        assert v["validators_visible"] == 2

    def test_recent_foreign_attestation_for_voted_hash_blocks_clean(self):
        idx = GossipObservationIndex()
        idx.note_request(100, RIVAL, ADDR2)
        idx.note_response(100, RIVAL, ADDR3)
        idx.note_response(100, H, ADDR2)  # foreign attestation for the voted hash
        v = idx.clean_verdict(100, H, window=60.0)
        assert v["clean"] is False
        assert v["attestations_seen"] == 1

    def test_request_rebroadcast_for_voted_hash_blocks_clean(self):
        idx = GossipObservationIndex()
        idx.note_request(100, RIVAL, ADDR2)
        idx.note_response(100, RIVAL, ADDR3)
        idx.note_request(100, H, PROPOSER)  # voted hash re-broadcast
        v = idx.clean_verdict(100, H, window=60.0)
        assert v["clean"] is False

    def test_partition_hides_mesh_and_blocks_clean(self):
        idx = GossipObservationIndex()
        # Only ourselves visible → below min_peers → not clean → hold.
        v = idx.clean_verdict(100, H, ignore={canonical_address(ADDR1)}, min_peers=2, window=60.0)
        assert v["clean"] is False
        assert v["mesh_visible"] is False

    def test_own_attestation_does_not_block_clean(self):
        """Our own prior vote for X is journal business, not gossip evidence —
        the honest unlock path must not be held by ourselves."""
        idx = GossipObservationIndex()
        idx.note_request(100, RIVAL, ADDR2)
        idx.note_response(100, RIVAL, ADDR3)
        idx.note_response(100, H, ADDR1)  # own address
        v = idx.clean_verdict(100, H, ignore={canonical_address(ADDR1)}, window=60.0)
        assert v["clean"] is True
        assert v["attestations_seen"] == 0


class TestUnfetchableSampler:
    @pytest.mark.asyncio
    async def test_miss_streak_proves_after_evidence_window(self, monkeypatch):
        locate = AsyncMock(return_value=None)
        monkeypatch.setattr(unavail, "locate_voted_block", locate)
        await unavail.reset_observation_indices()
        ok = await unfetchable_persists(CHAIN, 100, [H], timeout=5.0)
        assert ok is True
        assert locate.await_count >= 2

    @pytest.mark.asyncio
    async def test_fetch_hit_blocks_proof(self, monkeypatch):
        locate = AsyncMock(return_value="https://peer")
        monkeypatch.setattr(unavail, "locate_voted_block", locate)
        await unavail.reset_observation_indices()
        ok = await unfetchable_persists(CHAIN, 100, [H], timeout=2.0)
        assert ok is False

    @pytest.mark.asyncio
    async def test_hit_after_proof_revokes(self, monkeypatch):
        calls = {"n": 0}

        async def flaky(*a, **k):
            calls["n"] += 1
            return "https://peer" if calls["n"] > 6 else None

        monkeypatch.setattr(unavail, "locate_voted_block", flaky)
        await unavail.reset_observation_indices()
        assert await unfetchable_persists(CHAIN, 100, [H], timeout=5.0) is True
        # keep sampling: the hit must revoke the proof
        for _ in range(40):
            await asyncio.sleep(0.05)
            if not _sampler_state(CHAIN, 100, H):
                break
        assert _sampler_state(CHAIN, 100, H) is False


def _sampler_state(chain: str, height: int, block_hash: str) -> bool:
    sampler = unavail._FETCH_SAMPLERS.get((chain, height, block_hash))
    return bool(sampler and sampler.state())


class TestCombinedPredicate:
    @pytest.mark.asyncio
    async def test_collect_unavailability_cert_roundtrip(self, monkeypatch):
        """The gossip round assembles a self-verified cert from responses."""
        monkeypatch.setattr(unavail, "gossip_broker", _Broker())
        await unavail.reset_observation_indices()
        cert = await collect_unavailability_cert(CHAIN, 100, H, requester=ADDR1)
        assert cert is not None
        ok, reason = verify_unavailability_cert(cert, chain_id=CHAIN, height=100, block_hash=H)
        assert ok, reason
        assert len(cert.responses) == 2

    @pytest.mark.asyncio
    async def test_collect_times_out_without_responders(self, monkeypatch):
        monkeypatch.setattr(unavail, "gossip_broker", _Broker(responders=[]))
        await unavail.reset_observation_indices()
        assert await collect_unavailability_cert(CHAIN, 100, H) is None

    @pytest.mark.asyncio
    async def test_unlock_justification_returns_bundle(self, monkeypatch):
        await unavail.reset_observation_indices()
        monkeypatch.setattr(unavail, "locate_voted_block", AsyncMock(return_value=None))
        idx = await unavail.get_observation_index(CHAIN)
        idx.note_request(100, RIVAL, ADDR2)
        idx.note_response(100, RIVAL, ADDR3)
        cert = _cert()
        bundle = await unlock_justification(CHAIN, 100, [H], ignore={canonical_address(ADDR1)}, request_cert=cert.to_dict())
        assert bundle is not None
        assert bundle["kind"] == "unavailability_cert"
        assert bundle["certs"][0]["hash"] == H
        assert bundle["index"]["clean"] is True

    @pytest.mark.asyncio
    async def test_fetchable_voted_block_blocks_unlock(self, monkeypatch):
        """Leg-1 pin: unfetchable_persists=False must hold the unlock even
        with a clean index and a valid carried cert — kills the if-False
        mutation on the leg-1 gate."""
        await unavail.reset_observation_indices()
        persist = AsyncMock(return_value=False)
        monkeypatch.setattr(unavail, "unfetchable_persists", persist)
        collect = AsyncMock(return_value=_cert())
        monkeypatch.setattr(unavail, "collect_unavailability_cert", collect)
        idx = await unavail.get_observation_index(CHAIN)
        idx.note_request(100, RIVAL, ADDR2)
        idx.note_response(100, RIVAL, ADDR3)
        assert (
            await unlock_justification(CHAIN, 100, [H], ignore={canonical_address(ADDR1)}, request_cert=_cert().to_dict())
            is None
        )
        persist.assert_awaited_once()
        collect.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dirty_index_blocks_unlock(self, monkeypatch):
        await unavail.reset_observation_indices()
        monkeypatch.setattr(unavail, "locate_voted_block", AsyncMock(return_value=None))
        idx = await unavail.get_observation_index(CHAIN)
        idx.note_request(100, RIVAL, ADDR2)
        idx.note_response(100, RIVAL, ADDR3)
        idx.note_response(100, H, ADDR2)  # foreign attestation for voted hash
        # The ~1 s unfetchable wait would age the observation out of the
        # 0.25 s evidence window; freeze the index clock so it stays dirty.
        frozen = time.monotonic()
        idx._mono = lambda: frozen
        assert (
            await unlock_justification(CHAIN, 100, [H], ignore={canonical_address(ADDR1)}, request_cert=_cert().to_dict())
            is None
        )

    @pytest.mark.asyncio
    async def test_missing_and_invalid_cert_fall_through_to_collect(self, monkeypatch):
        await unavail.reset_observation_indices()
        monkeypatch.setattr(unavail, "locate_voted_block", AsyncMock(return_value=None))
        idx = await unavail.get_observation_index(CHAIN)
        idx.note_request(100, RIVAL, ADDR2)
        idx.note_response(100, RIVAL, ADDR3)
        # Invalid carried cert (wrong hash) → collector path; stub collect.
        collect = AsyncMock(return_value=_cert())
        monkeypatch.setattr(unavail, "collect_unavailability_cert", collect)
        bad = _cert(block_hash="0xother").to_dict()
        bundle = await unlock_justification(CHAIN, 100, [H], ignore={canonical_address(ADDR1)}, request_cert=bad)
        assert bundle is not None
        collect.assert_awaited()


class _Clock:
    def __init__(self, now: float = T0) -> None:
        self.now = now

    def time(self) -> float:
        return self.now

    def monotonic(self) -> float:
        return self.now

    def advance(self, s: float) -> None:
        self.now += s


class TestAttesterGateArmed:
    def _service(self, monkeypatch):
        broker = _Broker()
        monkeypatch.setattr(ra_module, "gossip_broker", broker)
        clock = _Clock()
        monkeypatch.setattr(ra_module, "time", clock)
        monkeypatch.setattr(vote_journal, "time", clock)
        locate = AsyncMock(return_value=None)
        monkeypatch.setattr(ra_module, "locate_voted_block", locate)
        svc = RemoteAttestationService(CHAIN, {ADDR1: KEY1})
        return svc, broker, clock, locate

    @pytest.mark.asyncio
    async def test_valve_expired_without_justification_refuses(self, monkeypatch):
        """Armed: the 300 s valve alone must NOT release the rival."""
        monkeypatch.setattr(settings, "vote_journal_justification_enabled", True)
        unlock = AsyncMock(return_value=None)
        monkeypatch.setattr(unavail, "unlock_justification", unlock)
        svc, broker, clock, _ = self._service(monkeypatch)
        await svc._handle_request(_request(100, H, PROPOSER, clock.now))
        assert len(broker.published) == 1

        clock.advance(10_000)
        await svc._handle_request(_request(100, RIVAL, PROPOSER, clock.now))

        unlock.assert_awaited()
        assert len(broker.published) == 1, "armed valve released without justification"
        votes = get_vote_journal(CHAIN).votes_at(100, ADDR1)
        assert all(v.block_hash != RIVAL for v in votes)

    @pytest.mark.asyncio
    async def test_valve_expired_with_justification_permits_and_records(self, monkeypatch):
        monkeypatch.setattr(settings, "vote_journal_justification_enabled", True)
        bundle = {"kind": "unavailability_cert", "height": 100, "hashes": [H], "index": {}, "certs": [_cert().to_dict()]}
        monkeypatch.setattr(unavail, "unlock_justification", AsyncMock(return_value=bundle))
        recorder = __import__("unittest.mock", fromlist=["Mock"]).Mock()
        svc, broker, clock, _ = self._service(monkeypatch)
        monkeypatch.setattr(svc, "_equivocation_recorder", lambda: recorder)
        await svc._handle_request(_request(100, H, PROPOSER, clock.now))

        clock.advance(10_000)
        await svc._handle_request(_request(100, RIVAL, PROPOSER, clock.now))

        assert len(broker.published) == 2, "justified unlock did not release the rival"
        rival_votes = [v for v in get_vote_journal(CHAIN).votes_at(100, ADDR1) if v.block_hash == RIVAL]
        assert rival_votes and rival_votes[0].justification == bundle
        # response carries the justification artifact
        last = broker.published[-1][1]
        assert last.get("unlock_justification") == bundle
        # evidence class tag reached the recorder
        calls = recorder.record_attestation_equivocation.call_args_list
        assert calls and calls[-1].kwargs.get("justification") == "unavailability_cert"

    @pytest.mark.asyncio
    async def test_flag_off_keeps_phase1_valve(self, monkeypatch):
        """Armed machinery must not run with the flag off."""
        unlock = AsyncMock(return_value=None)
        monkeypatch.setattr(unavail, "unlock_justification", unlock)
        svc, broker, clock, _ = self._service(monkeypatch)
        await svc._handle_request(_request(100, H, PROPOSER, clock.now))
        clock.advance(10_000)
        await svc._handle_request(_request(100, RIVAL, PROPOSER, clock.now))
        unlock.assert_not_awaited()
        assert len(broker.published) == 2


class TestProposerGateArmed:
    @pytest.mark.asyncio
    async def test_honor_vote_journal_armed(self, monkeypatch, tmp_path):
        from aitbc_chain.config import ProposerConfig

        config = ProposerConfig(
            chain_id=CHAIN,
            proposer_id=ADDR1,
            interval_seconds=1.0,
            max_txs_per_block=10,
            max_block_size_bytes=1_000_000,
        )
        proposer = PoAProposer(config=config, session_factory=lambda: None)
        proposer._validator_keys = {ADDR1: KEY1}
        journal = get_vote_journal(CHAIN)
        journal.record(100, ADDR1, H, "attest", 0, PROPOSER, now=1.0)
        # valve: vote is ancient
        votes = journal.votes_at(100, ADDR1)
        assert votes

        monkeypatch.setattr(settings, "vote_journal_justification_enabled", True)
        bundle = {"kind": "unavailability_cert", "height": 100, "hashes": [H], "index": {}, "certs": []}
        unlock = AsyncMock(return_value=bundle)
        monkeypatch.setattr(unavail, "unlock_justification", unlock)
        # locate miss so the fetch leg inside _honor_vote_journal passes
        monkeypatch.setattr(poa_module, "locate_voted_block", AsyncMock(return_value=None))

        suppressed = await proposer._honor_vote_journal(100, ADDR1)
        assert suppressed is False
        unlock.assert_awaited()
        assert proposer._unlock_justifications.get(100) == bundle

        # Without justification the proposal stays suppressed
        unlock.return_value = None
        proposer._unlock_justifications.pop(100, None)
        assert await proposer._honor_vote_journal(100, ADDR1) is True

    def test_journal_justification_roundtrip(self, tmp_path):
        from aitbc_chain.consensus.vote_journal import VoteJournal

        j = VoteJournal(CHAIN, tmp_path / "vj.json")
        just = {"kind": "unavailability_cert", "certs": [{"hash": H}]}
        j.record(5, ADDR1, RIVAL, KIND_ATTEST, justification=just, now=T0)
        reloaded = VoteJournal(CHAIN, tmp_path / "vj.json")
        votes = reloaded.votes_at(5, ADDR1)
        assert votes[0].justification == just

    def test_slashing_justification_field(self):
        mgr = SlashingManager()
        ev = mgr.record_attestation_equivocation(
            validator_address=ADDR1,
            height=100,
            round_number=None,
            block_hash_a=H,
            block_hash_b=RIVAL,
            justification="unavailability_cert",
        )
        payload = json.loads(ev.evidence)
        assert payload["justification"] == "unavailability_cert"
        ev2 = mgr.record_attestation_equivocation(
            validator_address=ADDR2,
            height=101,
            round_number=None,
            block_hash_a=H,
            block_hash_b=RIVAL,
        )
        assert "justification" not in json.loads(ev2.evidence)


def _counter(name: str) -> float:
    return float(metrics_registry._counters.get(name, 0.0))


class _SlowFlipBroker(_Broker):
    """Broker that records foreign attest activity for the voted hash while
    the UC collection is in flight — the quiet-flip-during-probe pin."""

    def __init__(self, idx, height: int, block_hash: str, signer: str, key: str, **kw):
        super().__init__(**kw)
        self._idx = idx
        self._height = height
        self._hash = block_hash
        self._signer = signer
        self._key = key

    async def publish(self, topic: str, message: dict) -> None:
        if "unavail_query" in topic:
            self._idx.note_response(self._height, self._hash, self._signer)
        await super().publish(topic, message)


class TestRespinProbeOrder:
    """#1281 respin (option c): quiet-hash → UC probe → full re-verdict.

    The pre-seeded-actor tests above cannot catch the h35 deadlock — the
    mesh-visibility leg must be fed by the probe itself. These pins run a
    COLD index (no actors, no entries) end-to-end.
    """

    @pytest.mark.asyncio
    async def test_h35_replay_cold_index_recovers(self, monkeypatch):
        """Regression: empty index + honest responders + unfetchable hash
        ⇒ unlock bundle. This is the exact h35 wedge shape."""
        await unavail.reset_observation_indices()
        monkeypatch.setattr(unavail, "locate_voted_block", AsyncMock(return_value=None))
        broker = _Broker(responders=[(ADDR2, KEY2), (ADDR3, KEY3)])
        bundle = await unlock_justification(CHAIN, 100, [H], ignore={canonical_address(ADDR1)}, broker=broker)
        assert bundle is not None, "cold-index probe must establish visibility and unlock"
        assert bundle["kind"] == "unavailability_cert"
        assert len(bundle["certs"]) == 1
        assert bundle["index"]["mesh_visible"] is True
        assert _counter("unavail_probe_total") >= 1
        assert _counter("unavail_cert_collected_total") >= 1
        assert _counter("unavail_unlock_justified_total") >= 1

    @pytest.mark.asyncio
    async def test_quiet_fail_skips_collection(self, monkeypatch):
        """Live attest traffic for the voted hash ⇒ None and the probe is
        never even started (no collection, no query published)."""
        await unavail.reset_observation_indices()
        monkeypatch.setattr(unavail, "unfetchable_persists", AsyncMock(return_value=True))
        collect = AsyncMock(return_value=_cert())
        monkeypatch.setattr(unavail, "collect_unavailability_cert", collect)
        idx = await unavail.get_observation_index(CHAIN)
        idx.note_response(100, H, ADDR2)  # fresh foreign attestation for voted hash
        broker = _Broker()
        assert await unlock_justification(CHAIN, 100, [H], ignore={canonical_address(ADDR1)}, broker=broker) is None
        collect.assert_not_awaited()
        assert not any("unavail_query" in t for t, _ in broker.published)
        assert _counter("unavail_not_quiet_total") >= 1

    @pytest.mark.asyncio
    async def test_failed_collection_backs_off_without_storm(self, monkeypatch):
        """< threshold responses ⇒ None; an immediate second evaluation
        hits the negative backoff and publishes no second query."""
        await unavail.reset_observation_indices()
        monkeypatch.setattr(unavail, "unfetchable_persists", AsyncMock(return_value=True))
        monkeypatch.setattr(settings, "unavail_collect_seconds", 0.2)
        broker = _Broker(responders=[])  # nobody answers
        ignore = {canonical_address(ADDR1)}
        assert await unlock_justification(CHAIN, 100, [H], ignore=ignore, broker=broker) is None
        assert await unlock_justification(CHAIN, 100, [H], ignore=ignore, broker=broker) is None
        queries = [m for t, m in broker.published if "unavail_query" in t]
        assert len(queries) == 1, "backoff must suppress the retry storm"
        assert _counter("unavail_collect_backoff_total") >= 1
        assert _counter("unavail_probe_total") == 1

    @pytest.mark.asyncio
    async def test_two_of_four_minority_never_unlocks(self, monkeypatch):
        """Partition safety: self + one peer assemble a valid 2-of-4 cert,
        but only ONE foreign validator is visible ⇒ mesh_visible False ⇒
        hold. Cert quorum is not mesh visibility."""
        await unavail.reset_observation_indices()
        monkeypatch.setattr(unavail, "unfetchable_persists", AsyncMock(return_value=True))
        # "Self" (ADDR1) answers our own query plus one peer — the cert
        # verifies at threshold 2, but ignore excludes self from visibility.
        broker = _Broker(responders=[(ADDR1, KEY1), (ADDR2, KEY2)])
        bundle = await unlock_justification(CHAIN, 100, [H], ignore={canonical_address(ADDR1)}, broker=broker)
        assert bundle is None
        assert _counter("unavail_mesh_not_visible_total") >= 1
        assert _counter("unavail_unlock_justified_total") == 0

    @pytest.mark.asyncio
    async def test_quiet_flip_during_probe_revokes(self, monkeypatch):
        """Attest activity arriving DURING the collect window must fail the
        post-probe re-verdict — acquisition is not authorization."""
        await unavail.reset_observation_indices()
        monkeypatch.setattr(unavail, "unfetchable_persists", AsyncMock(return_value=True))
        # Wide quiet window so the mid-collect note is still inside it at
        # re-check time (the default 0.25 s test window would expire first).
        monkeypatch.setattr(settings, "unavail_evidence_seconds", 5.0)
        idx = await unavail.get_observation_index(CHAIN)
        broker = _SlowFlipBroker(idx, 100, H, ADDR3, KEY3, responders=[(ADDR2, KEY2), (ADDR3, KEY3)])
        bundle = await unlock_justification(CHAIN, 100, [H], ignore={canonical_address(ADDR1)}, broker=broker)
        assert bundle is None
        assert _counter("unavail_not_quiet_total") >= 1

    @pytest.mark.asyncio
    async def test_concurrent_callers_share_one_probe_and_cache(self, monkeypatch):
        """Single-flight: concurrent evaluations publish ONE query; the
        success cert is cached and reused; expiry forces re-collection."""
        await unavail.reset_observation_indices()
        monkeypatch.setattr(unavail, "unfetchable_persists", AsyncMock(return_value=True))
        monkeypatch.setattr(settings, "unavail_collect_seconds", 0.2)
        # cert_max_age 31 ⇒ cache reuse margin = 1 s.
        monkeypatch.setattr(settings, "unavail_cert_max_age_seconds", 31.0)
        broker = _Broker(responders=[(ADDR2, KEY2), (ADDR3, KEY3)])
        ignore = {canonical_address(ADDR1)}
        b1, b2 = await asyncio.gather(
            unlock_justification(CHAIN, 100, [H], ignore=ignore, broker=broker),
            unlock_justification(CHAIN, 100, [H], ignore=ignore, broker=broker),
        )
        assert b1 is not None and b2 is not None
        queries = [m for t, m in broker.published if "unavail_query" in t]
        assert len(queries) == 1, "concurrent callers must share one collection"
        # Cached cert: immediate re-evaluation publishes nothing new.
        assert await unlock_justification(CHAIN, 100, [H], ignore=ignore, broker=broker) is not None
        queries = [m for t, m in broker.published if "unavail_query" in t]
        assert len(queries) == 1, "fresh cached cert must be reused"
        # Past the reuse margin the cert is re-collected.
        await asyncio.sleep(1.1)
        assert await unlock_justification(CHAIN, 100, [H], ignore=ignore, broker=broker) is not None
        queries = [m for t, m in broker.published if "unavail_query" in t]
        assert len(queries) == 2, "stale-margin cert must be re-collected"

    @pytest.mark.asyncio
    async def test_listener_path_never_awaits_inflight_probe(self, monkeypatch):
        """wait_for_probe=False returns None while a collection is in
        flight — the attest-request listener is never held for the
        collect window."""
        await unavail.reset_observation_indices()
        monkeypatch.setattr(unavail, "unfetchable_persists", AsyncMock(return_value=True))
        monkeypatch.setattr(settings, "unavail_collect_seconds", 0.4)
        broker = _Broker(responders=[(ADDR2, KEY2), (ADDR3, KEY3)])
        ignore = {canonical_address(ADDR1)}
        # Proposer-style caller starts and awaits the probe.
        waiting = asyncio.ensure_future(
            unlock_justification(CHAIN, 100, [H], ignore=ignore, broker=broker, wait_for_probe=True)
        )
        await asyncio.sleep(0.05)  # let it reach the in-flight collection
        start = time.monotonic()
        early = await unlock_justification(CHAIN, 100, [H], ignore=ignore, broker=broker, wait_for_probe=False)
        elapsed = time.monotonic() - start
        assert early is None
        assert elapsed < 0.3, f"listener-path evaluation blocked {elapsed:.2f}s on the probe"
        bundle = await waiting
        assert bundle is not None
