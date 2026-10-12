"""V-4 seal-path missing-data guard, dry-run mode — fixture tests (branch-only).

Pins the guard contract from docs/design/bridge-state-root-grandfathering.md:
flag defaults off and returns before touching txs; an underivable lock at or
above boundary 30000 is logged + counted as a *would*-refuse while the block
is built exactly as before; the same shape below the boundary is grandfathered.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from typing import Any

import pytest

from aitbc_chain.cross_chain.bridge_lock_guard import (
    GRANDFATHER_BOUNDARY,
    check_locks_dryrun,
    lock_derivation_source,
    run_guard_dryrun,
    run_guard_dryrun_dicts,
)
from aitbc_chain.metrics import metrics_registry

_LOCK_PAYLOAD = {"transfer_id": "tid-1", "amount": 42, "target_chain": "evm:1"}
_ENVELOPE_ONLY = {"transfer_id": "tid-2", "amount": 7, "target_chain": "evm:1", "signature": "x"}


def test_boundary_constant_is_operator_choice() -> None:
    assert GRANDFATHER_BOUNDARY == 30000


def test_derivation_source_payload_envelope_unreadable() -> None:
    assert lock_derivation_source(_LOCK_PAYLOAD, {}) == "payload"
    assert lock_derivation_source({}, _ENVELOPE_ONLY) == "envelope"
    assert lock_derivation_source({}, {}) == "unreadable"
    assert lock_derivation_source({"transfer_id": "x"}, {}) == "unreadable"


def test_flag_off_returns_none_and_touches_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    from aitbc_chain.config import settings

    monkeypatch.setattr(settings, "bridge_lock_guard_dryrun_enabled", False)
    txs = [{"type": "BRIDGE_LOCK", "tx_hash": "aa", "payload": {}, "envelope": {}}]
    assert run_guard_dryrun_dicts(copy.deepcopy(txs), height=31000, chain_id="c1") is None
    assert metrics_registry._counters.get("bridge_lock_guard_checked_total", 0.0) == 0.0


def test_would_refuse_at_or_above_boundary(caplog: pytest.LogCaptureFixture) -> None:
    metrics_registry.reset()
    with caplog.at_level(logging.WARNING):
        out = check_locks_dryrun(
            [("aabbccddeeff00112233", {}, {})],
            height=GRANDFATHER_BOUNDARY,
            boundary=GRANDFATHER_BOUNDARY,
            chain_id="c1",
        )
    assert out == {"checked": 1, "derivable": 0, "grandfathered": 0, "would_refuse": 1}
    assert metrics_registry._counters["bridge_lock_guard_would_refuse_total"] == 1.0
    assert any("would refuse" in r.message for r in caplog.records)


def test_below_boundary_is_grandfathered_not_refused(caplog: pytest.LogCaptureFixture) -> None:
    metrics_registry.reset()
    with caplog.at_level(logging.WARNING):
        out = check_locks_dryrun(
            [("aabb", {}, {})],
            height=GRANDFATHER_BOUNDARY - 1,
            boundary=GRANDFATHER_BOUNDARY,
            chain_id="c1",
        )
    assert out == {"checked": 1, "derivable": 0, "grandfathered": 1, "would_refuse": 0}
    assert metrics_registry._counters.get("bridge_lock_guard_would_refuse_total", 0.0) == 0.0
    assert metrics_registry._counters["bridge_lock_guard_grandfathered_total"] == 1.0
    assert not caplog.records


def test_derivable_lock_never_refused() -> None:
    metrics_registry.reset()
    out = check_locks_dryrun(
        [("h1", _LOCK_PAYLOAD, {}), ("h2", {}, _ENVELOPE_ONLY)],
        height=GRANDFATHER_BOUNDARY + 1000,
        boundary=GRANDFATHER_BOUNDARY,
        chain_id="c1",
    )
    assert out["derivable"] == 2 and out["would_refuse"] == 0


@dataclass
class _Pending:
    tx_hash: str
    content: dict[str, Any]


def test_propose_path_flag_on_counts_and_leaves_txs_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    from aitbc_chain.config import settings

    monkeypatch.setattr(settings, "bridge_lock_guard_dryrun_enabled", True)
    lock = _Pending(
        tx_hash="deadbeef00112233445566778899aabb",
        content={"type": "BRIDGE_LOCK", "from": "x", "payload": {}, "signature": "s"},
    )
    other = _Pending(tx_hash="nonlock", content={"type": "TRANSFER", "payload": {}})
    txs = [lock, other]
    before = [copy.deepcopy(t.content) for t in txs]
    metrics_registry.reset()
    out = run_guard_dryrun(txs, height=31000, chain_id="c1")
    assert out == {"checked": 1, "derivable": 0, "grandfathered": 0, "would_refuse": 1}
    # the guard is pure observation: tx objects and their content are unchanged
    assert [t.content for t in txs] == before


def test_propose_path_flag_off_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    from aitbc_chain.config import settings

    monkeypatch.setattr(settings, "bridge_lock_guard_dryrun_enabled", False)
    txs = [_Pending(tx_hash="x", content={"type": "BRIDGE_LOCK", "payload": {}})]
    assert run_guard_dryrun(txs, height=31000, chain_id="c1") is None


def test_dicts_path_type_from_payload_level(monkeypatch: pytest.MonkeyPatch) -> None:
    from aitbc_chain.config import settings

    monkeypatch.setattr(settings, "bridge_lock_guard_dryrun_enabled", True)
    # GAP-47 block-scoped shape: type only inside payload, leaf fields on the
    # top-level tx body (the sealed ``envelope`` column stores dict(tx)).
    tx = {"tx_hash": "bbcc", "payload": {"type": "BRIDGE_LOCK"}, "transfer_id": "tid-2", "amount": 7, "target_chain": "evm:1"}
    out = run_guard_dryrun_dicts([tx], height=31000, chain_id="c1")
    assert out == {"checked": 1, "derivable": 1, "grandfathered": 0, "would_refuse": 0}
