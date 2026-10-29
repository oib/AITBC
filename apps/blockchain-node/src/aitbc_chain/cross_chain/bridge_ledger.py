"""Client for the rpc-hosted shared transfer ledger (issue #696, decision A).

The ledger lives as an HTTP surface inside the designated host's
``aitbc-blockchain-rpc`` process (``/rpc/bridge/ledger/*``) — no new unit,
no pg. Remote rpcs keep their local ``cross_chain_transfer`` row as a
write-through cache: intake still writes locally, then registers with the
service; the relayer reads its worklist from the service instead of the
local ``status='pending'`` scan.

Every function here is best-effort: an unreachable service logs a warning
and returns a falsy value — the caller skips the pass. Block sealing and
the local lock path are never on this dependency. When
``settings.bridge_ledger_url`` is unset the module is inert and the
caller keeps today's byte-for-byte local-scan behaviour.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import TYPE_CHECKING, Any

import httpx

from ..config import settings
from ..logger import get_logger

if TYPE_CHECKING:
    from ..models import CrossChainTransfer

logger = get_logger(__name__)

_TIMEOUT_SECONDS = 5.0


def ledger_url() -> str:
    """Configured base URL of the ledger service, or "" when unarmed."""
    return str(getattr(settings, "bridge_ledger_url", "") or "").rstrip("/")


def ledger_enabled() -> bool:
    """True when BRIDGE_LEDGER_URL points at a ledger service."""
    return bool(ledger_url())


def _headers() -> dict[str, str]:
    key = os.environ.get("BLOCKCHAIN_RPC_API_KEY")
    return {"X-API-Key": key} if key else {}


def _request(method: str, path: str, **kwargs: Any) -> httpx.Response | None:
    """Fire one request at the ledger service; None on any failure."""
    url = ledger_url()
    if not url:
        return None
    try:
        with httpx.Client(timeout=_TIMEOUT_SECONDS, headers=_headers()) as client:
            response = client.request(method, f"{url}{path}", **kwargs)
        response.raise_for_status()
        return response
    except Exception as e:  # noqa: BLE001 - fire-and-log: a ledger outage never fails the caller
        logger.warning("Bridge ledger %s %s failed: %s", method, path, e)
        return None


def register_transfer(record: CrossChainTransfer) -> bool:
    """Idempotent upsert of a pending row into the shared ledger.

    Called by intake after the local row commit — write-through cache
    semantics: failure only logs, the local row stays the fallback copy.
    """
    payload = {
        "transfer_id": record.transfer_id,
        "source_chain": record.source_chain,
        "target_chain": record.target_chain,
        "sender": record.sender,
        "recipient": record.recipient,
        "amount": record.amount,
        "asset": record.asset,
        "status": record.status,
        "source_tx_hash": record.source_tx_hash,
        "lock_time": record.lock_time.isoformat() if record.lock_time else None,
        "release_amount": record.release_amount,
    }
    return _request("POST", "/rpc/bridge/ledger/register", json=payload) is not None


def fetch_pending(target_chain: str) -> list[dict[str, Any]] | None:
    """The relayer worklist for ``target_chain`` — None when the service failed.

    An empty list means "service reachable, nothing to relay"; ``None``
    means "service unreachable — skip the pass".
    """
    response = _request("GET", "/rpc/bridge/ledger/pending", params={"target_chain": target_chain})
    if response is None:
        return None
    try:
        data = response.json()
    except Exception as e:  # noqa: BLE001
        logger.warning("Bridge ledger pending response unreadable: %s", e)
        return None
    rows = data.get("transfers") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        logger.warning("Bridge ledger pending response missing 'transfers' list")
        return None
    return [r for r in rows if isinstance(r, dict)]


def write_status(
    transfer_id: str,
    status: str,
    *,
    target_tx_hash: str | None = None,
    proof_hash: str | None = None,
    confirm_time: datetime | None = None,
) -> bool:
    """Monotonic status writeback after relay/finalize — fire-and-log."""
    payload = {
        "status": status,
        "target_tx_hash": target_tx_hash,
        "proof_hash": proof_hash,
        "confirm_time": confirm_time.isoformat() if confirm_time else None,
    }
    return _request("POST", f"/rpc/bridge/ledger/{transfer_id}/status", json=payload) is not None
