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
    _tee_attests_computation as _tee_attests_computation,
    _validate_evm_receipt_target as _validate_evm_receipt_target,
    get_receipt_of_record as get_receipt_of_record,
)
from .payments_refund import PaymentRefundMixin
from .payments_release import PaymentReleaseMixin

# The mixin chain is PaymentFundingMixin -> PaymentEscrowMixin -> PaymentCoreMixin,
# with PaymentReleaseMixin / PaymentRefundMixin on PaymentCoreMixin; listing the
# three leaves keeps the MRO consistent.

# P2.1: high-value jobs require a verified ZK receipt proof before escrow release.
_ZK_THRESHOLD_AIT = Decimal(os.getenv("COORDINATOR_ZK_HIGH_VALUE_THRESHOLD", "10"))
_ZK_REQUIRE_PROOF = os.getenv("COORDINATOR_ZK_REQUIRE", "false").lower() == "true"


def _zk_required_for_payment(payment_amount: Decimal | None, job: Job | None) -> bool:
    """Return True when a job payment triggers the ZK-proof escrow gate.

    The gate applies when COORDINATOR_ZK_REQUIRE=true, the job explicitly
    requires a ZK proof, or the payment amount crosses the high-value
    threshold. Whether the requested model actually has a registered circuit
    is decided later when the receipt is generated/verified; the gate must
    not silently downgrade a required proof just because the model is missing.
    """
    if _ZK_THRESHOLD_AIT < 0:
        return False
    if _ZK_REQUIRE_PROOF:
        return True
    if job and job.constraints and job.constraints.get("zk_proof_required"):
        return True
    amount = payment_amount or Decimal("0")
    return _ZK_THRESHOLD_AIT == 0 or amount >= _ZK_THRESHOLD_AIT


class PaymentService(PaymentFundingMixin, PaymentReleaseMixin, PaymentRefundMixin):
    """Service for handling job payments"""
