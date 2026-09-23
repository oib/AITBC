"""Regression tests for the handler executor offload (W4).

Before the fix, async dispatch called synchronous do_* handlers directly on
the event-loop thread, so one blocking handler stalled every request. The
handlers now run on a bounded ThreadPoolExecutor.
"""

import asyncio
import threading
import time
from unittest.mock import patch

from starlette.requests import Request

from apps.exchange.simple_exchange import main as exchange_main
from apps.exchange.simple_exchange.main import FastAPIRequestAdapter, _dispatch


def _request(method: str = "GET", path: str = "/health", body: bytes = b"") -> Request:
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
    }
    return Request(scope, receive)


class TestExecutorOffload:
    def test_handler_runs_off_event_loop_thread(self):
        captured: dict[str, object] = {}

        def spy(self):
            captured["thread"] = threading.current_thread().name
            try:
                asyncio.get_running_loop()
                captured["on_loop"] = True
            except RuntimeError:
                captured["on_loop"] = False
            self._response_status = 200
            self.wfile.write(b'{"ok":true}')
            self._response_headers = [("Content-Type", "application/json")]

        async def run():
            with patch.object(FastAPIRequestAdapter, "do_GET", spy):
                return await _dispatch(_request("GET", "/health"), "GET")

        response = asyncio.run(run())
        assert response.status_code == 200
        assert captured["on_loop"] is False
        assert str(captured["thread"]).startswith("exchange-handler")

    def test_concurrent_dispatches_overlap(self):
        """Two slow handlers must overlap in wall time — serial execution on
        the loop would take ~2x as long."""
        barrier = threading.Barrier(2)

        def slow(self):
            barrier.wait(timeout=5)
            self._response_status = 200
            self.wfile.write(b'{"ok":true}')
            self._response_headers = [("Content-Type", "application/json")]

        async def run():
            with patch.object(FastAPIRequestAdapter, "do_GET", slow):
                start = time.monotonic()
                await asyncio.gather(
                    _dispatch(_request("GET", "/health"), "GET"),
                    _dispatch(_request("GET", "/health"), "GET"),
                )
                return time.monotonic() - start

        elapsed = asyncio.run(run())
        # Serial execution would deadlock the barrier and hit the 5s timeout.
        assert elapsed < 5

    def test_pool_is_bounded(self):
        assert exchange_main._HANDLER_POOL._max_workers >= 1
