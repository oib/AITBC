"""AUDIT-EDGE pin: #2804 miner media DNS-rebinding TOCTOU."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import miner_job_execution as mje  # noqa: E402


def _fake_addrinfo(global_ip="93.184.216.34"):
    return [(2, 1, 6, "", (global_ip, 443))]


def test_resolve_media_target_returns_pinned_ip(monkeypatch):
    monkeypatch.setattr(mje.socket, "getaddrinfo", lambda *a, **k: _fake_addrinfo())
    parsed, ip = mje._resolve_media_target("https://media.example.com/file.mp3")
    assert ip == "93.184.216.34"
    assert parsed.hostname == "media.example.com"


def test_resolve_media_target_refuses_mixed_answers(monkeypatch):
    infos = _fake_addrinfo() + [(2, 1, 6, "", ("10.0.0.5", 443))]
    monkeypatch.setattr(mje.socket, "getaddrinfo", lambda *a, **k: infos)
    with pytest.raises(ValueError, match="non-public"):
        mje._resolve_media_target("https://sneaky.example.com/x")


def test_fetch_uses_pinned_ip_not_requests(monkeypatch, tmp_path):
    """The fetch must dial the validated IP — requests.get (which would
    re-resolve and honour proxy env) must never be reached."""
    monkeypatch.setattr(mje.socket, "getaddrinfo", lambda *a, **k: _fake_addrinfo())
    monkeypatch.setattr(
        mje.requests,
        "get",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("requests.get reached")),
    )
    opened = {}

    class _Resp:
        status = 200

        def getheader(self, name):
            return None

        def read(self, n):
            return b""

    class _Conn:
        def getresponse(self):
            return _Resp()

        def close(self):
            pass

    def _fake_open(parsed, ip):
        opened["ip"] = ip
        return _Conn()

    monkeypatch.setattr(mje, "_open_pinned", _fake_open)
    dest = tmp_path / "m.bin"
    mje._fetch_http_media("https://media.example.com:8443/v1/file.mp3?q=1", str(dest), 1024, 1e12)
    assert opened["ip"] == "93.184.216.34"


def test_open_pinned_sends_original_authority(monkeypatch):
    """_open_pinned must dial the IP but send Host/path for the original URL."""
    import urllib.parse

    recorded = {}

    class _FakeConn:
        def __init__(self, *a, **k):
            recorded["args"] = a

        def request(self, method, path, headers=None):
            recorded.update(method=method, path=path, headers=headers)

        def getresponse(self):
            raise RuntimeError("stop")

        def close(self):
            pass

    monkeypatch.setattr(mje, "_PinnedHTTPSConnection", _FakeConn)
    monkeypatch.setattr(mje.http.client, "HTTPConnection", _FakeConn)
    parsed = urllib.parse.urlparse("https://media.example.com:8443/v1/file.mp3?q=1")
    mje._open_pinned(parsed, "93.184.216.34")
    assert recorded["method"] == "GET"
    assert recorded["path"] == "/v1/file.mp3?q=1"
    assert recorded["headers"]["Host"] == "media.example.com:8443"
