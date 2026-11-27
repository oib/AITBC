"""Payment service for job payments

Facade: the implementation is split across payments_core / payments_funding /
payments_escrow / payments_release / payments_refund / payments_helpers.
This module re-exports the moved names so the historical import surface
(`from .payments import PaymentService, _find_http_status_error, ...`) and the
test patch targets (`payments.settings`, `payments.AsyncAITBCHTTPClient`,
`payments._ZK_REQUIRE_PROOF`) are unchanged.
"""

from __future__ import annotations

import os

from decimal import Decimal
from typing import Any

from aitbc.network import AsyncAITBCHTTPClient  # noqa: F401  (test patch target)
from ....config import settings  # noqa: F401  (test patch target)
from ...infrastructure.domain.job import Job
from .payments_funding import PaymentFundingMixin
from .payments_helpers import (
    _OPS_ERRORS as _OPS_ERRORS,
    _bind_evm_agreement_or_fail as _bind_evm_agreement_or_fail,
    _computation_is_correct as _computation_is_correct,
    _escrow_failure_reason as _escrow_failure_reason,
    _escrow_record_is_settled as _escrow_record_is_settled,
    _fail_evm_payment as _fail_evm_payment,
    _find_http_status_error as _find_http_status_error,
    _is_settlement_underfunded as _is_settlement_underfunded,
    _lookup_chain_lock as _lookup_chain_lock,
    _lookup_chain_refund as _lookup_chain_refund,
    _lookup_escrow_record as _lookup_escrow_record,
    _parse_settled_at as _parse_settled_at,
    _resolve_authoritative_inputs as _resolve_authoritative_inputs,
    _validate_evm_receipt_target as _validate_evm_receipt_target,
    get_receipt_of_record as get_receipt_of_record,
)
from .payments_refund import PaymentRefundMixin
from .payments_release import PaymentReleaseMixin

# The mixin chain is PaymentFundingMixin -> PaymentEscrowMixin -> PaymentCoreMixin,
# with PaymentReleaseMixin / PaymentRefundMixin on PaymentCoreMixin; listing the
# three leaves keeps the MRO consistent.

# P2.1: high-value jobs require a verified ZK receipt proof before escrow release.
# #3079: the only shipped circuit is a toy and the proof binds nothing
# job-specific, so the gate is decorative — it must not carry value by
# default. The default is -1, the codebase's disabled convention for the
# *automatic* high-value trigger: explicit requirements
# (COORDINATOR_ZK_REQUIRE, per-job zk_proof_required) still gate, but no job
# is gated by price alone. Deployments that deliberately opted in keep their
# configured value; set a non-negative AIT amount to re-enable the threshold.
_ZK_THRESHOLD_AIT = Decimal(os.getenv("COORDINATOR_ZK_HIGH_VALUE_THRESHOLD", "-1"))
_ZK_REQUIRE_PROOF = os.getenv("COORDINATOR_ZK_REQUIRE", "false").lower() == "true"


def _zk_required_for_constraints(constraints: dict[str, Any] | None, payment_amount: Decimal | None) -> bool:
    """Return True when a job's constraints/price trigger the ZK-proof gate.

    The gate applies when COORDINATOR_ZK_REQUIRE=true, the job explicitly
    requires a ZK proof, or the payment amount crosses the high-value
    threshold. Whether the requested model actually has a registered circuit
    is decided by the caller; the gate must not silently downgrade a required
    proof just because the model is missing.

    #3079: a negative threshold disables only the *automatic* amount trigger —
    explicit requirements above still apply, matching the documented "-1
    disables the automatic high-value gate" contract. Previously the early
    return made -1 a silent master-off that ignored even an explicit
    zk_proof_required.
    """
    if _ZK_REQUIRE_PROOF:
        return True
    if constraints and constraints.get("zk_proof_required"):
        return True
    if _ZK_THRESHOLD_AIT < 0:
        return False
    amount = payment_amount or Decimal("0")
    return _ZK_THRESHOLD_AIT == 0 or amount >= _ZK_THRESHOLD_AIT


def _zk_required_for_payment(payment_amount: Decimal | None, job: Job | None) -> bool:
    """Return True when a job payment triggers the ZK-proof escrow gate."""
    constraints = job.constraints if job is not None and isinstance(job.constraints, dict) else None
    return _zk_required_for_constraints(constraints, payment_amount)


class PaymentService(PaymentFundingMixin, PaymentReleaseMixin, PaymentRefundMixin):
    """Service for handling job payments"""
