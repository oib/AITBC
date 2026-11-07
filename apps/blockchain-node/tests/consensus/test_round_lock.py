"""#1242 round-keyed attestation lock (attestation_round_lock_enabled).

Covers the AD-mandated controls: tip-height/canonical-parent authorization,
independent round derivation + signed round binding, the shared U1/U2
transition verdict (full gates-window failure evidence or monotonic
fallback), durable anti-equivocation persistence across restart, and the
proposer-side mirror in ``_honor_attestation_lock``.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from aitbc_chain.config import ProposerConfig, settings
from aitbc_chain.consensus import remote_attestation as ra_module
from aitbc_chain.consensus.poa import PoAProposer
from aitbc_chain.consensus.remote_attestation import RemoteAttestationService
from aitbc_chain.metrics import metrics_registry

PARENT_TS = datetime(2026, 1, 1, tzinfo=UTC)
ROUND_SECONDS = 60


@pytest.fixture(autouse=True)
def _round_lock_on(monkeypatch):
    monkeypatch.setattr(settings, "attestation_round_lock_enabled", True)
    monkeypatch.setattr(settings, "consensus_proposer_round_seconds", ROUND_SECONDS)
    monkeypatch.setattr(settings, "attestation_round_unlock_window_seconds", 16.0)
    monkeypatch.setattr(settings, "consensus_require_signed_attest_request", False)
    monkeypatch.setattr(settings, "consensus_enforce_proposer_schedule", False)
    metrics_registry.reset()
    yield
    metrics_registry.reset()


def _keys() -> tuple[str, str, str, str]:
    from eth_keys import keys

    our_key = "0x" + "11" * 32
    proposer_key = "0x" + "22" * 32
    our_addr = keys.PrivateKey(bytes.fromhex(our_key[2:])).public_key.to_checksum_address()
    proposer_addr = keys.PrivateKey(bytes.fromhex(proposer_key[2:])).public_key.to_checksum_address()
    return our_addr, our_key, proposer_addr, proposer_key


def _block_ts(round_: int) -> datetime:
    return PARENT_TS + timedelta(seconds=round_ * ROUND_SECONDS + 1)


def _header(
    height: int, block_hash: str, proposer: str, round_: int, parent_hash: str = "0xparent", chain_id: str = "test-chain"
) -> dict:
    return {
        "header": {
            "chain_id": chain_id,
            "height": height,
            "hash": block_hash,
            "parent_hash": parent_hash,
            "proposer": proposer,
            "state_root": "0xroot",
            "bridge_state_root": "",
            "timestamp": _block_ts(round_).isoformat(),
            "round": round_,
        },
        "timestamp": time.time(),
    }


class _StubBroker:
    def __init__(self):
        self.published: list[tuple[str, dict]] = []

    async def publish(self, topic: str, message: dict):
        self.published.append((topic, message))


def _service(
    monkeypatch,
    our_addr: str,
    our_key: str,
    proposer_addr: str,
    tmp_path,
    tip: tuple[int, str] = (99, "0xparent"),
) -> tuple[RemoteAttestationService, _StubBroker]:
    monkeypatch.setattr(
        settings,
        "validator_set",
        json.dumps([{"address": our_addr}, {"address": proposer_addr}]),
    )
    broker = _StubBroker()
    monkeypatch.setattr(ra_module, "gossip_broker", broker)
    svc = RemoteAttestationService("test-chain", {our_addr: our_key})
    svc._round_locks_path = tmp_path / "locks.json"
    # Tip authorization + round derivation stubs: tip is (99, "0xparent");
    # parent "0xparent" resolves to PARENT_TS so round = declared round.
    svc._local_head = lambda: tip  # type: ignore[method-assign]
    svc._canonical_hash_at = lambda h: {99: "0xparent", 100: "0xaaaa"}.get(h)  # type: ignore[method-assign]
    svc._parent_timestamp = lambda p: PARENT_TS if p == "0xparent" else None  # type: ignore[method-assign]
    return svc, broker


def _signed_rounds(svc: RemoteAttestationService) -> list[int]:
    return sorted(r for (_h, r) in svc._round_locks)


class TestTipAuthorization:
    @pytest.mark.asyncio
    async def test_tip_proposal_signs(self, monkeypatch, tmp_path):
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr, tmp_path)

        # height 100 == tip(99)+1, parent == tip hash → authorized.
        await svc._handle_request(_header(100, "0xaaaa", proposer_addr, 0))
        assert len(broker.published) == 1
        resp = broker.published[0][1]
        assert resp["round"] == 0

    @pytest.mark.asyncio
    async def test_stale_rival_at_decided_height_refused(self, monkeypatch, tmp_path):
        our_addr, our_key, proposer_addr, _ = _keys()
        # Tip IS height 100 (hash 0xaaaa): height 100 is decided.
        svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr, tmp_path, tip=(100, "0xaaaa"))

        # A rival 0xbbbb at the same decided height is the harvest path → refused.
        await svc._handle_request(_header(100, "0xbbbb", proposer_addr, 0))
        assert not broker.published

    @pytest.mark.asyncio
    async def test_canonical_history_attestation_allowed(self, monkeypatch, tmp_path):
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr, tmp_path, tip=(100, "0xaaaa"))

        # Attesting the canonical block at a decided height (proof path) is
        # allowed; it cannot feed a rival collection.
        await svc._handle_request(_header(100, "0xaaaa", proposer_addr, 0))
        assert len(broker.published) == 1

    @pytest.mark.asyncio
    async def test_future_height_refused(self, monkeypatch, tmp_path):
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr, tmp_path)

        await svc._handle_request(_header(105, "0xaaaa", proposer_addr, 0))
        assert not broker.published

    @pytest.mark.asyncio
    async def test_parent_mismatch_refused(self, monkeypatch, tmp_path):
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr, tmp_path)

        # height 100 extends tip but claims a different parent → refused.
        await svc._handle_request(_header(100, "0xaaaa", proposer_addr, 0, parent_hash="0xother"))
        assert not broker.published

    @pytest.mark.asyncio
    async def test_round_mismatch_refused(self, monkeypatch, tmp_path):
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr, tmp_path)

        # Declared round 5 but timestamps derive round 0 → refused.
        req = _header(100, "0xaaaa", proposer_addr, 0)
        req["header"]["round"] = 5
        await svc._handle_request(req)
        assert not broker.published


class TestRoundLockTransition:
    @pytest.mark.asyncio
    async def test_same_round_rival_refused(self, monkeypatch, tmp_path):
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr, tmp_path)

        await svc._handle_request(_header(100, "0xaaaa", proposer_addr, 0))
        await svc._handle_request(_header(100, "0xbbbb", proposer_addr, 0))
        assert len(broker.published) == 1
        assert svc._round_locks[(100, 0)].block_hash == "0xaaaa"

    @pytest.mark.asyncio
    async def test_same_round_same_hash_idempotent(self, monkeypatch, tmp_path):
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr, tmp_path)

        await svc._handle_request(_header(100, "0xaaaa", proposer_addr, 0))
        await svc._handle_request(_header(100, "0xaaaa", proposer_addr, 0))
        assert len(broker.published) == 2

    @pytest.mark.asyncio
    async def test_later_round_blocked_until_gates_window(self, monkeypatch, tmp_path):
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr, tmp_path)

        await svc._handle_request(_header(100, "0xaaaa", proposer_addr, 0))
        # Later-round rival: U1 ok but U2 unproven — the later request was
        # just seen and the locked round's gates window has not elapsed.
        await svc._handle_request(_header(100, "0xbbbb", proposer_addr, 1))
        assert len(broker.published) == 1

        # Age the locked round's request observation past the 16s gates
        # window → the same later-round rival now signs (U2 protocol path).
        entry = svc._round_locks[(100, 0)]
        entry.request_seen_at = time.monotonic() - 20.0
        svc._requests_seen[100][0] = entry.request_seen_at
        await svc._handle_request(_header(100, "0xbbbb", proposer_addr, 1))
        assert len(broker.published) == 2
        assert (100, 1) in svc._round_locks

    @pytest.mark.asyncio
    async def test_later_round_blocked_without_later_request_evidence(self, monkeypatch, tmp_path):
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr, tmp_path)

        await svc._handle_request(_header(100, "0xaaaa", proposer_addr, 0))
        # Simulate signing round 0 without ever having seen its request
        # (restored state): no request_seen → protocol U2 unavailable.
        entry = svc._round_locks[(100, 0)]
        entry.request_seen_at = None
        svc._requests_seen.clear()
        await svc._handle_request(_header(100, "0xbbbb", proposer_addr, 1))
        assert len(broker.published) == 1

    @pytest.mark.asyncio
    async def test_monotonic_fallback_unlocks_later_round(self, monkeypatch, tmp_path):
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr, tmp_path)

        await svc._handle_request(_header(100, "0xaaaa", proposer_addr, 0))
        # Backdate the signature past the 60s window → fallback U2.
        entry = svc._round_locks[(100, 0)]
        entry.signed_at = time.monotonic() - 3600
        entry.signed_wall = time.time() - 3600
        await svc._handle_request(_header(100, "0xbbbb", proposer_addr, 1))
        assert len(broker.published) == 2

    @pytest.mark.asyncio
    async def test_earlier_round_never_signs(self, monkeypatch, tmp_path):
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr, tmp_path)

        await svc._handle_request(_header(100, "0xaaaa", proposer_addr, 1))
        # An "earlier round" request (round 0 timestamps) at the same height:
        # U1 fails regardless of elapsed time — never sign backwards.
        svc._round_locks[(100, 1)].signed_at = time.monotonic() - 7200
        await svc._handle_request(_header(100, "0xbbbb", proposer_addr, 0))
        assert len(broker.published) == 1


class TestPersistence:
    def test_records_survive_restart(self, monkeypatch, tmp_path):
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, _ = _service(monkeypatch, our_addr, our_key, proposer_addr, tmp_path)
        svc._record_round_lock(100, 0, "0xaaaa", proposer_addr)
        assert svc._round_locks_path.exists()

        # Fresh service on the same path = restart.
        svc2 = RemoteAttestationService("test-chain", {our_addr: our_key})
        svc2._round_locks_path = tmp_path / "locks.json"
        verdict = svc2.round_lock_verdict(100, 0, "0xbbbb")
        assert not verdict.permitted
        assert verdict.reason == "round_not_advanced:locked_r0_req_r0"

    def test_persisted_entry_allows_u2_after_evidence(self, monkeypatch, tmp_path):
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, _ = _service(monkeypatch, our_addr, our_key, proposer_addr, tmp_path)
        svc._record_round_lock(100, 0, "0xaaaa", proposer_addr)

        svc2 = RemoteAttestationService("test-chain", {our_addr: our_key})
        svc2._round_locks_path = tmp_path / "locks.json"
        # Later round still blocked: no request evidence yet.
        assert not svc2.round_lock_verdict(100, 1, "0xbbbb").permitted
        # Observe a later-round request and age past the gates window.
        svc2._record_request_seen(100, 1)
        entry = svc2._round_locks[(100, 0)]
        # request_seen_at was restored from wall time — backdate it.
        entry.request_seen_at = time.monotonic() - 20.0
        assert svc2.round_lock_verdict(100, 1, "0xbbbb").permitted

    def test_same_hash_idempotent_across_restart(self, monkeypatch, tmp_path):
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, _ = _service(monkeypatch, our_addr, our_key, proposer_addr, tmp_path)
        svc._record_round_lock(100, 0, "0xaaaa", proposer_addr)

        svc2 = RemoteAttestationService("test-chain", {our_addr: our_key})
        svc2._round_locks_path = tmp_path / "locks.json"
        # Re-signing the SAME hash at the SAME round is idempotent.
        assert svc2.round_lock_verdict(100, 0, "0xaaaa").permitted


class TestProposerMirror:
    def _proposer(self, svc: RemoteAttestationService) -> tuple[PoAProposer, Mock]:
        sm = Mock()
        sm.pull_from_peer.return_value = True
        sm.pull_in_flight.return_value = False
        config = ProposerConfig(
            chain_id="test-chain",
            proposer_id="test-proposer",
            interval_seconds=1.0,
            max_txs_per_block=10,
            max_block_size_bytes=1_000_000,
        )
        proposer = PoAProposer(config=config, session_factory=lambda: Mock(), sync_manager=sm)
        proposer._remote_attestation = svc
        return proposer, sm

    @pytest.mark.asyncio
    async def test_same_round_proposal_suppressed(self, monkeypatch, tmp_path):
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, _ = _service(monkeypatch, our_addr, our_key, proposer_addr, tmp_path)
        svc._record_round_lock(100, 0, "0xaaaa", proposer_addr)
        proposer, sm = self._proposer(svc)
        monkeypatch.setattr(settings, "gossip_mesh_peer_urls", "")

        # Proposing a different hash at the locked round → suppressed.
        assert await proposer._honor_attestation_lock(100, 0) is True

    @pytest.mark.asyncio
    async def test_later_round_proposal_proceeds_after_u2(self, monkeypatch, tmp_path):
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, _ = _service(monkeypatch, our_addr, our_key, proposer_addr, tmp_path)
        svc._record_round_lock(100, 0, "0xaaaa", proposer_addr)
        svc._record_request_seen(100, 1)
        entry = svc._round_locks[(100, 0)]
        entry.request_seen_at = time.monotonic() - 20.0
        proposer, sm = self._proposer(svc)
        monkeypatch.setattr(settings, "gossip_mesh_peer_urls", "")

        # U1+U2 satisfied → proposal proceeds (no suppression).
        assert await proposer._honor_attestation_lock(100, 1) is False

    @pytest.mark.asyncio
    async def test_later_round_proposal_suppressed_before_u2(self, monkeypatch, tmp_path):
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, _ = _service(monkeypatch, our_addr, our_key, proposer_addr, tmp_path)
        svc._record_round_lock(100, 0, "0xaaaa", proposer_addr)
        svc._record_request_seen(100, 1)
        proposer, sm = self._proposer(svc)
        monkeypatch.setattr(settings, "gossip_mesh_peer_urls", "")

        assert await proposer._honor_attestation_lock(100, 1) is True
