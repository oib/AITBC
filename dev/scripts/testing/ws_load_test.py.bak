from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import List

import websockets

DEFAULT_WS_URL = "ws://127.0.0.1:8000/rpc/ws"
BLOCK_TOPIC = "/blocks"
TRANSACTION_TOPIC = "/transactions"


async def producer(ws_url: str, interval: float = 0.1, total: int = 100) -> None:
    async with websockets.connect(f"{ws_url}{BLOCK_TOPIC}") as websocket:
        for index in range(total):
            payload = {
                "height": index,
                "hash": f"0x{index:064x}",
                "parent_hash": f"0x{index-1:064x}",
                "timestamp": "2025-01-01T00:00:00Z",
                "tx_count": 0,
            }
            await websocket.send(json.dumps(payload))
            await asyncio.sleep(interval)


async def consumer(name: str, ws_url: str, path: str, duration: float = 5.0) -> None:
    async with websockets.connect(f"{ws_url}{path}") as websocket:
        end = asyncio.get_event_loop().time() + duration
        received = 0
        while asyncio.get_event_loop().time() < end:
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            received += 1
            if received % 10 == 0:
                print(f"[{name}] received {received} messages")
        print(f"[{name}] total received: {received}")


async def main() -> None:
    ws_url = DEFAULT_WS_URL
    consumers = [
        consumer("blocks-consumer", ws_url, BLOCK_TOPIC),
        consumer("tx-consumer", ws_url, TRANSACTION_TOPIC),
    ]
    await asyncio.gather(producer(ws_url), *consumers)


if __name__ == "__main__":
    asyncio.run(main())
