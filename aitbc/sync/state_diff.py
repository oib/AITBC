"""Block-to-block state diff for delta sync.

Computes the diff between two account states (e.g., block N and block N+K),
encoding only the changes for compact transmission during delta sync.
Uses ``aitbc.network.compression`` (from v0.6.0) for serialization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.network.compression import compress_json, decompress_json

logger = get_logger(__name__)


@dataclass
class AccountChange:
    """A change to a single account between two block heights."""

    address: str
    old_balance: int
    new_balance: int
    old_nonce: int
    new_nonce: int
    is_new: bool = False  # account didn't exist before
    is_deleted: bool = False  # account was deleted

    @property
    def balance_changed(self) -> bool:
        return self.old_balance != self.new_balance

    @property
    def nonce_changed(self) -> bool:
        return self.old_nonce != self.new_nonce

    def to_dict(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "old_balance": self.old_balance,
            "new_balance": self.new_balance,
            "old_nonce": self.old_nonce,
            "new_nonce": self.new_nonce,
            "is_new": self.is_new,
            "is_deleted": self.is_deleted,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AccountChange:
        return cls(
            address=data["address"],
            old_balance=data["old_balance"],
            new_balance=data["new_balance"],
            old_nonce=data["old_nonce"],
            new_nonce=data["new_nonce"],
            is_new=data.get("is_new", False),
            is_deleted=data.get("is_deleted", False),
        )


@dataclass
class StateDiff:
    """Diff between two account states (e.g., block N and block N+K)."""

    from_height: int
    to_height: int
    changes: list[AccountChange] = field(default_factory=list)
    from_state_root: str = ""
    to_state_root: str = ""
    chain_id: str = ""
    state_root_before: str = ""  # alias for from_state_root
    state_root_after: str = ""  # alias for to_state_root

    def __post_init__(self) -> None:
        # Sync alias fields
        if self.from_state_root and not self.state_root_before:
            self.state_root_before = self.from_state_root
        if self.to_state_root and not self.state_root_after:
            self.state_root_after = self.to_state_root
        if self.state_root_before and not self.from_state_root:
            self.from_state_root = self.state_root_before
        if self.state_root_after and not self.to_state_root:
            self.to_state_root = self.state_root_after

    @property
    def new_accounts(self) -> list[dict[str, Any]]:
        """Accounts created in this diff (derived from changes with is_new=True)."""
        return [{"address": c.address, "balance": c.new_balance, "nonce": c.new_nonce} for c in self.changes if c.is_new]

    @property
    def removed_accounts(self) -> list[str]:
        """Accounts removed in this diff (derived from changes with is_deleted=True)."""
        return [c.address for c in self.changes if c.is_deleted]

    def is_empty(self) -> bool:
        """Return True if there are no changes."""
        return len(self.changes) == 0

    def size_ratio(self, total_accounts: int) -> float:
        """Return ratio of changed accounts to total.

        Used for the delta threshold: if the ratio exceeds
        ``SYNC_DELTA_MAX_RATIO`` (default 0.3), the caller falls back to
        full sync.
        """
        if total_accounts <= 0:
            return 1.0 if not self.is_empty() else 0.0
        return len(self.changes) / total_accounts

    def size_bytes(self) -> int:
        """Estimated serialized size in bytes."""
        return len(self.changes) * 100 + 200

    def is_too_large(self, full_state_size: int, threshold: float = 0.5) -> bool:
        """Check if delta is too large (should fall back to full sync)."""
        if full_state_size <= 0:
            return False
        return self.size_bytes() > threshold * full_state_size

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_height": self.from_height,
            "to_height": self.to_height,
            "from_state_root": self.from_state_root,
            "to_state_root": self.to_state_root,
            "chain_id": self.chain_id,
            "changes": [c.to_dict() for c in self.changes],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StateDiff:
        return cls(
            from_height=data["from_height"],
            to_height=data["to_height"],
            from_state_root=data.get("from_state_root", ""),
            to_state_root=data.get("to_state_root", ""),
            chain_id=data.get("chain_id", ""),
            changes=[AccountChange.from_dict(c) for c in data.get("changes", [])],
        )

    def encode(self) -> bytes:
        """Serialize to compressed bytes for transmission."""
        return compress_json(self.to_dict())

    @classmethod
    def decode(cls, data: bytes) -> StateDiff:
        """Deserialize from compressed bytes."""
        return cls.from_dict(decompress_json(data))


def compute_state_diff(
    old_accounts: dict[str, tuple[int, int]],  # address → (balance, nonce)
    new_accounts: dict[str, tuple[int, int]],
    from_height: int,
    to_height: int,
    from_state_root: str = "",
    to_state_root: str = "",
    chain_id: str = "",
    state_root_before: str = "",
    state_root_after: str = "",
) -> StateDiff:
    """Compute the diff between two account states.

    Detects: new accounts, deleted accounts, balance changes, nonce changes.
    Accepts both ``from_state_root``/``to_state_root`` and
    ``state_root_before``/``state_root_after`` parameter names for
    backward compatibility.
    """
    # Resolve state root aliases
    if not from_state_root and state_root_before:
        from_state_root = state_root_before
    if not to_state_root and state_root_after:
        to_state_root = state_root_after

    changes: list[AccountChange] = []
    all_addresses = set(old_accounts.keys()) | set(new_accounts.keys())
    for addr in all_addresses:
        old = old_accounts.get(addr)
        new = new_accounts.get(addr)
        if old is None and new is not None:
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
                changes.append(
                    AccountChange(
                        address=addr,
                        old_balance=old[0],
                        new_balance=new[0],
                        old_nonce=old[1],
                        new_nonce=new[1],
                    )
                )

    diff = StateDiff(
        from_height=from_height,
        to_height=to_height,
        changes=changes,
        from_state_root=from_state_root,
        to_state_root=to_state_root,
        chain_id=chain_id,
    )
    logger.debug(
        "Computed state diff [%d→%d] chain=%s: %d changes",
        from_height,
        to_height,
        chain_id,
        len(changes),
    )
    return diff


# --- Backward-compatible function wrappers ---


def encode_state_diff(diff: StateDiff) -> bytes:
    """Encode a StateDiff for transmission (compressed). Backward compat."""
    return diff.encode()


def decode_state_diff(data: bytes) -> StateDiff:
    """Decode a StateDiff from compressed bytes. Backward compat."""
    return StateDiff.decode(data)


def apply_state_diff(
    diff: StateDiff,
    account_map: dict[str, Any],
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
            if isinstance(account, dict):
                account["balance"] = change.new_balance
                account["nonce"] = change.new_nonce
            else:
                account.balance = change.new_balance
                account.nonce = change.new_nonce
            changed.append(change.address)
    return changed
