"""Escrow release relay service (ESCROW-RELEASE-1).

Relays an escrow release trigger to the settlement-capable chain RPC from
inside the coordinator's network position. The chain route
``POST /rpc/escrow/{job_id}/release`` carries no caller signature — the
node signs the release with its own settlement key and source-IP gating is
the only authorization at the rpc edge — so the JWT boundary here is what
keeps release authority scoped: the escrow's on-chain ``buyer`` must equal
the wallet bound to the JWT subject (admin exempt).

Unlike the create relay there is no signed lock to forward: the relay asks
the chain for the escrow row first (also how it learns the buyer), then
posts ``{amount, job_tx_hash}`` and lets the node validate amounts,
settlement state and signatures. Replays — a stored relay row or an
already-released escrow — return the stored result without a second chain
call.

Refund deliberately has no relay: refunding is a settlement-node operation
only.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from aitbc.network import AsyncAITBCHTTPClient
from aitbc.utils.units import ait_to_units

from ....storage import get_session
from ..domain.escrow_release_relay import EscrowReleaseRelay
from .escrow_relay import EscrowRelayService
from .payments import _find_http_status_error

logger = logging.getLogger(__name__)


def _chain_detail(exc: BaseException, fallback: str) -> tuple[int | None, Any]:
    """Extract (status_code, detail) from a wrapped chain HTTP error."""
    status_error = _find_http_status_error(exc)
    if status_error is None:
        return None, fallback
    detail: Any = fallback
    try:
        resp_body = status_error.response.json()
        if isinstance(resp_body, dict) and isinstance(resp_body.get("detail"), str):
            detail = resp_body["detail"]
    except ValueError:
        pass
    return status_error.response.status_code, detail


class EscrowReleaseRelayService(EscrowRelayService):
    """Relay escrow release triggers to the chain RPC.

    Inherits the wallet-binding, buyer-binding and amount parsing checks
    from :class:`EscrowRelayService`; only the dedup shape (job_id, no
    signed payload) and the chain endpoints differ.
    """

    def __init__(self, session: Annotated[Session, Depends(get_session)]):
        super().__init__(session)

    async def _fetch_escrow(self, client: AsyncAITBCHTTPClient, job_id: str) -> dict[str, Any]:
        """Read the escrow row from the chain; 404s pass through."""
        try:
            escrow = await client.get(f"{self.blockchain_rpc_url}/rpc/escrow/{job_id}")
        except Exception as exc:
            code, detail = _chain_detail(exc, "the escrow lookup failed on the settlement node")
            if code is not None and 400 <= code < 500:
                raise HTTPException(status_code=code, detail=detail) from exc
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="the escrow relay could not reach the settlement node; the request can be retried",
            ) from exc
        if not isinstance(escrow, dict):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="the settlement node returned an unexpected escrow payload",
            )
        return escrow

    def _check_amount_within_lock(self, is_admin: bool, amount_units: int, escrow: dict[str, Any], job_id: str) -> None:
        """Bound the release by the escrow's locked amount.

        The chain enforces the same bound, but checking it here costs
        nothing (the row is already fetched) and refuses an over-release
        before any chain call. Admin callers are exempt, mirroring the
        create relay's cap exemption.
        """
        if is_admin:
            return
        raw = escrow.get("amount")
        try:
            locked_units = ait_to_units(Decimal(str(raw)))
        except (InvalidOperation, ValueError, TypeError):
            # Cannot derive the bound — let the chain validate the amount.
            logger.warning("escrow amount unreadable for job_id=%s; deferring cap to the chain", job_id)
            return
        if amount_units > locked_units:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"release amount exceeds the escrow's locked amount of {raw} AIT",
            )

    async def _post_release(self, client: AsyncAITBCHTTPClient, job_id: str, forward: dict[str, Any]) -> dict[str, Any]:
        """POST the release to the settlement node; 4xx pass through, else 502."""
        try:
            return await client.post(
                f"{self.blockchain_rpc_url}/rpc/escrow/{job_id}/release",
                json=forward,
            )
        except Exception as exc:
            code, detail = _chain_detail(exc, "the node refused the escrow release")
            if code is not None and 400 <= code < 500:
                # Chain 4xx: the node's refusal is a domain message safe to
                # pass through at the same status code.
                raise HTTPException(status_code=code, detail=detail) from exc
            # Timeout / 5xx / ambiguous post-send failure: the release may
            # still have landed — the replay dedup makes a retry safe.
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="the escrow release relay could not reach the settlement node; the request can be retried",
            ) from exc

    def _stored_result(self, row: EscrowReleaseRelay) -> dict[str, Any]:
        return {
            "success": True,
            "contract_id": row.contract_id,
            "tx_hash": row.tx_hash,
            "duplicate": True,
        }

    def _insert_or_existing(self, row: EscrowReleaseRelay) -> EscrowReleaseRelay | None:
        """Insert *row*; on a concurrent duplicate insert return the stored row instead.

        Two simultaneous releases can both pass the dedup lookup — the loser
        hits the unique job_id index. It must not surface a 500: the stored
        row is the correct replay result.
        """
        self.session.add(row)
        try:
            self.session.commit()
            return None
        except IntegrityError:
            self.session.rollback()
            return (
                self.session.execute(select(EscrowReleaseRelay).where(EscrowReleaseRelay.job_id == row.job_id))
                .scalars()
                .first()
            )

    async def release(self, client_id: str, is_admin: bool, body: dict[str, Any]) -> dict[str, Any]:
        """Validate, dedup and forward the escrow release to the chain.

        Returns a dict with ``tx_hash``/``contract_id``/``duplicate`` (plus
        any amount fields the chain reported).
        """
        job_id = body.get("job_id")
        if not isinstance(job_id, str) or not job_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="job_id is required",
            )
        job_tx_hash = body.get("job_tx_hash")
        # ``amount`` is optional: when omitted the relay releases the full
        # locked amount. It is derived AFTER the ownership check (below) —
        # a caller who is not the buyer must get 403, not data.
        amount_provided = body.get("amount") is not None
        amount_units: int | None = None

        client = AsyncAITBCHTTPClient(timeout=10.0, api_key=self.blockchain_rpc_api_key)

        # Ownership first: the buyer check must run before any dedup or
        # already-released return, or a logged-in caller who merely knows a
        # job_id could read that escrow's tx_hash/contract_id.
        escrow = await self._fetch_escrow(client, job_id)
        buyer = escrow.get("buyer")
        if not is_admin:
            if not isinstance(buyer, str) or not buyer:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="the settlement node did not report the escrow buyer",
                )
            self._check_buyer_binding(client_id, buyer)

        # Dedup: a prior relay row settles the job — return it without a
        # chain call so a replayed request can never double-release.
        existing: EscrowReleaseRelay | None = (
            self.session.execute(select(EscrowReleaseRelay).where(EscrowReleaseRelay.job_id == job_id)).scalars().first()
        )
        if existing is not None:
            return self._stored_result(existing)

        state = escrow.get("state")
        if state == "released" or escrow.get("released_at"):
            # Already settled on-chain: record the outcome and return it —
            # a second release POST is unnecessary and unsafe to repeat.
            row = EscrowReleaseRelay(
                client_id=client_id,
                job_id=job_id,
                tx_hash=escrow.get("release_tx_hash"),
                contract_id=escrow.get("contract_id"),
            )
            stored = self._insert_or_existing(row)
            return self._stored_result(stored if stored is not None else row)
        if state == "refunded" or escrow.get("refunded_at"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Escrow for job_id={job_id} has already been refunded",
            )

        # Derive the amount only after ownership has passed: an omitted
        # amount means "release the full lock" — the chain's own rule.
        if amount_provided:
            amount_units = self._amount_units(body.get("amount"))
            self._check_amount_within_lock(is_admin, amount_units, escrow, job_id)

        forward: dict[str, Any] = {}
        if amount_provided:
            forward["amount"] = str(body.get("amount"))
        if job_tx_hash is not None:
            forward["job_tx_hash"] = job_tx_hash

        chain_response = await self._post_release(client, job_id, forward)

        tx_hash = chain_response.get("tx_hash") if isinstance(chain_response, dict) else None
        contract_id = chain_response.get("contract_id") if isinstance(chain_response, dict) else None
        row = EscrowReleaseRelay(client_id=client_id, job_id=job_id, tx_hash=tx_hash, contract_id=contract_id)
        stored = self._insert_or_existing(row)
        if stored is not None:
            # Concurrent identical release: the row landed first — the chain
            # call may or may not have sealed; return the stored result.
            return self._stored_result(stored)
        # Audit: one line per relay — client, job and the tx, never payload detail.
        logger.info(
            "Escrow release relayed: client_id=%s job_id=%s contract_id=%s tx_hash=%s",
            client_id,
            job_id,
            contract_id,
            tx_hash,
        )
        result: dict[str, Any] = dict(chain_response) if isinstance(chain_response, dict) else {}
        result.setdefault("success", True)
        result["contract_id"] = contract_id
        result["tx_hash"] = tx_hash
        result["duplicate"] = bool(result.get("duplicate", False))
        return result
