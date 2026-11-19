"""Cross-chain bridge transfer lifecycle and proof validation.

Facade module: the implementation is decomposed into sibling mixins under
``cross_chain/`` (pure code motion — ``BridgeTransferMixin`` keeps the same
method surface it always had):

- ``bridge_transfer_intake`` — lock admission gates + ``initiate_transfer``
- ``bridge_transfer_confirm`` — confirm/refund/release flows + queries
- ``bridge_transfer_proof`` — ``build_proof`` + proof validation
- ``bridge_transfer_finalizer`` — header sync, relayer, finalizer loop, ledger
"""

from __future__ import annotations

from .bridge_transfer_confirm import BridgeTransferConfirmMixin as BridgeTransferConfirmMixin
from .bridge_transfer_finalizer import (
    _FINALIZER_DEADLINE_FRACTION as _FINALIZER_DEADLINE_FRACTION,
)
from .bridge_transfer_finalizer import BridgeTransferFinalizerMixin as BridgeTransferFinalizerMixin
from .bridge_transfer_intake import BridgeTransferIntakeMixin as BridgeTransferIntakeMixin
from .bridge_transfer_reconcile import BridgeTransferReconcileMixin as BridgeTransferReconcileMixin
from .bridge_transfer_proof import BridgeTransferProofMixin as BridgeTransferProofMixin


class BridgeTransferMixin(
    BridgeTransferIntakeMixin,
    BridgeTransferConfirmMixin,
    BridgeTransferProofMixin,
    BridgeTransferReconcileMixin,
    BridgeTransferFinalizerMixin,
):
    """Cross-chain transfer lock/confirm/refund and batch operations."""
