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
