"""Shared state root computation utilities.

Used by both consensus/poa.py (block proposal) and sync.py (block verification).
"""

from __future__ import annotations

from sqlmodel import Session, select

from ..logger import get_logger
from ..models import Account
from .merkle_patricia_trie import StateManager

logger = get_logger(__name__)


def compute_state_root_full(session: Session, chain_id: str) -> str | None:
    """Compute state root from current account state (full recompute).

    Loads ALL accounts from the DB and builds a new trie.
    Use as fallback when no account_map is available.
    """
    try:
        state_manager = StateManager()
        accounts = session.exec(select(Account).where(Account.chain_id == chain_id)).all()
        account_dict = {acc.address: acc for acc in accounts}
        root = state_manager.compute_state_root(account_dict)
        return "0x" + root.hex()
    except Exception as e:
        logger.warning("Failed to compute state root (full): %s", e)
        return None


def compute_state_root_incremental(
    session: Session,
    chain_id: str,
    account_map: dict[str, Account],
    changed_addresses: set[str],
) -> str | None:
    """Compute state root incrementally.

    Builds the trie from the batch-fetched account_map, then updates only
    the changed accounts. This avoids loading ALL accounts from the DB.

    Args:
        session: Database session (for reading updated account balances).
        chain_id: Chain identifier.
        account_map: In-memory account state (pre-fetched from DB).
        changed_addresses: Set of addresses that were modified during tx processing.

    Returns:
        State root hex string (e.g., "0x..."), or None on error.
    """
    try:
        state_manager = StateManager()
        # Build initial trie from account_map (already batch-fetched)
        for address, account in sorted(account_map.items()):
            state_manager.update_account(address, account.balance, account.nonce)
        # Incrementally update only accounts that changed during the tx loop
        for address in changed_addresses:
            acc = session.get(Account, (chain_id, address))
            if acc is not None:
                state_manager.update_account(address, acc.balance, acc.nonce)
            else:
                # Account may have been deleted — set to 0
                state_manager.update_account(address, 0, 0)
        root = state_manager.get_root()
        return "0x" + root.hex()
    except Exception as e:
        logger.warning("Failed to compute state root (incremental): %s", e)
        return None
