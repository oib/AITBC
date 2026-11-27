"""Chain transaction status helpers shared across services (#3049).

``sync_block_import`` stores apply-failed transactions as
``status='failed'`` **with** a ``block_height`` — a sealed row is not
proof the value moved. Every lane that adopts chain evidence as terminal
("did the settle land?") must apply the same predicate or the fleet holds
the disagreement by accident: the wallet's ``tx_sealed_confirmed`` and
coordinator-api's settlement reconciler already require confirmed+height;
the market sweepers and the agent-coordinator terminal sweeper drifted
to height-only (#1916 rule, AUDIT-SEALED-FOR-MONEY-DRIFT-1).
"""

from __future__ import annotations

from typing import Any


def tx_sealed_for_money(tx: dict[str, Any] | None) -> bool:
    """True only when ``tx`` provably applied value: ``status == 'confirmed'``
    AND a ``block_height``.

    ``status='failed'`` rows carry a height (they sealed into a block and
    the apply reverted — no value moved); ``status='rejected'`` rows are
    durable dead letters; mempool views carry ``state='pending'`` and no
    sealed status. None of those may close the books on a payment.
    """
    if not isinstance(tx, dict):
        return False
    return tx.get("status") == "confirmed" and tx.get("block_height") is not None
