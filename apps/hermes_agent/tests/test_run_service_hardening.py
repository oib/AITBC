"""Phase-0 pin for HERMES-RUN-SERVICE-HARDENING-1 (#808).

``/run`` answers with no credential, ``toolsets=','`` (empty/all-separator)
silently produces NO --toolsets flag so the agent falls through to the
full profile set, and there is no concurrency cap.

Desired behaviour (pinned here): (a) /run requires a shared secret when
HERMES_RUN_API_KEY is set — dependency-checked, 401 without it; (b) an
empty or all-separator toolsets string means "use the default", and when
neither default nor allow-list is configured an explicit conservative
--toolsets is passed (never the profile default); (c) concurrent runs are
capped by a semaphore. These FAIL on current main.
"""

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent))

import main as hermes
from main import HermesRunRequest, _build_command


def _req(**over):
    return HermesRunRequest(prompt="x", **over)


def _toolsets_arg(cmd):
    return cmd[cmd.index("--toolsets") + 1] if "--toolsets" in cmd else None


def test_empty_toolsets_uses_default(monkeypatch):
    monkeypatch.setattr(hermes, "_HERMES_PATH", "/bin/hermes")
    monkeypatch.setattr(hermes, "_HERMES_DEFAULT_TOOLSETS", "web,memory")
    monkeypatch.setattr(hermes, "_HERMES_ALLOWED_TOOLSETS", "web,memory")
    assert _toolsets_arg(_build_command(_req(toolsets=","), "/tmp/u")) == "web,memory"
    assert _toolsets_arg(_build_command(_req(toolsets=" , , "), "/tmp/u")) == "web,memory"
    assert _toolsets_arg(_build_command(_req(toolsets=""), "/tmp/u")) == "web,memory"


def test_unconfigured_env_forces_conservative_toolsets(monkeypatch):
    """No default and no allow-list: pass an explicit safe set, not the profile's."""
    monkeypatch.setattr(hermes, "_HERMES_PATH", "/bin/hermes")
    monkeypatch.setattr(hermes, "_HERMES_DEFAULT_TOOLSETS", "")
    monkeypatch.setattr(hermes, "_HERMES_ALLOWED_TOOLSETS", "")
    arg = _toolsets_arg(_build_command(_req(), "/tmp/u"))
    assert arg is not None and arg, "no --toolsets at all — falls through to the full profile"


def test_run_requires_credential(monkeypatch):
    """HERMES_RUN_API_KEY set + no Authorization header -> 401."""
    from fastapi.testclient import TestClient

    monkeypatch.setenv("HERMES_RUN_API_KEY", "s3cret")
    import importlib

    importlib.reload(hermes)
    client = TestClient(hermes.app)
    r = client.post("/run", json={"prompt": "x"})
    assert r.status_code == 401, f"/run answered {r.status_code} with no credential"


def test_run_semaphore_limits_concurrency():
    import asyncio

    assert hasattr(hermes, "_run_semaphore"), "no semaphore on /run — unbounded parallel runs"
    assert asyncio.Semaphore.__instancecheck__(hermes._run_semaphore)
