"""NO-CREATE-DB-OPEN-1 (#408): the DB layer must refuse to create a
missing chain.db — the stray-file class that produced the 0-byte
data/exchange/chain.db + data/ipfs-island/chain.db pair on hub (11:14:07
24 Oct, creator unidentified). get_engine/session_scope raise
FileNotFoundError unless the caller opts in with create_ok=True
(genesis/init/replay)."""

import pytest


def _db_path(tmp_path, chain_id):
    return tmp_path / chain_id / "chain.db"


def test_get_engine_refuses_missing_db(tmp_path, monkeypatch):
    from aitbc_chain import database
    from aitbc_chain.config import settings

    monkeypatch.setattr(database, "resolve_chain_id", lambda cid: cid or "default")
    paths = {}
    monkeypatch.setattr(type(settings), "get_db_path", lambda self, cid: paths.setdefault(cid, _db_path(tmp_path, cid)))
    database._engines.clear()
    with pytest.raises(FileNotFoundError):
        database.get_engine("ghost-chain")
    assert not paths["ghost-chain"].exists()  # refused AND not created


def test_get_engine_create_ok_allows_creation(tmp_path, monkeypatch):
    from aitbc_chain import database
    from aitbc_chain.config import settings

    monkeypatch.setattr(database, "resolve_chain_id", lambda cid: cid or "default")
    paths = {}
    monkeypatch.setattr(type(settings), "get_db_path", lambda self, cid: paths.setdefault(cid, _db_path(tmp_path, cid)))
    database._engines.clear()
    eng = database.get_engine("new-chain", create_ok=True)
    assert eng is not None


def test_session_scope_inherits_refusal(tmp_path, monkeypatch):
    from aitbc_chain import database
    from aitbc_chain.config import settings

    monkeypatch.setattr(database, "resolve_chain_id", lambda cid: cid or "default")
    monkeypatch.setattr(type(settings), "get_db_path", lambda self, cid: _db_path(tmp_path, cid))
    database._engines.clear()
    with pytest.raises(FileNotFoundError):
        with database.session_scope("ghost-chain"):
            pass


def test_existing_db_opens_normally(tmp_path, monkeypatch):
    from aitbc_chain import database
    from aitbc_chain.config import settings

    real = _db_path(tmp_path, "real-chain")
    monkeypatch.setattr(database, "resolve_chain_id", lambda cid: cid or "default")
    real.parent.mkdir(parents=True)
    real.touch()  # pre-existing (even empty) file: it exists, so open it
    monkeypatch.setattr(type(settings), "get_db_path", lambda self, cid: real)
    database._engines.clear()
    assert database.get_engine("real-chain") is not None


def test_app_returns_503_and_creates_no_file(tmp_path, monkeypatch):
    """Comment-2775 pin: a route raising ChainDbMissingError on the REAL
    app (create_app) answers 503 via app.py's registered handler and
    creates no file. Removing the handler in app.py makes this fail —
    the error surfaces unhandled instead."""
    from fastapi.testclient import TestClient
    from aitbc_chain import database
    from aitbc_chain.app import create_app
    from aitbc_chain.config import settings

    ghost = tmp_path / "ghost" / "chain.db"
    monkeypatch.setattr(database, "resolve_chain_id", lambda cid: cid or "default")
    monkeypatch.setattr(type(settings), "get_db_path", lambda self, cid: ghost)
    database._engines.clear()
    app = create_app()

    @app.get("/probe-missing-db")
    def _probe():
        database.get_engine("ghost")
        return {"ok": True}

    resp = TestClient(app).get("/probe-missing-db")
    assert resp.status_code == 503
    assert resp.json()["detail"] == "chain db missing"  # fixed string — no path leak
    assert not ghost.exists()


def test_unrelated_file_not_found_stays_unhandled(tmp_path, monkeypatch):
    """Narrowness pin: an ordinary FileNotFoundError (not the chain-db
    class) is NOT caught by the ChainDbMissingError handler — the app's
    catch-all middleware still 503s, but without the chain-db detail,
    proving the specific handler did not run."""
    from fastapi.testclient import TestClient
    from aitbc_chain.app import create_app

    app = create_app()

    @app.get("/probe-unrelated-fnf")
    def _probe():
        raise FileNotFoundError("some other file")

    resp = TestClient(app).get("/probe-unrelated-fnf")
    # widening the handler to FileNotFoundError must fail: it would apply
    # the chain-db detail to an unrelated error, and the message echo
    # variant would leak "some other file" — assert both
    assert "chain db missing" not in resp.text
    assert "some other file" not in resp.text
