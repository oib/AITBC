"""State-sync guards from incident 27207 (2026-09-28).

A proposer ran follower delta sync and overwrote committed state; followers
then accepted snapshots/deltas whose claimed root matched the *source's* root
but not the local head block's recorded ``state_root``. These tests pin the
guards: producers never state-sync, delta targets must equal the local head,
the source's claimed root must equal the recorded head root, and any applied
state is rolled back before commit if it does not reproduce that root.
"""

from __future__ import annotations

import base64
import json
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from aitbc.sync.state_diff import AccountChange, StateDiff
from aitbc_chain.base_models import Account, Block, ChainParameter
from aitbc_chain.config import is_block_producer, settings
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.metrics import metrics_registry
from aitbc_chain.state.state_root_utils import compute_state_root_full
from aitbc_chain.sync import ChainSync
from sqlmodel import Session, create_engine, select

CHAIN = "state-sync-guards"
T0 = datetime(2026, 1, 1, tzinfo=UTC)

ADDR_A = "0x" + "11" * 20
ADDR_B = "0x" + "22" * 20

HEAD = 5


@pytest.fixture()
def session_factory(tmp_path, monkeypatch):
    monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path))
    engine = create_engine(f"sqlite:///{tmp_path}/chain.db")
    chain_metadata.create_all(engine)

    @contextmanager
    def factory():
        with Session(engine) as session:
            yield session
            session.commit()

    return factory


@pytest.fixture(autouse=True)
def _reset_metrics():
    metrics_registry.reset()
    yield
    metrics_registry.reset()


@pytest.fixture(autouse=True)
def _follower_mode(monkeypatch):
    monkeypatch.setattr(settings, "blockchain_mode", "follower")
    monkeypatch.setattr(settings, "multi_validator_consensus_enabled", False)
    monkeypatch.setattr(settings, "sync_delta_enabled", True)
    monkeypatch.setattr(settings, "sync_delta_threshold", 100.0)


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeStream:
    """Async-context-manager stand-in for ``httpx.Response`` streaming."""

    def __init__(self, payload: dict[str, Any]):
        self._payload = payload

    async def __aenter__(self) -> _FakeStream:
        return self

    async def __aexit__(self, *args: Any) -> bool:
        return False

    def raise_for_status(self) -> None:
        return None

    async def aiter_bytes(self):
        yield json.dumps(self._payload).encode()


class _FakeClient:
    """Records calls; payloads keyed by URL path fragment."""

    def __init__(self, payloads: dict[str, dict[str, Any]]):
        self.payloads = payloads
        self.calls: list[tuple[str, Any]] = []

    async def get(self, url: str, params: Any = None):
        self.calls.append((url, params))
        for fragment, payload in self.payloads.items():
            if fragment in url:
                return _FakeResponse(payload)
        raise AssertionError(f"unexpected request to {url}")

    def stream(self, method: str, url: str, params: Any = None) -> _FakeStream:
        self.calls.append((url, params))
        for fragment, payload in self.payloads.items():
            if fragment in url:
                return _FakeStream(payload)
        raise AssertionError(f"unexpected request to {url}")


def _seed_state(session_factory, balance_a: int = 1000, nonce_a: int = 3) -> str:
    """Seed two accounts and a head block recording their real root."""
    with session_factory() as session:
        session.add(Account(chain_id=CHAIN, address=ADDR_A, balance=balance_a, nonce=nonce_a))
        session.add(Account(chain_id=CHAIN, address=ADDR_B, balance=500, nonce=1))
        session.flush()
        root = compute_state_root_full(session, CHAIN)
        session.add(
            Block(
                chain_id=CHAIN,
                height=HEAD,
                hash="0x" + "ab" * 32,
                parent_hash="0x00",
                proposer="test",
                timestamp=T0,
                tx_count=0,
                state_root=root,
            )
        )
        session.commit()
        return root


def _accounts(session_factory) -> dict[str, tuple[int, int]]:
    with session_factory() as session:
        rows = session.exec(select(Account).where(Account.chain_id == CHAIN)).all()
        return {a.address: (a.balance, a.nonce) for a in rows}


def _delta_payload(diff: StateDiff) -> dict[str, Any]:
    return {
        "diff": base64.b64encode(diff.encode()).decode(),
        "chain_parameters": [],
        "chain_parameter_history": [],
        "aux_state": {},
    }


def _snapshot_payload(root: str, accounts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "accounts": accounts
        if accounts is not None
        else [
            {"address": ADDR_A, "balance": 1000, "nonce": 3},
            {"address": ADDR_B, "balance": 500, "nonce": 1},
        ],
        "state_root": root,
        "chain_parameters": [],
        "chain_parameter_history": [],
        "aux_state": {},
    }


def _sync(session_factory, payloads: dict[str, dict[str, Any]]) -> tuple[ChainSync, _FakeClient]:
    sync = ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)
    client = _FakeClient(payloads)
    sync._client = client  # type: ignore[assignment]
    return sync, client


async def _no_divergence(self, source_url: str):
    return None, HEAD


@pytest.fixture(autouse=True)
def _patch_divergence(monkeypatch):
    monkeypatch.setattr(ChainSync, "peer_head_divergence", _no_divergence)


def test_is_block_producer_predicate(monkeypatch):
    monkeypatch.setattr(settings, "blockchain_mode", "hub")
    assert is_block_producer()
    monkeypatch.setattr(settings, "blockchain_mode", "follower")
    assert not is_block_producer()
    monkeypatch.setattr(settings, "multi_validator_consensus_enabled", True)
    monkeypatch.setattr(settings, "validator_set", "a,b")
    monkeypatch.setattr(settings, "proposer_id", "a")
    monkeypatch.setattr(settings, "proposer_key", "k")
    assert is_block_producer()


@pytest.mark.asyncio
async def test_producer_refuses_full_snapshot_without_network(session_factory, monkeypatch):
    root = _seed_state(session_factory)
    monkeypatch.setattr(settings, "blockchain_mode", "hub")
    sync, client = _sync(session_factory, {"state/snapshot": _snapshot_payload(root)})
    result = await sync.sync_state_from("http://peer")
    assert result["refused"] is True
    assert result["reason"] == "block_producer"
    assert client.calls == []
    assert metrics_registry._counters.get("state_sync_refused_total") == 1.0
    assert metrics_registry._counters.get("state_sync_refused_block_producer_total") == 1.0


@pytest.mark.asyncio
async def test_producer_refuses_delta_without_network(session_factory, monkeypatch):
    _seed_state(session_factory)
    monkeypatch.setattr(settings, "blockchain_mode", "hub")
    sync, client = _sync(session_factory, {})
    result = await sync.delta_sync_from("http://peer", HEAD - 1, HEAD)
    assert result["refused"] is True
    assert result["reason"] == "block_producer"
    assert client.calls == []


@pytest.mark.asyncio
async def test_delta_stale_target_refused(session_factory):
    _seed_state(session_factory)
    sync, client = _sync(session_factory, {})
    result = await sync.delta_sync_from("http://peer", HEAD - 2, HEAD - 1)
    assert result["refused"] is True
    assert result["reason"] == "stale_target"
    assert result["local_head"] == HEAD
    assert result["to_height"] == HEAD - 1
    assert client.calls == []
    assert metrics_registry._counters.get("state_sync_refused_stale_target_total") == 1.0


@pytest.mark.asyncio
async def test_delta_ahead_of_local_head_refused(session_factory, monkeypatch):
    _seed_state(session_factory)
    sync, client = _sync(session_factory, {})

    async def _boom(source_url):
        raise AssertionError("sync_state_from must not run for an ahead-of-head delta")

    monkeypatch.setattr(sync, "sync_state_from", _boom)
    result = await sync.delta_sync_from("http://peer", HEAD, HEAD + 1)
    assert result["refused"] is True
    assert result["reason"] == "ahead_of_local_head"
    assert result["local_head"] == HEAD
    assert client.calls == []


@pytest.mark.asyncio
async def test_delta_source_root_disagrees(session_factory):
    _seed_state(session_factory)
    diff = StateDiff(
        from_height=HEAD - 1,
        to_height=HEAD,
        to_state_root="0x" + "ff" * 32,
        changes=[AccountChange(ADDR_A, 1000, 1000, 3, 3)],
        chain_id=CHAIN,
    )
    sync, client = _sync(session_factory, {"state/delta": _delta_payload(diff)})
    result = await sync.delta_sync_from("http://peer", HEAD - 1, HEAD)
    assert result["refused"] is True
    assert result["reason"] == "source_root_disagrees"
    assert len(client.calls) == 1
    assert _accounts(session_factory) == {ADDR_A: (1000, 3), ADDR_B: (500, 1)}


@pytest.mark.asyncio
async def test_delta_wrong_resulting_root_rolls_back(session_factory):
    root = _seed_state(session_factory)
    # Claims our head root, but the change would produce a different one.
    diff = StateDiff(
        from_height=HEAD - 1,
        to_height=HEAD,
        to_state_root=root,
        changes=[AccountChange(ADDR_A, 1000, 42, 3, 3)],
        chain_id=CHAIN,
    )
    sync, _ = _sync(session_factory, {"state/delta": _delta_payload(diff)})
    result = await sync.delta_sync_from("http://peer", HEAD - 1, HEAD)
    assert result["refused"] is True
    assert result["reason"] == "root_mismatch_local_head"
    assert _accounts(session_factory) == {ADDR_A: (1000, 3), ADDR_B: (500, 1)}
    assert metrics_registry._counters.get("state_sync_refused_root_mismatch_local_head_total") == 1.0


@pytest.mark.asyncio
async def test_delta_matching_head_applies(session_factory):
    root = _seed_state(session_factory)
    diff = StateDiff(
        from_height=HEAD - 1,
        to_height=HEAD,
        to_state_root=root,
        changes=[AccountChange(ADDR_A, 1000, 1000, 3, 3)],
        chain_id=CHAIN,
    )
    sync, _ = _sync(session_factory, {"state/delta": _delta_payload(diff)})
    result = await sync.delta_sync_from("http://peer", HEAD - 1, HEAD)
    assert result.get("mode") == "delta"
    assert result["match"] is True


@pytest.mark.asyncio
async def test_snapshot_empty_head_refused_without_network(session_factory):
    """#1629: zero local blocks means no head root to verify against — the
    snapshot path must refuse before fetching rather than commit unverified
    state."""
    sync, client = _sync(session_factory, {"state/snapshot": _snapshot_payload("0x" + "00" * 32)})
    result = await sync.sync_state_from("http://peer")
    assert result["refused"] is True
    assert result["reason"] == "empty_head"
    assert client.calls == []
    assert metrics_registry._counters.get("state_sync_refused_empty_head_total") == 1.0


@pytest.mark.asyncio
async def test_delta_empty_head_refused_without_network(session_factory):
    """#1629: the delta path has the same unverified-commit hole on an empty
    head (its computed-root check keys on local_root too)."""
    sync, client = _sync(session_factory, {})
    result = await sync.delta_sync_from("http://peer", 0, HEAD)
    assert result["refused"] is True
    assert result["reason"] == "empty_head"
    assert client.calls == []


@pytest.mark.asyncio
async def test_snapshot_source_root_disagrees_refused_before_write(session_factory):
    _seed_state(session_factory)
    foreign = _snapshot_payload("0x" + "ff" * 32, accounts=[{"address": ADDR_A, "balance": 42, "nonce": 0}])
    sync, _ = _sync(session_factory, {"state/snapshot": foreign})
    result = await sync.sync_state_from("http://peer")
    assert result["refused"] is True
    assert result["reason"] == "source_root_disagrees"
    assert _accounts(session_factory) == {ADDR_A: (1000, 3), ADDR_B: (500, 1)}


@pytest.mark.asyncio
async def test_snapshot_oversized_response_body_refused(session_factory, monkeypatch):
    """#1627: the snapshot body is read with a decompressed-size cap — an
    oversized peer payload errors out before any account is touched."""
    root = _seed_state(session_factory)
    monkeypatch.setattr(settings, "sync_state_response_max_bytes", 16)
    sync, _ = _sync(session_factory, {"state/snapshot": _snapshot_payload(root)})
    result = await sync.sync_state_from("http://peer")
    assert result["synced"] == 0
    assert "error" in result
    assert _accounts(session_factory) == {ADDR_A: (1000, 3), ADDR_B: (500, 1)}


@pytest.mark.asyncio
async def test_delta_oversized_response_falls_back_to_capped_snapshot(session_factory, monkeypatch):
    """#1627: an oversized delta body takes the same fallback as any delta
    endpoint failure — and the snapshot it falls back to is equally capped."""
    root = _seed_state(session_factory)
    monkeypatch.setattr(settings, "sync_state_response_max_bytes", 16)
    sync, _ = _sync(
        session_factory,
        {"state/delta": _delta_payload(StateDiff(from_height=HEAD - 1, to_height=HEAD, to_state_root=root, changes=[]))},
    )
    result = await sync.delta_sync_from("http://peer", HEAD - 1, HEAD)
    assert result["synced"] == 0
    assert "error" in result
    assert _accounts(session_factory) == {ADDR_A: (1000, 3), ADDR_B: (500, 1)}


@pytest.mark.asyncio
async def test_snapshot_oversized_chain_parameters_rolls_back(session_factory, monkeypatch):
    """#1628: chain_parameters sit outside the state root — an oversized peer
    list must raise before any row applies, rolling back the whole sync."""
    root = _seed_state(session_factory)
    monkeypatch.setattr(settings, "sync_params_max_rows", 1)
    payload = _snapshot_payload(root)
    payload["chain_parameters"] = [
        {"parameter": "p1", "value": "1"},
        {"parameter": "p2", "value": "2"},
    ]
    sync, _ = _sync(session_factory, {"state/snapshot": payload})
    with pytest.raises(ValueError, match="chain_parameters"):
        await sync.sync_state_from("http://peer")
    assert _accounts(session_factory) == {ADDR_A: (1000, 3), ADDR_B: (500, 1)}
    with session_factory() as session:
        assert session.exec(select(ChainParameter).where(ChainParameter.chain_id == CHAIN)).all() == []


@pytest.mark.asyncio
async def test_delta_oversized_chain_parameters_rolls_back(session_factory, monkeypatch):
    """#1628: same ingest bound on the delta path."""
    root = _seed_state(session_factory)
    monkeypatch.setattr(settings, "sync_params_max_rows", 0)
    diff = StateDiff(
        from_height=HEAD - 1,
        to_height=HEAD,
        to_state_root=root,
        changes=[AccountChange(ADDR_A, 1000, 1000, 3, 3)],
        chain_id=CHAIN,
    )
    payload = _delta_payload(diff)
    payload["chain_parameter_history"] = [{"parameter": "p1", "value": "1", "applied_height": 1}]
    sync, _ = _sync(session_factory, {"state/delta": payload})
    with pytest.raises(ValueError, match="chain_parameters"):
        await sync.delta_sync_from("http://peer", HEAD - 1, HEAD)
    assert _accounts(session_factory) == {ADDR_A: (1000, 3), ADDR_B: (500, 1)}


@pytest.mark.asyncio
async def test_snapshot_wrong_resulting_root_rolls_back(session_factory):
    root = _seed_state(session_factory)
    # Claims our root, but the account values hash differently.
    foreign = _snapshot_payload(root, accounts=[{"address": ADDR_A, "balance": 42, "nonce": 0}])
    sync, _ = _sync(session_factory, {"state/snapshot": foreign})
    result = await sync.sync_state_from("http://peer")
    assert result["refused"] is True
    assert result["reason"] == "root_mismatch_local_head"
    assert _accounts(session_factory) == {ADDR_A: (1000, 3), ADDR_B: (500, 1)}


@pytest.mark.asyncio
async def test_snapshot_account_count_cap_refused_before_write(session_factory, monkeypatch):
    """#1594: refuse a snapshot whose account list exceeds sync_state_max_accounts."""
    root = _seed_state(session_factory)
    monkeypatch.setattr(settings, "sync_state_max_accounts", 1)
    payload = _snapshot_payload(root)
    sync, _ = _sync(session_factory, {"state/snapshot": payload})
    result = await sync.sync_state_from("http://peer")
    assert result["refused"] is True
    assert result["reason"] == "accounts_cap"
    assert _accounts(session_factory) == {ADDR_A: (1000, 3), ADDR_B: (500, 1)}


@pytest.mark.asyncio
async def test_delta_account_change_count_cap_refused(session_factory, monkeypatch):
    """#1594: refuse a delta whose change list exceeds sync_state_max_accounts."""
    root = _seed_state(session_factory)
    monkeypatch.setattr(settings, "sync_state_max_accounts", 0)
    diff = StateDiff(
        from_height=HEAD - 1,
        to_height=HEAD,
        to_state_root=root,
        changes=[AccountChange(ADDR_A, 1000, 1000, 3, 3)],
        chain_id=CHAIN,
    )
    sync, _ = _sync(session_factory, {"state/delta": _delta_payload(diff)})
    result = await sync.delta_sync_from("http://peer", HEAD - 1, HEAD)
    assert result["refused"] is True
    assert result["reason"] == "accounts_cap"
    assert _accounts(session_factory) == {ADDR_A: (1000, 3), ADDR_B: (500, 1)}
