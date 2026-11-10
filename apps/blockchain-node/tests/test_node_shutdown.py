"""#1705: SIGTERM/SIGINT reach the node's normal shutdown path, and
``_shutdown`` disposes the per-chain DB engines (which also re-encrypts a
db_encryption_enabled chain.db).
"""

from __future__ import annotations

import asyncio
import os
import signal

import pytest

from aitbc_chain import main as main_mod
from aitbc_chain.main import BlockchainNode


def _install_signal_handlers(node: BlockchainNode) -> None:
    main_mod._install_stop_signal_handlers(node)


@pytest.mark.asyncio
async def test_sigterm_sets_stop_event() -> None:
    """A SIGTERM delivered to the process trips the stop event instead of
    killing it mid-flight — systemd's stop signal now reaches _shutdown."""
    node = BlockchainNode()
    loop = asyncio.get_running_loop()
    _install_signal_handlers(node)
    try:
        os.kill(os.getpid(), signal.SIGTERM)
        await asyncio.wait_for(node._stop_event.wait(), timeout=5.0)
        assert node._stop_event.is_set()
    finally:
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(sig)


@pytest.mark.asyncio
async def test_shutdown_disposes_chain_dbs(monkeypatch: pytest.MonkeyPatch) -> None:
    """_shutdown calls shutdown_db for every supported chain, tolerating
    per-chain failures."""
    node = BlockchainNode()
    node._supported_chains = lambda: ["chain-a", "chain-b"]  # type: ignore[method-assign]

    disposed: list[str] = []

    def _fake_shutdown_db(chain_id: str = "") -> None:
        if chain_id == "chain-a":
            raise RuntimeError("dispose failed")
        disposed.append(chain_id)

    class _Broker:
        async def shutdown(self) -> None:
            return None

    class _Lease:
        async def stop(self) -> None:
            return None

    monkeypatch.setattr(main_mod, "shutdown_db", _fake_shutdown_db)
    monkeypatch.setattr(main_mod, "gossip_broker", _Broker())
    monkeypatch.setattr(main_mod, "lease_tracker", _Lease())
    await node._shutdown()
    # chain-a's failure is logged, not fatal; chain-b still disposed.
    assert disposed == ["chain-b"]
