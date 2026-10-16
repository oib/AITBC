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

from aitbc.dm_client import (
    dm_max_plaintext_bytes,
    dm_store_load,
    dm_store_save,
    fetch_dm_inbox,
    fetch_dm_key,
    generate_key_era,
    open_dm,
    seal_dm,
)
from aitbc.messaging import DM_TOPIC, build_envelope
from aitbc.messaging_client import UNREACHABLE, fetch_message, parse_seen_cursor
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


def _resolve_dm_key_path(wallet_name: str):
    """The wallet's ``dm-keys/<name>.json`` store path (same layout the CLI
    uses), or ``AITBCError`` when the wallet file cannot be found locally."""
    from pathlib import Path

    from aitbc.dm_client import dm_keys_dir

    try:
        from aitbc_cli.utils.wallet_paths import find_wallet_file_report, wallet_not_found_message
    except ImportError as e:
        raise AITBCError("cannot locate the dm-keys store without aitbc_cli; pass keys_path explicitly") from e
    report = find_wallet_file_report(wallet_name)
    if report.path is None:
        raise AITBCError(wallet_not_found_message(report))
    return dm_keys_dir(Path(report.path)) / f"{wallet_name}.json"


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

    # -- direct messages (MSG-8/MSG-15 Phase B) ------------------------------
    # Client-side SealedBox: plaintext and secret keys never leave this
    # process. Metadata (sender, recipient, size, time) is public by design.

    def dm_key_for(self, address: str) -> dict[str, Any]:
        """The recipient's published DM key; ``MessagingNotFoundError`` when
        they never published one, ``AITBCConnectionError`` on transport
        failure — kept distinct."""
        data = fetch_dm_key(self._rpc_base, address)
        if data is UNREACHABLE:
            raise AITBCConnectionError(f"RPC unreachable at {self._rpc_base}")
        if not isinstance(data, dict) or not data.get("enc_pubkey"):
            raise MessagingNotFoundError(f"no published dm_key for {address}")
        return dict(data)

    def dm_inbox(self, address: str, *, limit: int = 50, cursor: str | None = None) -> dict[str, Any]:
        """One page of ``address``'s DM inbox — ciphertext rows only,
        nothing decrypted."""
        data = fetch_dm_inbox(self._rpc_base, address, limit=limit, cursor=cursor)
        if data is UNREACHABLE:
            raise AITBCConnectionError(f"RPC unreachable at {self._rpc_base}")
        if not isinstance(data, dict):
            raise MessagingNotFoundError(f"dm inbox for {address}")
        return data

    def dm_publish_key(
        self,
        *,
        wallet: str,
        submit: SubmitFn,
        agent_address: str | None = None,
        keys_path=None,
        rotate: bool = False,
        fee_ait: str = "1",
    ) -> dict[str, Any]:
        """Create (or rotate) this wallet's X25519 DM key and publish the
        public half as a ``dm_key`` envelope.

        The secret half is appended to the mode-600 ``dm-keys/<wallet>.json``
        store (same layout the CLI uses); ``rotate=True`` keeps old eras so
        old ciphertext still opens. Returns ``{"tx_hash", "enc_pubkey",
        "keys_path"}``.
        """
        if not wallet:
            raise AITBCError("dm_publish_key requires an explicit wallet name")
        if submit is None:
            raise AITBCError("dm_publish_key requires a submit callable (see cli_submitter)")
        if agent_address is None:
            agent_address = _resolve_wallet_address(wallet)
        path = keys_path if keys_path is not None else _resolve_dm_key_path(wallet)
        store = dm_store_load(path)
        if store["keys"] and not rotate:
            return {
                "tx_hash": store["keys"][-1].get("published_tx"),
                "enc_pubkey": store["keys"][-1]["enc_pubkey"],
                "keys_path": str(path),
            }
        era = generate_key_era()
        envelope = build_envelope(kind="dm_key", topic=DM_TOPIC, agent_address=agent_address, enc_pubkey=era["enc_pubkey"])
        tx_hash = submit(wallet, envelope, fee_ait)
        era["published_tx"] = tx_hash
        store["keys"].append(era)
        dm_store_save(path, store)
        return {"tx_hash": tx_hash, "enc_pubkey": era["enc_pubkey"], "keys_path": str(path)}

    def dm_send(
        self,
        recipient: str,
        body: str,
        *,
        wallet: str,
        submit: SubmitFn,
        agent_address: str | None = None,
        fee_ait: str = "1",
    ) -> dict[str, Any]:
        """Seal ``body`` for ``recipient`` and submit it as a ``dm`` envelope.

        The recipient's ``enc_pubkey`` is fetched from the index; the body is
        encrypted in this process and only the ciphertext goes on the wire.
        ``submit`` receives the sealed envelope — it never sees plaintext.
        """
        if not wallet:
            raise AITBCError("dm_send requires an explicit wallet name")
        if submit is None:
            raise AITBCError("dm_send requires a submit callable (see cli_submitter)")
        if not body:
            raise AITBCError("empty DM body refused")
        if len(body.encode("utf-8")) > dm_max_plaintext_bytes():
            raise AITBCError(f"DM body exceeds the ~{dm_max_plaintext_bytes()}-byte limit")
        from aitbc.crypto.signature_recovery import canonical_address

        try:
            recipient_c = canonical_address(recipient, strict=True)
        except Exception as e:
            raise AITBCError(f"recipient {recipient!r} is not a 0x address") from e
        if agent_address is None:
            agent_address = _resolve_wallet_address(wallet)
        enc_pub = str(self.dm_key_for(recipient_c)["enc_pubkey"])
        ct = seal_dm(enc_pub, agent_address, recipient_c, body)
        envelope = build_envelope(kind="dm", topic=DM_TOPIC, agent_address=agent_address, to=recipient_c, ct=ct)
        tx_hash = submit(wallet, envelope, fee_ait)
        return {"tx_hash": tx_hash, "envelope": envelope, "kind": "dm", "to": recipient_c}

    def dm_read(
        self,
        tx_hash: str,
        *,
        wallet: str | None = None,
        address: str | None = None,
        secret_key: str | None = None,
        max_pages: int = 20,
    ) -> dict[str, Any]:
        """Fetch and decrypt one DM addressed to ``address``.

        The secret key comes from ``secret_key`` (base64 X25519, for callers
        that manage their own eras) or from the wallet's local ``dm-keys``
        store when ``wallet`` is named. Header verification is mandatory —
        a wrong-context, wrong-party or tampered payload raises ``AITBCError``,
        never returns unverified plaintext.
        """
        address, secret_key = _resolve_dm_read_identity(wallet, address, secret_key)
        row = self._dm_find_row(tx_hash, address, max_pages)
        try:
            body = open_dm(secret_key, str(row["sender"]), address, str(row["ct"]))
        except ValueError as e:
            raise AITBCError(f"cannot read DM: {e}") from e
        return {
            "tx_hash": row["tx_hash"],
            "block_height": row["block_height"],
            "from": row["sender"],
            "to": address,
            "body": body,
        }

    def _dm_find_row(self, tx_hash: str, address: str, max_pages: int) -> dict[str, Any]:
        """Scan the ``dm`` inbox pages for ``tx_hash`` (bare or 0x-prefixed)."""
        want = tx_hash.lower().removeprefix("0x")
        cursor: str | None = None
        for _ in range(max_pages):
            page = self.dm_inbox(address, limit=100, cursor=cursor)
            for m in page.get("messages") or []:
                if str(m.get("tx_hash", "")).lower().removeprefix("0x") == want:
                    return dict(m)
            cursor = page.get("next_cursor")
            if not cursor:
                break
        raise MessagingNotFoundError(f"no DM to {address} with tx hash {tx_hash} in the scanned inbox pages")


def _resolve_dm_read_identity(wallet: str | None, address: str | None, secret_key: str | None) -> tuple[str, str]:
    """Fill in ``address``/``secret_key`` from the named wallet's local state."""
    if address is None:
        if wallet is None:
            raise AITBCError("dm_read needs an address (or a wallet to resolve it from)")
        address = _resolve_wallet_address(wallet)
    if secret_key is None:
        if wallet is None:
            raise AITBCError("dm_read needs a secret_key (or a wallet whose dm-keys store holds it)")
        store = dm_store_load(_resolve_dm_key_path(wallet))
        if not store["keys"]:
            raise AITBCError(f"no DM key stored for wallet '{wallet}'")
        secret_key = str(store["keys"][-1]["secret_key"])
    return address, secret_key
