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
                _record("aitbc-x.service", "older"),
                _record("aitbc-y.service", "newer"),
            ]
        ),
    )
    monkeypatch.setattr(journal_mod, "_journald_reachable", lambda: True)
    body = client.get("/api/journal/recent").json()
    assert [e["message"] for e in body["entries"]] == ["newer", "older"]
    entry = body["entries"][0]
    assert entry["unit"] == "aitbc-y.service"
    assert entry["priority_name"] == "err"
    assert entry["timestamp_unix"] == 1_700_000_000
    assert entry["timestamp"] == "2023-11-14T22:13:20+00:00"


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


def test_priority_must_be_known(client):
    assert client.get("/api/journal/recent?priority=loud").status_code == 400
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
