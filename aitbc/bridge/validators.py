"""Bridge validator set registry with epoch tracking (v0.7.1 §A3).

In-memory cache of validator sets per chain, keyed by epoch. Agent B
creates the persistent SQLModel table (``BridgeValidator``) that backs this
registry. This module provides the lookup/verification logic that the
bridge proof verification path uses.

Epoch semantics:
- Each chain has a monotonically increasing epoch number.
- A validator set is authoritative for the epoch it was registered under.
- Old epochs are retained after ``advance_epoch`` so in-flight transfers
  can still be verified against the validator set that was active when the
  lock occurred (grace period). Pruning of ancient epochs is the caller's
  responsibility.
"""

from __future__ import annotations

import logging

from .types import ValidatorInfo, ValidatorSet

logger = logging.getLogger(__name__)


class ValidatorSetRegistry:
    """In-memory registry of validator sets per chain per epoch."""

    def __init__(self) -> None:
        # chain_id -> epoch -> ValidatorSet
        self._sets: dict[str, dict[int, ValidatorSet]] = {}
        # chain_id -> current epoch number
        self._current_epoch: dict[str, int] = {}

    def register_validator(self, info: ValidatorInfo) -> None:
        """Add or update a validator in the registry.

        If a validator with the same address already exists in the target
        epoch's set, it is replaced. The set's ``total`` is recomputed.
        The current epoch for the chain is advanced if this registration's
        epoch is newer than the tracked current epoch.
        """
        chain_sets = self._sets.setdefault(info.chain_id, {})
        epoch_set = chain_sets.get(info.epoch)
        if epoch_set is None:
            epoch_set = ValidatorSet(chain_id=info.chain_id, epoch=info.epoch)
            chain_sets[info.epoch] = epoch_set
        # Replace if already exists
        epoch_set.validators = [v for v in epoch_set.validators if v.address != info.address]
        epoch_set.validators.append(info)
        epoch_set.total = len(epoch_set.validators)
        # Update current epoch if this is the latest
        if info.epoch >= self._current_epoch.get(info.chain_id, 0):
            self._current_epoch[info.chain_id] = info.epoch

    def get_validator_set(self, chain_id: str, epoch: int | None = None) -> ValidatorSet | None:
        """Get the validator set for a chain at a specific epoch.

        If ``epoch`` is None, returns the current (latest) epoch's set.
        Returns None if the chain or epoch is unknown.
        """
        if epoch is None:
            epoch = self._current_epoch.get(chain_id, 0)
        chain_sets = self._sets.get(chain_id)
        if chain_sets is None:
            return None
        return chain_sets.get(epoch)

    def get_current_epoch(self, chain_id: str) -> int:
        """Get the current epoch number for a chain (0 if unknown)."""
        return self._current_epoch.get(chain_id, 0)

    def is_member(self, address: str, chain_id: str, epoch: int | None = None) -> bool:
        """Check if an address is a member of the validator set."""
        vset = self.get_validator_set(chain_id, epoch)
        if vset is None:
            return False
        return address in vset.addresses

    def advance_epoch(self, chain_id: str, new_set: ValidatorSet) -> int:
        """Advance to a new epoch for a chain.

        The old epoch's set is retained for in-flight transfer verification
        (grace period). Returns the new epoch number.
        """
        new_epoch = new_set.epoch
        self._sets.setdefault(chain_id, {})[new_epoch] = new_set
        self._current_epoch[chain_id] = new_epoch
        return new_epoch

    def remove_inactive(self, chain_id: str, epoch: int) -> int:
        """Remove inactive validators from a specific epoch's set.

        Returns the number of validators removed.
        """
        vset = self.get_validator_set(chain_id, epoch)
        if vset is None:
            return 0
        before = len(vset.validators)
        vset.validators = [v for v in vset.validators if v.is_active]
        vset.total = len(vset.validators)
        return before - len(vset.validators)
