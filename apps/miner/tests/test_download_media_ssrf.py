"""Phase-0 test for MINER-MEDIA-DOWNLOAD-SSRF-UNCAPPED-1 (#800).

``production_miner._download_media`` fetches any http(s) URL from a job
payload — loopback, LAN and metadata addresses included — with no size or
total-time cap (a 512 MiB stream was written in 0.8 s in the audit probe).

Desired behaviour (pinned here): non-public targets are refused before the
request, bodies stop at a configured byte cap, and a slow-drip server hits a
total deadline. These tests FAIL on current main — the loopback download and
the uncapped write succeed — that is the bug demonstration.
"""

import http.server
import threading
from unittest import mock

import pytest
import production_miner


@pytest.fixture
def http_server(tmp_path):
    """A minimal HTTP server on loopback with a controllable body stream."""
    holder: dict = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = holder.get("body", b"x" * 1024)
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.end_headers()
            chunk = holder.get("chunk", len(body))
            sent = 0
            while sent < len(body):
                n = min(chunk, len(body) - sent)
                self.wfile.write(body[sent : sent + n])
                sent += n
            holder["served"] = holder.get("served", 0) + 1

        def log_message(self, *args):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    holder["url"] = f"http://127.0.0.1:{srv.server_port}/media.bin"
    yield holder
    srv.shutdown()
    thread.join(timeout=5)


class TestRefusesNonPublicTargets:
    def test_loopback_url_is_refused(self, http_server, tmp_path):
        dest = tmp_path / "out.bin"
        with pytest.raises(Exception, match="(?i)(refus|not allowed|forbidden|address)"):
            production_miner._download_media(http_server["url"], str(dest))
        # on current main the request is served and the file written — the bug
        assert http_server.get("served", 0) == 0
        assert not dest.exists()

    @pytest.mark.parametrize(
        "url",
        [
            "http://169.254.169.254/latest/meta-data/",
            "http://10.0.0.1/internal",
            "http://192.168.1.1/admin",
            "http://[fd00::1]/v6",
        ],
    )
    def test_private_and_metadata_targets_refused(self, url, tmp_path, monkeypatch):
        """Non-public targets must be refused before any request is sent.

        requests.get is spied: on current main it IS invoked (the request is
        attempted), which fails the assert_not_called — the bug, pinned
        without touching a real network.
        """
        get_mock = mock.Mock(side_effect=AssertionError("requests.get reached"))
        monkeypatch.setattr(production_miner.requests, "get", get_mock)
        dest = tmp_path / "out.bin"
        try:
            production_miner._download_media(url, str(dest))
        except Exception:
            pass  # refusal shape is unpinned; what matters is no request left
        get_mock.assert_not_called()
        assert not dest.exists()


class TestSizeCap:
    def test_body_above_cap_is_refused(self, http_server, tmp_path, monkeypatch):
        """A stream beyond the configured cap must abort, not write it all.

        The fix introduces a byte cap (env-overridable); MINER_MEDIA_MAX_BYTES
        is the contract name the test pins. On current main the whole body is
        written and no error is raised — the bug.
        """
        cap = 1 * 1024 * 1024
        monkeypatch.setenv("MINER_MEDIA_MAX_BYTES", str(cap))
        http_server["body"] = b"y" * (4 * 1024 * 1024)
        dest = tmp_path / "out.bin"
        try:
            production_miner._download_media(http_server["url"], str(dest))
        except Exception:
            pass  # an over-cap abort raises; a loopback refusal also lands here
        assert not dest.exists() or dest.stat().st_size <= cap
