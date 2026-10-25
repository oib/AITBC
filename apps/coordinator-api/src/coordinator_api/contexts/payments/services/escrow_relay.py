"""Escrow relay service (ESCROW-ROUTE-1).

Relays a buyer-signed ``/rpc/escrow/create`` payload to the settlement-capable
chain RPC from inside the coordinator's network position. Market escrows mint
their job_id client-side, so the ``POST /v1/payments`` route — which requires
an owned coordinator job — cannot serve them; this route carries the raw chain
payload instead.

The coordinator never signs anything: the buyer's signature inside ``lock_tx``
is the fund authorization and the chain validates it. What the relay adds over
exposing ``/rpc/escrow/create`` to the internet is the JWT boundary, a
buyer↔credential binding check, an amount cap, replay dedup, and an audit row.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from sqlmodel import Session, select

from aitbc.network import AsyncAITBCHTTPClient
from aitbc.utils.units import ait_to_units

from ....config import settings
from ....storage import get_session
from ...infrastructure.domain.user import Wallet
from ..domain.escrow_relay import EscrowRelay
from .payments import _find_http_status_error

logger = logging.getLogger(__name__)

# 10 AIT in compute units (1 AIT = 36_000_000 units). Bounds the blast radius
# of a relayed lock; admin callers are exempt.
DEFAULT_ESCROW_RELAY_MAX_UNITS = 360_000_000


def _relay_max_units() -> int:
    """Max relayable escrow amount in compute units (env-configurable)."""
    raw = os.getenv("ESCROW_RELAY_MAX_UNITS", "")
    try:
        value = int(raw) if raw.strip() else DEFAULT_ESCROW_RELAY_MAX_UNITS
    except ValueError:
        logger.warning("Invalid ESCROW_RELAY_MAX_UNITS=%r; using default", raw)
        return DEFAULT_ESCROW_RELAY_MAX_UNITS
    return max(value, 0)


def _lock_tx_hash(lock_tx: dict[str, Any]) -> str:
    """Deterministic dedup hash over the buyer-signed lock transaction."""
    return hashlib.sha256(json.dumps(lock_tx, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


class EscrowRelayService:
    """Relay buyer-signed escrow creates to the chain RPC."""

    def __init__(self, session: Annotated[Session, Depends(get_session)]):
        self.session = session
        self.blockchain_rpc_url = settings.blockchain_rpc_url.rstrip("/")
        self.blockchain_rpc_api_key = settings.blockchain_rpc_api_key

    def _bound_wallet_address(self, client_id: str) -> str | None:
        """Return the wallet address bound to the JWT subject, if any."""
        wallet = self.session.execute(select(Wallet).where(Wallet.user_id == client_id)).scalars().first()
        return wallet.address if wallet is not None else None

    def _check_buyer_binding(self, client_id: str, buyer: str) -> None:
        """The relayed buyer must be the wallet bound to the JWT subject.

        Without this, any client credential could relay a lock signed by a
        different buyer — the chain checks the signature, but the relay must
        check the caller is entitled to act as that buyer at all.
        """
        bound = self._bound_wallet_address(client_id)
        if bound is None or bound.lower() != buyer.lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="escrow buyer does not match the wallet bound to this credential",
            )

    @staticmethod
    def _amount_units(amount: Any) -> int:
        """Parse the chain payload's AIT amount into compute units (400 on bad input)."""
        try:
            amount_dec = Decimal(str(amount))
        except (InvalidOperation, ValueError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid amount: {amount}",
            ) from None
        if amount_dec <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="escrow amount must be positive",
            )
        return ait_to_units(amount_dec)

    def _check_amount_cap(self, is_admin: bool, amount_units: int) -> None:
        if is_admin:
            return
        cap = _relay_max_units()
        if amount_units > cap:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"escrow amount exceeds the relay cap of {cap} units",
            )

    def _existing_relay(self, client_id: str, job_id: str, lock_hash: str) -> EscrowRelay | None:
        """Find a prior relay row for this lock or this (client, job) pair."""
        by_lock: EscrowRelay | None = (
            self.session.execute(select(EscrowRelay).where(EscrowRelay.lock_hash == lock_hash)).scalars().first()
        )
        if by_lock is not None:
            return by_lock
        by_pair: EscrowRelay | None = (
            self.session.execute(select(EscrowRelay).where(EscrowRelay.client_id == client_id, EscrowRelay.job_id == job_id))
            .scalars()
            .first()
        )
        return by_pair

    async def relay(self, client_id: str, is_admin: bool, body: dict[str, Any]) -> dict[str, Any]:
        """Validate, dedup and forward the escrow create payload to the chain.

        Returns ``{"contract_id": ..., "duplicate": bool}``.
        """
        job_id = body.get("job_id")
        buyer = body.get("buyer")
        provider = body.get("provider")
        lock_tx = body.get("lock_tx")
        if not all([job_id, buyer, provider]) or not isinstance(lock_tx, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="job_id, buyer, provider, and lock_tx are required",
            )
        if not isinstance(job_id, str) or not isinstance(buyer, str) or not isinstance(provider, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid types for job_id, buyer, or provider",
            )

        amount_units = self._amount_units(body.get("amount"))
        if not is_admin:
            self._check_buyer_binding(client_id, buyer)
        self._check_amount_cap(is_admin, amount_units)

        lock_hash = _lock_tx_hash(lock_tx)
        existing = self._existing_relay(client_id, job_id, lock_hash)
        if existing is not None:
            if existing.lock_hash != lock_hash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"an escrow was already relayed for job {job_id} with a different lock",
                )
            return {"contract_id": existing.contract_id, "duplicate": True}

        client = AsyncAITBCHTTPClient(timeout=10.0, api_key=self.blockchain_rpc_api_key)
        try:
            chain_response = await client.post(
                f"{self.blockchain_rpc_url}/rpc/escrow/create",
                json=body,
            )
        except Exception as exc:
            status_error = _find_http_status_error(exc)
            if status_error is not None and 400 <= status_error.response.status_code < 500:
                # Chain 4xx: the node's refusal is a domain message safe to
                # pass through at the same status code.
                detail: Any = f"the node refused the escrow (HTTP {status_error.response.status_code})"
                try:
                    resp_body = status_error.response.json()
                    if isinstance(resp_body, dict) and isinstance(resp_body.get("detail"), str):
                        detail = resp_body["detail"]
                except ValueError:
                    pass
                raise HTTPException(status_code=status_error.response.status_code, detail=detail) from exc
            # Timeout / 5xx / ambiguous post-send failure: the lock may still
            # have landed — the replay dedup makes a retry safe.
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="the escrow relay could not reach the settlement node; the request can be retried",
            ) from exc

        contract_id = chain_response.get("contract_id") if isinstance(chain_response, dict) else None
        row = EscrowRelay(client_id=client_id, job_id=job_id, lock_hash=lock_hash, contract_id=contract_id)
        self.session.add(row)
        self.session.commit()
        # Audit: one line per relay — never log lock_tx or signature content.
        logger.info(
            "Escrow relayed: client_id=%s job_id=%s contract_id=%s",
            client_id,
            job_id,
            contract_id,
        )
        return {"contract_id": contract_id, "duplicate": bool(chain_response.get("duplicate"))}
