"""GET /v1/transactions — SQL-level filters and pagination (#1362)."""

import asyncio
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession


def _seed():
    from trading_service.domain.trading import TradeRequest, TradeStatus, TradeType
    from trading_service.storage import engine

    suffix = uuid4().hex[:8]

    async def _run():
        async with AsyncSession(engine) as session:
            session.add(
                TradeRequest(
                    request_id=f"req-open-{suffix}",
                    buyer_agent_id="buyer-a",
                    trade_type=TradeType.AI_POWER,
                    title="open request",
                    status=TradeStatus.OPEN,
                )
            )
            session.add(
                TradeRequest(
                    request_id=f"req-done-{suffix}",
                    buyer_agent_id="buyer-b",
                    trade_type=TradeType.COMPUTE_RESOURCES,
                    title="done request",
                    status=TradeStatus.COMPLETED,
                )
            )
            await session.commit()

    asyncio.run(_run())
    return suffix


def _ids(payload):
    return {row.get("request_id") for row in payload if row.get("action") == "request"}


def test_status_filter_uses_sql(client):
    suffix = _seed()
    resp = client.get("/v1/transactions", params={"action": "request", "status": "open"})
    assert resp.status_code == 200
    ids = _ids(resp.json())
    assert f"req-open-{suffix}" in ids
    assert f"req-done-{suffix}" not in ids


def test_transaction_type_filter_applies(client):
    suffix = _seed()
    resp = client.get("/v1/transactions", params={"action": "request", "transaction_type": "ai_power"})
    assert resp.status_code == 200
    ids = _ids(resp.json())
    assert f"req-open-{suffix}" in ids
    assert f"req-done-{suffix}" not in ids


def test_invalid_filter_values_return_empty(client):
    _seed()
    resp = client.get("/v1/transactions", params={"action": "request", "status": "not-a-status"})
    assert resp.status_code == 200
    assert resp.json() == []


def test_limit_and_offset(client):
    _seed()
    resp = client.get("/v1/transactions", params={"action": "request", "limit": 1})
    assert resp.status_code == 200
    rows = [r for r in resp.json() if r.get("action") == "request"]
    assert len(rows) == 1
