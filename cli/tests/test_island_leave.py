"""CLI-ISLAND-LEAVE-STUB-1: node island leave must call /rpc/islands/leave."""

import importlib


def test_leave_posts_to_rpc(monkeypatch):
    """A fake client records the POST; mutation (stub) leaves it empty."""
    isl = importlib.import_module("aitbc_cli.commands.node.island")

    calls = []

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def post(self, path, json=None):
            calls.append((path, json))
            return {"success": True, "status": "left"}

    import aitbc_cli.utils.http_client as hc

    monkeypatch.setattr(hc, "AITBCHTTPClient", FakeClient)
    import aitbc_cli.config as cfg

    monkeypatch.setattr(cfg, "get_config", lambda: type("C", (), {"blockchain_rpc_api_key": "k"})())

    isl.leave_island_command(None, "i")
    assert calls == [("/rpc/islands/leave", {"island_id": "i"})]
