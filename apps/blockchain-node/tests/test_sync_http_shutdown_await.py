"""#738-class regression: ``BlockchainNode._shutdown`` must await
``SyncManagerStatusServer.stop()`` — unawaited, the coroutine was dropped so
``should_exit`` was never set and ``serve()`` never returned: node shutdown
hung on the immediately following ``await self._sync_http_task``.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
import aitbc_chain.main as main_mod
from aitbc_chain.main import BlockchainNode


class _FakeServer:
    def __init__(self):
        self.stopped = False

    async def stop(self):
        self.stopped = True


class _FakeTaskRegistry:
    async def cancel_all(self, timeout=0.0):
        return None


class _FakeShutdown:
    async def shutdown(self):
        return None

    async def stop(self):
        return None


@pytest.mark.asyncio
async def test_shutdown_awaits_sync_http_stop(monkeypatch):
    server = _FakeServer()
    monkeypatch.setattr(main_mod, "gossip_broker", _FakeShutdown())
    monkeypatch.setattr(main_mod, "lease_tracker", _FakeShutdown())

    async def _serve():
        return None

    task = asyncio.create_task(_serve())
    node = SimpleNamespace(
        _sync_http_server=server,
        _sync_http_task=task,
        _sync_manager=None,
        _multi_chain_manager=None,
        _task_registry=_FakeTaskRegistry(),
        _settlement_coordinators=[],
        _proposers={},
    )
    await BlockchainNode._shutdown(node)
    await task
    assert server.stopped is True  # False pre-fix: stop() coroutine was discarded
