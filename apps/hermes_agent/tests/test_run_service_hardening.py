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

import importlib.util
import sys
from pathlib import Path


# Load under a unique module name — sibling root-layout apps ship their own
# main.py and a bare ``import main`` collides in sys.modules across suites
# (whoever imports first wins; the loser's tests get the wrong FastAPI app).
# Same convention as test_smoke.py in this directory. Registered in
# sys.modules so importlib.reload() below keeps working. Attribute access
# (hermes.X) rather than name aliases so a reload cannot leave stale refs.
_MAIN_PATH = Path(__file__).resolve().parents[1] / "main.py"


def _load_main():
    """Exec main.py fresh under the unique test module name.

    ``importlib.reload`` cannot be used: it re-resolves the module by name
    through sys.path, and ``aitbc_hermes_main`` exists only as a
    spec_from_file_location module, so reload raises ModuleNotFoundError.
    """
    spec = importlib.util.spec_from_file_location("aitbc_hermes_main", _MAIN_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_spec = importlib.util.spec_from_file_location("aitbc_hermes_main", _MAIN_PATH)
hermes = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["aitbc_hermes_main"] = hermes
_spec.loader.exec_module(hermes)


def _req(**over):
    return hermes.HermesRunRequest(prompt="x", **over)


def _toolsets_arg(cmd):
    return cmd[cmd.index("--toolsets") + 1] if "--toolsets" in cmd else None


def test_empty_toolsets_uses_default(monkeypatch):
    monkeypatch.setattr(hermes, "_HERMES_PATH", "/bin/hermes")
    monkeypatch.setattr(hermes, "_HERMES_DEFAULT_MODEL", "shop-model")
    monkeypatch.setattr(hermes, "_HERMES_DEFAULT_PROVIDER", "shopprov")
    monkeypatch.setattr(hermes, "_HERMES_DEFAULT_TOOLSETS", "web,memory")
    monkeypatch.setattr(hermes, "_HERMES_ALLOWED_TOOLSETS", ["web", "memory"])
    assert _toolsets_arg(hermes._build_command(_req(toolsets=","), "/tmp/u")) == "web,memory"
    assert _toolsets_arg(hermes._build_command(_req(toolsets=" , , "), "/tmp/u")) == "web,memory"
    assert _toolsets_arg(hermes._build_command(_req(toolsets=""), "/tmp/u")) == "web,memory"


def test_unconfigured_env_fail_closed(monkeypatch):
    """No defaults and no allow-lists: refuse instead of Hermes profile fallthrough."""
    import pytest
    from fastapi import HTTPException

    monkeypatch.setattr(hermes, "_HERMES_PATH", "/bin/hermes")
    monkeypatch.setattr(hermes, "_HERMES_DEFAULT_MODEL", "")
    monkeypatch.setattr(hermes, "_HERMES_DEFAULT_PROVIDER", "")
    monkeypatch.setattr(hermes, "_HERMES_DEFAULT_TOOLSETS", "")
    monkeypatch.setattr(hermes, "_HERMES_ALLOWED_MODELS", [])
    monkeypatch.setattr(hermes, "_HERMES_ALLOWED_PROVIDERS", [])
    monkeypatch.setattr(hermes, "_HERMES_ALLOWED_TOOLSETS", [])
    with pytest.raises(HTTPException) as exc:
        hermes._build_command(_req(), "/tmp/u")
    assert exc.value.status_code == 503


def test_run_requires_credential(monkeypatch):
    """HERMES_RUN_API_KEY set + no Authorization header -> 401."""
    from fastapi.testclient import TestClient

    monkeypatch.setenv("HERMES_RUN_API_KEY", "s3cret")
    fresh = _load_main()  # re-exec so the env var is read at module level
    client = TestClient(fresh.app)
    r = client.post("/run", json={"prompt": "x"})
    assert r.status_code == 401, f"/run answered {r.status_code} with no credential"


def test_run_semaphore_limits_concurrency():
    import asyncio

    assert hasattr(hermes, "_run_semaphore"), "no semaphore on /run — unbounded parallel runs"
    assert asyncio.Semaphore.__instancecheck__(hermes._run_semaphore)


# --- HERMES-IPFS-DEPTH2-1 (#1633): empty allowlist means "default only" ---


def _base_env(monkeypatch):
    monkeypatch.setattr(hermes, "_HERMES_PATH", "/bin/hermes")
    monkeypatch.setattr(hermes, "_HERMES_DEFAULT_MODEL", "shop/default-model")
    monkeypatch.setattr(hermes, "_HERMES_DEFAULT_PROVIDER", "shopprov")
    monkeypatch.setattr(hermes, "_HERMES_DEFAULT_TOOLSETS", "core")
    monkeypatch.setattr(hermes, "_HERMES_ALLOWED_MODELS", [])
    monkeypatch.setattr(hermes, "_HERMES_ALLOWED_PROVIDERS", [])
    monkeypatch.setattr(hermes, "_HERMES_ALLOWED_TOOLSETS", [])


def test_empty_allowlist_rejects_nondefault_model(monkeypatch):
    """Empty HERMES_ALLOWED_MODELS + default set: buyer model != default -> 400."""
    import pytest
    from fastapi import HTTPException

    _base_env(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        hermes._build_command(_req(model="buyer/chosen"), "/tmp/u")
    assert exc.value.status_code == 400


def test_empty_allowlist_accepts_default_model(monkeypatch):
    _base_env(monkeypatch)
    cmd = hermes._build_command(_req(model="shop/default-model"), "/tmp/u")
    assert "--model" in cmd


def test_empty_allowlist_rejects_nondefault_provider(monkeypatch):
    import pytest
    from fastapi import HTTPException

    _base_env(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        hermes._build_command(_req(provider="evilprov"), "/tmp/u")
    assert exc.value.status_code == 400


def test_empty_allowlist_toolsets_bounded_by_default(monkeypatch):
    """Buyer toolsets must be a subset of the default set when no allowlist."""
    import pytest
    from fastapi import HTTPException

    _base_env(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        hermes._build_command(_req(toolsets="core,shell"), "/tmp/u")
    assert exc.value.status_code == 400
    cmd = hermes._build_command(_req(toolsets="core"), "/tmp/u")
    assert _toolsets_arg(cmd) == "core"


def test_no_allowlist_no_default_rejects_buyer_toolsets(monkeypatch):
    """Nothing configured at all: fail closed before buyer-chosen toolsets run."""
    import pytest
    from fastapi import HTTPException

    _base_env(monkeypatch)
    monkeypatch.setattr(hermes, "_HERMES_DEFAULT_TOOLSETS", "")
    monkeypatch.setattr(hermes, "_HERMES_DEFAULT_MODEL", "")
    monkeypatch.setattr(hermes, "_HERMES_DEFAULT_PROVIDER", "")
    with pytest.raises(HTTPException) as exc:
        hermes._build_command(_req(toolsets="shell"), "/tmp/u")
    assert exc.value.status_code == 503


# --- HERMES-ALLOWLIST-1 (#1804): empty resolved allow set is not allow-all ---


def test_fail_closed_when_only_toolsets_missing(monkeypatch):
    """Models and providers configured but toolsets resolve empty -> 503."""
    import pytest
    from fastapi import HTTPException

    monkeypatch.setattr(hermes, "_HERMES_PATH", "/bin/hermes")
    monkeypatch.setattr(hermes, "_HERMES_DEFAULT_MODEL", "shop/model")
    monkeypatch.setattr(hermes, "_HERMES_DEFAULT_PROVIDER", "shopprov")
    monkeypatch.setattr(hermes, "_HERMES_DEFAULT_TOOLSETS", "")
    monkeypatch.setattr(hermes, "_HERMES_ALLOWED_MODELS", [])
    monkeypatch.setattr(hermes, "_HERMES_ALLOWED_PROVIDERS", [])
    monkeypatch.setattr(hermes, "_HERMES_ALLOWED_TOOLSETS", [])
    with pytest.raises(HTTPException) as exc:
        hermes._build_command(_req(), "/tmp/u")
    assert exc.value.status_code == 503
    assert "Toolsets" in exc.value.detail


def test_nonempty_allowlist_unrequested_emits_bounded_toolsets(monkeypatch):
    """Allowlist set but nothing resolved: never fall through to full profile."""
    _base_env(monkeypatch)
    monkeypatch.setattr(hermes, "_HERMES_DEFAULT_TOOLSETS", "")
    monkeypatch.setattr(hermes, "_HERMES_ALLOWED_TOOLSETS", ["alpha", "beta"])
    cmd = hermes._build_command(_req(), "/tmp/u")
    arg = _toolsets_arg(cmd)
    assert arg is not None, "no --toolsets — hermes would use its full profile"
    assert set(arg.split(",")) <= {"alpha", "beta"}
