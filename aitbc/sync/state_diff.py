"""Block-to-block state diff for delta sync.

Computes the diff between two account states (e.g., block N and block N+K),
encoding only the changes for compact transmission during delta sync.
Uses ``aitbc.network.compress_json`` (from v0.6.0) for serialization.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aitbc.network.compression import compress_json, decompress_json


@dataclass
class AccountChange:
    """A single account state change in a diff."""

    address: str
    old_balance: int
    new_balance: int
    old_nonce: int
    new_nonce: int
    is_new: bool = False  # account didn't exist before
    is_deleted: bool = False  # account was deleted


@dataclass
class StateDiff:
    """State diff between two block heights.

    Contains only the accounts that changed. Can be encoded for
    transmission and applied to local state.
    """

    from_height: int
    to_height: int
    changes: list[AccountChange]
    from_state_root: str
    to_state_root: str

    def size_bytes(self) -> int:
        """Estimated serialized size in bytes."""
        # Each change has address (~40 chars) + 4 ints + 2 bools
        # Rough estimate: ~100 bytes per change + overhead
        return len(self.changes) * 100 + 200

    def is_too_large(self, full_state_size: int, threshold: float = 0.5) -> bool:
        """Check if delta is too large (should fall back to full sync).

        Returns True if diff size > threshold * full_state_size.
        """
        if full_state_size <= 0:
            return False
        return self.size_bytes() > threshold * full_state_size


def compute_state_diff(
    old_accounts: dict[str, tuple[int, int]],  # {address: (balance, nonce)}
    new_accounts: dict[str, tuple[int, int]],
    from_height: int,
    to_height: int,
    from_state_root: str,
    to_state_root: str,
) -> StateDiff:
    """Compute the diff between two account snapshots.

    Pure function — takes two snapshots, returns a StateDiff.
    Detects: new accounts, deleted accounts, balance changes, nonce changes.
    """
    changes: list[AccountChange] = []
    all_addresses = set(old_accounts.keys()) | set(new_accounts.keys())
    for addr in all_addresses:
        old = old_accounts.get(addr)
        new = new_accounts.get(addr)
        if old is None and new is not None:
            # New account
            changes.append(
                AccountChange(
                    address=addr,
                    old_balance=0,
                    new_balance=new[0],
                    old_nonce=0,
                    new_nonce=new[1],
                    is_new=True,
                )
            )
        elif old is not None and new is None:
            # Deleted account
            changes.append(
                AccountChange(
                    address=addr,
                    old_balance=old[0],
                    new_balance=0,
                    old_nonce=old[1],
                    new_nonce=0,
                    is_deleted=True,
                )
            )
        elif old is not None and new is not None:
            if old[0] != new[0] or old[1] != new[1]:
                # Balance or nonce changed
                changes.append(
                    AccountChange(
                        address=addr,
                        old_balance=old[0],
                        new_balance=new[0],
                        old_nonce=old[1],
                        new_nonce=new[1],
                    )
                )
    return StateDiff(
        from_height=from_height,
        to_height=to_height,
        changes=changes,
        from_state_root=from_state_root,
        to_state_root=to_state_root,
    )


def encode_state_diff(diff: StateDiff) -> bytes:
    """Encode a StateDiff for transmission (compressed).

    Uses JSON serialization + gzip compression (reuse aitbc.network.compression).
    """
    payload = {
        "from_height": diff.from_height,
        "to_height": diff.to_height,
        "from_state_root": diff.from_state_root,
        "to_state_root": diff.to_state_root,
        "changes": [
            {
                "address": c.address,
                "old_balance": c.old_balance,
                "new_balance": c.new_balance,
                "old_nonce": c.old_nonce,
                "new_nonce": c.new_nonce,
                "is_new": c.is_new,
                "is_deleted": c.is_deleted,
            }
            for c in diff.changes
        ],
    }
    return compress_json(payload)


def decode_state_diff(data: bytes) -> StateDiff:
    """Decode a StateDiff from compressed bytes."""
    payload = decompress_json(data)
    changes = [
        AccountChange(
            address=c["address"],
            old_balance=c["old_balance"],
            new_balance=c["new_balance"],
            old_nonce=c["old_nonce"],
            new_nonce=c["new_nonce"],
            is_new=c.get("is_new", False),
            is_deleted=c.get("is_deleted", False),
        )
        for c in payload["changes"]
    ]
    return StateDiff(
        from_height=payload["from_height"],
        to_height=payload["to_height"],
        changes=changes,
        from_state_root=payload["from_state_root"],
        to_state_root=payload["to_state_root"],
    )


def apply_state_diff(
    diff: StateDiff,
    account_map: dict[str, Any],  # Account-like objects with balance/nonce
) -> list[str]:
    """Apply a StateDiff to an account_map.

    Mutates account_map in place. Creates new accounts (as dicts with
    'balance' and 'nonce' keys), updates existing, handles deletions.
    Returns list of changed addresses.
    """
    changed: list[str] = []
    for change in diff.changes:
        if change.is_deleted:
            if change.address in account_map:
                del account_map[change.address]
                changed.append(change.address)
            continue
        if change.is_new or change.address not in account_map:
            account_map[change.address] = {
                "balance": change.new_balance,
                "nonce": change.new_nonce,
            }
            changed.append(change.address)
        else:
            account = account_map[change.address]
            # Handle both dict-style and attribute-style accounts
            if isinstance(account, dict):
                account["balance"] = change.new_balance
                account["nonce"] = change.new_nonce
            else:
                account.balance = change.new_balance
                account.nonce = change.new_nonce
            changed.append(change.address)
    return changed
