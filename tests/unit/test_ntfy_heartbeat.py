"""Tests for scripts/monitoring/ntfy-heartbeat.py (SD-2c).

The heartbeat posts one whitelisted ntfy message to the aitbc-heartbeat
topic; the bearer token comes from the environment and never reaches a
command line or a log line. Loaded by path, same as test_alert_digest.py.
"""

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "monitoring" / "ntfy-heartbeat.py"
spec = importlib.util.spec_from_file_location("ntfy_heartbeat", SCRIPT)
heartbeat = importlib.util.module_from_spec(spec)
sys.modules["ntfy_heartbeat"] = heartbeat
spec.loader.exec_module(heartbeat)


def _capture(monkeypatch):
    calls = []

    class _Resp:
        def read(self):
            return b""

    monkeypatch.setattr(heartbeat.urllib.request, "urlopen", lambda req, timeout=None: calls.append(req) or _Resp())
    return calls


def _env(monkeypatch, url="https://ntfy.test", token="tk_TESTONLY"):
    monkeypatch.setenv("AITBC_HEARTBEAT_URL", url)
    monkeypatch.delenv("AITBC_WATCH_NOTIFY_URL", raising=False)
    monkeypatch.setenv("AITBC_WATCH_NOTIFY_TOKEN", token)


def test_hourly_beat_is_silent_priority(monkeypatch):
    calls = _capture(monkeypatch)
    _env(monkeypatch)
    assert heartbeat.main(["--kind", "hourly"]) == 0
    req = calls[0]
    assert req.get_header("Authorization") == "Bearer tk_TESTONLY"
    payload = json.loads(req.data)
    assert set(payload) == {"topic", "title", "message", "priority"}
    assert payload["topic"] == "aitbc-heartbeat"
    assert payload["priority"] == 1
    assert payload["message"] == "all quiet"


def test_daily_beat_is_visible_priority(monkeypatch):
    calls = _capture(monkeypatch)
    _env(monkeypatch)
    assert heartbeat.main(["--kind", "daily"]) == 0
    payload = json.loads(calls[0].data)
    assert payload["priority"] == 2
    assert payload["message"] == "alive"


def test_url_falls_back_to_the_watcher_env(monkeypatch):
    calls = _capture(monkeypatch)
    monkeypatch.delenv("AITBC_HEARTBEAT_URL", raising=False)
    monkeypatch.setenv("AITBC_WATCH_NOTIFY_URL", "https://ntfy.test https://other.test")
    monkeypatch.setenv("AITBC_WATCH_NOTIFY_TOKEN", "tk_TESTONLY")
    assert heartbeat.main(["--kind", "hourly"]) == 0
    # First URL only — the heartbeat is a single liveness signal.
    assert len(calls) == 1
    assert calls[0].full_url == "https://ntfy.test"


def test_missing_token_posts_nothing(monkeypatch, capsys):
    calls = _capture(monkeypatch)
    monkeypatch.setenv("AITBC_HEARTBEAT_URL", "https://ntfy.test")
    monkeypatch.delenv("AITBC_WATCH_NOTIFY_TOKEN", raising=False)
    assert heartbeat.main(["--kind", "hourly"]) == 1
    assert calls == []
    assert "TOKEN is unset" in capsys.readouterr().err


def test_missing_url_posts_nothing(monkeypatch, capsys):
    calls = _capture(monkeypatch)
    monkeypatch.delenv("AITBC_HEARTBEAT_URL", raising=False)
    monkeypatch.delenv("AITBC_WATCH_NOTIFY_URL", raising=False)
    monkeypatch.setenv("AITBC_WATCH_NOTIFY_TOKEN", "tk_TESTONLY")
    assert heartbeat.main(["--kind", "hourly"]) == 1
    assert calls == []
    assert "heartbeat skipped" in capsys.readouterr().err


def test_non_http_url_is_refused(monkeypatch, capsys):
    calls = _capture(monkeypatch)
    _env(monkeypatch, url="file:///etc/passwd")
    assert heartbeat.main(["--kind", "hourly"]) == 1
    assert calls == []
    assert "refusing non-http(s)" in capsys.readouterr().err


def test_a_failed_post_never_prints_the_token(monkeypatch, capsys):
    def _boom(req, timeout=None):
        raise OSError(f"connection refused for {req.full_url}")

    monkeypatch.setattr(heartbeat.urllib.request, "urlopen", _boom)
    _env(monkeypatch, url="https://ntfy.test/?auth=tk_TESTONLY")
    assert heartbeat.main(["--kind", "hourly"]) == 1
    assert "tk_TESTONLY" not in capsys.readouterr().err


def test_title_names_the_fleet_host(monkeypatch):
    monkeypatch.setattr(heartbeat.socket, "gethostname", lambda: "node2.aitbc.bubuit.net")
    calls = _capture(monkeypatch)
    _env(monkeypatch)
    heartbeat.main(["--kind", "daily"])
    assert json.loads(calls[0].data)["title"] == "aitbc heartbeat on node2"


def test_an_unknown_hostname_becomes_fleet(monkeypatch):
    monkeypatch.setattr(heartbeat.socket, "gethostname", lambda: "desktop-9")
    calls = _capture(monkeypatch)
    _env(monkeypatch)
    heartbeat.main(["--kind", "daily"])
    assert json.loads(calls[0].data)["title"] == "aitbc heartbeat on fleet"
