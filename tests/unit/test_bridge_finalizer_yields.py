"""The bridge release finalizer must not run its pass on the event loop.

Regression cover for the RPC startup stall of 2026-09-23: a blockchain-rpc
restart left the unit ``active (running)`` with nothing listening on its port
for eighteen minutes.

``start_finalizer`` is created as a task during lifespan startup, and its body
called ``_finalizer_pass`` inline. Every phase of a pass is synchronous SQLModel
work, and the first pass after a restart is a backfill -- ``store_block_header``
commits one row per block the bridge header table is behind, measured at 0.75
headers/second. So the task never reached its first ``await``, uvicorn never
finished starting, and the socket was never bound until the backfill drained.

Both assertions below fail against the inline version.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading

from aitbc_chain.cross_chain.bridge_transfer import BridgeTransferMixin

CHAIN_ID = "test-chain"


class _Finalizer:
    """Minimal stand-in: ``start_finalizer`` only reads these two members."""

    start_finalizer = BridgeTransferMixin.start_finalizer

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()
        self.thread_ident: int | None = None
        self.returned = False

    def _known_chains(self) -> list[str]:
        return [CHAIN_ID]

    def _finalizer_pass(self, chain_id: str, relayer_enabled: bool) -> None:
        """Stands in for the synchronous sqlite backfill."""
        self.thread_ident = threading.get_ident()
        self.entered.set()
        self.release.wait(timeout=2.0)
        self.returned = True


async def test_finalizer_pass_does_not_run_on_the_event_loop() -> None:
    finalizer = _Finalizer()
    loop_thread = threading.get_ident()
    task = asyncio.create_task(finalizer.start_finalizer())
    try:
        for _ in range(200):
            if finalizer.entered.is_set():
                break
            await asyncio.sleep(0.01)
        assert finalizer.entered.is_set(), "the finalizer never started a pass"

        # Observed while the pass is still parked in release.wait(): control
        # came back to this coroutine mid-pass. Run inline, the loop could not
        # reach this line until the pass had already returned.
        assert not finalizer.returned, "the loop was blocked until the pass finished"
        assert finalizer.thread_ident != loop_thread, "the pass ran on the event loop thread"
    finally:
        finalizer.release.set()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
