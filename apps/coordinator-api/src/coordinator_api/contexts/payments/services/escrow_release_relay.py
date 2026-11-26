"""Escrow release relay service (ESCROW-RELEASE-1).

Relays an escrow release trigger to the settlement-capable chain RPC from
inside the coordinator's network position. The chain route
``POST /rpc/escrow/{job_id}/release`` carries no caller signature — the
node signs the release with its own settlement key — and since #1917 it
additionally requires the settlement credential as ``X-Settlement-Key``
on top of ``X-API-Key``; this service forwards
``blockchain_rpc_settlement_api_key`` as that header. Source-IP gating
plus the credential are the only authorization at the rpc edge — so the JWT boundary here is what
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
from starlette.concurrency import run_in_threadpool
from sqlmodel import Session, select

from aitbc.network import AsyncAITBCHTTPClient
from aitbc.utils.units import ait_to_units

from ....storage import get_session
from ..domain.escrow_release_relay import EscrowReleaseRelay
from .escrow_relay import EscrowRelayService
from .escrow_relay_metrics import RESULT_CHAIN_TIMEOUT, RESULT_UPSTREAM_5XX, tag_escrow_result
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
            # code is None → the call died in transport (timeout/DNS/refused).
            raise tag_escrow_result(
                HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="the escrow relay could not reach the settlement node; the request can be retried",
                ),
                RESULT_UPSTREAM_5XX if code is not None else RESULT_CHAIN_TIMEOUT,
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
                headers=self._settlement_headers(),
            )
        except Exception as exc:
            code, detail = _chain_detail(exc, "the node refused the escrow release")
            if code is not None and 400 <= code < 500:
                # Chain 4xx: the node's refusal is a domain message safe to
                # pass through at the same status code.
                raise HTTPException(status_code=code, detail=detail) from exc
            # Timeout / 5xx / ambiguous post-send failure: the release may
            # still have landed — the replay dedup makes a retry safe. Tag
            # the classified result: no HTTP status means transport failure
            # (timeout), a status >= 500 is a real upstream 5xx.
            raise tag_escrow_result(
                HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="the escrow release relay could not reach the settlement node; the request can be retried",
                ),
                RESULT_UPSTREAM_5XX if code is not None else RESULT_CHAIN_TIMEOUT,
            ) from exc

    def _check_amount_is_full_lock(self, amount_units: int, escrow: dict[str, Any], job_id: str) -> None:
        """Non-admin releases may only name the escrow's full locked amount (#1912).

        The chain treats ``amount`` as the billed figure and refunds the
        unbilled remainder to the *buyer* — a caller-chosen dust amount pays
        the provider ~nothing while ``released_at`` blocks any alarm. The
        market sweeper always releases the full lock, so partial releases
        are an admin/ops tool: a buyer either omits ``amount`` (the chain
        releases the full lock) or names exactly the lock. An unreadable
        escrow amount fails closed — the chain would honor a partial.
        """
        raw = escrow.get("amount")
        try:
            locked_units = ait_to_units(Decimal(str(raw)))
        except (InvalidOperation, ValueError, TypeError):
            locked_units = None
        if locked_units is None or amount_units != locked_units:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "release amount must equal the escrow's full locked amount "
                    f"({raw} AIT); omit 'amount' to release the full lock"
                ),
            )

    def _release_forward(
        self,
        body: dict[str, Any],
        amount_provided: bool,
        escrow: dict[str, Any],
        is_admin: bool,
        job_id: str,
    ) -> dict[str, Any]:
        """The {amount?, job_tx_hash?} body forwarded to the settlement node.

        Derivation runs only after ownership has passed: an omitted amount
        means "release the full lock" — the chain's own rule. A provided
        amount is bounded by the lock for everyone and, for non-admin
        callers, must equal the lock exactly (#1912).
        """
        forward: dict[str, Any] = {}
        if amount_provided:
            amount_units = self._amount_units(body.get("amount"))
            self._check_amount_within_lock(is_admin, amount_units, escrow, job_id)
            if not is_admin:
                self._check_amount_is_full_lock(amount_units, escrow, job_id)
            forward["amount"] = str(body.get("amount"))
        return forward

    def _stored_result(self, row: EscrowReleaseRelay) -> dict[str, Any]:
        return {
            "success": True,
            "contract_id": row.contract_id,
            "tx_hash": row.tx_hash,
            "duplicate": True,
        }

    @staticmethod
    def _chain_release_settled(chain_response: Any) -> bool:
        """True only for a chain answer that proves the release settled.

        ``success: true`` alone is not proof — the dedup row replays
        ``success: true`` forever, so a response without a transaction hash
        (absent ``success``, ``success: null``, a proxy error body) must not
        become one (#2813).
        """
        return (
            isinstance(chain_response, dict) and chain_response.get("success") is True and bool(chain_response.get("tx_hash"))
        )

    def _clear_dead_dedup_hash(self, row: EscrowReleaseRelay) -> None:
        """Drop a stored tx_hash the escrow state proved dead (#3009).

        The row stays (job_id dedup + audit trail); only the dead hash is
        cleared. ``_record_relay_row`` then heals it with the replacement
        release's hash once the re-drive verifies.
        """
        dead = row.tx_hash
        row.tx_hash = None
        self.session.add(row)
        self.session.commit()
        logger.warning(
            "Escrow release relay cleared dead tx_hash %s for job_id=%s; re-driving the release",
            dead,
            row.job_id,
        )

    def _fill_dedup_row(self, row: EscrowReleaseRelay, *, tx_hash: Any, contract_id: Any) -> None:
        """Heal a dedup row recorded without a tx_hash once the release verifies."""
        row.tx_hash = tx_hash
        row.contract_id = contract_id
        self.session.add(row)
        self.session.commit()

    async def _record_settled_release(
        self,
        client_id: str,
        job_id: str,
        escrow: dict[str, Any],
        existing: EscrowReleaseRelay | None,
    ) -> dict[str, Any]:
        """Record (or heal) the dedup row for an escrow already released on-chain."""
        # The chain's hash is authoritative when present; a released escrow
        # that omits it must not wipe a hash the row already carries (#3009).
        tx_hash = escrow.get("release_tx_hash") or (existing.tx_hash if existing is not None else None)
        contract_id = escrow.get("contract_id")
        if existing is not None:
            await run_in_threadpool(self._fill_dedup_row, existing, tx_hash=tx_hash, contract_id=contract_id)
            return self._stored_result(existing)
        row = EscrowReleaseRelay(client_id=client_id, job_id=job_id, tx_hash=tx_hash, contract_id=contract_id)
        stored = await run_in_threadpool(self._insert_or_existing, row)
        return self._stored_result(stored if stored is not None else row)

    async def _ambiguous_release_result(
        self,
        client: AsyncAITBCHTTPClient,
        client_id: str,
        job_id: str,
        chain_response: Any,
        existing: EscrowReleaseRelay | None,
    ) -> dict[str, Any]:
        """Handle a chain answer that is not a verified settle.

        Re-reads the escrow: if the release landed anyway (ambiguous
        post-send failure, ``success`` absent), record the dedup row from
        the on-chain state. Otherwise return a retryable failure — no dedup
        row, so the next request re-attempts the chain call (#2813).
        """
        logger.warning(
            "Escrow release answer not a verified settle: client_id=%s job_id=%s response=%r",
            client_id,
            job_id,
            chain_response,
        )
        escrow_now = await self._fetch_escrow(client, job_id)
        if escrow_now.get("state") == "released" or escrow_now.get("released_at"):
            return await self._record_settled_release(client_id, job_id, escrow_now, existing)
        failure: dict[str, Any] = dict(chain_response) if isinstance(chain_response, dict) else {}
        failure["success"] = False
        failure["duplicate"] = False
        return failure

    async def _release_answer_result(
        self,
        client: AsyncAITBCHTTPClient,
        client_id: str,
        job_id: str,
        chain_response: Any,
        existing: EscrowReleaseRelay | None,
    ) -> dict[str, Any]:
        """Turn the chain's release answer into the relay result.

        Only a verified settle (``success: true`` + tx_hash) records the
        dedup row; anything else re-checks the escrow on-chain or returns
        a retryable failure (#2813).
        """
        if not self._chain_release_settled(chain_response):
            return await self._ambiguous_release_result(client, client_id, job_id, chain_response, existing)

        tx_hash = chain_response["tx_hash"]
        contract_id = chain_response.get("contract_id")
        stored = await self._record_relay_row(client_id, job_id, tx_hash, contract_id, existing)
        if stored is not None:
            if stored.tx_hash:
                # Concurrent identical release: the row landed first — the chain
                # call may or may not have sealed; return the stored result.
                return self._stored_result(stored)
            # A concurrent wedge row (no tx_hash) won the insert — heal it
            # with the verified hash and return this call's fresh result.
            await run_in_threadpool(self._fill_dedup_row, stored, tx_hash=tx_hash, contract_id=contract_id)
        # Audit: one line per relay — client, job and the tx, never payload detail.
        logger.info(
            "Escrow release relayed: client_id=%s job_id=%s contract_id=%s tx_hash=%s",
            client_id,
            job_id,
            contract_id,
            tx_hash,
        )
        result: dict[str, Any] = dict(chain_response)
        result["success"] = True
        result["contract_id"] = contract_id
        result["tx_hash"] = tx_hash
        result["duplicate"] = False
        return result

    async def _record_relay_row(
        self,
        client_id: str,
        job_id: str,
        tx_hash: Any,
        contract_id: Any,
        existing: EscrowReleaseRelay | None,
    ) -> EscrowReleaseRelay | None:
        """Persist the dedup row for a verified release.

        Returns the concurrently-stored row when another request won the
        insert (caller replays it), or None when this call's row is the
        record — including the healed pre-existing wedge row.
        """
        if existing is not None:
            await run_in_threadpool(self._fill_dedup_row, existing, tx_hash=tx_hash, contract_id=contract_id)
            return None
        row = EscrowReleaseRelay(client_id=client_id, job_id=job_id, tx_hash=tx_hash, contract_id=contract_id)
        return await run_in_threadpool(self._insert_or_existing, row)

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
        amount_provided = body.get("amount") not in (None, "")

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
            await run_in_threadpool(self._check_buyer_binding, client_id, buyer)

        state = escrow.get("state")
        settled_on_chain = state == "released" or bool(escrow.get("released_at"))

        # Dedup row lookup happens after the escrow read because the fresh
        # escrow state is the arbiter (#3009): the node marks released_at at
        # release-submit time and its sweeper demotes the row once the
        # envelope proves unsealed.
        #
        # - Escrow reads released (pending *or* confirmed — both carry
        #   released_at): _record_settled_release returns the chain's
        #   authoritative release_tx_hash and repairs a stale cached one,
        #   so a replayed request can never double-release and a dead
        #   recorded hash is never reported as the settlement.
        # - Escrow does NOT read released but a relay row carries a
        #   tx_hash: the stored attempt is dead (apply-rejected, node
        #   record demoted). Replaying it would report a release that
        #   never happened — clear the corpse and re-drive instead.
        # - Hashless rows fall through either way (#2813 wedge contract).
        existing: EscrowReleaseRelay | None = await run_in_threadpool(
            lambda: (
                self.session.execute(select(EscrowReleaseRelay).where(EscrowReleaseRelay.job_id == job_id)).scalars().first()
            )
        )
        if settled_on_chain:
            # Already settled on-chain: record the outcome and return it —
            # a second release POST is unnecessary and unsafe to repeat.
            return await self._record_settled_release(client_id, job_id, escrow, existing)
        if existing is not None and existing.tx_hash:
            await run_in_threadpool(self._clear_dead_dedup_hash, existing)
        if state == "refunded" or escrow.get("refunded_at"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Escrow for job_id={job_id} has already been refunded",
            )

        forward = self._release_forward(body, amount_provided, escrow, is_admin, job_id)
        if job_tx_hash is not None:
            forward["job_tx_hash"] = job_tx_hash

        chain_response = await self._post_release(client, job_id, forward)
        return await self._release_answer_result(client, client_id, job_id, chain_response, existing)
