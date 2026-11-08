"""#1265 pins: chain.db integrity verification (PRAGMA quick_check).

Covers the Phase-5 drill gap: a mid-file page corruption used to be silently
tolerated — the node kept importing for minutes. Now:

- ``init_db`` fails fast with ``ChainDbCorruptError`` on a corrupt store
  (same failure mode as the WAL-pragma structural path);
- mid-run detection quarantines the chain — ``import_block``, the propose
  path, and attestation checks all refuse instead of writing/endorsing on a
  corrupt DB;
- quarantine is keyed per DB identity, so a fresh engine/file for the same
  chain id is not poisoned by an earlier store's verdict.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from aitbc_chain.config import settings
from aitbc_chain.database import (
    ChainDbCorruptError,
    clear_chain_db_quarantine,
    ensure_chain_db_healthy,
    init_db,
    is_chain_db_quarantined,
    shutdown_db,
    verify_chain_db_integrity,
)
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.sync import ChainSync

CHAIN = "dbcheck-test-chain"


def _unique_chain() -> str:
    return f"dbcheck-{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def _clean_quarantine():
    clear_chain_db_quarantine()
    yield
    clear_chain_db_quarantine()


def _file_engine(tmp_path: Path, name: str = "chain.db"):
    path = tmp_path / name
    engine = create_engine(f"sqlite:///{path}", echo=False)
    chain_metadata.create_all(engine)
    # Give the file real pages to corrupt: a handful of rows across tables.
    with Session(engine) as session:
        session.execute(text("CREATE TABLE IF NOT EXISTS dbcheck_probe (a TEXT)"))
        session.execute(
            text(
                "INSERT INTO dbcheck_probe "
                "WITH RECURSIVE cnt(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM cnt WHERE x < 2000) "
                "SELECT 'x' || x FROM cnt"
            )
        )
        session.commit()
    engine.dispose()
    return path


def _corrupt_file(path: Path) -> None:
    """Overwrite several mid-file pages — the Phase-5 drill's lazy-corruption
    shape (B-tree page payloads), leaving the 100-byte header intact."""
    size = path.stat().st_size
    with open(path, "r+b") as f:
        for i in range(1, 6):
            off = ((size * i) // 8) // 4096 * 4096
            f.seek(off)
            f.write(b"\xff" * 512)


def test_healthy_db_passes(tmp_path):
    path = _file_engine(tmp_path)
    engine = create_engine(f"sqlite:///{path}", echo=False)
    try:
        ok, detail = verify_chain_db_integrity("healthy-chain", engine=engine)
        assert (ok, detail) == (True, "ok")
        assert not is_chain_db_quarantined("healthy-chain")
        ok2, _ = ensure_chain_db_healthy("healthy-chain", engine=engine)
        assert ok2 is True
    finally:
        engine.dispose()


def test_corrupt_db_flags_and_quarantines(tmp_path):
    path = _file_engine(tmp_path)
    _corrupt_file(path)
    engine = create_engine(f"sqlite:///{path}", echo=False)
    try:
        ok, detail = verify_chain_db_integrity("corrupt-chain", engine=engine, raise_on_failure=False)
        assert ok is False
        assert detail
        assert is_chain_db_quarantined("corrupt-chain")
        ok2, reason = ensure_chain_db_healthy("corrupt-chain", engine=engine)
        assert ok2 is False
        assert reason == detail
    finally:
        engine.dispose()


def test_init_db_fails_fast_on_corrupt_store(monkeypatch):
    chain = _unique_chain()
    try:
        init_db(chain)  # healthy store materializes
        shutdown_db(chain)  # close engine + quarantine state; file remains
        path = settings.get_db_path(chain)
        _corrupt_file(path)
        with pytest.raises(ChainDbCorruptError):
            init_db(chain)
        assert is_chain_db_quarantined(chain)
    finally:
        clear_chain_db_quarantine(chain)
        try:
            shutdown_db(chain)
        except Exception:
            pass


def test_init_db_passes_on_healthy_store():
    chain = _unique_chain()
    try:
        init_db(chain)
        assert not is_chain_db_quarantined(chain)
    finally:
        shutdown_db(chain)


def test_disabled_flag_skips_checks(monkeypatch):
    monkeypatch.setattr(settings, "db_integrity_check_enabled", False)
    engine = create_engine("sqlite:///:memory:", echo=False)
    try:
        ok, _ = verify_chain_db_integrity("flag-off", engine=engine)
        # verify itself is unconditional; the flag gates callers.
        assert ok is True
        ok2, detail = ensure_chain_db_healthy("flag-off", engine=engine)
        assert (ok2, detail) == (True, "disabled")
    finally:
        engine.dispose()


def test_quarantine_is_per_db_identity(tmp_path):
    """A corrupt store quarantines its chain id, but a *different* engine/file
    for the same chain id is a different store — it verifies fresh and is not
    refused by the earlier store's verdict."""
    bad = _file_engine(tmp_path, "bad.db")
    _corrupt_file(bad)
    bad_engine = create_engine(f"sqlite:///{bad}", echo=False)
    good_path = _file_engine(tmp_path, "good.db")
    good_engine = create_engine(f"sqlite:///{good_path}", echo=False)
    chain = _unique_chain()
    try:
        ok, _ = verify_chain_db_integrity(chain, engine=bad_engine)
        assert ok is False
        assert is_chain_db_quarantined(chain)
        ok2, _ = ensure_chain_db_healthy(chain, engine=good_engine)
        assert ok2 is True
        assert not is_chain_db_quarantined(chain)
    finally:
        bad_engine.dispose()
        good_engine.dispose()


def test_import_block_refuses_on_corrupt_db(tmp_path):
    """A node importing on a corrupt DB must not continue — the apply path
    refuses before touching block state."""
    path = _file_engine(tmp_path)
    _corrupt_file(path)
    engine = create_engine(f"sqlite:///{path}", echo=False)
    factory = sessionmaker(engine, class_=Session)
    sync = ChainSync(factory, chain_id="import-corrupt", validate_signatures=False)
    try:
        result = sync.import_block(
            {
                "chain_id": "import-corrupt",
                "height": 1,
                "hash": "0x" + "ab" * 32,
                "parent_hash": "0x" + "00" * 32,
                "proposer": "0x" + "11" * 20,
                "timestamp": "2026-11-08T00:00:00+00:00",
                "tx_count": 0,
            },
            transactions=[],
        )
        assert result.accepted is False
        assert "integrity" in result.reason
        assert is_chain_db_quarantined("import-corrupt")
    finally:
        engine.dispose()
        clear_chain_db_quarantine("import-corrupt")


def test_import_block_passes_on_healthy_db(tmp_path):
    """Healthy DB: the gate is transparent — import proceeds to its normal
    (here: duplicate/unknown-parent) verdict rather than an integrity refusal."""
    path = _file_engine(tmp_path)
    engine = create_engine(f"sqlite:///{path}", echo=False)
    factory = sessionmaker(engine, class_=Session)
    sync = ChainSync(factory, chain_id="import-healthy", validate_signatures=False)
    try:
        result = sync.import_block(
            {
                "chain_id": "import-healthy",
                "height": 1,
                "hash": "0x" + "cd" * 32,
                "parent_hash": "0x" + "00" * 32,
                "proposer": "0x" + "11" * 20,
                "timestamp": "2026-11-08T00:00:00+00:00",
                "tx_count": 0,
            },
            transactions=[],
        )
        assert "integrity" not in (result.reason or "")
    finally:
        engine.dispose()
        clear_chain_db_quarantine("import-healthy")


def test_v9_attestation_check_refuses_on_corrupt_db(tmp_path):
    """Attesters must not sign from corrupt state: _v9_check_transactions
    returns the db_corrupt refusal once the store fails quick_check."""
    from aitbc_chain.consensus.remote_attestation import RemoteAttestationService

    path = _file_engine(tmp_path)
    _corrupt_file(path)
    engine = create_engine(f"sqlite:///{path}", echo=False)
    factory = sessionmaker(engine, class_=Session)
    svc = RemoteAttestationService("attest-corrupt", {}, session_factory=factory)
    try:
        # The header must pass the v9 tx-set recompute before the session opens —
        # build it exactly like collect_attestations does.
        from aitbc_chain.consensus.block_hash import compute_block_hash

        header = {
            "chain_id": "attest-corrupt",
            "height": 1,
            "hash": "",
            "parent_hash": "0x" + "00" * 32,
            "proposer": "0x" + "11" * 20,
            "state_root": "",
            "bridge_state_root": "",
            "aux_state_root": "",
            "timestamp": "2026-11-08T00:00:00+00:00",
            "tx_count": 0,
            "tx_hashes": [],
        }
        header["hash"] = compute_block_hash(
            "attest-corrupt",
            1,
            header["parent_hash"],
            header["timestamp"],
            [],
            header["proposer"],
            "",
            "",
            "",
        )
        reason = svc._v9_check_transactions(header, [])
        assert reason == "db_corrupt"
    finally:
        engine.dispose()
        clear_chain_db_quarantine("attest-corrupt")


def test_propose_head_refuses_on_quarantined_db(tmp_path):
    """The propose path must not build on corrupt state."""
    from aitbc_chain.consensus.poa import PoAProposer, ProposerConfig

    path = _file_engine(tmp_path)
    _corrupt_file(path)
    engine = create_engine(f"sqlite:///{path}", echo=False)
    factory = sessionmaker(engine, class_=Session)
    config = ProposerConfig(
        chain_id="propose-corrupt",
        proposer_id="0x" + "22" * 20,
        interval_seconds=60,
        max_block_size_bytes=1_000_000,
        max_txs_per_block=100,
    )
    proposer = PoAProposer(config=config, session_factory=factory)
    try:
        with Session(engine) as session:
            assert proposer._resolve_proposal_head(session) is None
    finally:
        engine.dispose()
        clear_chain_db_quarantine("propose-corrupt")
