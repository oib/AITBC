#!/usr/bin/env python3
"""Scratch gossip filter for the bc-2 rehearsal harness (RESET-REHEARSAL-FAULTS-1).

Each configured port proxies one upstream ``/rpc/gossip/ws`` endpoint. The
mesh backend opens one websocket per (peer, topic), bound at connect time
by ``?topic=`` — so a denied topic is refused here without parsing a
single frame, producing the same connect failure a dead peer produces.

Every rule may name a ``trigger`` file: while it is absent the rule is
transparent — ALL topics are proxied — so the partition wiring (env
rewrites, node restarts) can settle without changing behaviour. The
instant the file appears, connections carrying a denied topic are closed
and new ones refused: the cut lands inside one poll interval (~0.25 s),
which is what lets the fork phase arm the partition exactly when the
victim's proposer slot opens. A rule without ``trigger`` is armed from
startup.

Non-websocket HTTP gets an error on every port: peers derive ``http://h:p``
from the mesh ``ws://h:p`` URL (``proposal_freshness``) and pull
``/rpc/head`` + ``/rpc/blocks`` through it, so one port covers the gossip
and the pull layers — the scratch equivalent of the retired partition
recipe's nginx-444 leg.

Loopback only, spec-driven, run as the transient ``bc2-gossip-filter``
unit. Never deployed anywhere but the rehearsal scratch root.

    spec = [{"port": 18600,
             "upstream": "ws://127.0.0.1:18402/rpc/gossip/ws",
             "deny_topics": ["blocks.bc-2"],
             "trigger": "/tmp/bc2-rehearsal/filter.trigger"}]
    gossip_filter.py <spec.json>
"""

from __future__ import annotations

import asyncio
import json
import sys
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


def topic_denied(topic: str | None, deny_topics: list[str]) -> bool:
    """Connect-time gate. A missing topic means a malformed upgrade —
    refuse it the same way the real endpoint does (websocket.py:104)."""
    return topic is None or topic in deny_topics


async def _pipe(src, dst) -> None:
    try:
        async for frame in src:
            await dst.send(frame)
    except Exception:
        pass
    finally:
        try:
            await dst.close()
        except Exception:
            pass


async def _handle(client, upstream: str, state: dict, live: dict) -> None:
    from websockets.asyncio.client import connect

    query = urlsplit(client.request.path).query
    topic = parse_qs(query).get("topic", [None])[0]
    if state["armed"] and topic_denied(topic, state["deny"]):
        await client.close(code=1008)
        return
    async with connect(f"{upstream}?{query}") as up:
        live[client] = topic
        try:
            left = asyncio.create_task(_pipe(client, up))
            right = asyncio.create_task(_pipe(up, client))
            _done, pending = await asyncio.wait({left, right}, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
        finally:
            live.pop(client, None)


async def _watch_trigger(trigger: Path, state: dict, live: dict) -> None:
    """One-way arm: once the trigger file exists, denied topics die —
    tracked live connections are closed and the connect gate starts
    refusing them. Arming is permanent for the life of the filter unit;
    recovery happens by env restore, not by disarming."""
    while not state["armed"]:
        if trigger.exists():
            state["armed"] = True
            for conn, topic in list(live.items()):
                if topic in state["deny"]:
                    try:
                        await conn.close(code=1008)
                    except Exception:
                        pass
            return
        await asyncio.sleep(0.25)


def _gate(state: dict):
    def process_request(connection, request):
        split = urlsplit(request.path)
        if split.path != "/rpc/gossip/ws":
            # The 444 leg: every non-gossip URL on this port is dead —
            # /rpc/head probes and /rpc/blocks pulls fail through it.
            return connection.respond(HTTPStatus.SERVICE_UNAVAILABLE, "filtered\n")
        if state["armed"]:
            topic = parse_qs(split.query).get("topic", [None])[0]
            if topic_denied(topic, state["deny"]):
                return connection.respond(HTTPStatus.SERVICE_UNAVAILABLE, "filtered\n")
        return None

    return process_request


async def _serve(spec_path: str) -> None:
    from websockets.asyncio.server import serve

    rules = json.loads(Path(spec_path).read_text())
    if not rules:
        raise SystemExit("empty filter spec")
    for rule in rules:
        upstream = rule["upstream"].rstrip("/")
        state = {"deny": list(rule.get("deny_topics") or []), "armed": False}
        live: dict = {}
        trigger = Path(rule["trigger"]) if rule.get("trigger") else None

        async def handler(client, upstream=upstream, state=state, live=live):
            try:
                await _handle(client, upstream, state, live)
            except Exception:
                # Upstream unreachable mid-stream or refused: drop the
                # client side too — an unreachable upstream is the fault
                # being simulated, not a filter bug.
                pass

        if trigger is None:
            state["armed"] = True
        else:
            asyncio.create_task(_watch_trigger(trigger, state, live))
        await serve(handler, "127.0.0.1", int(rule["port"]), process_request=_gate(state))
        print(f"filter :{rule['port']} -> {upstream} deny={state['deny']} trigger={trigger}", flush=True)
    await asyncio.Future()  # runs until systemd stops the unit


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: gossip_filter.py <spec.json>", file=sys.stderr)
        return 2
    try:
        asyncio.run(_serve(sys.argv[1]))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
