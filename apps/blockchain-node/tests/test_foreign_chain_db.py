"""FOREIGN-CHAIN-DB-1 (#673): opening an existing chain.db for a chain the
process does not declare is refused unless the caller opts in.

The declared set is supported_chains ∪ bridge_supported_chains ∪ chain_id
∪ chains this process materialized (init_db/create_ok) — serving and
following lists, not arbitrary paths. Opt-ins: per-call ``allow_foreign``
or the AITBC_DB_ALLOW_FOREIGN_CHAINS env var for one-off tools.
"""

import logging

import pytest


def _db_path(tmp_path, chain_id):
    return tmp_path / chain_id / "chain.db"


def _patch_paths(monkeypatch, tmp_path, database, settings):
    monkeypatch.setattr(database, "resolve_chain_id", lambda cid: cid or "default")
    monkeypatch.setattr(type(settings), "get_db_path", lambda self, cid: _db_path(tmp_path, cid))
    database._engines.clear()
    database._session_factories.clear()
    database._registered_chain_ids.clear()


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()


def test_existing_foreign_db_open_refused(tmp_path, monkeypatch):
    from aitbc_chain import database
    from aitbc_chain.config import settings

    _patch_paths(monkeypatch, tmp_path, database, settings)
    _touch(_db_path(tmp_path, "foreign-island"))
    with pytest.raises(database.ForeignChainDbError):
        database.get_engine("foreign-island")


def test_declared_chain_opens_normally(tmp_path, monkeypatch):
    from aitbc_chain import database
    from aitbc_chain.config import settings

    _patch_paths(monkeypatch, tmp_path, database, settings)
    _touch(_db_path(tmp_path, "chain-a"))  # in conftest's supported_chains
    assert database.get_engine("chain-a") is not None


def test_allow_foreign_opt_in_opens(tmp_path, monkeypatch):
    from aitbc_chain import database
    from aitbc_chain.config import settings

    _patch_paths(monkeypatch, tmp_path, database, settings)
    _touch(_db_path(tmp_path, "foreign-island"))
    assert database.get_engine("foreign-island", allow_foreign=True) is not None


def test_env_opt_in_opens(tmp_path, monkeypatch):
    from aitbc_chain import database
    from aitbc_chain.config import settings

    _patch_paths(monkeypatch, tmp_path, database, settings)
    _touch(_db_path(tmp_path, "foreign-island"))
    monkeypatch.setenv("AITBC_DB_ALLOW_FOREIGN_CHAINS", "1")
    assert database.get_engine("foreign-island") is not None


def test_created_chain_registers_for_later_opens(tmp_path, monkeypatch):
    """init_db/create_ok materialization is itself the opt-in: a chain this
    process created (genesis for a not-yet-configured id) may be opened."""
    from aitbc_chain import database
    from aitbc_chain.config import settings

    _patch_paths(monkeypatch, tmp_path, database, settings)
    database.get_engine("brand-new-chain", create_ok=True)
    assert "brand-new-chain" in database.node_chain_ids()


def test_session_scope_refusal(tmp_path, monkeypatch):
    from aitbc_chain import database
    from aitbc_chain.config import settings

    _patch_paths(monkeypatch, tmp_path, database, settings)
    _touch(_db_path(tmp_path, "foreign-island"))
    with pytest.raises(database.ForeignChainDbError):
        with database.session_scope("foreign-island"):
            pass


def test_app_returns_403_for_foreign_chain(tmp_path, monkeypatch):
    """A route surfacing ForeignChainDbError answers 403 via the registered
    handler — the serve-list counterpart of the 503 missing-db pin."""
    from fastapi.testclient import TestClient
    from aitbc_chain import database
    from aitbc_chain.app import create_app
    from aitbc_chain.config import settings

    _patch_paths(monkeypatch, tmp_path, database, settings)
    _touch(_db_path(tmp_path, "foreign-island"))
    app = create_app()

    @app.get("/probe-foreign-db")
    def _probe():
        database.get_engine("foreign-island")
        return {"ok": True}

    resp = TestClient(app).get("/probe-foreign-db")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "chain not served by this node"


def test_messaging_metrics_absent_store_warns_once(tmp_path, monkeypatch, caplog):
    """A served-but-not-followed chain raises ChainDbMissingError per scrape;
    the collector must report it once at INFO, not WARNING every interval."""
    from aitbc_chain import database, messaging_metrics as mm

    def _missing_scope(chain_id: str = "", **_kw):
        from contextlib import contextmanager

        @contextmanager
        def _gen():
            raise database.ChainDbMissingError("chain db missing: /nope")
            yield  # pragma: no cover

        return _gen()

    monkeypatch.setattr(mm, "session_scope", _missing_scope, raising=False)
    # collect_all imports session_scope lazily inside the function — patch the source.
    monkeypatch.setattr(database, "session_scope", _missing_scope)
    mm._absent_store_noted.clear()

    with caplog.at_level(logging.DEBUG, logger="aitbc_chain.messaging_metrics"):
        mm.collect_all(["ghost-island"])
        mm.collect_all(["ghost-island"])

    infos = [r for r in caplog.records if r.levelno == logging.INFO and "ghost-island" in r.getMessage()]
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(infos) == 1
    assert not warnings
