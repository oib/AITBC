#!/usr/bin/env python3
"""Asynchronous load harness for blockchain-node WebSocket + gossip pipeline."""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import httpx
import websockets


@dataclass
class PublishStats:
    sent: int = 0
    failed: int = 0
    latencies: List[float] = field(default_factory=list)

    @property
    def average_latency_ms(self) -> Optional[float]:
        if not self.latencies:
            return None
        return (sum(self.latencies) / len(self.latencies)) * 1000.0

    @property
    def p95_latency_ms(self) -> Optional[float]:
        if not self.latencies:
            return None
        sorted_latencies = sorted(self.latencies)
        index = int(len(sorted_latencies) * 0.95)
        index = min(index, len(sorted_latencies) - 1)
        return sorted_latencies[index] * 1000.0


@dataclass
class SubscriptionStats:
    messages: int = 0
    disconnects: int = 0


async def _publish_transactions(
    base_url: str,
    stats: PublishStats,
    stop_event: asyncio.Event,
    rate_hz: float,
    job_id: str,
    client_id: str,
    timeout: float,
) -> None:
    interval = 1 / rate_hz if rate_hz > 0 else 0
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
        while not stop_event.is_set():
            payload = {
                "type": "TRANSFER",
                "sender": f"miner-{client_id}",
                "nonce": stats.sent,
                "fee": 1,
                "payload": {
                    "job_id": job_id,
                    "amount": random.randint(1, 10),
                    "timestamp": time.time_ns(),
                },
            }
            started = time.perf_counter()
            try:
                response = await client.post("/rpc/sendTx", json=payload)
                response.raise_for_status()
            except httpx.HTTPError:
                stats.failed += 1
            else:
                stats.sent += 1
                stats.latencies.append(time.perf_counter() - started)

            if interval:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=interval)
                except asyncio.TimeoutError:
                    continue
            else:
                await asyncio.sleep(0)


async def _subscription_worker(
    websocket_url: str,
    stats: SubscriptionStats,
    stop_event: asyncio.Event,
    client_name: str,
) -> None:
    while not stop_event.is_set():
        try:
            async with websockets.connect(websocket_url) as ws:
                while not stop_event.is_set():
                    try:
                        message = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue
                    except websockets.ConnectionClosed:
                        stats.disconnects += 1
                        break
                    else:
                        _ = message  # lightweight backpressure test only
                        stats.messages += 1
        except OSError:
            stats.disconnects += 1
            await asyncio.sleep(0.5)


async def run_load(args: argparse.Namespace) -> None:
    stop_event = asyncio.Event()

    publish_stats: List[PublishStats] = [PublishStats() for _ in range(args.publishers)]
    subscription_stats: Dict[str, SubscriptionStats] = {
        "blocks": SubscriptionStats(),
        "transactions": SubscriptionStats(),
    }

    publisher_tasks = [
        asyncio.create_task(
            _publish_transactions(
                base_url=args.http_base,
                stats=publish_stats[i],
                stop_event=stop_event,
                rate_hz=args.publish_rate,
                job_id=f"load-test-job-{i}",
                client_id=f"{i}",
                timeout=args.http_timeout,
            ),
            name=f"publisher-{i}",
        )
        for i in range(args.publishers)
    ]

    subscriber_tasks = [
        asyncio.create_task(
            _subscription_worker(
                websocket_url=f"{args.ws_base}/blocks",
                stats=subscription_stats["blocks"],
                stop_event=stop_event,
                client_name="blocks",
            ),
            name="subscriber-blocks",
        ),
        asyncio.create_task(
            _subscription_worker(
                websocket_url=f"{args.ws_base}/transactions",
                stats=subscription_stats["transactions"],
                stop_event=stop_event,
                client_name="transactions",
            ),
            name="subscriber-transactions",
        ),
    ]

    all_tasks = publisher_tasks + subscriber_tasks

    try:
        await asyncio.wait_for(stop_event.wait(), timeout=args.duration)
    except asyncio.TimeoutError:
        pass
    finally:
        stop_event.set()
        await asyncio.gather(*all_tasks, return_exceptions=True)

    _print_summary(publish_stats, subscription_stats)


def _print_summary(publish_stats: List[PublishStats], subscription_stats: Dict[str, SubscriptionStats]) -> None:
    total_sent = sum(s.sent for s in publish_stats)
    total_failed = sum(s.failed for s in publish_stats)
    all_latencies = [lat for s in publish_stats for lat in s.latencies]

    summary = {
        "publish": {
            "total_sent": total_sent,
            "total_failed": total_failed,
            "average_latency_ms": (sum(all_latencies) / len(all_latencies) * 1000.0) if all_latencies else None,
            "p95_latency_ms": _p95(all_latencies),
        },
        "subscriptions": {
            name: {
                "messages": stats.messages,
                "disconnects": stats.disconnects,
            }
            for name, stats in subscription_stats.items()
        },
    }
    print(json.dumps(summary, indent=2))


def _p95(latencies: List[float]) -> Optional[float]:
    if not latencies:
        return None
    sorted_latencies = sorted(latencies)
    index = int(len(sorted_latencies) * 0.95)
    index = min(index, len(sorted_latencies) - 1)
    return sorted_latencies[index] * 1000.0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AITBC blockchain-node WebSocket load harness")
    parser.add_argument("--http-base", default="http://127.0.0.1:8080", help="Base URL for REST API")
    parser.add_argument("--ws-base", default="ws://127.0.0.1:8080/rpc/ws", help="Base URL for WebSocket API")
    parser.add_argument("--duration", type=float, default=30.0, help="Duration in seconds")
    parser.add_argument("--publishers", type=int, default=4, help="Concurrent transaction publishers")
    parser.add_argument("--publish-rate", type=float, default=5.0, help="Transactions per second per publisher")
    parser.add_argument("--http-timeout", type=float, default=5.0, help="HTTP client timeout in seconds")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    try:
        asyncio.run(run_load(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
