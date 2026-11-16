"""GPU ``_vt_*`` validation gates for ``StateTransition.validate_transaction`` (#1860 pure-move split).

Import ``aitbc_chain.state.state_transition`` first (it wires these
mixins into ``StateTransition``); this module is not meant to be imported
directly.
"""

from __future__ import annotations

from decimal import Decimal

from sqlmodel import select

from ..config import settings
from .gpu_resources import (
    GPURegistration,
    gpu_allocate_admission_error,
    gpu_allocate_deactivated_error,
    gpu_deregister_error,
    retired_gpu_error,
)
from .state_transition import _TxValidationCtx, _gpu_price_per_hour_in_range
from aitbc.crypto.signature_recovery import canonical_address


class _ValidationGpuMixin:
    def _vt_gpu_register_fields(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        if ctx.tx_type != "GPU_REGISTER":
            return None
        ctx.payload = ctx.tx_data.get("payload") or {}
        if not ctx.payload.get("gpu_id"):
            return (False, "GPU_REGISTER payload must include gpu_id")
        if not ctx.payload.get("miner_id"):
            return (False, "GPU_REGISTER payload must include miner_id")
        if not ctx.payload.get("model"):
            return (False, "GPU_REGISTER payload must include model")
        if not isinstance(ctx.payload.get("memory_gb"), int):
            return (False, "GPU_REGISTER payload must include integer memory_gb")
        try:
            gpu_price = Decimal(str(ctx.payload.get("price_per_hour", 0)))
        except (ArithmeticError, TypeError, ValueError):
            return (False, "GPU_REGISTER payload must include a valid price_per_hour")
        if ctx.block_version >= 25 and not _gpu_price_per_hour_in_range(gpu_price):
            # v25 (#1566): negative/NaN/Infinity/oversized prices were
            # storable pre-gate; bound them now that the column is
            # Numeric(20,8). Below v25 the parse-only rule replays history.
            return (False, "GPU_REGISTER price_per_hour out of range")
        if ctx.value != 0:
            return (False, "GPU_REGISTER must have value=0")
        return None

    def _vt_gpu_register_ownership(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        if ctx.tx_type != "GPU_REGISTER":
            return None
        if ctx.block_version >= 7:
            # Ownership gate: only the recorded registrant may update an
            # existing gpu_id. registered_by is the first registrant's tx
            # sender and cannot be rewritten from the payload, so a
            # foreign signed GPU_REGISTER can't reprice, re-spec, or
            # reactivate someone else's GPU. Fails closed if the row
            # carries no registrant.
            gpu_id = str(ctx.payload.get("gpu_id"))
            existing = ctx.session.exec(
                select(GPURegistration).where(GPURegistration.chain_id == ctx.chain_id, GPURegistration.gpu_id == gpu_id)
            ).first()
            if existing is not None:
                if not existing.registered_by:
                    return (False, f"GPU {gpu_id} has no registrant on record; updates are not permitted")
                if canonical_address(existing.registered_by) != canonical_address(ctx.sender_addr):
                    return (
                        False,
                        f"GPU_REGISTER for {gpu_id} must come from its registrant {existing.registered_by}, got {ctx.sender_addr}",
                    )
        return None

    def _vt_gpu_deregister(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        if ctx.tx_type != "GPU_DEREGISTER" or ctx.block_version < 10:
            return None
        # v10: the registrant takes its own GPU out of service. The row stays (status ``deactivated``) so
        # ``registered_by`` keeps guarding the id and the registrant can reactivate it by re-registering.
        # The rule lives in state/gpu_resources.py::gpu_deregister_error, shared with mempool admission
        # (rpc/transactions.py) so a transaction the proposer would drop is refused at the door too.
        error = gpu_deregister_error(ctx.session, ctx.chain_id, ctx.tx_data.get("payload"), ctx.sender_addr)
        if error:
            return (False, error)
        return None

    def _vt_gpu_allocate(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        if ctx.tx_type != "GPU_ALLOCATE":
            return None
        ctx.payload = ctx.tx_data.get("payload") or {}
        if not ctx.payload.get("gpu_id"):
            return (False, "GPU_ALLOCATE payload must include gpu_id")
        if ctx.block_version >= 10:
            # v10: a deactivated GPU takes no new allocations. Checked here, before apply mutates anything.
            # The rule lives in state/gpu_resources.py::gpu_allocate_deactivated_error, shared with mempool
            # admission (rpc/transactions.py) so a transaction the proposer would drop is refused at the door too.
            deactivated_error = gpu_allocate_deactivated_error(ctx.session, ctx.chain_id, ctx.payload)
            if deactivated_error:
                return (False, deactivated_error)
        if ctx.block_version >= 16:
            # v16 (GPU-ADMISSION-1 #384): allocation_id is mandatory and gpu_id must
            # resolve — apply can no longer be the first place that checks, and it can
            # no longer mint a nondeterministic alloc_<uuid4> for a sealed tx.
            admission_error = gpu_allocate_admission_error(ctx.session, ctx.chain_id, ctx.payload)
            if admission_error:
                return (False, admission_error)
        if not ctx.payload.get("client_id"):
            return (False, "GPU_ALLOCATE payload must include client_id")
        try:
            float(ctx.payload.get("duration_hours", 0))
            Decimal(str(ctx.payload.get("total_cost", 0)))
        except (ArithmeticError, TypeError, ValueError):
            return (False, "GPU_ALLOCATE payload must include valid duration_hours and total_cost")
        if ctx.value != 0:
            return (False, "GPU_ALLOCATE must have value=0")
        return None

    def _vt_retired_gpu(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        if ctx.block_version < 10:
            return None
        # v10: the retired-id door (GPU_RETIRED_IDS) is consensus, not just admission — a
        # proposer that skipped admission cannot re-register or allocate a retired gpu_id
        # via a crafted block. Below v10 this never fires, so replay is unchanged. The env
        # list MUST be identical on every node once v10 is live; fleet-config-check.sh
        # compares it across hosts.
        retired_error = retired_gpu_error(ctx.tx_type, ctx.tx_data.get("payload"), settings.gpu_retired_id_set())
        if retired_error:
            return (False, retired_error)
        return None
