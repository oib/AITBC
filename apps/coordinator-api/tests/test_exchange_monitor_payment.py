"""monitor_payment termination pins (#1602).

The background watcher must stop on ANY terminal status — previously only
a vanished row or a pending-payment expiry broke the loop, so a payment
confirmed by another path polled Redis every 30s forever.
"""

from __future__ import annotations

import time

import pytest

import coordinator_api.contexts.infrastructure.routers.exchange as exch_mod


class _FakeState:
    def __init__(self, payment):
        self.payment = payment
        self.set_payloads: list[dict] = []

    async def get_doc(self, ns: str, pid: str):
        return self.payment

    async def set_doc(self, ns: str, pid: str, payload, ttl: int | None = None) -> None:
        self.set_payloads.append(payload)

    async def get_doc(self, ns: str, key: str):
        return self.payment

    async def set_doc(self, ns: str, key: str, value: dict, ttl: int | None = None) -> None:
        self.set_payloads.append(value)
        self.payment = value

    async def docs(self, ns: str):
        return {"pay": self.payment} if self.payment is not None else {}


@pytest.mark.asyncio
async def test_confirmed_status_breaks_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _FakeState({"status": "confirmed", "expires_at": time.time() + 9999})
    monkeypatch.setattr(exch_mod, "_state", state)
    await exch_mod.monitor_payment("pay-1")
    assert state.set_payloads == []


@pytest.mark.asyncio
async def test_failed_status_breaks_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _FakeState({"status": "failed", "expires_at": time.time() + 9999})
    monkeypatch.setattr(exch_mod, "_state", state)
    await exch_mod.monitor_payment("pay-2")
    assert state.set_payloads == []


@pytest.mark.asyncio
async def test_missing_payment_breaks_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _FakeState(None)
    monkeypatch.setattr(exch_mod, "_state", state)
    await exch_mod.monitor_payment("pay-3")


@pytest.mark.asyncio
async def test_pending_expiry_marks_expired_and_breaks(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _FakeState({"status": "pending", "expires_at": time.time() - 1})
    monkeypatch.setattr(exch_mod, "_state", state)
    await exch_mod.monitor_payment("pay-4")
    assert state.set_payloads and state.set_payloads[0]["status"] == "expired"
