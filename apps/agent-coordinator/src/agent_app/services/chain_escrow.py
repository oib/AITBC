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
from aitbc.crypto.payment_escrow import EscrowCallback, EscrowStatus
from aitbc.utils.units import units_to_ait

logger = get_logger(__name__)


class EscrowRPCError(RuntimeError):
    """Raised when the chain escrow RPC rejects or fails a submission.

    ``status_code``/``retry_after`` carry the HTTP answer through so the
    task-submit path can tell a retryable "lock not confirmed yet" (425 +
    Retry-After) from a permanent rejection instead of flattening both into
    the same 502.
    """

    def __init__(self, message: str, *, status_code: int | None = None, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


from aitbc.island_deferral import IslandDegradedError as _IslandDegradedError


class EscrowDegradedError(_IslandDegradedError, EscrowRPCError):
    """Deferred submit under island-degraded — dual-typed below so existing
    `except EscrowRPCError` paths log + retry (that IS the deferral) while
    code that must distinguish catches IslandDegradedError."""


class ChainEscrowClient:
    """Synchronous client for the blockchain escrow RPC.

    Args:
        base_url: Blockchain RPC base URL (``http://127.0.0.1:8202`` on hub).
        api_key: ``X-API-Key`` for the escrow routes (``BLOCKCHAIN_RPC_API_KEY``).
        settlement_api_key: ``X-Settlement-Key`` for release/refund only
            (``BLOCKCHAIN_RPC_SETTLEMENT_API_KEY``, #1917).
        timeout: Per-request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout: float = 15.0,
        transport: httpx.BaseTransport | None = None,
        settlement_api_key: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        if self._base_url.endswith("/rpc"):
            self._base_url = self._base_url[: -len("/rpc")]
        headers = {"X-API-Key": api_key} if api_key else {}
        self._settlement_api_key = settlement_api_key
        self._client = httpx.Client(base_url=self._base_url, headers=headers, timeout=timeout, transport=transport)

    def close(self) -> None:
        self._client.close()

    def _post(self, path: str, body: dict[str, Any], *, settlement: bool = False) -> dict[str, Any]:
        from aitbc.island_deferral import should_defer

        if should_defer("escrow-submit"):
            raise EscrowDegradedError(f"island-degraded: escrow submit deferred ({path})")
        # Release/refund additionally require the settlement node's dedicated
        # credential (X-Settlement-Key, #1917); create does not.
        headers = {"X-Settlement-Key": self._settlement_api_key} if settlement and self._settlement_api_key else None
        try:
            response = self._client.post(path, json=body, headers=headers)
        except httpx.HTTPError as e:
            raise EscrowRPCError(f"escrow RPC {path} unreachable: {e}") from e
        if response.status_code >= 400:
            retry_after = None
            raw_retry_after = response.headers.get("Retry-After")
            if raw_retry_after:
                try:
                    retry_after = float(raw_retry_after)
                except ValueError:
                    retry_after = None
            raise EscrowRPCError(
                f"escrow RPC {path} returned {response.status_code}: {response.text[:300]}",
                status_code=response.status_code,
                retry_after=retry_after,
            )
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
            # The endpoint takes the lock_tx path when present — the signature
            # must be embedded in the tx or it is submitted unsigned.
            body["lock_tx"] = (
                {**lock_tx, "signature": lock_signature} if lock_signature and not lock_tx.get("signature") else lock_tx
            )
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

    def release(
        self,
        job_id: str,
        *,
        job_tx_hash: str | None = None,
        amount_units: int | None = None,
        auto_reinvest_pct: float | None = None,
    ) -> dict[str, Any]:
        """Release escrow to the provider; returns the RPC response dict.

        ``amount_units`` bills a partial amount (the chain refunds the unbilled
        remainder to the buyer); omitting it releases the whole lock.
        ``auto_reinvest_pct`` asks the chain to stake that share of the release
        for the escrow's recorded provider — the stake address is derived from
        the contract on the chain side, so it cannot be redirected from here.
        The response may then carry ``reinvest_stake_id``/``reinvest_amount``.
        """
        body: dict[str, Any] = {}
        if job_tx_hash:
            body["job_tx_hash"] = job_tx_hash
        if amount_units is not None:
            body["amount"] = str(units_to_ait(amount_units))
        if auto_reinvest_pct is not None:
            body["auto_reinvest_pct"] = str(auto_reinvest_pct)
        result = self._post(f"/rpc/escrow/{job_id}/release", body, settlement=True)
        tx_hash = result.get("tx_hash") or result.get("release_tx_hash")
        logger.info("On-chain escrow released: job_id=%s tx=%s", job_id, tx_hash)
        return result

    def refund(self, job_id: str, *, reason: str = "timeout") -> str | None:
        """Refund escrow to the buyer; returns the refund tx hash."""
        result = self._post(f"/rpc/escrow/{job_id}/refund", {"reason": reason}, settlement=True)
        tx_hash = result.get("refund_tx_hash") or result.get("tx_hash")
        logger.info("On-chain escrow refunded: job_id=%s tx=%s", job_id, tx_hash)
        return str(tx_hash) if tx_hash else None

    def transaction_status(self, tx_hash: str, chain_id: str | None = None) -> dict[str, Any] | None:
        """Return the chain's record for ``tx_hash``; ``None`` when unreadable.

        The answer carries ``status`` (``confirmed`` / ``rejected`` / the
        pending view) and, for apply-time rejections, ``rejected_reason`` /
        ``rejected_at_height``. A lookup failure is ``None`` — callers must
        treat unknown as "not proven dead", never as rejected.
        """
        params = {"chain_id": chain_id} if chain_id else None
        try:
            response = self._client.get(f"/rpc/transaction/{tx_hash}", params=params, timeout=5.0)
        except httpx.HTTPError:
            return None
        if response.status_code != 200:
            return None
        try:
            data = response.json()
        except ValueError:
            return None
        return data if isinstance(data, dict) else None

    def node_wallet(self) -> str | None:
        """Return the settlement node's wallet address (escrow custodian).

        Read from the RPC ``/health`` endpoint — the same source
        ``get_node_wallet`` uses. Older nodes report only ``proposer_id``.
        """
        try:
            response = self._client.get("/health")
            if response.status_code != 200:
                return None
            data = response.json()
            if isinstance(data, dict):
                wallet = data.get("node_wallet") or data.get("proposer_id")
                return str(wallet) if wallet else None
        except (httpx.HTTPError, ValueError):
            pass
        return None


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
    client: ChainEscrowClient,
    task_id: str,
    job_tx_hash: str | None = None,
    amount_units: int | None = None,
    auto_reinvest_pct: float | None = None,
) -> EscrowCallback:
    """Build a submitter that releases the on-chain escrow for ``task_id``.

    Returns ``(chain_id, from, to, amount) -> tx_hash``; like
    ``make_lock_submitter`` the chain's full response is kept on
    ``last_response`` so the router can read the reinvest outcome
    (``reinvest_stake_id``/``reinvest_amount``) off it.
    """
    last_response: dict[str, Any] = {}

    def _submit(chain_id: str, from_addr: str, to_addr: str, amount: int) -> str:
        result = client.release(
            task_id, job_tx_hash=job_tx_hash, amount_units=amount_units, auto_reinvest_pct=auto_reinvest_pct
        )
        last_response.update(result)
        tx_hash = result.get("tx_hash") or result.get("release_tx_hash")
        if not tx_hash:
            raise EscrowRPCError(f"escrow release for {task_id} returned no tx hash")
        return str(tx_hash)

    _submit.last_response = last_response  # type: ignore[attr-defined]
    return _submit


def reconcile_rejected_lock(escrow_rpc: ChainEscrowClient | None, entry: Any) -> bool:
    """Mark ``entry`` REJECTED when its lock transaction is dead on-chain (#2744).

    ``PaymentEscrow.lock`` records LOCKED on mempool admission, not on seal —
    an apply-time rejection (bad nonce, failed gate) leaves the bookkeeping
    claiming funds that never moved. This probes the chain's tx record:
    ``status == "rejected"`` flips the entry to the terminal REJECTED state
    with the reason in ``metadata["lock_rejected_reason"]``. Unknown answers
    (probe failure, still pending, confirmed) leave the entry untouched —
    only a proven rejection reconciles. The caller persists the entry.
    """
    if escrow_rpc is None or getattr(entry, "status", None) != EscrowStatus.LOCKED:
        return False
    tx_hash = getattr(entry, "tx_hash_lock", None)
    if not tx_hash:
        return False
    info = escrow_rpc.transaction_status(str(tx_hash), chain_id=getattr(entry, "chain_id", None))
    # The endpoint's mempool fallback tags pending views with state="pending";
    # only a durable rejected row (no pending marker) proves the lock is dead.
    if not isinstance(info, dict) or info.get("status") != "rejected" or info.get("state") == "pending":
        return False
    entry.status = EscrowStatus.REJECTED
    reason = info.get("rejected_reason") or "lock transaction rejected on-chain"
    entry.metadata["lock_rejected_reason"] = str(reason)
    return True


def _settle_tx_rejected(escrow_rpc: ChainEscrowClient, entry: Any, tx_hash: Any, chain_id: Any) -> str | None:
    """Return the rejection reason when ``tx_hash`` is proven dead on-chain.

    ``None`` for every non-proof: probe failure, still pending/confirmed, or
    a mempool-pending view (``state == "pending"``) — only a durable rejected
    row settles the question, same rule as ``reconcile_rejected_lock``.
    """
    if not tx_hash:
        return None
    info = escrow_rpc.transaction_status(str(tx_hash), chain_id=chain_id)
    if not isinstance(info, dict) or info.get("status") != "rejected" or info.get("state") == "pending":
        return None
    return str(info.get("rejected_reason") or "settlement transaction rejected on-chain")


def reconcile_rejected_release(escrow_rpc: ChainEscrowClient | None, entry: Any) -> bool:
    """Revert a RELEASED entry to LOCKED when its release tx died on-chain (#2926).

    ``PaymentEscrow.release`` records RELEASED on mempool admission, not on
    seal — an apply-time rejection leaves the bookkeeping claiming the
    provider was paid while the funds stay locked in the escrow contract,
    stranded forever (the sweeper only touches LOCKED rows). A proven
    rejection restores LOCKED — the honest pre-settle state — clears
    ``released_at``, and records ``metadata["release_rejected_reason"]`` so
    the expire sweep can refund or an operator can retry the release. The
    dead ``tx_hash_release`` is kept for audit; a later successful release
    overwrites it. The caller persists the entry.
    """
    if escrow_rpc is None or getattr(entry, "status", None) != EscrowStatus.RELEASED:
        return False
    reason = _settle_tx_rejected(escrow_rpc, entry, getattr(entry, "tx_hash_release", None), getattr(entry, "chain_id", None))
    if reason is None:
        return False
    entry.status = EscrowStatus.LOCKED
    entry.released_at = None
    entry.metadata["release_rejected_reason"] = reason
    return True


def reconcile_rejected_refund(escrow_rpc: ChainEscrowClient | None, entry: Any) -> bool:
    """Revert a REFUNDED entry to LOCKED when its refund tx died on-chain (#2926).

    Same mempool-admission asymmetry as the release path: a proven-rejected
    refund means the buyer was never made whole and the funds remain locked.
    Restoring LOCKED hands the row back to the expire sweep (which retries
    the refund) and to operator inspection. ``metadata["refund_rejected_reason"]``
    carries the chain's reason; ``tx_hash_refund`` is kept for audit. The
    caller persists the entry.
    """
    if escrow_rpc is None or getattr(entry, "status", None) != EscrowStatus.REFUNDED:
        return False
    reason = _settle_tx_rejected(escrow_rpc, entry, getattr(entry, "tx_hash_refund", None), getattr(entry, "chain_id", None))
    if reason is None:
        return False
    entry.status = EscrowStatus.LOCKED
    entry.metadata["refund_rejected_reason"] = reason
    return True


def make_refund_submitter(client: ChainEscrowClient, task_id: str, reason: str = "timeout") -> EscrowCallback:
    """Build a submitter that refunds the on-chain escrow for ``task_id``."""

    def _submit(chain_id: str, from_addr: str, to_addr: str, amount: int) -> str:
        tx_hash = client.refund(task_id, reason=reason)
        if not tx_hash:
            raise EscrowRPCError(f"escrow refund for {task_id} returned no tx hash")
        return tx_hash

    return _submit
