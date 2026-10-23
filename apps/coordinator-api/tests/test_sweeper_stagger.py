"""Coordinator respawn-burst mitigation tests (B2, note 1493).

Two changes under test:

* ``_maybe_start_sweeper`` / ``_sweeper_after_delay`` — every sweeper loop
  sleeps ``interval_seconds`` before its first sweep, so all eight tasks
  began their countdown at the same instant on every respawn and stayed
  aligned forever. A fixed per-sweeper i×stagger offset (env
  ``COORDINATOR_SWEEPER_STAGGER_SECONDS``, default 10 s) desynchronizes
  same-period loops and defers the constructor past the delay.
* ``storage.db.get_async_engine`` — the secondary async engine on sqlite
  now pools 2+3 connections instead of the configured 10+20; aiosqlite
  serializes writers regardless.
"""

from __future__ import annotations

import pytest

from coordinator_api import main as cmain
from coordinator_api.storage import db as storage_db


class _TaskManagerSpy:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    async def start_task(self, name, coro, *args, **kwargs) -> None:
        self.calls.append((name, (coro,) + args, kwargs))


class _FakeSweeper:
    constructed = 0
    ran = 0

    def __init__(self) -> None:
        type(self).constructed += 1

    async def run_forever(self) -> None:
        type(self).ran += 1


@pytest.fixture(autouse=True)
def _reset_counters():
    _FakeSweeper.constructed = 0
    _FakeSweeper.ran = 0
    yield


def test_stagger_seconds_default_and_env(monkeypatch):
    monkeypatch.delenv("COORDINATOR_SWEEPER_STAGGER_SECONDS", raising=False)
    assert cmain._sweeper_stagger_seconds() == 10.0
    monkeypatch.setenv("COORDINATOR_SWEEPER_STAGGER_SECONDS", "2.5")
    assert cmain._sweeper_stagger_seconds() == 2.5
    monkeypatch.setenv("COORDINATOR_SWEEPER_STAGGER_SECONDS", "not-a-number")
    assert cmain._sweeper_stagger_seconds() == 10.0
    monkeypatch.setenv("COORDINATOR_SWEEPER_STAGGER_SECONDS", "-5")
    assert cmain._sweeper_stagger_seconds() == 0.0


@pytest.mark.asyncio
async def test_maybe_start_enabled_defers_via_delay(monkeypatch):
    monkeypatch.setenv("COORDINATOR_SWEEPER_STAGGER_SECONDS", "10")
    tm = _TaskManagerSpy()
    await cmain._maybe_start_sweeper(tm, "sw", lambda: True, _FakeSweeper, "on", "off", stagger_index=3)
    assert len(tm.calls) == 1
    name, args, _ = tm.calls[0]
    assert name == "sw"
    assert args[0] is cmain._sweeper_after_delay
    assert args[1] == 30.0  # stagger_index 3 × 10 s
    assert args[2] is _FakeSweeper
    # Not yet constructed — the delay wrapper runs first.
    assert _FakeSweeper.constructed == 0


@pytest.mark.asyncio
async def test_maybe_start_disabled_does_not_schedule(monkeypatch):
    tm = _TaskManagerSpy()
    await cmain._maybe_start_sweeper(tm, "sw", lambda: False, _FakeSweeper, "on", "off", stagger_index=2)
    assert tm.calls == []


@pytest.mark.asyncio
async def test_delay_zero_runs_immediately():
    await cmain._sweeper_after_delay(0, _FakeSweeper)
    assert _FakeSweeper.constructed == 1
    assert _FakeSweeper.ran == 1


@pytest.mark.asyncio
async def test_delay_sleeps_then_constructs(monkeypatch):
    import asyncio

    slept: list[float] = []

    async def fake_sleep(d):
        slept.append(d)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    await cmain._sweeper_after_delay(42.5, _FakeSweeper)
    assert slept == [42.5]
    assert _FakeSweeper.constructed == 1
    assert _FakeSweeper.ran == 1


@pytest.mark.asyncio
async def test_async_engine_sqlite_uses_small_pool(monkeypatch):
    """sqlite secondary pool is capped 2+3; other URLs keep settings."""
    captured: dict = {}

    def fake_create(url, **kw):
        captured.update(kw)
        return object()

    db_cfg = storage_db.settings.database
    monkeypatch.setattr(storage_db, "_async_engine", None)
    monkeypatch.setattr(storage_db, "create_async_engine", fake_create)
    monkeypatch.setattr(storage_db.settings, "db_pool_size", 10)
    monkeypatch.setattr(storage_db.settings, "db_max_overflow", 20)
    # effective_url is a read-only pydantic property — patch the class.
    monkeypatch.setattr(type(db_cfg), "effective_url", property(lambda self: "sqlite:////tmp/x.db"))
    await storage_db.get_async_engine()
    assert captured["pool_size"] == 2
    assert captured["max_overflow"] == 3

    storage_db._async_engine = None
    captured.clear()
    monkeypatch.setattr(type(db_cfg), "effective_url", property(lambda self: "postgresql://u:p@h/db"))
    await storage_db.get_async_engine()
    assert captured["pool_size"] == 10
    assert captured["max_overflow"] == 20
    storage_db._async_engine = None
