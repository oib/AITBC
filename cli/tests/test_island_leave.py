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


# --- NODE-ISLAND-LEAVE-CODE-1 (#577): not_member rc 0, forbidden/legacy aborts


def _leave_with(monkeypatch, body, ctx=None):
    """Invoke leave_island_command with a fake client returning ``body``."""
    isl = importlib.import_module("aitbc_cli.commands.node.island")

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def post(self, path, json=None):
            return body

    import aitbc_cli.utils.http_client as hc

    monkeypatch.setattr(hc, "AITBCHTTPClient", FakeClient)
    import aitbc_cli.config as cfg

    monkeypatch.setattr(cfg, "get_config", lambda: type("C", (), {"blockchain_rpc_api_key": "k"})())
    return isl.leave_island_command(ctx, "island-1")


def _ctx(fmt):
    return type("C", (), {"obj": {"output_format": fmt}})()


def test_leave_not_member_code_rc0(monkeypatch):
    body = {"success": False, "status": "not_member", "code": "not_member", "message": "Not a member of island island-1"}
    # must return normally (no click.Abort) in table and json formats
    _leave_with(monkeypatch, body)
    _leave_with(monkeypatch, body, ctx=_ctx("json"))


def test_leave_forbidden_default_aborts(monkeypatch):
    import click
    import pytest

    with pytest.raises(click.Abort):
        _leave_with(
            monkeypatch,
            {
                "success": False,
                "status": "forbidden_default",
                "code": "forbidden_default",
                "message": "Cannot leave the default island d",
            },
        )


def test_leave_legacy_codeless_refusal_aborts(monkeypatch):
    import click
    import pytest

    with pytest.raises(click.Abort):
        _leave_with(
            monkeypatch,
            {"success": False, "status": "failed", "message": "Failed to leave island island-1 (may not be a member)"},
        )


def test_leave_success_rc0(monkeypatch):
    _leave_with(monkeypatch, {"success": True, "status": "left"})
