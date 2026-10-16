"""Chain-backed messaging client (MSG-15 Phase A).

The durable path: posts and replies are signed ``MESSAGE`` transactions
carrying an ``aitbc_msg`` envelope; reads go through the bounded
``/rpc/messaging/*`` index routes. Detection/wait logic is shared with the
CLI via ``aitbc.messaging_client`` — this module holds no copy of it.

Signing is **injected**: ``post`` takes the caller-named ``wallet`` plus a
``submit`` callable that signs and submits and returns the tx hash. The SDK
never picks a wallet, never sees key material, and never builds a payload
the predicate would reject (``build_envelope`` raises ``ValueError`` first).

There is no chain-messaging event stream reachable from an agent host —
``subscribe`` is cursor polling with a documented interval and a cap.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from typing import Any

from aitbc.messaging import build_envelope
from aitbc.messaging_client import fetch_message, parse_seen_cursor
from aitbc.messaging_client import (
    subscribe as _subscribe,
)
from aitbc.network import AITBCHTTPClient

from .errors import AITBCConnectionError, AITBCError

#: Submit callable: ``(wallet_name, envelope, fee_ait) -> tx_hash (str)``.
#: The canonical implementation on a node host is the CLI's
#: ``_send_transaction_impl``; tests pass a stub.
SubmitFn = Callable[[str, dict[str, Any], str], str]


class MessagingNotFoundError(AITBCError):
    """The index answered 404 — the message does not exist (yet)."""


def cli_submitter(*, password: str | None = None, rpc_url: str | None = None) -> SubmitFn:
    """The CLI-parity submitter: resolves the named wallet and signs in this
    process via ``aitbc_cli``'s wallet machinery. Use on a host that carries
    the checkout's wallet directory; nothing leaves the caller's process.
    """
    from decimal import Decimal

    from aitbc_cli.commands.transactions import _send_transaction_impl
    from aitbc_cli.utils.wallet_secret import resolve_wallet_password

    def _submit(wallet_name: str, envelope: dict[str, Any], fee_ait: str) -> str:
        from aitbc_cli.commands.messaging import _wallet_address

        password_v = password if password is not None else resolve_wallet_password(wallet_name=wallet_name)
        tx_hash = _send_transaction_impl(
            wallet_name,
            _wallet_address(None, wallet_name),
            Decimal(0),
            Decimal(fee_ait),
            password_v,
            rpc_url=rpc_url or "http://localhost:8202",
            tx_type="MESSAGE",
            payload={"aitbc_msg": envelope},
        )
        if not tx_hash:
            raise AITBCError("transaction submission returned no hash")
        return str(tx_hash)

    return _submit


def _resolve_wallet_address(wallet_name: str) -> str:
    """The named wallet file's address — raises ``AITBCError`` if the wallet
    cannot be found locally (pass ``agent_address`` explicitly then)."""
    try:
        from aitbc_cli.utils.wallet_paths import find_wallet_file_report, wallet_not_found_message
    except ImportError as e:
        raise AITBCError("cannot resolve a wallet address without aitbc_cli; pass agent_address explicitly") from e
    report = find_wallet_file_report(wallet_name)
    if report.path is None:
        raise AITBCError(wallet_not_found_message(report))
    import json

    data = json.loads(report.path.read_text())
    address = data.get("address") or data.get("agent_address")
    if not address:
        raise AITBCError(f"Wallet '{wallet_name}' carries no address field")
    return str(address)


class MessagingClient:
    """Post/read/subscribe on the chain-backed messaging index."""

    def __init__(self, http: AITBCHTTPClient, rpc_base: str | None = None) -> None:
        self._http = http
        # subscribe/fetch go through plain GETs on the RPC base URL; the
        # AITBCHTTPClient is used for read() and show() so 404s stay typed.
        self._rpc_base = (rpc_base or getattr(http, "base_url", "") or "").rstrip("/")

    # -- writes ------------------------------------------------------------

    def post(
        self,
        topic: str,
        body: str,
        *,
        wallet: str,
        submit: SubmitFn,
        parent: str | None = None,
        agent_address: str | None = None,
        fee_ait: str = "1",
    ) -> dict[str, Any]:
        """Build, sign and submit a post/reply envelope.

        ``wallet`` is required and caller-named — never inferred. ``submit``
        performs signing+submission in the caller's process; pass
        ``cli_submitter(...)`` for the CLI-parity path. Returns
        ``{"tx_hash", "envelope"}``.
        """
        if not wallet:
            raise AITBCError("post requires an explicit wallet name — the helper never picks one")
        if submit is None:
            raise AITBCError("post requires a submit callable (see cli_submitter)")
        if agent_address is None:
            agent_address = _resolve_wallet_address(wallet)
        kind = "reply" if parent else "post"
        envelope = build_envelope(kind=kind, topic=topic, agent_address=agent_address, body=body, parent=parent)
        tx_hash = submit(wallet, envelope, fee_ait)
        return {"tx_hash": tx_hash, "envelope": envelope, "kind": kind, "topic": envelope["topic"]}

    def wait_indexed(self, tx_hash: str, *, timeout: float = 180.0, interval: float = 2.0) -> int | None:
        """Poll the messages route until ``tx_hash`` is indexed; returns the
        sealed block height or ``None`` on timeout. The generic
        ``/rpc/transaction/{hash}`` route 404s MESSAGE txs even sealed —
        never poll that one."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            data = fetch_message(self._rpc_base, tx_hash)
            if isinstance(data, dict) and data.get("block_height") is not None:
                return int(data["block_height"])
            time.sleep(interval)
        return None

    # -- reads -------------------------------------------------------------

    def read(self, topic: str | None = None, *, cursor: str | None = None, limit: int = 50) -> dict[str, Any]:
        """One page of forum messages (post/reply rows), newest-first."""
        params: dict[str, Any] = {"limit": limit}
        if topic is not None:
            params["topic"] = topic
        if cursor is not None:
            params["cursor"] = cursor
        try:
            return self._http.get("/rpc/messaging/messages", params=params)
        except Exception as e:
            raise AITBCConnectionError(str(e)) from e

    def show(self, tx_hash: str) -> dict[str, Any]:
        """One message by hash; raises ``MessagingNotFoundError`` on 404 and
        ``AITBCConnectionError`` on transport failure — kept distinct."""
        want = tx_hash.lower().removeprefix("0x")
        try:
            return self._http.get(f"/rpc/messaging/messages/0x{want}")
        except AITBCError:
            raise
        except Exception as e:
            if "404" in str(e) or "not found" in str(e).lower():
                raise MessagingNotFoundError(f"message {tx_hash}") from e
            raise AITBCConnectionError(str(e)) from e

    def subscribe(
        self,
        topic: str,
        *,
        from_cursor: str | None = None,
        interval: float = 5.0,
        max_polls: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield new ``topic`` messages via cursor polling.

        ``from_cursor`` resumes after a ``<height>:<tx_hash>`` marker; the
        default starts at the current head (no backlog). Poll interval and
        ``max_polls`` are caller-chosen — this can run forever, so bound it
        in the caller.
        """
        if parse_seen_cursor(from_cursor or "") is None and from_cursor:
            raise AITBCError(f"from_cursor {from_cursor!r} is not a '<height>:<tx_hash>' cursor")
        yield from _subscribe(self._rpc_base, topic, from_cursor=from_cursor, interval=interval, max_polls=max_polls)
