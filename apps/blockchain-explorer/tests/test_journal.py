"""Tests for the journal endpoint (routers/journal.py).

``journalctl`` itself is faked by patching ``_run_journalctl``; the endpoint's
validation and the aitbc-only filter are what get exercised.
"""

import pytest
from fastapi.testclient import TestClient

import routers.journal as journal_mod
from main import app


@pytest.fixture
def client():
    return TestClient(app)


def _record(unit: str, message: str = "boom", priority: int = 3, ts_us: int = 1_700_000_000_000_000) -> dict:
    return {
        "_SYSTEMD_UNIT": unit,
        "PRIORITY": str(priority),
        "MESSAGE": message,
        "__REALTIME_TIMESTAMP": str(ts_us),
    }


def _fake_journal(records):
    def fake(priority, since_minutes, limit, unit):
        return records

    return fake


def test_returns_aitbc_entries_newest_first(client, monkeypatch):
    monkeypatch.setattr(
        journal_mod,
        "_run_journalctl",
        _fake_journal(
            [
                _record("aitbc-x.service", "older", ts_us=1_700_000_000_000_000),
                _record("aitbc-y.service", "newer", ts_us=1_700_000_100_000_000),
            ]
        ),
    )
    monkeypatch.setattr(journal_mod, "_journald_reachable", lambda: True)
    body = client.get("/api/journal/recent").json()
    assert [e["message"] for e in body["entries"]] == ["newer", "older"]
    entry = body["entries"][0]
    assert entry["unit"] == "aitbc-y.service"
    assert entry["priority_name"] == "err"
    assert entry["timestamp_unix"] == 1_700_000_100
    assert entry["timestamp"] == "2023-11-14T22:15:00+00:00"


def test_non_aitbc_units_are_dropped(client, monkeypatch):
    monkeypatch.setattr(
        journal_mod,
        "_run_journalctl",
        _fake_journal(
            [
                _record("sshd.service"),
                _record("aitbc-node.service"),
                _record("init.scope"),
            ]
        ),
    )
    body = client.get("/api/journal/recent").json()
    assert [e["unit"] for e in body["entries"]] == ["aitbc-node.service"]


def test_unit_filter_must_be_aitbc(client):
    assert client.get("/api/journal/recent?unit=sshd.service").status_code == 400
    assert client.get("/api/journal/recent?unit=cron").status_code == 400


def test_unit_filter_bare_name_gets_service_suffix(client, monkeypatch):
    seen = {}

    def fake(priority, since_minutes, limit, unit):
        seen["unit"] = unit
        return [_record("aitbc-x.service")]

    monkeypatch.setattr(journal_mod, "_run_journalctl", fake)
    body = client.get("/api/journal/recent?unit=aitbc-x").json()
    assert seen["unit"] == "aitbc-x.service"
    assert body["entries"]


def test_priority_must_be_known(client, monkeypatch):
    assert client.get("/api/journal/recent?priority=loud").status_code == 400
    monkeypatch.setattr(journal_mod, "_run_journalctl", _fake_journal([]))
    monkeypatch.setattr(journal_mod, "_journald_reachable", lambda: True)
    assert client.get("/api/journal/recent?priority=err").status_code == 200


def test_limit_and_since_are_bounded(client):
    assert client.get("/api/journal/recent?limit=0").status_code == 422
    assert client.get("/api/journal/recent?limit=5000").status_code == 422
    assert client.get("/api/journal/recent?since_minutes=999999").status_code == 422


def test_message_truncated(client, monkeypatch):
    monkeypatch.setattr(journal_mod, "_run_journalctl", _fake_journal([_record("aitbc-x.service", "x" * 900)]))
    body = client.get("/api/journal/recent").json()
    assert len(body["entries"][0]["message"]) == 501  # 500 + ellipsis


def test_journalctl_failure_is_503(client, monkeypatch):
    def boom(*_a):
        raise journal_mod.HTTPException(status_code=503, detail="journal unavailable on this host")

    monkeypatch.setattr(journal_mod, "_run_journalctl", boom)
    assert client.get("/api/journal/recent").status_code == 503


def test_no_journal_access_reports_flag(client, monkeypatch):
    monkeypatch.setattr(journal_mod, "_run_journalctl", _fake_journal([]))
    monkeypatch.setattr(journal_mod, "_journald_reachable", lambda: False)
    body = client.get("/api/journal/recent").json()
    assert body["entries"] == []
    assert body["journal_access"] is False


def test_syslog_identifier_falls_back_as_unit(client, monkeypatch):
    record = {
        "SYSLOG_IDENTIFIER": "aitbc-custom",
        "PRIORITY": "4",
        "MESSAGE": "warn",
        "__REALTIME_TIMESTAMP": "1700000000000000",
    }
    monkeypatch.setattr(journal_mod, "_run_journalctl", _fake_journal([record]))
    body = client.get("/api/journal/recent").json()
    assert body["entries"][0]["unit"] == "aitbc-custom"
    assert body["entries"][0]["priority_name"] == "warning"


def test_text_level_maps_priority_6_stdout_logs(client, monkeypatch):
    # aitbc services log via stdout: journald stores PRIORITY=6, the true level
    # lives in the "[WARNING]"/"[ERROR]" message prefix — surface it.
    record = _record("aitbc-x.service", message="[WARNING] silence file unreadable", priority=6)
    monkeypatch.setattr(journal_mod, "_run_journalctl", _fake_journal([record]))
    body = client.get("/api/journal/recent").json()
    entry = body["entries"][0]
    assert entry["priority"] == 4
    assert entry["priority_name"] == "warning"


def test_text_error_levels_map_down_to_err(client, monkeypatch):
    record = _record("aitbc-x.service", message="[ERROR] boom", priority=6)
    monkeypatch.setattr(journal_mod, "_run_journalctl", _fake_journal([record]))
    body = client.get("/api/journal/recent").json()
    assert body["entries"][0]["priority_name"] == "err"


def test_real_run_merges_priority_and_grep_passes(monkeypatch):
    calls = []

    def fake_jctl(extra, since_minutes, limit):
        calls.append(extra[0])
        if extra[0] == "-p":
            return [_record("init.scope", priority=3)]
        return [_record("aitbc-x.service", message="[WARNING] w", priority=6)]

    monkeypatch.setattr(journal_mod, "_journalctl", fake_jctl)
    records = journal_mod._run_journalctl("warning", 60, 50, None)
    assert calls == ["-p", "-g"]
    assert {r.get("_SYSTEMD_UNIT") for r in records} == {"init.scope", "aitbc-x.service"}


def test_real_run_dedupes_overlapping_passes(monkeypatch):
    shared = _record("aitbc-x.service", message="[ERROR] e", priority=6)
    shared["__CURSOR"] = "s=c1"

    def fake_jctl(extra, since_minutes, limit):
        return [shared]  # both passes return the same entry

    monkeypatch.setattr(journal_mod, "_journalctl", fake_jctl)
    records = journal_mod._run_journalctl("warning", 60, 50, None)
    assert len(records) == 1


def _prom_result(pairs):
    return {
        "status": "success",
        "data": {"result": [{"metric": metric, "value": [1700000000, str(value)]} for metric, value in pairs]},
    }


def _fake_counts(*, errors=(), warnings=(), ages=()):
    async def fake(path, params=None):
        query = (params or {}).get("query", "")
        if "error_messages" in query:
            return _prom_result(errors)
        if "warning_messages" in query:
            return _prom_result(warnings)
        return _prom_result(ages)

    return fake


def test_journal_counts_aggregates_per_node(client, monkeypatch):
    monkeypatch.setattr(
        journal_mod,
        "_prometheus_get",
        _fake_counts(
            errors=[({"instance": "node1", "unit": "aitbc-x.service"}, 2)],
            warnings=[
                ({"instance": "node1", "unit": "aitbc-x.service"}, 5),
                ({"instance": "node1", "unit": "aitbc-y.service"}, 1),
                ({"instance": "hub", "unit": "aitbc-z.service"}, 1),
            ],
            ages=[({"instance": "node1"}, 20), ({"instance": "hub"}, 30)],
        ),
    )
    body = client.get("/api/journal/counts").json()
    assert body["prometheus_ok"] is True
    node1, hub = body["nodes"][0], body["nodes"][1]
    assert node1["instance"] == "node1"  # sorted errors-first
    assert (node1["errors"], node1["warnings"]) == (2, 6)
    assert node1["units"]["aitbc-x.service"] == {"errors": 2, "warnings": 5}
    assert node1["units"]["aitbc-y.service"] == {"errors": 0, "warnings": 1}
    assert node1["scan_age_seconds"] == 20.0
    assert node1["stale"] is False
    assert hub["instance"] == "hub" and hub["errors"] == 0 and hub["warnings"] == 1


def test_journal_counts_marks_stale_scan(client, monkeypatch):
    monkeypatch.setattr(journal_mod, "_prometheus_get", _fake_counts(ages=[({"instance": "node2"}, 900)]))
    node = client.get("/api/journal/counts").json()["nodes"][0]
    assert node["instance"] == "node2"
    assert node["stale"] is True
    assert node["scan_age_seconds"] == 900.0


def test_journal_counts_node_without_scan_is_stale(client, monkeypatch):
    monkeypatch.setattr(
        journal_mod,
        "_prometheus_get",
        _fake_counts(errors=[({"instance": "ghost", "unit": "aitbc-x.service"}, 1)]),
    )
    node = client.get("/api/journal/counts").json()["nodes"][0]
    assert node["instance"] == "ghost"
    assert node["stale"] is True
    assert node["scan_age_seconds"] is None


def test_journal_counts_prometheus_down(client, monkeypatch):
    async def down(path, params=None):
        return None

    monkeypatch.setattr(journal_mod, "_prometheus_get", down)
    body = client.get("/api/journal/counts").json()
    assert body["prometheus_ok"] is False
    assert body["nodes"] == []
