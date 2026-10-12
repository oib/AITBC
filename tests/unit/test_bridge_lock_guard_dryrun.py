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


def _errors() -> float:
    return metrics_registry._counters.get("bridge_lock_guard_errors_total", 0.0)


class _NoHash:
    """Processed-tx-shaped object that lacks tx_hash entirely."""

    content = {"type": "BRIDGE_LOCK", "payload": _LOCK_PAYLOAD}


def test_malformed_processed_txs_count_errors_never_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """Flag on: string payload, None content, missing tx_hash and non-dict
    envelope are each counted on bridge_lock_guard_errors_total and
    skipped — nothing raises, the tx list is untouched."""
    from aitbc_chain.config import settings

    monkeypatch.setattr(settings, "bridge_lock_guard_dryrun_enabled", True)
    metrics_registry.reset()
    txs: list[Any] = [
        _Pending(tx_hash="h-str", content={"type": "BRIDGE_LOCK", "payload": "not-a-dict"}),
        _Pending(tx_hash="h-none", content=None),
        _NoHash(),
        _Pending(tx_hash="h-env", content="not-a-dict"),
        _Pending(tx_hash="h-ok", content={"type": "BRIDGE_LOCK", "payload": _LOCK_PAYLOAD}),
    ]
    before = [copy.deepcopy(getattr(t, "content", t)) for t in txs]
    out = run_guard_dryrun(txs, height=31000, chain_id="c1")
    # the one well-formed lock still classifies; the four malformed txs error
    assert out == {"checked": 1, "derivable": 1, "grandfathered": 0, "would_refuse": 0}
    assert _errors() == 4.0
    assert [getattr(t, "content", t) for t in txs] == before


def test_malformed_dict_txs_count_errors_never_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same contract on the sync-import path: non-dict envelope (the tx
    itself is the envelope), missing tx_hash and a string payload."""
    from aitbc_chain.config import settings

    monkeypatch.setattr(settings, "bridge_lock_guard_dryrun_enabled", True)
    metrics_registry.reset()
    txs: list[dict[str, Any]] = [
        "not-a-dict",
        {"type": "BRIDGE_LOCK", "payload": _LOCK_PAYLOAD},  # no tx_hash
        {"type": "BRIDGE_LOCK", "tx_hash": "h3", "payload": "not-a-dict"},
        {"type": "BRIDGE_LOCK", "tx_hash": "h4", "payload": _LOCK_PAYLOAD},
    ]
    before = copy.deepcopy(txs)
    out = run_guard_dryrun_dicts(txs, height=31000, chain_id="c1")
    assert out == {"checked": 1, "derivable": 1, "grandfathered": 0, "would_refuse": 0}
    assert _errors() == 3.0
    assert txs == before


def test_check_locks_malformed_items_count_errors_never_raise() -> None:
    """Direct callers get the same containment: a non-3-tuple item and
    non-dict payload/envelope members are errors, not exceptions."""
    metrics_registry.reset()
    out = check_locks_dryrun(
        [("h1", "not-a-dict", {}), ("h2", {}, "not-a-dict"), "not-a-tuple"],
        height=GRANDFATHER_BOUNDARY + 1,
        boundary=GRANDFATHER_BOUNDARY,
        chain_id="c1",
    )
    assert out == {"checked": 3, "derivable": 0, "grandfathered": 0, "would_refuse": 0}
    assert _errors() == 3.0


def test_unexpected_guard_failure_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """The catch-all: if classification itself blows up the entry point
    returns None and counts the error — the seal path proceeds."""
    from aitbc_chain.config import settings

    import aitbc_chain.cross_chain.bridge_lock_guard as guard

    monkeypatch.setattr(settings, "bridge_lock_guard_dryrun_enabled", True)

    def _boom(*_a: Any, **_k: Any) -> dict[str, int]:
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(guard, "check_locks_dryrun", _boom)
    metrics_registry.reset()
    txs = [_Pending(tx_hash="h", content={"type": "BRIDGE_LOCK", "payload": _LOCK_PAYLOAD})]
    assert run_guard_dryrun(txs, height=31000, chain_id="c1") is None
    assert (
        run_guard_dryrun_dicts([{"type": "BRIDGE_LOCK", "tx_hash": "h", "payload": _LOCK_PAYLOAD}], height=1, chain_id="c1")
        is None
    )
    assert _errors() == 2.0
