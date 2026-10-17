"""Canonical BRIDGE_LOCK leaf for ``block.bridge_state_root``.

The proposer (``consensus/poa.py``), the importer fallback
(``sync_block_import.py``) and the proof builder/verifier
(``cross_chain/bridge_transfer.py``) must build byte-identical leaves, or the
sealed root and the proofs drawn from it disagree. Every one of them goes
through ``lock_leaf_value``.

From ``bridge_lock_leaf_v2_height`` the leaf also commits to the recipient, so
a Merkle proof binds every field the target chain pays out on. Below it (and
while the height is unset) the historical three-field leaf is kept.
"""

from __future__ import annotations

from ..config import settings


def lock_leaf_v2_active(height: int | None) -> bool:
    """True when a source block at ``height`` seals recipient-bound leaves."""
    threshold = getattr(settings, "bridge_lock_leaf_v2_height", None)
    if threshold is None or not isinstance(height, int) or isinstance(height, bool):
        return False
    return int(height) >= int(threshold)


def lock_leaf_value(transfer_id: str, amount: int, target_chain: str, recipient: str, height: int | None) -> str:
    """Leaf string a lock contributes to the bridge trie at ``height``."""
    if lock_leaf_v2_active(height):
        return f"lock:{transfer_id}:{amount}:{target_chain}:{recipient}"
    return f"lock:{transfer_id}:{amount}:{target_chain}"


def unknown_lock_leaf(tx_hash: str) -> str:
    """Leaf for a sealed lock this node holds no transfer record for."""
    return f"lock:{tx_hash}:0:unknown"
