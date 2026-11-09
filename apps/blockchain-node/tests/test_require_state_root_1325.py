"""#1325 option (e): an empty state_root must not skip the importer's root check."""

from __future__ import annotations

from aitbc_chain.config import settings
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


def _tx():
    return _signed_tx(KEY_A, ADDR_A, 1, amount=50, tx_hash="0x" + "79" * 32)


def _import(fixture_db, state_root, *, skip=False):  # noqa: F811
    engine, factory = fixture_db
    txs = [_tx()]
    root, aux = _proposer_roots(engine, txs, 1)
    block = _block(1, "0x" + "00" * 32, txs, root if state_root == "real" else state_root, aux)
    sync = ChainSync(factory, chain_id=CHAIN, validate_signatures=False)
    return sync.import_block(block, transactions=txs, skip_state_root_validation=skip)


def test_empty_root_refused_at_or_above_height(fixture_db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(settings, "sync_require_state_root_height", 1)
    for empty in ("", None):
        result = _import(fixture_db, empty)
        assert not result.accepted
        assert result.reason == "Missing state root"


def test_empty_root_accepted_below_height(fixture_db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(settings, "sync_require_state_root_height", 2)
    assert _import(fixture_db, "").accepted


def test_flag_off_keeps_legacy_bypass(fixture_db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(settings, "sync_require_state_root_height", None)
    assert _import(fixture_db, "").accepted


def test_valid_root_still_accepted_when_armed(fixture_db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(settings, "sync_require_state_root_height", 1)
    result = _import(fixture_db, "real")
    assert result.accepted, result.reason


def test_skip_flag_is_honoured_for_trusted_bulk(fixture_db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(settings, "sync_require_state_root_height", 1)
    assert _import(fixture_db, "", skip=True).accepted
