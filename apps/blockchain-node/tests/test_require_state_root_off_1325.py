"""#1325 option (e) — flag OFF (``sync_require_state_root_height=None``) leaves
the import path unchanged.

``test_require_state_root_1325.py`` covers the armed behavior and one OFF
case. This file pins the OFF *side effects*: the shipped default is off, an
empty/omitted root takes the legacy bypass with no rejection bookkeeping and
no counter movement, a non-empty wrong root is still refused by the existing
validation (not by the new branch), and a valid root is accepted. An armed
control on the same harness proves the OFF assertions are not vacuous.
"""

from __future__ import annotations

import pytest
from aitbc_chain.config import ChainSettings, settings
from aitbc_chain.metrics import metrics_registry
from aitbc_chain.sync import ChainSync

from .test_importer_recipient_precreation import (
    ADDR_A,
    CHAIN,
    KEY_A,
    _block,
    _proposer_roots,
    _signed_tx,
    fixture_db,  # noqa: F401 - pytest fixture re-export
)

MISSING_COUNTER = "sync_state_root_missing_rejected_total"


def _run(fixture_db, state_root, monkeypatch):  # noqa: F811
    """Import height 1 with ``state_root`` (``"real"`` = the proposer's root);
    returns (result, rejection_tracking_calls)."""
    engine, factory = fixture_db
    txs = [_signed_tx(KEY_A, ADDR_A, 1, amount=50, tx_hash="0x" + "79" * 32)]
    root, aux = _proposer_roots(engine, txs, 1)
    block = _block(1, "0x" + "00" * 32, txs, root if state_root == "real" else state_root, aux)
    sync = ChainSync(factory, chain_id=CHAIN, validate_signatures=False)
    tracked: list[str] = []
    monkeypatch.setattr(sync, "_track_rejection", lambda chain_id: tracked.append(chain_id))
    return sync.import_block(block, transactions=txs), tracked


@pytest.fixture(autouse=True)
def _reset_metrics():
    metrics_registry.reset()
    yield
    metrics_registry.reset()


def test_default_is_off():
    assert ChainSettings.model_fields["sync_require_state_root_height"].default is None


@pytest.mark.parametrize("empty", ["", None], ids=["empty-string", "omitted"])
def test_off_empty_root_takes_legacy_bypass_without_bookkeeping(fixture_db, monkeypatch, empty):  # noqa: F811
    monkeypatch.setattr(settings, "sync_require_state_root_height", None)
    result, tracked = _run(fixture_db, empty, monkeypatch)
    assert result.accepted, result.reason
    assert tracked == [], "OFF must not record a rejection"
    assert metrics_registry._counters.get(MISSING_COUNTER, 0.0) == 0.0


def test_off_wrong_nonempty_root_still_refused_by_existing_check(fixture_db, monkeypatch):  # noqa: F811
    """The new branch only ever fires on an EMPTY root. A non-empty wrong root
    is refused by the pre-existing validation with its own reason, flag or no
    flag — OFF must not change which check catches it."""
    monkeypatch.setattr(settings, "sync_require_state_root_height", None)
    result, _tracked = _run(fixture_db, "0x" + "ab" * 32, monkeypatch)
    assert not result.accepted
    assert result.reason != "Missing state root"
    assert metrics_registry._counters.get(MISSING_COUNTER, 0.0) == 0.0


def test_off_valid_root_accepted(fixture_db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(settings, "sync_require_state_root_height", None)
    result, tracked = _run(fixture_db, "real", monkeypatch)
    assert result.accepted, result.reason
    assert tracked == []


def test_armed_control_records_rejection_and_counter(fixture_db, monkeypatch):  # noqa: F811
    """Same harness armed at height 1: refusal + bookkeeping + counter — so the
    OFF legs above cannot pass vacuously."""
    monkeypatch.setattr(settings, "sync_require_state_root_height", 1)
    result, tracked = _run(fixture_db, "", monkeypatch)
    assert not result.accepted
    assert result.reason == "Missing state root"
    assert tracked == [CHAIN]
    assert metrics_registry._counters.get(MISSING_COUNTER, 0.0) == 1.0
