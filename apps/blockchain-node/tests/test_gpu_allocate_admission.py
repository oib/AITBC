"""GPU-ADMISSION-1 (#384): version-gated admission for GPU_ALLOCATE.

FAILING-TEST-FIRST (Phase 1, no implementation). Today GPU_ALLOCATE is in
AUTHORITY_OPEN_TX_TYPES: any funded sender with a good nonce passes
``_validate_transaction_admission`` — a missing ``allocation_id`` is minted
per-host at apply (``alloc_<uuid4>``, nondeterministic) and an unknown
``gpu_id`` dies only at apply after reaching the mempool.

Target rule, armed at ``STATE_TRANSITION_V16_HEIGHT`` (operator ruling
24 Oct: this gate takes v16; multisig-accounts moves to v17 if it lands
second). ``None`` default = unarmed, v15-style.
Below the height nothing changes (replay of sealed eras stays valid); at/after
it, a GPU_ALLOCATE whose payload lacks ``allocation_id`` or names a ``gpu_id``
absent from GPURegistration is refused at the door — same helper-shared door
as ``gpu_allocate_deactivated_error`` (state/gpu_resources.py + the mirrored
branch at rpc/transactions.py ~L223-234). bc-2 currently holds zero
GPU_ALLOCATE txs, so no recorded block is reachable. The existence half is
already retro-consistent (apply always required the registration row); the
divergent half is allocation_id — proven by
``gpu_allocation.allocation_id in CANONICAL_EXCLUDED_COLUMNS``
(side_root_shadow.py: "differs on every host").
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from aitbc.utils import DEFAULT_TX_FEE_UNITS
from aitbc_chain.rpc.transactions import _validate_transaction_admission

CHAIN = "bc-2"
SENDER = "0x" + "aa" * 20


def _allocate_tx(**payload_over: Any) -> dict[str, Any]:
    payload = {"gpu_id": "gpu-live-1", "client_id": "c-1", "duration_hours": 1.0, "total_cost": "1"}
    payload.update(payload_over)
    return {
        "from": SENDER,
        "to": SENDER,
        "amount": 0,
        "fee": DEFAULT_TX_FEE_UNITS,
        "nonce": 0,
        "type": "GPU_ALLOCATE",
        "chain_id": CHAIN,
        "payload": payload,
    }


def _mempool():
    return MagicMock()


def _armed(monkeypatch):
    """Arm the v16 gate at height 1."""
    monkeypatch.setenv("STATE_TRANSITION_V16_HEIGHT", "1")


def test_allocate_missing_allocation_id_refused_when_armed(monkeypatch):
    _armed(monkeypatch)
    with pytest.raises((HTTPException, ValueError)):
        _validate_transaction_admission(_allocate_tx(), _mempool())


def test_allocate_with_allocation_id_still_refused_without_gpu_row(monkeypatch):
    _armed(monkeypatch)
    tx = _allocate_tx(allocation_id="alloc-fixed-1")
    with pytest.raises(
        (HTTPException, ValueError)
    ):  # gpu-live-1 is not registered; door raises ValueError per test_gpu_deregister convention
        _validate_transaction_admission(tx, _mempool())


def test_allocate_unarmed_height_passes_door(monkeypatch):
    monkeypatch.delenv("STATE_TRANSITION_V16_HEIGHT", raising=False)
    try:
        _validate_transaction_admission(_allocate_tx(), _mempool())
    except HTTPException:
        pytest.fail("unarmed gate must not change admission")
