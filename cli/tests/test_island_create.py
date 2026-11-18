"""#2203: island create must register via RPC; joined_at renders ISO; hub redis auth."""

import importlib
import json

import click
import pytest


def _ctx(fmt="table"):
    return type("C", (), {"obj": {"output_format": fmt}})()


def _patch_rpc_client(monkeypatch, response):
    """Install a fake AITBCHTTPClient that records posts and returns ``response``."""
    calls = []

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def post(self, path, json=None):
            calls.append((path, json))
            return response

        def close(self):
            pass

    import aitbc_cli.utils.http_client as hc

    monkeypatch.setattr(hc, "AITBCHTTPClient", FakeClient)
    # island.py binds AITBCHTTPClient at module level for the join path
    isl = importlib.import_module("aitbc_cli.commands.node.island")
    monkeypatch.setattr(isl, "AITBCHTTPClient", FakeClient, raising=False)
    import aitbc_cli.config as cfg

    monkeypatch.setattr(cfg, "get_config", lambda: type("C", (), {"blockchain_rpc_api_key": "k"})())
    return calls


JOIN_OK = {
    "success": True,
    "island_id": "isl-1",
    "island_name": "new-island",
    "island_chain_id": "ait-isl-1",
    "status": "joined",
    "message": "ok",
    "credentials": {"chain_id": "ait-isl-1"},
    "members": [{"node_id": "n1", "is_hub": True}],
}


def test_create_posts_join_with_is_hub(monkeypatch):
    """create must call /rpc/islands/join with is_hub=True, not just print ids."""
    isl = importlib.import_module("aitbc_cli.commands.node.island")
    calls = _patch_rpc_client(monkeypatch, JOIN_OK)
    monkeypatch.setattr(isl, "_store_island_credentials", lambda resp, creds: "/tmp/creds.json")

    isl.create_island_command(_ctx(), "isl-1", "new-island", "ait-isl-1", node_url="http://127.0.0.1:8202")

    assert calls == [
        (
            "/rpc/islands/join",
            {
                "island_id": "isl-1",
                "island_name": "new-island",
                "chain_id": "ait-isl-1",
                "is_hub": True,
                "role": "hub",
            },
        )
    ]


def test_create_generates_ids_and_aborts_on_rpc_failure(monkeypatch):
    isl = importlib.import_module("aitbc_cli.commands.node.island")
    _patch_rpc_client(monkeypatch, {"success": False, "status": "failed", "message": "nope"})

    with pytest.raises(click.Abort):
        isl.create_island_command(_ctx(), None, "x", None)


def test_format_joined_at_epoch_and_passthrough():
    isl = importlib.import_module("aitbc_cli.commands.node.island")
    assert isl._format_joined_at(1794948505.854829) == "2026-11-17T20:48:25.854829+00:00"
    assert isl._format_joined_at("2024-01-01T00:00:00") == "2024-01-01T00:00:00"
    assert isl._format_joined_at(None) == "N/A"
    assert isl._format_joined_at("") == "N/A"


def test_island_info_formats_joined_at(monkeypatch, capsys):
    isl = importlib.import_module("aitbc_cli.commands.node.island")

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def get(self, path):
            return {"island_id": "i", "joined_at": 1794948505.0}

        def close(self):
            pass

    import aitbc_cli.utils.http_client as hc

    monkeypatch.setattr(hc, "AITBCHTTPClient", FakeClient)
    import aitbc_cli.config as cfg

    monkeypatch.setattr(cfg, "get_config", lambda: type("C", (), {"blockchain_rpc_api_key": "k"})())

    isl.island_info_command(_ctx("json"), "i")
    out = capsys.readouterr().out
    assert "2026-11-17" in out
    assert "1794948505" not in out


# --- hub redis auth (#2203 finding 2) ---


def test_resolve_redis_url_precedence(monkeypatch):
    hub = importlib.import_module("aitbc_cli.commands.node.hub")
    import aitbc_cli.config as cfg

    monkeypatch.setattr(cfg, "get_config", lambda: type("C", (), {"redis_url": "redis://cfg:6379/2"})())
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)

    assert hub._resolve_redis_url(None) == "redis://cfg:6379/2"
    assert hub._resolve_redis_url("redis://flag:6379") == "redis://flag:6379"
    # password injection preserves an existing username and port
    assert hub._resolve_redis_url("redis://user@cache:6380", "s3cret") == "redis://user:s3cret@cache:6380"
    # existing password is not overwritten
    assert hub._resolve_redis_url("redis://:pw@cache:6379", "other") == "redis://:pw@cache:6379"


def test_list_hubs_reads_hub_keys(monkeypatch, capsys):
    """list-hubs must read the hub:<node_id> keys HubManager writes, not only the 'hubs' hash."""
    hub = importlib.import_module("aitbc_cli.commands.node.hub")

    stored = {
        b"hub:node-1": json.dumps(
            {
                "node_id": "node-1",
                "island_id": "isl",
                "island_name": "main",
                "address": "10.0.0.1",
                "port": 7070,
                "public_address": "1.2.3.4",
                "public_port": 8202,
            }
        ).encode(),
    }

    class FakeRedis:
        def __init__(self, url):
            pass

        async def scan_iter(self, pattern):
            for k in stored:
                yield k

        async def get(self, key):
            return stored.get(key)

        async def hgetall(self, name):
            return {}

        async def close(self):
            pass

    import redis.asyncio as rai

    monkeypatch.setattr(rai, "from_url", lambda url, **kw: FakeRedis(url))
    monkeypatch.setattr(hub, "_resolve_redis_url", lambda url, pw=None: "redis://x")

    hub.list_hubs_command(_ctx(), None)
    out = capsys.readouterr().out
    assert "node-1" in out
    assert "1.2.3.4" in out
    assert "8202" in out


def test_list_hubs_auth_error_is_clean(monkeypatch):
    hub = importlib.import_module("aitbc_cli.commands.node.hub")

    class FakeRedis:
        def __init__(self, url):
            pass

        async def scan_iter(self, pattern):
            if pattern == "never":
                yield pattern
            raise RuntimeError("unreachable")

        async def hgetall(self, name):
            return {}

        async def close(self):
            pass

    import redis.asyncio as rai
    from redis.exceptions import AuthenticationError

    def _auth(url, **kw):
        class R(FakeRedis):
            async def scan_iter(self, pattern):
                if pattern == "never":
                    yield pattern
                raise AuthenticationError("invalid password")

        return R(url)

    monkeypatch.setattr(rai, "from_url", _auth)
    monkeypatch.setattr(hub, "_resolve_redis_url", lambda url, pw=None: "redis://:bad@h:6379")

    with pytest.raises(click.Abort):
        hub.list_hubs_command(_ctx(), None)
