"""Pin for AUDIT-EDGE-HERMES-ENV-INHERIT (#2903).

The hermes workload child must NOT inherit the service environment:
provider keys it needs are passed by explicit name, while service secrets
(PROPOSER_KEY, VALIDATOR_KEYS, JWT_SECRET, AITBC_* wiring) stay out — a
prompt-driven agent could otherwise print them to stdout and return them
to the paying caller.
"""

import importlib.util
import sys
from pathlib import Path

_MAIN_PATH = Path(__file__).resolve().parents[1] / "main.py"


def _load_main():
    spec = importlib.util.spec_from_file_location("aitbc_hermes_main_env", _MAIN_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_spec = importlib.util.spec_from_file_location("aitbc_hermes_main_env", _MAIN_PATH)
hermes = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["aitbc_hermes_main_env"] = hermes
_spec.loader.exec_module(hermes)


def test_child_env_excludes_service_secrets(monkeypatch):
    """Secrets in os.environ must not reach the hermes child."""
    monkeypatch.setenv("PROPOSER_KEY", "0xdeadbeef")
    monkeypatch.setenv("VALIDATOR_KEYS", "keymaterial")
    monkeypatch.setenv("JWT_SECRET", "jwtsecret")
    monkeypatch.setenv("MARKET_API_KEY", "marketkey")
    monkeypatch.setenv("AITBC_DATA_DIR", "/var/lib/aitbc")
    monkeypatch.setenv("HERMES_RUN_API_KEY", "run-secret")
    env = hermes._hermes_child_env()
    for leaked in ("PROPOSER_KEY", "VALIDATOR_KEYS", "JWT_SECRET", "MARKET_API_KEY", "AITBC_DATA_DIR", "HERMES_RUN_API_KEY"):
        assert leaked not in env, f"{leaked} leaked into hermes child env"


def test_child_env_includes_provider_keys_and_base(monkeypatch):
    """Provider keys, HERMES_HOME, proxies and the subprocess_env base pass through."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-key")
    monkeypatch.setenv("HERMES_HOME", "/var/lib/aitbc/hermes")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy:3128")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setenv("TMPDIR", "/tmp")
    env = hermes._hermes_child_env()
    assert env["OPENROUTER_API_KEY"] == "or-key"
    assert env["ANTHROPIC_API_KEY"] == "ant-key"
    assert env["HERMES_HOME"] == "/var/lib/aitbc/hermes"
    assert env["HTTPS_PROXY"] == "http://proxy:3128"
    assert env["PATH"] == "/usr/bin:/bin"
    assert env["TMPDIR"] == "/tmp"


def test_child_env_allowlist_escape_hatch(monkeypatch):
    """HERMES_CHILD_ENV_ALLOWLIST adds operator-named extras; unset names skipped."""
    monkeypatch.setenv("HERMES_CHILD_ENV_ALLOWLIST", "CUSTOM_PROVIDER_KEY, MISSING_VAR")
    monkeypatch.setenv("CUSTOM_PROVIDER_KEY", "custom")
    monkeypatch.delenv("MISSING_VAR", raising=False)
    env = hermes._hermes_child_env()
    assert env["CUSTOM_PROVIDER_KEY"] == "custom"
    assert "MISSING_VAR" not in env


def test_run_passes_bounded_env(monkeypatch):
    """_run_hermes_inner must spawn the child with _hermes_child_env(), not inherit."""
    import asyncio

    captured = {}

    class _FakeProc:
        returncode = 0
        pid = 999999

        async def communicate(self):
            return b"", b""

        async def wait(self):
            return 0

        def kill(self):
            pass

    async def fake_exec(*args, **kwargs):
        captured.update(kwargs)
        return _FakeProc()

    monkeypatch.setattr(hermes, "_HERMES_PATH", "/bin/hermes")
    monkeypatch.setattr(hermes, "_HERMES_DEFAULT_MODEL", "m")
    monkeypatch.setattr(hermes, "_HERMES_DEFAULT_PROVIDER", "p")
    monkeypatch.setattr(hermes, "_HERMES_DEFAULT_TOOLSETS", "core")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    # _communicate_bounded reads proc.stdout/stderr streams; give it fakes.
    class _Stream:
        async def read(self, n):
            return b""

    _FakeProc.stdout = _Stream()
    _FakeProc.stderr = _Stream()

    req = hermes.HermesRunRequest(prompt="x")
    asyncio.run(hermes._run_hermes_inner(req))
    assert "env" in captured, "create_subprocess_exec called without env= — child inherits os.environ"
    assert "PROPOSER_KEY" not in captured["env"]
