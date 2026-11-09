"""Authoritative scalar account reads for state-transition v24 (#1314 layer 2).

``read_current_account`` issues a scalar ``SELECT balance, nonce`` on the
caller's uncommitted transaction. It bypasses the ORM identity map entirely —
raw-SQL writes and ``session.flush()`` output are visible, identity-mapped
``Account`` objects are not consulted — creates no ``Account`` row, and is
never cached across an intervening mutation. Callers that need a mutated
object for ORM writes keep using ``session.get``; this helper is for
verdict/balance checks only.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlmodel import Session

from ..base_models import Account


def read_current_account(session: Session, chain_id: str, address: str) -> tuple[Decimal | int | None, int, bool]:
    """Return ``(balance, nonce, exists)`` for ``address`` as committed-in-tx.

    ``balance`` is ``None`` when the account does not exist (``exists=False``);
    ``nonce`` is 0 in that case. Balance comes back in the column's stored
    units (Numeric → int/Decimal depending on backend).
    """
    row = session.execute(
        text("SELECT balance, nonce FROM account WHERE chain_id = :chain_id AND address = :address"),
        {"chain_id": chain_id, "address": address},
    ).first()
    if row is None:
        return None, 0, False
    return row[0], int(row[1] or 0), True


def prepare_account_for_orm_write(session: Session, chain_id: str, address: str) -> Any | None:
    """Return the ``Account`` ORM object safe for ``+=``/``-=``/APY writes.

    Flushes that account's legitimate pending writes, then expires the
    identity-map instance so the next attribute access reloads committed
    state before the caller computes absolutes. Returns ``None`` when no
    ``Account`` object is loaded (callers that need creation keep their own
    ``_ensure_account`` path). Mechanical guard only — does not prove any
    economic invariant.
    """
    session.flush()
    account = session.get(Account, (chain_id, address))
    if account is not None:
        session.expire(account)
        account = session.get(Account, (chain_id, address))
    return account
