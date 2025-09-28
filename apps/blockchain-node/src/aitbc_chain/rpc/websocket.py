from __future__ import annotations

import asyncio
from typing import AsyncIterator, Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..gossip import gossip_broker

router = APIRouter(prefix="/ws", tags=["ws"])


async def _stream_topic(topic: str, websocket: WebSocket) -> None:
    subscription = await gossip_broker.subscribe(topic)
    try:
        while True:
            message = await subscription.get()
            await websocket.send_json(message)
    except WebSocketDisconnect:
        pass
    finally:
        subscription.close()


@router.websocket("/blocks")
async def blocks_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    await _stream_topic("blocks", websocket)


@router.websocket("/transactions")
async def transactions_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    await _stream_topic("transactions", websocket)
