"""#2271: `aitbc --api-key K governance ...` must send K as X-API-Key.

The global ``--api-key`` flag lands in ``ctx.obj["api_key"]`` but
``governance._get_client`` only consulted ``GOVERNANCE_API_KEY`` and the
configured ``api_key`` — the flag was silently dropped, so mutating routes
(#1873 X-Api-Key requirement) 403'd for flag-only invocations.
"""

from types import SimpleNamespace

import aitbc_cli.commands.governance as governance_mod


def _ctx(api_key=None, config=None):
    return SimpleNamespace(obj={"api_key": api_key, "config": config})


def _key_of(client):
    return client.headers.get("X-API-Key")


def test_flag_api_key_wins(monkeypatch):
    monkeypatch.setenv("GOVERNANCE_API_KEY", "env-key")
    monkeypatch.delenv("GOVERNANCE_SERVICE_URL", raising=False)
    client = governance_mod._get_client(_ctx(api_key="flag-key"))
    assert _key_of(client) == "flag-key"


def test_env_key_used_when_no_flag(monkeypatch):
    monkeypatch.setenv("GOVERNANCE_API_KEY", "env-key")
    client = governance_mod._get_client(_ctx(api_key=None))
    assert _key_of(client) == "env-key"


def test_config_key_fallback(monkeypatch):
    monkeypatch.delenv("GOVERNANCE_API_KEY", raising=False)
    cfg = SimpleNamespace(api_key="cfg-key", governance_service_url="")
    client = governance_mod._get_client(_ctx(api_key=None, config=cfg))
    assert _key_of(client) == "cfg-key"


def test_no_key_anywhere_sends_none(monkeypatch, tmp_path):
    monkeypatch.delenv("GOVERNANCE_API_KEY", raising=False)
    monkeypatch.delenv("AITBC_API_KEY", raising=False)
    # Ensure get_config() fallback cannot leak a host key into the test, and
    # point the service-env fallback at a path that does not exist (#2411).
    monkeypatch.setattr(governance_mod, "get_config", lambda: SimpleNamespace(api_key=None))
    monkeypatch.setattr(governance_mod, "_GOVERNANCE_ENV_FILE", tmp_path / "absent.env")
    client = governance_mod._get_client(_ctx(api_key=None))
    assert _key_of(client) is None


def test_service_env_file_fallback(monkeypatch, tmp_path):
    """#2411: with no flag/env/config key, the service env file supplies it."""
    monkeypatch.delenv("GOVERNANCE_API_KEY", raising=False)
    monkeypatch.setattr(governance_mod, "get_config", lambda: SimpleNamespace(api_key=None))
    env_file = tmp_path / "aitbc-governance.env"
    env_file.write_text('DB_PASS="x"\nGOVERNANCE_API_KEY="svc-file-key"\n')
    monkeypatch.setattr(governance_mod, "_GOVERNANCE_ENV_FILE", env_file)
    client = governance_mod._get_client(_ctx(api_key=None))
    assert _key_of(client) == "svc-file-key"


def test_service_env_file_loses_to_config_key(monkeypatch, tmp_path):
    """The env file is the last resort — configured api_key still wins."""
    monkeypatch.delenv("GOVERNANCE_API_KEY", raising=False)
    cfg = SimpleNamespace(api_key="cfg-key", governance_service_url="")
    env_file = tmp_path / "aitbc-governance.env"
    env_file.write_text("GOVERNANCE_API_KEY=svc-file-key\n")
    monkeypatch.setattr(governance_mod, "_GOVERNANCE_ENV_FILE", env_file)
    client = governance_mod._get_client(_ctx(api_key=None, config=cfg))
    assert _key_of(client) == "cfg-key"
