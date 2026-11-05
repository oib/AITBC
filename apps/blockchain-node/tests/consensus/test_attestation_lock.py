"""Attester lock (v0.25.x).

A validator that signs (attests) a peer's block X at height h must not
propose — or re-attest — a different block at h for one proposer round.
While the lock is live the proposer path tries to fetch X from a mesh peer
and pull it; if no peer serves it the proposal is suppressed until the lock
expires, which bounds the liveness hit. This closes the equivocation that
turned the 2026-09-27 asymmetric partitions into same-height forks: hub1
attested node2's block, never received it, then proposed a rival.
"""

from __future__ import annotations

import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from aitbc_chain.config import ProposerConfig, settings
from aitbc_chain.consensus import poa as poa_module
from aitbc_chain.consensus import remote_attestation as ra_module
from aitbc_chain.consensus.poa import PoAProposer
from aitbc_chain.consensus.remote_attestation import RemoteAttestationService
from aitbc_chain.metrics import metrics_registry


@pytest.fixture(autouse=True)
def _reset_metrics():
    metrics_registry.reset()
    yield
    metrics_registry.reset()


def _keys() -> tuple[str, str, str, str]:
    """(our_addr, our_key, proposer_addr, proposer_key) — distinct test keys."""
    from eth_keys import keys

    our_key = "0x" + "11" * 32
    proposer_key = "0x" + "22" * 32
    our_addr = keys.PrivateKey(bytes.fromhex(our_key[2:])).public_key.to_checksum_address()
    proposer_addr = keys.PrivateKey(bytes.fromhex(proposer_key[2:])).public_key.to_checksum_address()
    return our_addr, our_key, proposer_addr, proposer_key


def _header(height: int, block_hash: str, proposer: str, chain_id: str = "test-chain") -> dict:
    return {
        "header": {
            "chain_id": chain_id,
            "height": height,
            "hash": block_hash,
            "parent_hash": "0xparent",
            "proposer": proposer,
            "state_root": "0xroot",
            "bridge_state_root": "",
        },
        "timestamp": time.time(),
    }


class _StubBroker:
    def __init__(self):
        self.published: list[tuple[str, dict]] = []

    async def publish(self, topic: str, message: dict):
        self.published.append((topic, message))


def _service(monkeypatch, our_addr: str, our_key: str, proposer_addr: str) -> tuple[RemoteAttestationService, _StubBroker]:
    monkeypatch.setattr(
        settings,
        "validator_set",
        json.dumps([{"address": our_addr}, {"address": proposer_addr}]),
    )
    broker = _StubBroker()
    monkeypatch.setattr(ra_module, "gossip_broker", broker)
    svc = RemoteAttestationService("test-chain", {our_addr: our_key})
    return svc, broker


class TestAttesterLockRecord:
    @pytest.mark.asyncio
    async def test_signing_a_peer_header_records_the_lock(self, monkeypatch):
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr)

        await svc._handle_request(_header(100, "0xaaaa", proposer_addr))

        assert broker.published, "attestation response should have been published"
        lock = svc.attestation_lock(100, 60.0)
        assert lock is not None
        assert lock[0] == "0xaaaa"
        assert lock[1] == proposer_addr

    @pytest.mark.asyncio
    async def test_own_proposal_does_not_lock(self, monkeypatch):
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr)

        # Proposer field equals our own key — we never attest our own block.
        await svc._handle_request(_header(100, "0xaaaa", our_addr))

        assert not broker.published
        assert svc.attestation_lock(100, 60.0) is None

    @pytest.mark.asyncio
    async def test_rival_header_at_locked_height_is_refused(self, monkeypatch):
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr)

        await svc._handle_request(_header(100, "0xaaaa", proposer_addr))
        assert len(broker.published) == 1

        # A rival block at the same height must not collect our signature.
        await svc._handle_request(_header(100, "0xbbbb", proposer_addr))
        assert len(broker.published) == 1
        assert svc.attestation_lock(100, 60.0)[0] == "0xaaaa"

    @pytest.mark.asyncio
    async def test_same_height_same_hash_re_signs(self, monkeypatch):
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr)

        await svc._handle_request(_header(100, "0xaaaa", proposer_addr))
        await svc._handle_request(_header(100, "0xaaaa", proposer_addr))
        assert len(broker.published) == 2  # idempotent re-sign is allowed

    @pytest.mark.asyncio
    async def test_rival_signs_after_lock_expiry(self, monkeypatch):
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr)

        await svc._handle_request(_header(100, "0xaaaa", proposer_addr))
        # Backdate the lock past the window.
        svc._attested[100] = ("0xaaaa", proposer_addr, time.monotonic() - 3600)

        await svc._handle_request(_header(100, "0xbbbb", proposer_addr))
        assert len(broker.published) == 2
        assert svc.attestation_lock(100, 60.0)[0] == "0xbbbb"

    def test_lock_accessor_expires_entries(self):
        svc = RemoteAttestationService("test-chain", {})
        svc._attested[5] = ("0xaaaa", "0xPROP", time.monotonic() - 3600)
        assert svc.attestation_lock(5, 60.0) is None
        assert 5 not in svc._attested

    @pytest.mark.asyncio
    async def test_lock_disabled_flag_restores_double_sign(self, monkeypatch):
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr)
        monkeypatch.setattr(settings, "attestation_lock_enabled", False)

        await svc._handle_request(_header(100, "0xaaaa", proposer_addr))
        await svc._handle_request(_header(100, "0xbbbb", proposer_addr))
        assert len(broker.published) == 2  # legacy behaviour: signed both


class TestProposalSuppression:
    def _proposer(self, locked: tuple[str, str] | None) -> tuple[PoAProposer, Mock]:
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
        attestation = SimpleNamespace(attestation_lock=lambda h, w: locked if h == 100 else None)
        proposer._remote_attestation = attestation  # type: ignore[attr-defined]
        return proposer, sm

    @pytest.mark.asyncio
    async def test_locked_height_fetches_block_and_pulls(self, monkeypatch):
        proposer, sm = self._proposer(("0xaaaa", "0xPROP"))
        monkeypatch.setattr(settings, "gossip_mesh_peer_urls", "wss://peer1.example/rpc/gossip/ws")
        monkeypatch.setattr(settings, "attestation_lock_enabled", True)

        get = AsyncMock(return_value=SimpleNamespace(status_code=200, json=lambda: {"height": 100, "hash": "0xaaaa"}))
        monkeypatch.setattr(poa_module.SharedHttpClient, "get", get)

        assert await proposer._honor_attestation_lock(100) is True
        sm.pull_from_peer.assert_called_once_with("test-chain", "https://peer1.example")
        assert get.await_count == 1

    @pytest.mark.asyncio
    async def test_locked_height_without_serving_peer_still_suppresses(self, monkeypatch):
        proposer, sm = self._proposer(("0xaaaa", "0xPROP"))
        monkeypatch.setattr(settings, "gossip_mesh_peer_urls", "wss://peer1.example/rpc/gossip/ws")
        monkeypatch.setattr(settings, "attestation_lock_enabled", True)

        get = AsyncMock(return_value=SimpleNamespace(status_code=404, json=lambda: {}))
        monkeypatch.setattr(poa_module.SharedHttpClient, "get", get)

        assert await proposer._honor_attestation_lock(100) is True
        sm.pull_from_peer.assert_not_called()

    @pytest.mark.asyncio
    async def test_peer_serving_different_hash_does_not_pull(self, monkeypatch):
        proposer, sm = self._proposer(("0xaaaa", "0xPROP"))
        monkeypatch.setattr(settings, "gossip_mesh_peer_urls", "wss://peer1.example/rpc/gossip/ws")
        monkeypatch.setattr(settings, "attestation_lock_enabled", True)

        get = AsyncMock(return_value=SimpleNamespace(status_code=200, json=lambda: {"height": 100, "hash": "0xbbbb"}))
        monkeypatch.setattr(poa_module.SharedHttpClient, "get", get)

        assert await proposer._honor_attestation_lock(100) is True
        sm.pull_from_peer.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_lock_proceeds(self, monkeypatch):
        proposer, sm = self._proposer(None)
        monkeypatch.setattr(settings, "attestation_lock_enabled", True)
        assert await proposer._honor_attestation_lock(100) is False
        sm.pull_from_peer.assert_not_called()

    @pytest.mark.asyncio
    async def test_disabled_flag_proceeds(self, monkeypatch):
        proposer, sm = self._proposer(("0xaaaa", "0xPROP"))
        monkeypatch.setattr(settings, "attestation_lock_enabled", False)
        assert await proposer._honor_attestation_lock(100) is False
        sm.pull_from_peer.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_attestation_service_proceeds(self, monkeypatch):
        proposer, sm = self._proposer(None)
        proposer._remote_attestation = None
        monkeypatch.setattr(settings, "attestation_lock_enabled", True)
        assert await proposer._honor_attestation_lock(100) is False


# ---------------------------------------------------------------------------
# #1058: attester must refuse a header whose proposer is not the scheduled one
# ---------------------------------------------------------------------------


def _schedule(monkeypatch, scheduled_addr: str, parent_ts=None):
    """Arrange the proposer schedule so select_proposer() -> scheduled_addr and
    the round derivation sees a known parent timestamp."""
    from datetime import UTC, datetime

    from aitbc_chain.consensus import multi_validator_poa as mvpoa

    class _Sched:
        def select_proposer(self, height, round_number=0):
            return scheduled_addr

    monkeypatch.setattr(mvpoa, "get_consensus", lambda chain_id: _Sched())
    parent = parent_ts or datetime(2026, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(
        RemoteAttestationService,
        "_parent_timestamp",
        lambda self, ph: parent,
    )
    return parent


def _timed_header(height: int, block_hash: str, proposer: str, ts) -> dict:
    h = _header(height, block_hash, proposer)
    h["header"]["timestamp"] = ts.isoformat()
    return h


@pytest.mark.asyncio
async def test_unscheduled_proposer_is_refused(monkeypatch):
    """A valid-set validator that is NOT scheduled for the height/round gets
    no signature and no lock — the #1058 forged-header path."""
    from datetime import timedelta

    our_addr, our_key, proposer_addr, _ = _keys()
    svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr)

    # schedule picks our_addr, but the request claims proposer_addr
    parent_ts = _schedule(monkeypatch, our_addr)
    block_ts = parent_ts + timedelta(seconds=10)  # round 0
    await svc._handle_request(_timed_header(100, "0xaaaa", proposer_addr, block_ts))

    assert not broker.published
    assert svc.attestation_lock(100, 60.0) is None


@pytest.mark.asyncio
async def test_scheduled_proposer_still_signed(monkeypatch):
    """The scheduled validator is attested as before — gate is not over-broad."""
    from datetime import timedelta

    our_addr, our_key, proposer_addr, _ = _keys()
    svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr)

    parent_ts = _schedule(monkeypatch, proposer_addr)
    block_ts = parent_ts + timedelta(seconds=10)
    await svc._handle_request(_timed_header(100, "0xaaaa", proposer_addr, block_ts))

    assert broker.published
    assert svc.attestation_lock(100, 60.0)[0] == "0xaaaa"


@pytest.mark.asyncio
async def test_untraceable_schedule_stays_permissive(monkeypatch):
    """No parent timestamp / no schedule data → permissive, same policy as
    _is_scheduled_proposer in pbft.py (never lock the honest path out)."""
    from datetime import UTC, datetime, timedelta

    our_addr, our_key, proposer_addr, _ = _keys()
    svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr)

    monkeypatch.setattr(RemoteAttestationService, "_parent_timestamp", lambda self, ph: None)
    ts = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=10)
    await svc._handle_request(_timed_header(100, "0xaaaa", proposer_addr, ts))

    assert broker.published


@pytest.mark.asyncio
async def test_lagging_tip_mismatch_stays_permissive(monkeypatch, tmp_path):
    """#1058 rework: the tip fallback may only fire when the tip IS the parent.
    A lagging attester (parent block absent, tip hash != parent_hash) must not
    derive a round from the wrong block and refuse the honest proposer — the
    schedule becomes untraceable and the path stays permissive."""
    from contextlib import contextmanager
    from datetime import UTC, datetime, timedelta

    from aitbc_chain.base_models import Block
    from aitbc_chain.metadata import chain_metadata
    from aitbc_chain.consensus import multi_validator_poa as mvpoa
    from sqlmodel import Session, create_engine

    our_addr, our_key, proposer_addr, _ = _keys()
    engine = create_engine(f"sqlite:///{tmp_path}/chain.db")
    chain_metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            Block(
                chain_id="test-chain",
                height=50,
                hash="0x" + "99" * 32,  # the tip — NOT the parent hash
                parent_hash="0x" + "00" * 32,
                proposer=our_addr,
                timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                tx_count=0,
            )
        )
        session.commit()

    @contextmanager
    def factory():
        with Session(engine) as s:
            yield s
            s.commit()

    svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr)
    svc._session_factory = factory  # real _parent_timestamp, real DB
    assert svc._parent_timestamp("0x" + "aa" * 32) is None  # tip hash != parent

    # a schedule that WOULD refuse proposer_addr if it could be derived
    class _Sched:
        def select_proposer(self, height, round_number=0):
            return our_addr

    monkeypatch.setattr(mvpoa, "get_consensus", lambda chain_id: _Sched())

    block_ts = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=10)
    await svc._handle_request(_timed_header(100, "0xaaaa", proposer_addr, block_ts))
    assert broker.published  # permissive — honest proposer not refused


@pytest.mark.asyncio
async def test_tip_matching_parent_drives_schedule(monkeypatch, tmp_path):
    """When the tip IS the parent, the tip timestamp drives the round — the
    scheduled check still fires through the real _parent_timestamp."""
    from contextlib import contextmanager
    from datetime import UTC, datetime, timedelta

    from aitbc_chain.base_models import Block
    from aitbc_chain.metadata import chain_metadata
    from aitbc_chain.consensus import multi_validator_poa as mvpoa
    from sqlmodel import Session, create_engine

    our_addr, our_key, proposer_addr, _ = _keys()
    parent_hash = "0x" + "77" * 32
    engine = create_engine(f"sqlite:///{tmp_path}/chain.db")
    chain_metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            Block(
                chain_id="test-chain",
                height=99,
                hash=parent_hash,  # tip == parent
                parent_hash="0x" + "00" * 32,
                proposer=our_addr,
                timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                tx_count=0,
            )
        )
        session.commit()

    @contextmanager
    def factory():
        with Session(engine) as s:
            yield s
            s.commit()

    svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr)
    svc._session_factory = factory
    pts = svc._parent_timestamp(parent_hash)
    assert pts is not None and pts.replace(tzinfo=None) == datetime(2026, 1, 1)

    class _Sched:
        def select_proposer(self, height, round_number=0):
            return our_addr  # not the claimed proposer → refuse

    monkeypatch.setattr(mvpoa, "get_consensus", lambda chain_id: _Sched())

    h = _timed_header(100, "0xaaaa", proposer_addr, datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=10))
    h["header"]["parent_hash"] = parent_hash
    await svc._handle_request(h)
    assert not broker.published  # schedule was derivable → wrong proposer refused


# #1058 residual: the request must carry the proposer's block signature —
# the schedule check proves the claimed name, not authorship.
# ---------------------------------------------------------------------------


def _signed_request(height: int, block_hash: str, signer_key: str, proposer_addr: str, ts) -> dict:
    """A timed request signed with ``signer_key`` while claiming ``proposer_addr``."""
    from aitbc.crypto.consensus_signing import sign_block_hash

    req = _timed_header(height, block_hash, proposer_addr, ts)
    req["proposer_signature"] = sign_block_hash(req["header"], signer_key)
    return req


@pytest.mark.asyncio
async def test_signed_request_from_scheduled_proposer_is_attested(monkeypatch):
    from datetime import timedelta

    our_addr, our_key, proposer_addr, proposer_key = _keys()
    svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr)
    parent_ts = _schedule(monkeypatch, proposer_addr)

    req = _signed_request(100, "0xcccc", proposer_key, proposer_addr, parent_ts + timedelta(seconds=10))
    await svc._handle_request(req)

    assert broker.published
    assert svc.attestation_lock(100, 60.0)[0] == "0xcccc"


@pytest.mark.asyncio
async def test_forged_signature_other_key_is_refused(monkeypatch):
    """A request naming the scheduled proposer but signed by another key is
    forged — no attestation, no lock (#1058 done_when)."""
    from datetime import timedelta

    our_addr, our_key, proposer_addr, _ = _keys()
    forger_key = "0x" + "77" * 32
    svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr)
    parent_ts = _schedule(monkeypatch, proposer_addr)

    req = _signed_request(100, "0xdddd", forger_key, proposer_addr, parent_ts + timedelta(seconds=10))
    await svc._handle_request(req)

    assert not broker.published
    assert svc.attestation_lock(100, 60.0) is None


@pytest.mark.asyncio
async def test_unsigned_request_refused_once_armed(monkeypatch):
    """After consensus_require_signed_attest_request is armed an unsigned
    request is the unproven-forgery case — refused."""
    from datetime import timedelta

    our_addr, our_key, proposer_addr, _ = _keys()
    svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr)
    parent_ts = _schedule(monkeypatch, proposer_addr)
    monkeypatch.setattr(settings, "consensus_require_signed_attest_request", True)

    await svc._handle_request(_timed_header(100, "0xeeee", proposer_addr, parent_ts + timedelta(seconds=10)))

    assert not broker.published
    assert svc.attestation_lock(100, 60.0) is None


@pytest.mark.asyncio
async def test_unsigned_request_shadow_until_armed(monkeypatch):
    """Rollout: old peers send unsigned requests — before arming they stay
    attestable but are counted, never silently accepted."""
    from datetime import timedelta

    our_addr, our_key, proposer_addr, _ = _keys()
    svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr)
    parent_ts = _schedule(monkeypatch, proposer_addr)
    monkeypatch.setattr(settings, "consensus_require_signed_attest_request", False)

    await svc._handle_request(_timed_header(100, "0xffff", proposer_addr, parent_ts + timedelta(seconds=10)))

    assert broker.published
    assert svc.attestation_lock(100, 60.0)[0] == "0xffff"


@pytest.mark.asyncio
async def test_published_request_carries_verifying_proposer_signature(monkeypatch):
    """#1156: the attest_request carries ``proposer_signature`` populated at
    request-build time, verifiable against the scheduled proposer's key —
    not only stamped post-commit."""
    from aitbc.crypto.consensus_signing import sign_block_hash, verify_block_signature

    class _Sub:
        async def get(self):
            import asyncio

            await asyncio.sleep(60)

        def close(self):
            pass

    our_addr, our_key, proposer_addr, proposer_key = _keys()
    svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr)
    broker.subscribe = lambda *a, **k: _async_return(_Sub())

    block = SimpleNamespace(
        chain_id="test-chain",
        height=100,
        hash="0x" + "ab" * 32,
        parent_hash="0x" + "99" * 32,
        proposer=proposer_addr,
        state_root="0xroot",
        bridge_state_root="",
        aux_state_root="",
        timestamp=None,
        signature="",
    )
    # Signed exactly the way PoAProposer._sign_block_hash_for signs.
    block.signature = sign_block_hash(block, proposer_key)

    await svc.collect_attestations(block, min_count=1, timeout=0.05)

    reqs = [m for topic, m in broker.published if topic == svc._request_topic]
    assert reqs, "no attest_request was published"
    sig = reqs[0].get("proposer_signature")
    assert sig == block.signature
    assert verify_block_signature(reqs[0]["header"], sig, proposer_addr)


async def _async_return(value):
    return value


@pytest.mark.asyncio
async def test_signature_stamped_before_consensus_gates(monkeypatch):
    """#1156: ``block.signature`` exists when ``_run_consensus_gates`` runs —
    the attest_request published inside the gates carries it as
    ``proposer_signature``. Reverting the stamp to post-gates (the #1058
    regression that stalled the fleet at h18796) must fail this pin."""
    from contextlib import contextmanager
    from datetime import UTC, datetime

    @contextmanager
    def _null_session():
        yield None

    config = ProposerConfig(
        chain_id="test-chain",
        proposer_id="test-node",
        interval_seconds=1,
        max_block_size_bytes=1000,
        max_txs_per_block=100,
    )
    proposer = PoAProposer(config=config, session_factory=_null_session)

    block = SimpleNamespace()
    block.block_metadata = ""

    head = SimpleNamespace()
    head.timestamp = datetime.now(UTC)

    captured: dict = {}

    async def _gates(_session, _block, _hash, *_args, **_kwargs):
        captured["signature"] = _block.signature
        return True

    async def _passes_early_gates(*_args, **_kwargs):
        return SimpleNamespace()

    async def _broadcast(*_args, **_kwargs):
        return True

    monkeypatch.setattr(proposer, "_passes_early_gates", _passes_early_gates)
    monkeypatch.setattr(proposer, "_resolve_proposal_head", lambda *_: (head, 1, b"parent", 1))
    monkeypatch.setattr(proposer, "_select_round_proposer", lambda *_: ("0x" + "0" * 40, 0))
    monkeypatch.setattr(proposer, "_collect_proposal_txs", lambda *_: ([], {}, {}))
    monkeypatch.setattr(proposer, "_process_proposal_txs", lambda *_: ([], set(), True))
    monkeypatch.setattr(proposer, "_reject_if_all_invalid", lambda *_: False)
    monkeypatch.setattr(proposer, "_assemble_proposal_block", lambda *_: (block, b"fake-block-hash"))
    monkeypatch.setattr(proposer, "_run_consensus_gates", _gates)
    monkeypatch.setattr(proposer, "_sign_block_hash_for", lambda *_: "sig")
    monkeypatch.setattr(proposer, "_commit_and_record_block", lambda *_: None)
    monkeypatch.setattr(proposer, "_broadcast_block", _broadcast)

    result = await proposer._propose_block()

    assert result is True
    assert captured["signature"] == "sig", "block reached consensus gates unsigned"
