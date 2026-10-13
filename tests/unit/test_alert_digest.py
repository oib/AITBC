"""Tests for scripts/monitoring/alert-digest.py (SD-2).

The digest reads the prometheus-watch alert log and posts one plain-text
summary of warning-severity events. Loaded by path, same as
test_verify_genesis_root.py / test_replay_chain.py.
"""

import importlib.util
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "monitoring" / "alert-digest.py"
spec = importlib.util.spec_from_file_location("alert_digest", SCRIPT)
digest = importlib.util.module_from_spec(spec)
sys.modules["alert_digest"] = digest
spec.loader.exec_module(digest)

NOW = int(time.time())


def _record(alertname="ServiceDown", severity="warning", event="prometheus_alert_firing", **kw):
    rec = {
        "event": event,
        "alertname": alertname,
        "severity": severity,
        "summary": f"{alertname} summary",
        "timestamp_unix": NOW - 60,
        "labels": {"alertname": alertname, "severity": severity},
    }
    rec.update(kw)
    return rec


def _log(tmp_path, records):
    path = tmp_path / "alerts.log"
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    return path


def test_collect_groups_warning_events_by_alertname(tmp_path):
    log = _log(
        tmp_path,
        [
            _record("ServiceDown"),
            _record("ServiceDown", event="prometheus_alert_resolved"),
            _record("MemoryPressure"),
        ],
    )
    groups = digest._collect(log, NOW - 3600)
    assert set(groups) == {"ServiceDown", "MemoryPressure"}
    assert groups["ServiceDown"]["firing"] == 1
    assert groups["ServiceDown"]["resolved"] == 1
    assert groups["MemoryPressure"]["firing"] == 1


def test_collect_ignores_non_warning_and_stale_and_non_alert_lines(tmp_path):
    log = _log(
        tmp_path,
        [
            _record("Crit", severity="critical"),  # critical pushes live, not digested
            _record("Info", severity="info"),  # info stays in the log only
            _record("Old", timestamp_unix=NOW - 90000),  # outside the window
            _record("WatchLifecycle", event="prometheus_watch_started", severity=None),
        ],
    )
    # plus a malformed line and a non-JSON line
    with log.open("a") as f:
        f.write("{not json\nplain text line\n")
    groups = digest._collect(log, NOW - 3600)
    assert groups == {}


def test_empty_window_posts_nothing(tmp_path, capsys):
    log = _log(tmp_path, [_record("Crit", severity="critical")])
    rc = digest.main(["--alert-log", str(log), "--notify-url", "http://x/y"])
    assert rc == 0
    assert "nothing to send" in capsys.readouterr().out


def test_dry_run_renders_the_digest(tmp_path, capsys):
    log = _log(
        tmp_path,
        [
            _record("ServiceDown", labels={"instance": "node0:9100"}),
            _record("ServiceDown", labels={"instance": "node0:9100"}),
        ],
    )
    rc = digest.main(["--alert-log", str(log), "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ServiceDown" in out
    assert "node0:9100" in out
    assert "2 firing" in out


def test_post_calls_every_url_once(tmp_path, monkeypatch):
    sent = []

    class _Resp:
        def read(self):
            return b""

    monkeypatch.setattr(digest.urllib.request, "urlopen", lambda req, timeout=None: sent.append(req.full_url) or _Resp())
    failures = digest._post(["http://a/t", "http://b/t"], "body")
    assert failures == 0
    assert sent == ["http://a/t", "http://b/t"]


def test_post_refuses_non_http_schemes(tmp_path, monkeypatch):
    calls = []

    class _Resp:
        def read(self):
            return b""

    monkeypatch.setattr(digest.urllib.request, "urlopen", lambda *a, **k: calls.append(a) or _Resp())
    failures = digest._post(["file:///etc/passwd", "ftp://x/y", "http://ok/t"], "body")
    assert failures == 2
    assert len(calls) == 1


# --- ntfy publish mode (SD-2c) -------------------------------------------------


def _capture_requests(monkeypatch):
    """Stub urlopen and collect the Request objects it was called with."""
    calls = []

    class _Resp:
        def read(self):
            return b""

    monkeypatch.setattr(digest.urllib.request, "urlopen", lambda req, timeout=None: calls.append(req) or _Resp())
    return calls


def test_ntfy_digest_posts_counts_and_alert_names_only(monkeypatch):
    """Instance addresses and annotation text must never reach the ntfy body."""
    calls = _capture_requests(monkeypatch)
    groups = {
        "ServiceDown": {
            "firing": 2,
            "resolved": 0,
            "still_firing": 0,
            "instances": {"node0:9100"},
            "summary": "exporter on 0x1111222233334444555566667777888899990000 is down",
        }
    }
    body = digest._render_ntfy(groups, 24, "hub")
    assert "ServiceDown: 2 firing" in body
    assert "on hub" in body
    # FQDN collapses to the fleet name; unknown hosts collapse to "fleet".
    assert "on hub" in digest._render_ntfy(groups, 24, "hub.aitbc.bubuit.net")
    assert "on fleet" in digest._render_ntfy(groups, 24, "desktop-9")
    assert "node0:9100" not in body
    assert "0x1111222233334444555566667777888899990000" not in body
    assert "exporter on" not in body
    failures = digest._post(["http://ntfy.test/"], body, notify_format="ntfy", token="tk_TESTONLY")
    assert failures == 0
    req = calls[0]
    assert req.get_header("Authorization") == "Bearer tk_TESTONLY"
    payload = json.loads(req.data)
    assert set(payload) == {"topic", "title", "message", "priority", "click"}
    assert payload["topic"] == "aitbc-alerts"
    assert payload["title"] == "AITBC daily digest"
    assert payload["priority"] == 2
    assert "ServiceDown: 2 firing" in payload["message"]
    assert "0x1111" not in payload["message"]


def test_ntfy_digest_without_a_token_posts_nothing(monkeypatch, capsys):
    calls = _capture_requests(monkeypatch)
    failures = digest._post(["http://ntfy.test/"], "body", notify_format="ntfy", token=None)
    assert failures == 1
    assert calls == []
    assert "TOKEN is unset" in capsys.readouterr().err


def test_json_digest_keeps_the_plaintext_body(monkeypatch):
    calls = _capture_requests(monkeypatch)
    failures = digest._post(["http://ok/t"], "ServiceDown [node0:9100]: 2 firing")
    assert failures == 0
    req = calls[0]
    assert req.get_header("Content-type") == "text/plain"
    assert req.data == b"ServiceDown [node0:9100]: 2 firing"
