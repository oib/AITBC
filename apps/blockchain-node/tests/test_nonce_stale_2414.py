"""#2414 pins: crosschain swap/bridge nonce reuse.

Two halves:

- ``BridgeTransferIntakeMixin._next_lock_nonce`` — the intake nonce floor
  must account for locks already pending in the local mempool, not just
  the sealed account nonce (every rapid swap/bridge previously reused it).
- ``_ProposalGatesMixin._partition_stale_nonce_txs`` — the proposer must
  drop drained txs whose enforced nonce already sealed below the account
  nonce instead of burning a consensus-gates round on them.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

import pytest

from aitbc_chain.consensus.poa_proposal_gates import _ProposalGatesMixin
from aitbc_chain.cross_chain.bridge_transfer_intake import BridgeTransferIntakeMixin


class _FakeMempool:
    def __init__(self, pending: list[dict[str, Any]] | Exception):
        self._pending = pending

    def get_pending_transactions(self, chain_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if isinstance(self._pending, Exception):
            raise self._pending
        return self._pending


def _pending_entry(sender: str, nonce: int) -> dict[str, Any]:
    return {"from": sender, "to": "bridge_lock", "nonce": nonce, "type": "BRIDGE_LOCK"}


def _next_nonce(monkeypatch: pytest.MonkeyPatch, pending: list[dict[str, Any]] | Exception, sealed: int = 156) -> int:
    import aitbc_chain.mempool as mempool_mod

    monkeypatch.setattr(mempool_mod, "get_mempool", lambda: _FakeMempool(pending))
    return BridgeTransferIntakeMixin._next_lock_nonce("test-chain", "0xSender", sealed)


class TestNextLockNonce:
    def test_no_pending_returns_sealed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert _next_nonce(monkeypatch, []) == 156

    def test_pending_claims_next_nonce(self, monkeypatch: pytest.MonkeyPatch) -> None:
        pending = [_pending_entry("0xSender", 156), _pending_entry("0xSender", 157)]
        assert _next_nonce(monkeypatch, pending) == 158

    def test_other_sender_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        pending = [_pending_entry("0xOther", 156), _pending_entry("0xOther", 200)]
        assert _next_nonce(monkeypatch, pending) == 156

    def test_sender_case_insensitive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        pending = [_pending_entry("0xsender", 156)]
        assert _next_nonce(monkeypatch, pending) == 157

    def test_stale_pending_below_sealed_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        pending = [_pending_entry("0xSender", 150)]
        assert _next_nonce(monkeypatch, pending, sealed=156) == 156

    def test_unclaimed_gap_not_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A lone future pending entry must not strand the lock at nonce+1.
        pending = [_pending_entry("0xSender", 160)]
        assert _next_nonce(monkeypatch, pending, sealed=156) == 156

    def test_mempool_failure_falls_back_to_sealed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert _next_nonce(monkeypatch, RuntimeError("mempool down")) == 156


class _PendingTx:
    def __init__(self, tx_hash: str, content: dict[str, Any]):
        self.tx_hash = tx_hash
        self.content = content


def _gates_self() -> Any:
    return SimpleNamespace(
        _logger=logging.getLogger("test.2414"),
        _config=SimpleNamespace(chain_id="test-chain"),
    )


def _partition(
    pending: list[_PendingTx],
    account_nonce: int | None,
    block_version: int,
    sender: str = "0xabc",
) -> tuple[list[_PendingTx], list[_PendingTx]]:
    account_map = {} if account_nonce is None else {sender: SimpleNamespace(nonce=account_nonce)}
    return _ProposalGatesMixin._partition_stale_nonce_txs(_gates_self(), pending, account_map, block_version)


def _signed_tx(tx_hash: str, nonce: int, sender: str = "0xabc") -> _PendingTx:
    return _PendingTx(tx_hash, {"from": sender, "to": "0xdef", "nonce": nonce, "signature": "0xsig"})


def _bridge_lock_tx(tx_hash: str, nonce: int, sender: str = "0xabc") -> _PendingTx:
    return _PendingTx(
        tx_hash,
        {
            "from": sender,
            "to": "bridge_lock",
            "nonce": nonce,
            "type": "BRIDGE_LOCK",
            "bridge_signature": "0xsig",
        },
    )


def _unsigned_tx(tx_hash: str, nonce: int, sender: str = "0xabc") -> _PendingTx:
    return _PendingTx(tx_hash, {"from": sender, "to": "bridge_lock", "nonce": nonce, "type": "BRIDGE_LOCK"})


class TestPartitionStaleNonceTxs:
    def test_signed_stale_nonce_dropped(self) -> None:
        kept, stale = _partition([_signed_tx("h1", 156)], account_nonce=157, block_version=27)
        assert kept == [] and [t.tx_hash for t in stale] == ["h1"]

    def test_signed_current_nonce_kept(self) -> None:
        kept, stale = _partition([_signed_tx("h1", 157)], account_nonce=157, block_version=27)
        assert [t.tx_hash for t in kept] == ["h1"] and stale == []

    def test_signed_future_nonce_kept(self) -> None:
        kept, stale = _partition([_signed_tx("h1", 158)], account_nonce=157, block_version=27)
        assert [t.tx_hash for t in kept] == ["h1"] and stale == []

    def test_unsigned_stale_exempt_nonce_rewritten(self) -> None:
        # Unsigned protocol writes get their nonce rewritten at apply —
        # the stored value is a placeholder and must not trigger eviction.
        kept, stale = _partition([_unsigned_tx("h1", 156)], account_nonce=157, block_version=27)
        assert [t.tx_hash for t in kept] == ["h1"] and stale == []

    def test_signed_bridge_lock_stale_at_v27_dropped(self) -> None:
        kept, stale = _partition([_bridge_lock_tx("h1", 156)], account_nonce=157, block_version=27)
        assert kept == [] and [t.tx_hash for t in stale] == ["h1"]

    def test_signed_bridge_lock_below_v27_kept(self) -> None:
        # Pre-rung the nonce is still rewritten at apply.
        kept, stale = _partition([_bridge_lock_tx("h1", 156)], account_nonce=157, block_version=26)
        assert [t.tx_hash for t in kept] == ["h1"] and stale == []

    def test_signed_tx_below_v7_kept(self) -> None:
        kept, stale = _partition([_signed_tx("h1", 156)], account_nonce=157, block_version=6)
        assert [t.tx_hash for t in kept] == ["h1"] and stale == []

    def test_missing_account_kept(self) -> None:
        kept, stale = _partition([_signed_tx("h1", 1)], account_nonce=None, block_version=27)
        assert [t.tx_hash for t in kept] == ["h1"] and stale == []

    def test_mixed_set_partitions(self) -> None:
        pending = [
            _signed_tx("stale", 156),
            _signed_tx("live", 157),
            _unsigned_tx("internal", 100),
            _bridge_lock_tx("lock", 155),
        ]
        kept, stale = _partition(pending, account_nonce=157, block_version=27)
        assert sorted(t.tx_hash for t in kept) == ["internal", "live"]
        assert sorted(t.tx_hash for t in stale) == ["lock", "stale"]
