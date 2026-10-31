"""#745 multi-worker audit regression tests — two-instance/cross-process shapes."""

from __future__ import annotations

import threading


from aitbc_chain.rpc import transactions as transactions_mod
from aitbc_chain.rpc import utils as rpc_utils


class TestAdminNonceConcurrentClaim:
    """#5: the sqlite nonce store is the shared authority across workers —
    a claimed nonce must admit exactly once no matter how many 'workers'
    race it (pre-hardening this could deadlock or double-admit)."""

    def test_concurrent_same_nonce_single_winner(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rpc_utils, "_nonce_db_path", lambda: tmp_path / "admin_nonces.db")
        results: list[bool] = []
        lock = threading.Lock()

        def claim() -> None:
            r = rpc_utils._nonce_seen("0xdeadbeef")
            with lock:
                results.append(r)

        threads = [threading.Thread(target=claim) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert results.count(False) == 1  # exactly one first-timer
        assert results.count(True) == 9


class TestImportAdvisoryLock:
    """#3: acquire/release is a no-op on non-postgresql dialects (sqlite
    serializes writers at the file level) and holds/releases on pg."""

    def test_sqlite_noop_acquire_release(self, tmp_path, monkeypatch):
        from sqlalchemy import create_engine
        from sqlmodel import Session

        engine = create_engine(f"sqlite:///{tmp_path / 'c.db'}")

        class _FakeScope:
            def __enter__(self):
                return Session(engine)

            def __exit__(self, *a):
                return None

        # session_scope is imported lazily inside acquire — patch its source
        from aitbc_chain import database as db_mod

        monkeypatch.setattr(db_mod, "session_scope", lambda chain_id: _FakeScope())
        held = rpc_utils.import_advisory_acquire("test-chain")
        assert held is None
        rpc_utils.import_advisory_release(held)  # no-op, no raise


class TestFanoutObservability:
    """#8a: the done-callback surfaces task exceptions instead of GC-swallowing."""

    def test_done_callback_logs_task_exception(self, caplog):
        import asyncio

        async def boom() -> None:
            raise RuntimeError("peer unreachable")

        loop = asyncio.new_event_loop()
        try:
            task = loop.create_task(boom())
            task.add_done_callback(transactions_mod._fanout_done)
            with caplog.at_level("WARNING"):
                loop.run_until_complete(asyncio.sleep(0))
            assert "tx fan-out task raised" in caplog.text or any("fan-out" in r.message for r in caplog.records)
        finally:
            loop.close()
