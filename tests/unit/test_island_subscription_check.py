"""Exit-code contract for island-subscription-check.sh (C21).

The unit lost its API-key source when the coordinator-api teardown removed
/etc/aitbc/aitbc-coordinator-api.env (the file the CLI's _resolve_api_key
read MINER_API_KEYS from). The script now distinguishes:

    0  subscription active
    1  subscription expired / missing  (actionable: renew)
    2  coordinator down / unreachable (transient)
    3  no API key configured          (AITBC_API_KEY absent on every leg)
    4  key configured but refused     (HTTP 401/403)
    5  other inconclusive output

Tests stub the `aitbc` binary (prints $AITBC_STUB_OUT verbatim) and `logger`
(appends "priority|message" lines to $STUB_LOG). No fixture ever carries a
real key; the leak test uses a sentinel string and asserts it never appears
in output or the log.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "monitoring" / "island-subscription-check.sh"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")

AITBC_STUB = "#!/bin/sh\nprintf '%s\\n' \"$AITBC_STUB_OUT\"\n"
LOGGER_STUB = '#!/bin/sh\nprio=""; while [ "${1#-}" != "$1" ]; do shift; done\nwhile [ $# -gt 1 ]; do case "$1" in -t|-p) shift 2;; *) prio="$1"; shift;; esac; done\nprintf "%s|%s\\n" "$prio" "$1" >> "$STUB_LOG"\n'

SECRET = "test-sentinel-key-DO-NOT-USE-9f4e2a"


@pytest.fixture
def env(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("aitbc", AITBC_STUB), ("logger", LOGGER_STUB)):
        stub = bin_dir / name
        stub.write_text(body)
        stub.chmod(0o755)
    log = tmp_path / "log"
    e = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "STUB_LOG": str(log),
        "AITBC_STUB_OUT": "",
        "AITBC_WALLET_DIR": str(tmp_path / "wallets"),
    }
    return SimpleNamespace(env=e, tmp=tmp_path, log=log)


def _run(env: SimpleNamespace, out: str, **overrides) -> subprocess.CompletedProcess:
    e = dict(env.env)
    e["AITBC_STUB_OUT"] = out
    e.update(overrides)
    return subprocess.run(["bash", str(SCRIPT)], env=e, capture_output=True, text=True, timeout=60)


def _log(env: SimpleNamespace) -> str:
    return env.log.read_text() if env.log.exists() else ""


def _all_output(env: SimpleNamespace, r: subprocess.CompletedProcess) -> str:
    return f"{r.stdout}\n{r.stderr}\n{_log(env)}"


def test_active_subscription_exits_0(env):
    r = _run(env, '{"success": true, "swarm_key": "k"}')
    assert r.returncode == 0
    assert "subscription active" in _log(env)


def test_expired_subscription_exits_1(env):
    r = _run(env, '{"success": false, "error": "No active IPFS subscription"}')
    assert r.returncode == 1
    assert "EXPIRED" in _log(env)


def test_missing_api_key_exits_3_and_names_variable(env):
    """The resolver's own failure message when every leg missed."""
    r = _run(env, "Error: No API key available; set AITBC_API_KEY, add api_key to config, or pass --api-key")
    assert r.returncode == 3
    log = _log(env)
    assert "AITBC_API_KEY is not configured" in log
    assert "/etc/aitbc/aitbc-island-subscription-check.env" in log


def test_refused_key_exits_4(env):
    for body in (
        "Error: HTTP 401 Unauthorized: invalid API key",
        '{"success": false, "error": "403 Forbidden"}',
    ):
        r = _run(env, body, AITBC_API_KEY=SECRET)
        assert r.returncode == 4, body
        log = _log(env)
        assert "refused" in log
        assert "401" in log or "403" in log


def test_coordinator_down_exits_2(env):
    for body in (
        "Error: Connection refused",
        "curl: (7) Failed to connect to hub.aitbc.invalid",
        "Error: request timed out",
    ):
        r = _run(env, body, AITBC_API_KEY=SECRET)
        assert r.returncode == 2, body


def test_unknown_output_exits_5(env):
    r = _run(env, "panic: something unexpected happened", AITBC_API_KEY=SECRET)
    assert r.returncode == 5


def test_key_value_never_appears_in_output_or_log(env):
    """Every failure mode must name the variable, never print the value."""
    for body in (
        "Error: No API key available; set AITBC_API_KEY",
        "Error: HTTP 403 Forbidden",
        "Error: Connection refused",
        "garbage",
    ):
        env.log.unlink(missing_ok=True)
        r = _run(env, body, AITBC_API_KEY=SECRET)
        assert SECRET not in _all_output(env, r), f"key leaked on {body!r}"
