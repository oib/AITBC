"""Tests for chain divergence detection (V23-90).

The production failure these cover: a follower kept 4,211 blocks of a chain its hub had thrown
away, and for 46 hours every mechanism that could have noticed reported health instead — bulk
sync said "Already up to date" because the hub's height was lower, the force-pull gap check saw a
negative gap as no gap, fork rejections carried a reason that read like a win, and the state root
comparison logged a mismatch at INFO while copying the hub's balances over ours.
"""

import hashlib
from contextlib import contextmanager
from datetime import datetime

import pytest
from aitbc_chain import sync_divergence
from aitbc_chain.main import _pull_trigger
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.metrics import metrics_registry
from aitbc_chain.models import Account, Block
from aitbc_chain.sync import ChainSync
from aitbc_chain.sync_divergence import clear_divergence, report_divergence
from sqlmodel import Session, create_engine, select

CHAIN = "test-chain"
PEER = "https://hub.example.invalid"


@pytest.fixture(autouse=True)
def reset_state():
    metrics_registry.reset()
    sync_divergence._last_reported.clear()
    yield
    metrics_registry.reset()
    sync_divergence._last_reported.clear()


@pytest.fixture
def session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'divergence.db'}", echo=False)
    chain_metadata.create_all(engine)

    @contextmanager
    def _factory():
        with Session(engine) as session:
            yield session

    try:
        yield _factory
    finally:
        engine.dispose()


def _hash(height, marker):
    return "0x" + hashlib.sha256(f"{marker}|{height}".encode()).hexdigest()


def _seed(session_factory, count, marker="ours", chain_id=CHAIN):
    """Seed `count` blocks (heights 0..count-1) whose hashes depend on `marker`."""
    parent = "0x00"
    with session_factory() as session:
        for height in range(count):
            block_hash = _hash(height, marker)
            session.add(
                Block(
                    chain_id=chain_id,
                    height=height,
                    hash=block_hash,
                    parent_hash=parent,
                    proposer="proposer-a",
                    timestamp=datetime(2026, 1, 1, 0, 0, min(height, 59)),
                    tx_count=0,
                )
            )
            parent = block_hash
        session.commit()


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    """Answers /rpc/head only. Any other request is a test failure, which is how these tests
    assert that no blocks and no state snapshot were fetched."""

    def __init__(self, head):
        self._head = head
        self.paths: list[str] = []

    async def get(self, url, **kwargs):
        self.paths.append(url)
        if url.endswith("/rpc/head"):
            return _FakeResponse(self._head)
        raise AssertionError(f"unexpected request to {url}")

    async def aclose(self):
        return None


def _sync(session_factory, head):
    sync = ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)
    sync._client = _FakeClient(head)  # type: ignore[assignment]
    return sync


class TestDetectDivergence:
    def test_none_when_hash_agrees(self, session_factory):
        _seed(session_factory, 5)
        sync = ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)
        assert sync.detect_divergence(PEER, 4, _hash(4, "ours")) is None

    def test_flags_a_differing_hash(self, session_factory):
        _seed(session_factory, 5)
        sync = ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)
        div = sync.detect_divergence(PEER, 2, _hash(2, "theirs"))
        assert div is not None
        assert div.height == 2
        assert div.our_hash == _hash(2, "ours")
        assert div.peer_hash == _hash(2, "theirs")
        assert div.peer_url == PEER

    def test_none_when_we_have_no_block_at_that_height(self, session_factory):
        """A peer ahead of us has nothing to compare — that is an ordinary gap, not divergence."""
        _seed(session_factory, 3)
        sync = ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)
        assert sync.detect_divergence(PEER, 9, _hash(9, "theirs")) is None


class TestReportDivergence:
    def test_throttles_repeats_and_reports_again_after_clear(self):
        div = sync_divergence.Divergence(height=7, our_hash="0xours", peer_hash="0xtheirs", peer_url=PEER)
        assert report_divergence(CHAIN, div) is True
        assert report_divergence(CHAIN, div) is False
        clear_divergence(CHAIN)
        assert report_divergence(CHAIN, div) is True

    def test_counts_every_detection_even_when_the_log_is_throttled(self):
        div = sync_divergence.Divergence(height=7, our_hash="0xours", peer_hash="0xtheirs", peer_url=PEER)
        for _ in range(4):
            report_divergence(CHAIN, div)
        prom = metrics_registry.render_prometheus()
        assert "sync_divergence_detected_total 4" in prom


class TestBulkImportDivergence:
    async def test_reports_divergence_instead_of_up_to_date(self, session_factory):
        """The headline fault: the peer is *behind* us on a chain we do not have."""
        _seed(session_factory, 12)
        sync = _sync(session_factory, {"height": 5, "hash": _hash(5, "theirs")})

        imported = await sync.bulk_import_from(PEER)

        assert imported == 0
        prom = metrics_registry.render_prometheus()
        assert "sync_divergence_detected_total 1" in prom
        assert "sync_diverged 1.0" in prom

    async def test_up_to_date_when_the_peer_agrees(self, session_factory):
        _seed(session_factory, 12)
        sync = _sync(session_factory, {"height": 5, "hash": _hash(5, "ours")})

        imported = await sync.bulk_import_from(PEER)

        assert imported == 0
        prom = metrics_registry.render_prometheus()
        assert "sync_divergence_detected_total" not in prom
        assert "sync_diverged 0.0" in prom

    async def test_no_local_blocks_is_not_divergence(self, session_factory):
        """An empty node must not read a peer's genesis as a disagreement."""
        sync = _sync(session_factory, {"height": -1, "hash": ""})
        assert await sync.bulk_import_from(PEER) == 0
        assert "sync_divergence_detected_total" not in metrics_registry.render_prometheus()


class TestForkRejectionIsFlagged:
    def test_divergent_block_is_rejected_and_marked(self, session_factory):
        _seed(session_factory, 5)
        sync = ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)

        result = sync.import_block(
            {
                "height": 3,
                "hash": _hash(3, "theirs"),
                "parent_hash": _hash(2, "theirs"),
                "proposer": "proposer-b",
                "timestamp": datetime(2026, 6, 15).isoformat(),
            }
        )

        assert result.accepted is False
        assert result.diverged is True
        assert "different block at height 3" in result.reason
        assert "sync_divergence_rejected_total" in metrics_registry.render_prometheus()

    def test_a_duplicate_is_not_divergence(self, session_factory):
        """Same block we already hold: refused, but nothing is wrong with our chain."""
        _seed(session_factory, 5)
        sync = ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)

        result = sync.import_block(
            {
                "height": 3,
                "hash": _hash(3, "ours"),
                "parent_hash": _hash(2, "ours"),
                "proposer": "proposer-a",
                "timestamp": datetime(2026, 1, 1, 0, 0, 3).isoformat(),
            }
        )

        assert result.accepted is False
        assert result.diverged is False

    def test_a_gap_ahead_of_us_is_not_divergence(self, session_factory):
        _seed(session_factory, 5)
        sync = ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)

        result = sync.import_block(
            {
                "height": 20,
                "hash": _hash(20, "ours"),
                "parent_hash": _hash(19, "ours"),
                "proposer": "proposer-a",
                "timestamp": datetime(2026, 1, 1, 0, 0, 20).isoformat(),
            }
        )

        assert result.accepted is False
        assert result.diverged is False


class TestPullTrigger:
    @pytest.mark.parametrize(
        ("gap", "expected"),
        [
            (-1458, "ahead"),  # the production case: hub reset, follower kept its history
            (-1, "ahead"),
            (0, None),
            (2, None),
            (3, "behind"),
            (2758, "behind"),
        ],
    )
    def test_classifies_the_gap(self, gap, expected):
        assert _pull_trigger(gap) == expected


class TestSubscriptionClientEscalation:
    """The push path is where 2,787 rejections were logged identically. The counter has to live on
    the client, since ChainSync is rebuilt for every block."""

    async def test_reports_after_the_threshold_and_resets_when_a_block_is_accepted(self, monkeypatch):
        from aitbc_chain import subscription_client as sc
        from aitbc_chain.sync_validator import ImportResult

        div = sync_divergence.Divergence(height=2748, our_hash="0xours", peer_hash="0xtheirs", peer_url=PEER)
        outcome = [ImportResult(accepted=False, height=2748, block_hash="0xtheirs", reason="Divergent chain", diverged=True)]

        class _StubSync:
            def __init__(self, session_factory=None, chain_id=""):
                pass

            def import_block(self, block_data, transactions=None, skip_state_root_validation=False):
                return outcome[0]

            def detect_divergence(self, peer_url, peer_height, peer_hash):
                return div

        monkeypatch.setattr(sc, "ChainSync", _StubSync)
        client = sc.SubscriptionClient(PEER, "node-1", CHAIN)

        for _ in range(2):
            await client._import_block({"height": 2748, "hash": "0xtheirs"})
        assert client._consecutive_divergence == 2
        assert "sync_divergence_detected_total" not in metrics_registry.render_prometheus()

        await client._import_block({"height": 2748, "hash": "0xtheirs"})
        assert "sync_divergence_detected_total 1" in metrics_registry.render_prometheus()

        outcome[0] = ImportResult(accepted=True, height=2749, block_hash="0xok", reason="Appended to chain")
        await client._import_block({"height": 2749, "hash": "0xok"})
        assert client._consecutive_divergence == 0
        assert "sync_diverged 0.0" in metrics_registry.render_prometheus()

    async def test_a_transient_rejection_does_not_accumulate(self, monkeypatch):
        from aitbc_chain import subscription_client as sc
        from aitbc_chain.sync_validator import ImportResult

        class _StubSync:
            def __init__(self, session_factory=None, chain_id=""):
                pass

            def import_block(self, block_data, transactions=None):
                return ImportResult(accepted=False, height=9, block_hash="0x9", reason="Gap detected (our height: 4)")

            def detect_divergence(self, peer_url, peer_height, peer_hash):
                raise AssertionError("a gap must not be treated as divergence")

        monkeypatch.setattr(sc, "ChainSync", _StubSync)
        client = sc.SubscriptionClient(PEER, "node-1", CHAIN)

        for _ in range(5):
            await client._import_block({"height": 9, "hash": "0x9"})
        assert client._consecutive_divergence == 0
        assert "sync_divergence_detected_total" not in metrics_registry.render_prometheus()


class TestStateSyncRefusesADivergedPeer:
    async def test_balances_are_not_copied_from_a_chain_we_reject(self, session_factory):
        _seed(session_factory, 12)
        with session_factory() as session:
            session.add(Account(chain_id=CHAIN, address="ait1local", balance=500, nonce=1))
            session.commit()
        sync = _sync(session_factory, {"height": 5, "hash": _hash(5, "theirs")})

        result = await sync.sync_state_from(PEER)

        assert result["diverged"] is True
        assert result["divergence_height"] == 5
        assert result["synced"] == 0
        # The fake client fails any request other than /rpc/head, so reaching the snapshot at all
        # would have raised. Assert the balance too, since that is what the guard protects.
        assert sync._client.paths == [f"{PEER}/rpc/head"]  # type: ignore[attr-defined]
        with session_factory() as session:
            account = session.exec(select(Account).where(Account.address == "ait1local")).first()
            assert account is not None
            assert account.balance == 500
