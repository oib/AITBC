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
    except Exception:  # noqa: BLE001 - masked-exc reconstruction fallback
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
    except Exception:  # noqa: BLE001 - best-effort probe — any RPC failure returns None
        return None
    return body.get("result")


class _BroadcastRefused(RuntimeError):
    """The node answered with a JSON-RPC ``error`` — a definitive refusal,
    unlike a transport failure whose tx may still have landed."""


def _signed_tx_hash(raw: str) -> str | None:
    """keccak256 of the signed serialized transaction — the hash the node
    would return, computable locally so a timed-out broadcast can still be
    tracked. Advisory only: unparseable input returns None."""
    try:
        from eth_utils import keccak

        data = bytes.fromhex(str(raw).removeprefix("0x"))
        return "0x" + keccak(data).hex() if data else None
    except Exception:  # noqa: BLE001 - the advisory hash must never mask the real error
        return None


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
        # ``error`` is failure only when truthy — some clients answer
        # ``"error": null`` alongside a valid result (#2539).
        if body.get("error"):
            raise _BroadcastRefused(body["error"])
        result = body.get("result")
        if result is None:
            raise RuntimeError("empty result")
        return str(result)

    try:
        return asyncio.run(_post())
    except Exception as e:
        tx_hash = _signed_tx_hash(raw)
        tx_part = f" tx {tx_hash}" if tx_hash else ""
        # A JSON-RPC refusal is definitive; a transport failure may still
        # have landed — the signed tx hash lets the caller check first.
        hint = "" if isinstance(e, _BroadcastRefused) else " — it may still have landed; check the tx before retrying"
        abort(
            ctx,
            f"{label} broadcast failed{tx_part} at {display_rpc_url(rpc_url)} (not retried){hint}: "
            f"{mask_rpc_url(str(e), rpc_url)}",
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
