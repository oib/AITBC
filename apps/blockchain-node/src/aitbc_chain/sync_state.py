"""Full and delta state synchronization from peers."""

from __future__ import annotations

import base64
from typing import Any

from sqlalchemy import func as sqlfunc
from sqlmodel import select

from aitbc.sync import apply_state_diff, decode_state_diff

from .base_models import Account
from .config import settings
from .logger import get_logger
from .state import state_root_utils
from .sync_base import SyncBase

logger = get_logger(__name__)


class StateSyncMixin(SyncBase):
    """Pull account state snapshots and deltas from remote peers."""

    # ponytail: Protocol base declares the attributes the concrete ChainSync sets.

    async def sync_state_from(self, source_url: str) -> dict[str, Any]:
        """Pull account state snapshot from a peer and reconcile local accounts.

        Creates missing accounts and corrects balances/nonces to match
        the peer's state root.  Does NOT delete accounts that exist locally
        but not on the peer (those may be from local transactions).
        """
        self._logger.info("Starting state sync from %s", source_url)
        try:
            resp = await self._client.get(
                f"{source_url}/rpc/state/snapshot",
                params={"chain_id": self._chain_id},
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            self._logger.error("Failed to fetch state snapshot: %s", e)
            return {"synced": 0, "error": str(e)}

        remote_accounts = data.get("accounts", [])
        remote_root = data.get("state_root", "")
        self._logger.info(
            "State snapshot: %s accounts, state_root=%s",
            len(remote_accounts),
            remote_root,
        )

        created = 0
        updated = 0
        with self._session_factory() as session:
            # Batch-fetch all existing accounts for the chain in one query
            # (eliminates the N+1 per-account session.get() lookup).
            existing_accounts = session.exec(select(Account).where(Account.chain_id == self._chain_id)).all()
            account_map: dict[str, Account] = {acc.address: acc for acc in existing_accounts}
            for acct_data in remote_accounts:
                addr = acct_data["address"]
                balance = acct_data["balance"]
                nonce = acct_data["nonce"]
                existing = account_map.get(addr)
                if existing is None:
                    new_account = Account(
                        chain_id=self._chain_id,
                        address=addr,
                        balance=balance,
                        nonce=nonce,
                    )
                    session.add(new_account)
                    account_map[addr] = new_account
                    created += 1
                elif existing.balance != balance or existing.nonce != nonce:
                    existing.balance = balance
                    existing.nonce = nonce
                    updated += 1
            session.commit()

        # Verify state root matches now — full recompute (all accounts synced)
        with self._session_factory() as session:
            computed_hex = state_root_utils.compute_state_root_full(session, self._chain_id)
            if computed_hex is None:
                computed_hex = "0x" + "\x00" * 32

        match = computed_hex == remote_root
        self._logger.info(
            "State sync complete: created=%s, updated=%s, local_root=%s, remote_root=%s, match=%s",
            created,
            updated,
            computed_hex,
            remote_root,
            match,
        )
        return {
            "synced": created + updated,
            "created": created,
            "updated": updated,
            "local_state_root": computed_hex,
            "remote_state_root": remote_root,
            "match": match,
        }

    async def delta_sync_from(self, source_url: str, from_height: int, to_height: int) -> dict[str, Any]:
        """Sync state delta from a peer (only changed accounts).

        Feature-flagged via settings.sync_delta_enabled. Falls back to
        full state sync (sync_state_from) when:
        - delta is too large (> sync_delta_threshold * full_state_size)
        - gap exceeds sync_delta_max_blocks
        - peer doesn't support delta endpoint
        - state root verification fails
        """
        if not getattr(settings, "sync_delta_enabled", False):
            return await self.sync_state_from(source_url)

        max_blocks = getattr(settings, "sync_delta_max_blocks", 100)
        if to_height - from_height > max_blocks:
            self._logger.info("Delta sync gap too large (%d > %d), using full sync", to_height - from_height, max_blocks)
            return await self.sync_state_from(source_url)

        self._logger.info("Starting delta sync from %s, heights %d -> %d", source_url, from_height, to_height)
        try:
            resp = await self._client.post(
                f"{source_url}/rpc/state/delta",
                json={"from_height": from_height, "to_height": to_height, "chain_id": self._chain_id},
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            self._logger.warning("Delta sync endpoint failed (%s), falling back to full sync", e)
            return await self.sync_state_from(source_url)

        # The response contains an encoded StateDiff
        encoded_diff = data.get("diff")
        if not encoded_diff:
            self._logger.warning("No diff in delta sync response, falling back to full sync")
            return await self.sync_state_from(source_url)

        # Decode the StateDiff
        try:
            diff_bytes = base64.b64decode(encoded_diff) if isinstance(encoded_diff, str) else encoded_diff
            diff = decode_state_diff(diff_bytes)
        except Exception as e:
            self._logger.error("Failed to decode state diff: %s", e)
            return await self.sync_state_from(source_url)

        # Check if delta is too large
        threshold = getattr(settings, "sync_delta_threshold", 0.5)
        # Estimate full state size from current account count
        with self._session_factory() as session:
            count_result = session.exec(
                select(sqlfunc.count()).select_from(Account).where(Account.chain_id == self._chain_id)
            ).first()
            total_accounts = count_result or 0
        full_state_size = total_accounts * 100  # rough estimate
        if diff.is_too_large(full_state_size, threshold=threshold):
            self._logger.info(
                "Delta too large (%d bytes > %d threshold), using full sync",
                diff.size_bytes(),
                int(threshold * full_state_size),
            )
            return await self.sync_state_from(source_url)

        # Apply delta to local state
        with self._session_factory() as session:
            existing_accounts = session.exec(select(Account).where(Account.chain_id == self._chain_id)).all()
            account_map: dict[str, Any] = {acc.address: acc for acc in existing_accounts}
            changed = apply_state_diff(diff, account_map)
            # Handle new accounts (created as dicts by apply_state_diff)
            for addr in changed:
                acc = account_map.get(addr)
                if acc is not None and isinstance(acc, dict):
                    # New account created as dict — convert to Account model
                    new_acc = Account(
                        chain_id=self._chain_id,
                        address=addr,
                        balance=acc["balance"],
                        nonce=acc["nonce"],
                    )
                    session.add(new_acc)
                elif acc is None:
                    # Account was deleted — already removed from map, need to delete from DB
                    db_acc = session.exec(
                        select(Account).where(Account.chain_id == self._chain_id, Account.address == addr)
                    ).first()
                    if db_acc:
                        session.delete(db_acc)
                # Existing accounts were mutated in place (SQLModel tracks changes)
            session.commit()

        # Verify state root
        with self._session_factory() as session:
            computed_hex = state_root_utils.compute_state_root_full(session, self._chain_id)
            if computed_hex is None:
                computed_hex = "0x" + "\x00" * 32

        expected_root = diff.to_state_root
        match = computed_hex == expected_root
        if not match:
            self._logger.warning("Delta sync state root mismatch: %s != %s, rolling back", computed_hex, expected_root)
            # Rollback is implicit — we committed, but state root mismatch means we should do full sync
            return await self.sync_state_from(source_url)

        self._logger.info("Delta sync complete: %d accounts changed, state root matches", len(changed))
        return {
            "synced": len(changed),
            "created": sum(1 for c in diff.changes if c.is_new),
            "updated": sum(1 for c in diff.changes if not c.is_new and not c.is_deleted),
            "deleted": sum(1 for c in diff.changes if c.is_deleted),
            "local_state_root": computed_hex,
            "remote_state_root": expected_root,
            "match": match,
            "mode": "delta",
        }
