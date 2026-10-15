"""EVM JSON-RPC helpers shared by the Sepolia send commands.

``rpc_call`` is strict: an unreachable endpoint or an RPC error is a
nonzero exit carrying the reason — never a fabricated value. ``rpc_try``
is the display-only variant that returns ``None`` so an unsigned preview
can still render partial fields. ``broadcast_raw`` performs exactly one
``eth_sendRawTransaction``; a failure is reported, never retried.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from .error_handling import abort


def rpc_call(ctx, rpc_url: str, method: str, params: list[Any]) -> Any:
    """One synchronous JSON-RPC call — wrapped so tests substitute a fake."""
    import httpx

    try:
        resp = httpx.post(
            rpc_url,
            json={"jsonrpc": "2.0", "method": method, "params": params, "id": 1},
            timeout=15.0,
        )
        resp.raise_for_status()
        body = resp.json()
    except Exception as e:
        abort(ctx, f"EVM RPC {method} failed at {rpc_url}: {e}", from_exception=e)
        raise AssertionError("unreachable: abort always raises") from e
    if "error" in body:
        abort(ctx, f"EVM RPC {method} refused: {body['error']}")
    return body.get("result")


def rpc_try(ctx, rpc_url: str, method: str, params: list[Any]) -> Any:
    """Best-effort variant of ``rpc_call`` — returns None instead of aborting."""
    import httpx

    try:
        resp = httpx.post(
            rpc_url,
            json={"jsonrpc": "2.0", "method": method, "params": params, "id": 1},
            timeout=15.0,
        )
        resp.raise_for_status()
        body = resp.json()
    except Exception:
        return None
    return body.get("result")


def broadcast_raw(ctx, rpc_url: str, raw: str, label: str = "ETH transfer") -> str:
    """One eth_sendRawTransaction — a failure is reported, never retried."""

    async def _post() -> str:
        import httpx

        async with httpx.AsyncClient(timeout=15.0) as http:
            resp = await http.post(
                rpc_url,
                json={"jsonrpc": "2.0", "method": "eth_sendRawTransaction", "params": [raw], "id": 1},
            )
            resp.raise_for_status()
            body = resp.json()
        if "error" in body:
            raise RuntimeError(body["error"])
        return str(body["result"])

    try:
        return asyncio.run(_post())
    except Exception as e:
        abort(ctx, f"{label} broadcast failed (not retried): {e}", from_exception=e)
        raise AssertionError("unreachable: abort always raises") from e


def resolve_rpc_url(ctx, override: str | None, network: str = "Sepolia") -> str:
    """``--eth-rpc-url`` beats the ETH_RPC_URL env var and CLI config
    (which itself reads the node env files)."""
    from ..config import get_config

    rpc = override or os.getenv("ETH_RPC_URL") or getattr(get_config(), "eth_rpc_url", None)
    if not rpc:
        abort(ctx, f"{network} RPC unresolved — pass --eth-rpc-url or set ETH_RPC_URL")
    return str(rpc)


def hex_to_int(ctx, value: Any, what: str) -> int:
    """Parse a 0x-prefixed RPC quantity; malformed values abort honestly."""
    try:
        return int(value, 16) if isinstance(value, str) else int(value)
    except (TypeError, ValueError) as e:
        abort(ctx, f"unusable {what} from the EVM RPC: {value!r}")
        raise AssertionError("unreachable: abort always raises") from e
