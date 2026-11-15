"""Tests for scripts/monitoring/ntfy-alert-bridge.py (#2122).

The bridge long-polls the ntfy JSON stream for aitbc-alerts, appends every
message to the on-host forensic log, and republishes fresh alerts to the
bridge topic. The bearer token comes from NTFY_BRIDGE_TOKEN and is never
logged. Loaded by path, same as test_ntfy_heartbeat.py.
"""

import importlib.util
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "monitoring" / "ntfy-alert-bridge.py"
spec = importlib.util.spec_from_file_location("ntfy_alert_bridge", SCRIPT)
bridge = importlib.util.module_from_spec(spec)
sys.modules["ntfy_alert_bridge"] = bridge
spec.loader.exec_module(bridge)


def _env(monkeypatch, token="tk_TESTONLY"):
    monkeypatch.setenv("AITBC_HEARTBEAT_URL", "https://ntfy.test")
    monkeypatch.delenv("AITBC_WATCH_NOTIFY_URL", raising=False)
    monkeypatch.setenv("NTFY_BRIDGE_TOKEN", token)


def test_republish_sends_bearer_and_bridge_body(monkeypatch):
    calls = []

    class _Resp:
        def read(self):
            return b""

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(bridge.urllib.request, "urlopen", lambda req, timeout=None: calls.append(req) or _Resp())
    _env(monkeypatch)
    bridge._republish(
        {
            "event": "message",
            "time": int(time.time()),
            "message": "ALERT test",
            "title": "aitbc",
            "priority": 4,
            "tags": ["warning"],
        }
    )
    assert len(calls) == 1
    req = calls[0]
    assert req.full_url == "https://ntfy.test/aitbc-alerts-bridge"
    assert req.headers.get("Authorization") == "Bearer tk_TESTONLY"
    body = json.loads(req.data.decode())
    assert body["topic"] == "aitbc-alerts-bridge"
    assert body["message"] == "ALERT test"


def test_republish_skips_stale_replay(monkeypatch):
    calls = []

    class _Resp:
        def read(self):
            return b""

    monkeypatch.setattr(bridge.urllib.request, "urlopen", lambda req, timeout=None: calls.append(req) or _Resp())
    _env(monkeypatch)
    bridge._republish(
        {
            "event": "message",
            "time": int(time.time()) - 3600,
            "message": "old cached alert",
            "title": "aitbc",
        }
    )
    assert calls == []


def test_republish_no_token_is_noop(monkeypatch):
    calls = []

    class _Resp:
        def read(self):
            return b""

    monkeypatch.setattr(bridge.urllib.request, "urlopen", lambda req, timeout=None: calls.append(req) or _Resp())
    monkeypatch.delenv("NTFY_BRIDGE_TOKEN", raising=False)
    monkeypatch.delenv("AITBC_WATCH_NOTIFY_TOKEN", raising=False)
    bridge._republish({"event": "message", "time": int(time.time()), "message": "x"})
    assert calls == []
