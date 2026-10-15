"""EVM JSON-RPC helpers shared by the Sepolia send commands.

``rpc_call`` is strict: an unreachable endpoint or an RPC error is a
nonzero exit carrying the reason — never a fabricated value. ``rpc_try``
is the display-only variant that returns ``None`` so an unsigned preview
can still render partial fields. ``broadcast_raw`` performs exactly one
``eth_sendRawTransaction``; a failure is reported, never retried.

Error text never carries the RPC URL or its key material: provider keys
sit in the URL path (Infura ``/v3/<key>``, Alchemy ``/v2/<key>``) or the
query string, and a raw echo would drop them into journals, CI logs and
pasted error reports. Messages show the masked display URL instead and
scrub path/query/userinfo out of any echoed exception text.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any
from urllib.parse import urlsplit

from .error_handling import abort


def display_rpc_url(rpc_url: str) -> str:
    """Scheme + host + port only — the parts of an RPC URL that never hold
    a provider key."""
    try:
        parts = urlsplit(rpc_url)
    except ValueError:
        return "<unparseable RPC URL>"
    if not parts.hostname:
        return "<unparseable RPC URL>"
    shown = f"{parts.scheme}://{parts.hostname}"
    if parts.port:
        shown += f":{parts.port}"
    return shown


def mask_rpc_url(text: str, rpc_url: str) -> str:
    """Scrub key-bearing URL parts out of ``text`` — the full URL, its
    path, its query, and any embedded credentials each become ``***``."""
    out = text.replace(rpc_url, display_rpc_url(rpc_url))
    try:
        parts = urlsplit(rpc_url)
    except ValueError:
        return out
    for secret in (parts.path, parts.query, parts.password, parts.username):
        if secret and len(secret) > 1:
            out = out.replace(secret, "***")
    return out


def _masked_exc(e: Exception, rpc_url: str) -> Exception:
    """``e`` re-thrown with its text scrubbed — ``abort`` puts
    ``str(from_exception)`` into the JSON error detail, so the raw httpx
    exception (which can echo the full URL) must never become the cause."""
    masked = mask_rpc_url(str(e), rpc_url)
    try:
        return type(e)(masked)
    except Exception:
        return RuntimeError(masked)


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
        abort(
            ctx,
            f"EVM RPC {method} failed at {display_rpc_url(rpc_url)}: {mask_rpc_url(str(e), rpc_url)}",
            from_exception=_masked_exc(e, rpc_url),
        )
        raise AssertionError("unreachable: abort always raises") from e
    if "error" in body:
        abort(ctx, f"EVM RPC {method} refused: {mask_rpc_url(str(body['error']), rpc_url)}")
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
        abort(
            ctx,
            f"{label} broadcast failed at {display_rpc_url(rpc_url)} (not retried): {mask_rpc_url(str(e), rpc_url)}",
            from_exception=_masked_exc(e, rpc_url),
        )
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
