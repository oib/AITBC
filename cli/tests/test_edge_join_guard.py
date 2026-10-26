"""EDGE-JOIN-UNREACHABLE-1: join must not write without --confirm/yes."""


def test_join_without_confirm_writes_nothing(monkeypatch):
    """Refusing the prompt must prevent the POST (no record)."""
    import aitbc_cli.commands.edge as edge

    posts = []

    class FakeClient:
        def post(self, path, json=None):
            posts.append((path, json))
            return type("R", (), {"raise_for_status": lambda s: None, "json": lambda s: {"success": True}})()

    monkeypatch.setattr(edge, "get_edge_client", lambda: FakeClient())
    monkeypatch.setattr("click.confirm", lambda *a, **k: False)
    try:
        edge.join.callback if hasattr(edge.join, "callback") else edge.join
    except Exception:
        pass
    from click.testing import CliRunner

    r = CliRunner().invoke(edge.join, ["--island-id", "i", "--island-name", "n", "--chain-id", "c"])
    assert posts == [] and r.exit_code != 0


def test_join_confirm_posts(monkeypatch):
    """With --confirm the POST goes through."""
    import aitbc_cli.commands.edge as edge
    from click.testing import CliRunner

    posts = []

    class FakeClient:
        def post(self, path, json=None):
            posts.append((path, json))
            return type("R", (), {"raise_for_status": lambda s: None, "json": lambda s: {"success": True}})()

    monkeypatch.setattr(edge, "get_edge_client", lambda: FakeClient())
    CliRunner().invoke(edge.join, ["--island-id", "i", "--island-name", "n", "--chain-id", "c", "--confirm"])
    assert posts and posts[0][0] == "/v1/islands/join"
