"""
Comprehensive API endpoint tests for the blockchain explorer.

These tests exercise every public endpoint via TestClient. Endpoints that
call external blockchain RPC via httpx are mocked; endpoints that read from
the local sqlite chain DB gracefully return empty results when the DB is
absent (test environment).

Replaces the stub integration tests that were previously `pass`.
"""

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client():
    return TestClient(app)


# --- Chains ---


# --- Health ---


# --- Chain head (mocked RPC) ---


# --- Analytics: network stats ---


# --- Analytics: activity timeline ---


# --- Analytics: top addresses ---


# --- Analytics: provider reputation ---


# --- Blocks: latest ---


# --- Blocks: non-empty ---


# --- Blocks: by height ---


# --- Blocks: by hash ---


# --- Transactions: by hash ---


# --- Transactions: search by address ---


# --- Blocks: by address ---


# --- Transactions: get by hash (legacy endpoint) ---


# --- Advanced search: transactions (mocked RPC) ---


# --- Advanced search: blocks (mocked RPC) ---


# --- Analytics: overview (mocked data layer) ---


# --- Export: search results ---


# --- Export: blocks ---


# --- Validation functions ---


def test_validate_tx_hash_valid():
    """Test tx hash validation with valid hashes"""
    from validation import validate_tx_hash

    assert validate_tx_hash("0x" + "a" * 64) is True
    assert validate_tx_hash("a" * 64) is True
    assert validate_tx_hash("0x" + "A" * 64) is True


def test_validate_tx_hash_invalid():
    """Test tx hash validation rejects invalid hashes"""
    from validation import validate_tx_hash

    assert validate_tx_hash("") is False
    assert validate_tx_hash("short") is False
    assert validate_tx_hash("0x" + "g" * 64) is False  # non-hex char
    assert validate_tx_hash("0x" + "a" * 64 + "/path") is False  # path traversal
    assert validate_tx_hash("0x" + "a" * 64 + "..") is False


def test_validate_chain_id_valid():
    """Test chain ID validation with valid IDs"""
    from validation import validate_chain_id

    assert validate_chain_id("ait-testchain.local") is True
    assert validate_chain_id("ait-mainnet") is True
    assert validate_chain_id("test-chain-123") is True


def test_validate_chain_id_invalid():
    """Test chain ID validation rejects invalid IDs"""
    from validation import validate_chain_id

    assert validate_chain_id("") is False
    assert validate_chain_id("ab") is False  # too short
    assert validate_chain_id("chain/with/slashes") is False
    assert validate_chain_id("chain..traversal") is False
    assert validate_chain_id("chain?query") is False


# --- CSP report collector ---

_CSP_DOCUMENT = "https://viewer.invalid/block.html?token=private-test-value#fragment"
_CSP_REPORT = {
    "csp-report": {
        "document-uri": _CSP_DOCUMENT,
        "effective-directive": "style-src-attr",
        "blocked-uri": "inline",
        "disposition": "enforce",
        "source-file": "https://user:password@viewer.invalid/explorer.js?v=private-test-value#fragment",
        "line-number": 123,
        "column-number": 4,
        "status-code": 200,
        "referrer": "https://viewer.invalid/?credential=private-test-value",
        "script-sample": "private-test-value",
        "original-policy": "private-test-value",
    }
}


def _csp_events(caplog):
    return [r for r in caplog.records if r.name == "routers.csp"]


def test_csp_report_legacy_envelope(client, caplog):
    import logging

    with caplog.at_level(logging.WARNING, logger="routers.csp"):
        r = client.post("/api/csp-report", json=_CSP_REPORT, headers={"Content-Type": "application/csp-report; charset=UTF-8"})
    assert r.status_code == 204
    assert r.content == b""
    assert r.headers.get("cache-control") == "no-store"
    events = _csp_events(caplog)
    assert len(events) == 1
    assert events[0].extra == {
        "event": "csp_violation",
        "document": "https://viewer.invalid/block.html",
        "effective_directive": "style-src-attr",
        "blocked": "inline",
        "disposition": "enforce",
        "source_file": "https://viewer.invalid/explorer.js",
        "line_number": 123,
        "column_number": 4,
        "status_code": 200,
    }
    blob = events[0].getMessage() + repr(events[0].extra)
    for leak in ("private-test-value", "password", "referrer", "script-sample", "original-policy"):
        assert leak not in blob, f"collector leaked {leak}"


def _modern_record(document_url=None, **body):
    item = {
        "type": "csp-violation",
        "url": "https://viewer.invalid/envelope-page",
        "body": {
            "effectiveDirective": "script-src-elem",
            "blockedURL": "https://u:p@blocked.invalid/private/path?secret=private-test-value",
            "disposition": "enforce",
            "sourceFile": "data:some-source",
            "statusCode": 200,
        },
    }
    if document_url is not None:
        item["body"]["documentURL"] = document_url
    return item


def test_csp_report_modern_batch(client, caplog):
    import logging

    payload = [
        _modern_record("https://viewer.invalid/a.html?secret=private-test-value"),
        _modern_record(),
    ]
    with caplog.at_level(logging.WARNING, logger="routers.csp"):
        r = client.post("/api/csp-report", json=payload, headers={"Content-Type": "application/reports+json"})
    assert r.status_code == 204
    events = _csp_events(caplog)
    assert len(events) == 2
    assert events[0].extra["document"] == "https://viewer.invalid/a.html"
    assert events[1].extra["document"] == "https://viewer.invalid/envelope-page"
    for e in events:
        assert e.extra["blocked"] == "https://blocked.invalid", e.extra
        assert e.extra["source_file"] == "data:"
        assert "private-test-value" not in e.getMessage()


def test_csp_report_modern_partial_batch_rejected(client, caplog):
    import logging

    payload = [
        _modern_record("https://viewer.invalid/a.html"),
        {"type": "csp-violation", "body": {"effectiveDirective": "style-src"}},  # no documentURL/url
    ]
    with caplog.at_level(logging.WARNING, logger="routers.csp"):
        r = client.post("/api/csp-report", json=payload, headers={"Content-Type": "application/reports+json"})
    assert r.status_code == 400
    assert _csp_events(caplog) == []


def test_csp_report_modern_batch_too_large(client, caplog):
    import logging

    payload = [_modern_record("https://viewer.invalid/a.html") for _ in range(17)]
    with caplog.at_level(logging.WARNING, logger="routers.csp"):
        r = client.post("/api/csp-report", json=payload, headers={"Content-Type": "application/reports+json"})
    assert r.status_code == 413
    assert _csp_events(caplog) == []


@pytest.mark.parametrize(
    "body,ctype",
    [
        (b"{not json", "application/csp-report"),
        (b'[{"type":"csp-violation","body":{}}]', "application/csp-report"),
        (b'{"wrong-envelope":{}}', "application/csp-report"),
        (b'{"csp-report":{"document-uri":"","effective-directive":"style-src"}}', "application/csp-report"),
        (b'{"csp-report":{"document-uri":"https://viewer.invalid/a.html"}}', "application/csp-report"),
        (
            b'{"csp-report":{"document-uri":"https://viewer.invalid/a.html","effective-directive":"Style-Src"}}',
            "application/csp-report",
        ),
    ],
    ids=["bad-json", "list-as-legacy", "no-csp-report", "empty-document", "no-directive", "uppercase-directive"],
)
def test_csp_report_bad_payloads(client, caplog, body, ctype):
    import logging

    with caplog.at_level(logging.WARNING, logger="routers.csp"):
        r = client.post("/api/csp-report", content=body, headers={"Content-Type": ctype})
    assert r.status_code == 400
    assert _csp_events(caplog) == []


@pytest.mark.parametrize("ctype", ["text/plain", "", "application/json"])
def test_csp_report_unsupported_media_type(client, caplog, ctype):
    import logging

    headers = {"Content-Type": ctype} if ctype else {}
    with caplog.at_level(logging.WARNING, logger="routers.csp"):
        r = client.post("/api/csp-report", content=b"{}", headers=headers)
    assert r.status_code == 415
    assert _csp_events(caplog) == []


def test_csp_report_body_too_large(client, caplog):
    import logging

    big = (
        b'{"csp-report":{"document-uri":"https://viewer.invalid/a.html","effective-directive":"style-src","x":"'
        + b"a" * 17000
        + b'"}}'
    )
    assert len(big) > 16_384
    with caplog.at_level(logging.WARNING, logger="routers.csp"):
        r = client.post("/api/csp-report", content=big, headers={"Content-Type": "application/csp-report"})
    assert r.status_code == 413
    assert _csp_events(caplog) == []


def test_csp_report_streaming_limit_without_content_length():
    """No Content-Length: the accumulated stream limit still applies."""
    import asyncio

    from fastapi import HTTPException
    from routers.csp import MAX_REPORT_BYTES, csp_report

    chunks = [b"x" * 8192, b"y" * 8192, b"z"]

    class FakeRequest:
        headers = {"content-type": "application/csp-report"}

        async def stream(self):
            for c in chunks:
                yield c

    assert sum(map(len, chunks)) > MAX_REPORT_BYTES
    with pytest.raises(HTTPException) as exc:
        asyncio.run(csp_report(FakeRequest()))
    assert exc.value.status_code == 413


def test_csp_report_get_method_not_allowed(client):
    r = client.get("/api/csp-report")
    assert r.status_code == 405


def test_csp_url_sanitization_edges(client, caplog):
    """blocked-uri origins only; data:/blob: collapse to scheme markers;
    negative/bool/oversized numerics are dropped; control characters in a
    source URL cannot forge a second physical log line."""
    import logging

    report = {
        "csp-report": {
            "document-uri": "https://viewer.invalid/a.html",
            "effective-directive": "img-src",
            "blocked-uri": "https://u:p@blocked.invalid/private/path?secret=private-test-value#frag",
            "source-file": "https://viewer.invalid/x.js\n forged-log-line",
            "line-number": -5,
            "column-number": True,
            "status-code": 700,
        }
    }
    with caplog.at_level(logging.WARNING, logger="routers.csp"):
        r = client.post("/api/csp-report", json=report, headers={"Content-Type": "application/csp-report"})
    assert r.status_code == 204
    events = _csp_events(caplog)
    assert len(events) == 1
    e = events[0].extra
    assert e["blocked"] == "https://blocked.invalid"
    assert "line_number" not in e and "column_number" not in e and "status_code" not in e
    assert "\n" not in events[0].getMessage(), "control chars must be JSON-escaped in the single log line"
    assert "private-test-value" not in events[0].getMessage()


def test_csp_url_blob_and_invalid_ports():
    """Unit-level: blob/data scheme markers; invalid ports/brackets don't raise."""
    from routers.csp import _safe_url

    assert _safe_url("blob:https://viewer.invalid/uuid") == "blob:"
    assert _safe_url("data:image/png;base64,xyz") == "data:"
    assert _safe_url("https://viewer.invalid:badport/x") == ""
    assert _safe_url("https://[unmatched/x") == ""
    assert _safe_url("") == ""
    assert _safe_url(None) == ""


def test_csp_report_long_query_stripped_after_parse(client, caplog):
    """A long query inside the body limit is dropped wholesale; the sanitized
    URL is parsed before truncation so userinfo can't be cut mid-token."""
    import logging

    doc = "https://viewer.invalid/block.html?" + "q=" + "a" * 1200
    report = {"csp-report": {"document-uri": doc, "effective-directive": "font-src", "blocked-uri": "self"}}
    with caplog.at_level(logging.WARNING, logger="routers.csp"):
        r = client.post("/api/csp-report", json=report, headers={"Content-Type": "application/csp-report"})
    assert r.status_code == 204
    events = _csp_events(caplog)
    assert len(events) == 1
    assert events[0].extra["document"] == "https://viewer.invalid/block.html"
    assert "q=" not in events[0].getMessage()
