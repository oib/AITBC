"""Common router helpers and export error/format paths."""

import json
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from main import app
from routers.common import like_pattern, sanitize_csv_value


@pytest.fixture
def client():
    return TestClient(app)


def test_like_pattern_escapes_wildcards_and_pipe():
    assert like_pattern("a%b_c") == "%a|%b|_c%"
    assert like_pattern("x|y") == "%x||y%"


@pytest.mark.parametrize(
    "value,expected",
    [
        ("plain", "plain"),
        ("=1+1", "' =1+1"),
        ("-sum", "' -sum"),
        ("@import", "' @import"),
        ("\ttab", "' \ttab"),
        ("", ""),
    ],
)
def test_sanitize_csv_value_formula_prefix(value, expected):
    assert sanitize_csv_value(value) == expected


def test_export_search_rejects_empty_data(client):
    r = client.get("/api/export/search", params={"format": "csv", "data": ""})
    assert r.status_code == 400
    assert "No data" in r.json()["detail"]


def test_export_search_rejects_invalid_json(client):
    r = client.get("/api/export/search", params={"format": "csv", "data": "{not-json"})
    assert r.status_code == 400
    assert "valid JSON" in r.json()["detail"]


def test_export_search_rejects_non_object_list(client):
    r = client.get("/api/export/search", params={"format": "csv", "data": json.dumps([1, 2])})
    assert r.status_code == 400


def test_export_search_unsupported_format(client):
    data = quote(json.dumps([{"hash": "0x1"}]))
    r = client.get(f"/api/export/search?format=xml&type=transactions&data={data}")
    assert r.status_code == 400
    assert "Unsupported format" in r.json()["detail"]


def test_export_search_csv_neutralizes_formula_cells(client):
    row = {
        "hash": "=cmd|calc",
        "type": "transfer",
        "from": "+alias",
        "to": "0x2",
        "amount": "1",
        "fee": "0",
        "timestamp": "t",
    }
    data = quote(json.dumps([row]))
    r = client.get(f"/api/export/search?format=csv&type=transactions&data={data}")
    assert r.status_code == 200
    body = r.content.decode()
    assert "' =cmd|calc" in body
    assert "' +alias" in body


def test_export_blocks_csv_with_mocked_latest(client, monkeypatch):
    async def _fake_latest(limit):
        assert limit == 50
        return [{"height": 1, "hash": "=h", "validator": "v", "tx_count": 0, "timestamp": "ts"}]

    monkeypatch.setattr("routers.export.get_latest_blocks", _fake_latest)
    r = client.get("/api/export/blocks", params={"format": "csv"})
    assert r.status_code == 200
    assert "' =h" in r.content.decode()


def test_export_blocks_unsupported_format(client, monkeypatch):
    async def _empty(limit):
        return []

    monkeypatch.setattr("routers.export.get_latest_blocks", _empty)
    r = client.get("/api/export/blocks", params={"format": "xls"})
    assert r.status_code == 400
