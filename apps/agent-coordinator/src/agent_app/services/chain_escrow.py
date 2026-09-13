"""On-chain escrow RPC client for task payments (v0.25 Phase 3).

Thin synchronous client for the blockchain node's escrow routes — the same
surface ``market/escrow.py`` uses:

* ``POST /rpc/escrow/create``            — buyer-signed ESCROW_LOCK settles the lock
* ``POST /rpc/escrow/{job_id}/release``  — settlement-key release to the provider
* ``POST /rpc/escrow/{job_id}/refund``   — settlement-key refund to the buyer

The escrow ``job_id`` is the task's ``task_id`` so the on-chain contract and
the coordinator's bookkeeping entry share one identifier. ``PaymentEscrow``
callbacks keep their ``(chain_id, from, to, amount) -> tx_hash`` signature;
the factories below close over the task-specific context (lock tx, reason)
that the four-argument signature cannot carry.
"""

from __future__ import annotations

from typing import Any

import httpx

from aitbc.aitbc_logging import get_logger
from aitbc.crypto.payment_escrow import EscrowCallback
from aitbc.utils.units import units_to_ait

logger = get_logger(__name__)


class EscrowRPCError(RuntimeError):
    """Raised when the chain escrow RPC rejects or fails a submission."""


class ChainEscrowClient:
    """Synchronous client for the blockchain escrow RPC.

    Args:
        base_url: Blockchain RPC base URL (``http://127.0.0.1:8202`` on hub).
        api_key: ``X-API-Key`` for the escrow routes (``BLOCKCHAIN_RPC_API_KEY``).
        timeout: Per-request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout: float = 15.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        if self._base_url.endswith("/rpc"):
            self._base_url = self._base_url[: -len("/rpc")]
        headers = {"X-API-Key": api_key} if api_key else {}
        self._client = httpx.Client(base_url=self._base_url, headers=headers, timeout=timeout, transport=transport)

    def close(self) -> None:
        self._client.close()

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.post(path, json=body)
        except httpx.HTTPError as e:
            raise EscrowRPCError(f"escrow RPC {path} unreachable: {e}") from e
        if response.status_code >= 400:
            raise EscrowRPCError(f"escrow RPC {path} returned {response.status_code}: {response.text[:300]}")
        try:
            data = response.json()
        except ValueError as e:
            raise EscrowRPCError(f"escrow RPC {path} returned non-JSON response") from e
        if not isinstance(data, dict):
            raise EscrowRPCError(f"escrow RPC {path} returned unexpected payload: {data!r}")
        return data

    def create(
        self,
        *,
        job_id: str,
        buyer: str,
        provider: str,
        amount_units: int,
        lock_tx: dict[str, Any] | None = None,
        lock_signature: str | None = None,
        lock_nonce: int | None = None,
        lock_fee: int | None = None,
    ) -> dict[str, Any]:
        """Create the on-chain escrow; returns the RPC response dict.

        ``amount_units`` are compute-units (the ``PaymentEscrow`` convention);
        the chain endpoint prices escrows in AIT.
        """
        body: dict[str, Any] = {
            "job_id": job_id,
            "buyer": buyer,
            "provider": provider,
            "amount": str(units_to_ait(amount_units)),
        }
        if lock_tx:
            body["lock_tx"] = lock_tx
        if lock_signature:
            body["lock_signature"] = lock_signature
        if lock_nonce is not None:
            body["lock_nonce"] = lock_nonce
        if lock_fee is not None:
            body["lock_fee"] = lock_fee
        result = self._post("/rpc/escrow/create", body)
        logger.info(
            "On-chain escrow created: job_id=%s contract=%s lock_tx=%s",
            job_id,
            result.get("contract_id"),
            result.get("lock_tx_hash"),
        )
        return result

    def release(self, job_id: str, *, job_tx_hash: str | None = None, amount_units: int | None = None) -> str | None:
        """Release escrow to the provider; returns the release tx hash.

        ``amount_units`` bills a partial amount (the chain refunds the unbilled
        remainder to the buyer); omitting it releases the whole lock.
        """
        body: dict[str, Any] = {}
        if job_tx_hash:
            body["job_tx_hash"] = job_tx_hash
        if amount_units is not None:
            body["amount"] = str(units_to_ait(amount_units))
        result = self._post(f"/rpc/escrow/{job_id}/release", body)
        tx_hash = result.get("tx_hash") or result.get("release_tx_hash")
        logger.info("On-chain escrow released: job_id=%s tx=%s", job_id, tx_hash)
        return str(tx_hash) if tx_hash else None

    def refund(self, job_id: str, *, reason: str = "timeout") -> str | None:
        """Refund escrow to the buyer; returns the refund tx hash."""
        result = self._post(f"/rpc/escrow/{job_id}/refund", {"reason": reason})
        tx_hash = result.get("refund_tx_hash") or result.get("tx_hash")
        logger.info("On-chain escrow refunded: job_id=%s tx=%s", job_id, tx_hash)
        return str(tx_hash) if tx_hash else None


def make_lock_submitter(
    client: ChainEscrowClient,
    task_id: str,
    lock_tx: dict[str, Any] | None,
    lock_signature: str | None,
) -> EscrowCallback:
    """Build a ``PaymentEscrow``-compatible submitter that locks on-chain.

    Returns ``(chain_id, from, to, amount) -> tx_hash``; the escrow contract id
    is stored in the response the router can stash on the entry's metadata.
    """
    last_response: dict[str, Any] = {}

    def _submit(chain_id: str, from_addr: str, to_addr: str, amount: int) -> str:
        result = client.create(
            job_id=task_id,
            buyer=from_addr,
            provider=to_addr,
            amount_units=amount,
            lock_tx=lock_tx,
            lock_signature=lock_signature,
        )
        last_response.update(result)
        tx_hash = result.get("lock_tx_hash") or result.get("tx_hash")
        if not tx_hash:
            raise EscrowRPCError(f"escrow create for {task_id} returned no lock tx hash: {result}")
        return str(tx_hash)

    _submit.last_response = last_response  # type: ignore[attr-defined]
    return _submit


def make_release_submitter(
    client: ChainEscrowClient, task_id: str, job_tx_hash: str | None = None, amount_units: int | None = None
) -> EscrowCallback:
    """Build a submitter that releases the on-chain escrow for ``task_id``."""

    def _submit(chain_id: str, from_addr: str, to_addr: str, amount: int) -> str:
        tx_hash = client.release(task_id, job_tx_hash=job_tx_hash, amount_units=amount_units)
        if not tx_hash:
            raise EscrowRPCError(f"escrow release for {task_id} returned no tx hash")
        return tx_hash

    return _submit


def make_refund_submitter(client: ChainEscrowClient, task_id: str, reason: str = "timeout") -> EscrowCallback:
    """Build a submitter that refunds the on-chain escrow for ``task_id``."""

    def _submit(chain_id: str, from_addr: str, to_addr: str, amount: int) -> str:
        tx_hash = client.refund(task_id, reason=reason)
        if not tx_hash:
            raise EscrowRPCError(f"escrow refund for {task_id} returned no tx hash")
        return tx_hash

    return _submit
