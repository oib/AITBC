"""#2107: operations agent/ai commands must resolve the agent coordinator
URL from config instead of hardcoding http://localhost:8107."""

import aitbc_cli.commands.operations as ops_mod


def test_agent_coordinator_url_uses_config(monkeypatch):
    monkeypatch.setattr(
        ops_mod,
        "get_config",
        lambda: type("Cfg", (), {"agent_coordinator_url": "http://agent-coord:8107"})(),
    )
    assert ops_mod._agent_coordinator_url() == "http://agent-coord:8107"


def test_agent_coordinator_url_default(monkeypatch):
    monkeypatch.setattr(ops_mod, "get_config", lambda: type("Cfg", (), {"agent_coordinator_url": ""})())
    assert ops_mod._agent_coordinator_url() == "http://localhost:8107"
