"""Performance bond query endpoints.

Bond state transitions (BOND_LOCK, BOND_RELEASE, BOND_SLASH) are handled by
the normal transaction pipeline. This module exposes read-only bond status
endpoints under /rpc/bond.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import HTTPException, Request
from sqlmodel import select

from aitbc.crypto.signature_recovery import canonical_address
from aitbc.rate_limiting import rate_limit

from ..base_models import Bond
from ..database import session_scope
from ..logger import get_logger
from .utils import get_chain_id

_logger = get_logger(__name__)


@rate_limit(rate=100, per=60)
async def get_bond(request: Request, bond_id: str, chain_id: str | None = None) -> dict[str, Any]:
    chain_id = get_chain_id(chain_id)
    with session_scope(chain_id) as session:
        bond = session.exec(
            select(Bond).where(Bond.chain_id == chain_id, Bond.bond_id == bond_id)
        ).first()
        if not bond:
            raise HTTPException(status_code=404, detail=f"Bond not found: {bond_id}")
        return {
            "success": True,
            "bond_id": bond.bond_id,
            "provider": bond.provider,
            "amount": bond.amount,
            "status": bond.status,
            "locked_until": bond.locked_until.isoformat() if bond.locked_until else None,
            "created_tx_hash": bond.created_tx_hash,
            "released_tx_hash": bond.released_tx_hash,
            "slashed_tx_hash": bond.slashed_tx_hash,
            "created_at": bond.created_at.isoformat() if bond.created_at else None,
            "updated_at": bond.updated_at.isoformat() if bond.updated_at else None,
        }


@rate_limit(rate=100, per=60)
async def list_bonds(request: Request, provider: str, chain_id: str | None = None) -> dict[str, Any]:
    chain_id = get_chain_id(chain_id)
    with session_scope(chain_id) as session:
        bonds = session.exec(
            select(Bond).where(Bond.chain_id == chain_id, Bond.provider == canonical_address(provider))
        ).all()
        return {
            "success": True,
            "provider": provider,
            "bonds": [
                {
                    "bond_id": b.bond_id,
                    "amount": b.amount,
                    "status": b.status,
                    "locked_until": b.locked_until.isoformat() if b.locked_until else None,
                }
                for b in bonds
            ],
        }
