from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..config import settings
from ..gossip import gossip_broker
from ..lease_tracker import lease_tracker
from ..logger import get_logger

router = APIRouter(prefix="", tags=["ws"])
logger = get_logger(__name__)

# Active WebSocket connections for subscription push
_active_subscribers: dict[str, WebSocket] = {}


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


@router.websocket("/subscribe/ws")
async def subscription_websocket(websocket: WebSocket) -> None:
    """WebSocket endpoint for follower nodes to subscribe to block pushes.

    Protocol:
    1. Client connects and sends subscription message: {"node_id": "...", "chain_id": "...", "transport": "websocket"}
    2. Server validates the subscriber has a valid lease
    3. Server subscribes to block topic and pushes new blocks to client
    4. Server sends ping every 20s, expects pong response
    """
    await websocket.accept()
    node_id: str | None = None
    subscription_task: asyncio.Task | None = None

    try:
        # Receive subscription message
        message = await websocket.receive_text()
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            await websocket.send_json({"error": "Invalid JSON"})
            await websocket.close(code=1008)
            return

        node_id = data.get("node_id")
        chain_id = data.get("chain_id", settings.chain_id)
        transport = data.get("transport", "websocket")

        if not node_id:
            await websocket.send_json({"error": "node_id is required"})
            await websocket.close(code=1008)
            return

        # Validate subscriber has valid lease
        try:
            expiry = await lease_tracker.get_lease_expiry(node_id)
            import time
            if expiry <= time.time():
                await websocket.send_json({"error": "No valid lease found. Register subscription first via POST /rpc/subscribe"})
                await websocket.close(code=1008)
                return
        except Exception as e:
            logger.error(f"Failed to validate lease for {node_id}: {e}")
            await websocket.send_json({"error": "Failed to validate lease"})
            await websocket.close(code=1011)
            return

        # Store connection
        _active_subscribers[node_id] = websocket
        logger.info(f"WebSocket subscriber connected: {node_id} (chain={chain_id}, transport={transport})")

        # Send confirmation
        await websocket.send_json({
            "status": "subscribed",
            "node_id": node_id,
            "chain_id": chain_id,
            "transport": transport
        })

        # Subscribe to block topic
        topic = f"blocks.{chain_id}"
        block_subscription = await gossip_broker.subscribe(topic)

        async def _send_blocks() -> None:
            """Send blocks to subscriber."""
            try:
                async for block_data in block_subscription:
                    if isinstance(block_data, str):
                        block_data = json.loads(block_data)
                    await websocket.send_json(block_data)
                    logger.debug(f"Sent block to {node_id}")
            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected for {node_id}")
            except Exception as e:
                logger.error(f"Error sending block to {node_id}: {e}")

        async def _heartbeat() -> None:
            """Send periodic pings to keep connection alive."""
            try:
                while True:
                    await asyncio.sleep(20)
                    await websocket.send_json({"type": "ping", "timestamp": time.time()})
            except WebSocketDisconnect:
                pass
            except Exception:
                pass

        # Run block sending and heartbeat concurrently
        from asyncio import create_task, wait
        block_task = create_task(_send_blocks())
        heartbeat_task = create_task(_heartbeat())

        done, pending = await wait([block_task, heartbeat_task], return_when=asyncio.FIRST_COMPLETED)

        # Cancel remaining tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    except WebSocketDisconnect:
        logger.info(f"WebSocket subscriber disconnected: {node_id}")
    except Exception as e:
        logger.error(f"WebSocket error for {node_id}: {e}")
    finally:
        # Clean up
        if node_id and node_id in _active_subscribers:
            del _active_subscribers[node_id]
        try:
            await websocket.close()
        except Exception:
            pass
        logger.info(f"WebSocket subscriber cleanup complete: {node_id}")
