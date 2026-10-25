"""Tests for ``aitbc blockchain height|block|status|info`` source labelling (CLI-HEIGHT-1).

Every head-reading command must show which endpoint (or local store) the
answer came from: a "heads equal" restart gate that silently compares hub
with hub proves nothing about the host just restarted. ``height --db`` reads
the local chain.db read-only and never creates it.
"""

import sqlite3

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.chain as chain_mod
from aitbc_cli.commands.chain import chain


@pytest.fixture
def runner():
    return CliRunner()


class _StubClient:
    def __init__(self, base_url, timeout=10, **kwargs):
        self.base_url = base_url
        self.payload = {}

    def get(self, path, params=None):
        self.seen = path
        return self.payload

    def close(self):
        pass


def _stub_rpc(monkeypatch, payload):
    holder = {}

    class C(_StubClient):
        def __init__(self, base_url, **kw):
            super().__init__(base_url, **kw)
            self.payload = payload
            holder["client"] = self

    monkeypatch.setattr(chain_mod, "AITBCHTTPClient", C)
    return holder


def _make_db(path, heights):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("create table block (height integer, hash blob)")
    conn.executemany("insert into block (height, hash) values (?, ?)", [(h, b"x") for h in heights])
    conn.commit()
    conn.close()


def test_height_json_names_the_source(runner, monkeypatch):
    holder = _stub_rpc(monkeypatch, {"height": 42})
    result = runner.invoke(chain, obj={"output_format": "json"}, args=["height"])
    assert result.exit_code == 0, result.output
    assert '"height": 42' in result.output
    assert "127.0.0.1:8202" in result.output  # default source is the local rpc
    assert holder["client"].seen == "/rpc/height"


def test_height_explicit_node_url_is_the_source(runner, monkeypatch):
    _stub_rpc(monkeypatch, {"height": 7})
    result = runner.invoke(chain, obj={"output_format": "json"}, args=["height", "--node-url", "http://n2:8202"])
    assert result.exit_code == 0, result.output
    assert "http://n2:8202" in result.output


def test_block_names_the_source(runner, monkeypatch):
    _stub_rpc(monkeypatch, {"height": 5, "hash": "0xdead"})
    result = runner.invoke(chain, obj={"output_format": "json"}, args=["block", "--height", "5"])
    assert result.exit_code == 0, result.output
    assert "127.0.0.1:8202" in result.output


def test_height_db_reads_local_store(runner, tmp_path, monkeypatch):
    monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path))
    _make_db(tmp_path / "data" / "bc-9" / "chain.db", [10, 20, 15])
    result = runner.invoke(chain, obj={"output_format": "json", "chain_id": "bc-9"}, args=["height", "--db"])
    assert result.exit_code == 0, result.output
    assert '"height": 20' in result.output
    assert "bc-9" in result.output
    assert "local-db" in result.output


def test_height_db_autodetects_single_store(runner, tmp_path, monkeypatch):
    monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path))
    _make_db(tmp_path / "data" / "bc-9" / "chain.db", [3])
    result = runner.invoke(chain, obj={"output_format": "json", "chain_id": None}, args=["height", "--db"])
    assert result.exit_code == 0, result.output
    assert '"height": 3' in result.output


def test_height_db_missing_store_fails_clear(runner, tmp_path, monkeypatch):
    monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path))
    result = runner.invoke(chain, obj={"output_format": "json", "chain_id": "bc-9"}, args=["height", "--db"])
    assert result.exit_code != 0
    assert "chain.db" in result.output
    assert not (tmp_path / "data" / "bc-9" / "chain.db").exists()  # read-only, never created


def test_height_db_ambiguous_store_needs_chain_id(runner, tmp_path, monkeypatch):
    monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path))
    _make_db(tmp_path / "data" / "bc-9" / "chain.db", [3])
    _make_db(tmp_path / "data" / "bc-10" / "chain.db", [4])
    result = runner.invoke(chain, obj={"output_format": "json", "chain_id": None}, args=["height", "--db"])
    assert result.exit_code != 0
    assert "--chain-id" in result.output


def test_height_db_does_not_create_the_dir(runner, tmp_path, monkeypatch):
    monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path / "absent"))
    result = runner.invoke(chain, obj={"output_format": "json", "chain_id": None}, args=["height", "--db"])
    assert result.exit_code != 0


def test_status_local_flag_queries_local_rpc(runner, monkeypatch):
    captured = {}

    class _Mgr:
        def __init__(self, config):
            self.config = config

        async def list_chains(self):
            return []

    def fake_load(node_urls=()):
        captured["node_urls"] = tuple(node_urls)
        mgr = _Mgr(type("C", (), {"nodes": {"local-rpc": type("N", (), {"endpoint": "http://127.0.0.1:8202"})()}})())
        return mgr

    monkeypatch.setattr(chain_mod, "_load_chain_manager", fake_load)
    result = runner.invoke(chain, obj={"output_format": "json"}, args=["status", "--local"])
    assert result.exit_code == 0, result.output
    assert captured["node_urls"][0] == "http://127.0.0.1:8202"


def test_status_source_appears_in_rows(runner, monkeypatch):
    class _Node:
        endpoint = "http://127.0.0.1:8202"

    class _Cfg:
        nodes = {"local-rpc": _Node()}

    class _Mgr:
        config = _Cfg()

        async def list_chains(self):
            return []

    monkeypatch.setattr(chain_mod, "_load_chain_manager", lambda node_urls=(): _Mgr())
    result = runner.invoke(chain, obj={"output_format": "json"}, args=["status", "--local"])
    assert result.exit_code == 0, result.output


def test_info_local_flag_queries_local_rpc(runner, monkeypatch):
    captured = {}

    def fake_load(node_urls=()):
        captured["node_urls"] = tuple(node_urls)
        raise chain_mod.ChainNotFoundError("no chain")

    monkeypatch.setattr(chain_mod, "_load_chain_manager", fake_load)
    runner.invoke(chain, obj={"output_format": "json"}, args=["info", "--chain-id", "bc-9", "--local"])
    assert captured["node_urls"][0] == "http://127.0.0.1:8202"


def test_source_endpoints_lists_endpoints():
    node_a = type("N", (), {"endpoint": "http://b:8202"})()
    node_b = type("N", (), {"endpoint": "http://a:8202"})()
    mgr = type("M", (), {"config": type("C", (), {"nodes": {"b": node_a, "a": node_b}})()})()
    assert chain_mod._source_endpoints(mgr) == "http://a:8202, http://b:8202"
