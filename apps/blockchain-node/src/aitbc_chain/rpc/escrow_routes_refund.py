"""Escrow refund read/settle path for the escrow RPC split (#1867 pure-move).

Import ``aitbc_chain.rpc.escrow_routes`` first (it wires these
modules into the ``escrow_routes`` facade); this module is not meant to be
imported directly. All facade-owned names are reached via ``_er.`` so
monkeypatching ``escrow_routes.<name>`` stays visible."""

from __future__ import annotations

from . import escrow_routes as _er


@_er.dataclass(frozen=True)
class _RefundRow:
    """The escrow row as the refund's guards read it."""

    record: _er.Escrow | None
    locked_units: int | None
    refunded: bool
    released: bool


def _read_refund_row(job_id: str) -> _er._RefundRow:
    with _er.session_scope() as session:
        record = session.get(_er.Escrow, job_id)
        if not record:
            return _er._RefundRow(None, None, False, False)
        return _er._RefundRow(record, record.amount, record.refunded_at is not None, record.released_at is not None)


@_er.dataclass(frozen=True)
class _RefundPlan:
    """What the locked read found: the contract to refund, why, and the chain-locked ceiling."""

    contract_id: str
    reason: str
    locked_units: int | None


async def _refund_read_locked(
    mgr: _er.Any, job_id: str, body: dict[str, _er.Any] | None
) -> dict[str, _er.Any] | _er._RefundPlan:
    """Read the row under the escrow's cross-worker lock (#780): the stored result for a
    refund that already happened, else what the settle step needs.

    The sealed-lock and v2-era gates sit between this and the settle step, in the
    route, so they stay on the route's own error list in the published OpenAPI spec.
    """
    # Reconciliation/duplicate refund handling: a refund is only final when the
    # same job_id has an ESCROW_REFUND transaction on-chain.
    row = _er._RefundRow(None, None, False, False)
    try:
        row = await _er.run_in_threadpool(_er._read_refund_row, job_id)
    except Exception as e:
        _er._logger.warning("Failed to check escrow refund state: %s", e)
    record, locked_units = row.record, row.locked_units
    if row.refunded:
        existing_refund = await _er._find_existing_refund(job_id)
        refund_tx_hash = existing_refund or (record.refund_tx_hash if record else None)
        if refund_tx_hash:
            return {
                "success": True,
                "contract_id": "",
                "job_id": job_id,
                "message": "Escrow already refunded",
                "refund_tx_hash": refund_tx_hash,
            }
    if row.released:
        raise _er.HTTPException(
            status_code=400,
            detail=f"Escrow for job_id={job_id} has already been released",
        )

    contract_id = await _er._find_contract_id(mgr, job_id)
    if contract_id is None:
        raise _er.HTTPException(status_code=404, detail=f"No escrow contract found for job_id={job_id}")
    contract = mgr.escrow_contracts.get(contract_id)
    if contract and contract.state in {
        _er.EscrowState.JOB_COMPLETED,
        _er.EscrowState.RELEASED,
        _er.EscrowState.REFUNDED,
        _er.EscrowState.EXPIRED,
    }:
        if contract.state == _er.EscrowState.REFUNDED:
            existing_refund = await _er._find_existing_refund(job_id)
            if existing_refund:
                return {
                    "success": True,
                    "contract_id": contract_id,
                    "job_id": job_id,
                    "message": "Escrow already refunded",
                    "refund_tx_hash": existing_refund,
                }
            # B-residue: the contract was marked refunded but no ESCROW_REFUND landed.
            _er._logger.warning(
                "Escrow %s for job %s is REFUNDED in memory but not on-chain; resetting for a real refund",
                contract_id,
                job_id,
            )
            contract.refunded_amount = _er.Decimal("0")
            contract.state = _er.EscrowState.FUNDED
            mgr.active_contracts.add(contract_id)
        else:
            raise _er.HTTPException(status_code=400, detail=f"Escrow already in final state: {contract.state.value}")
    reason = (body or {}).get("reason", "buyer_requested")
    return _er._RefundPlan(contract_id, reason, locked_units)


async def _refund_settle_locked(
    mgr: _er.Any, job_id: str, plan: _er._RefundPlan, txn: _er.EscrowMutation
) -> dict[str, _er.Any]:
    """Settle the refund on-chain and record it, still holding the escrow's lock (#780).

    refund_contract marks the cached contract REFUNDED before settlement;
    any raise after that must not leave the mark, or the cache shows a
    refund the chain never saw (same class as #833). Evict on every error
    exit.
    """
    try:
        return await _er._refund_settle_locked_impl(mgr, job_id, plan, txn)
    except Exception:
        if plan.contract_id in mgr.escrow_contracts:
            mgr.evict_contract(plan.contract_id)
        raise


async def _refund_settle_locked_impl(
    mgr: _er.Any, job_id: str, plan: _er._RefundPlan, txn: _er.EscrowMutation
) -> dict[str, _er.Any]:
    contract_id = plan.contract_id
    reason = plan.reason
    locked_units = plan.locked_units
    # B: a refund is only final once the on-chain ESCROW_REFUND transaction lands.
    # Apply the in-memory state, then settle on-chain, then drop the cached contract if
    # settlement fails (the row is only written after it lands, so a rebuild reads it as it was).
    success, message = await mgr.refund_contract(contract_id, reason)
    if not success:
        raise _er.HTTPException(status_code=400, detail=message)
    contract = mgr.escrow_contracts.get(contract_id)
    refund_amount = contract.refunded_amount if contract else _er.Decimal(0)
    if locked_units is not None:
        # The lock is the ceiling: this pays out of the node wallet, and the
        # in-memory contract is a reconstruction of an on-chain fact rather
        # than the fact itself. It has been wrong before -- by exactly the
        # platform fee -- and a refund that overpays is money the operator
        # cannot get back, so cap it at what the chain says was locked.
        locked_ait = _er.units_to_ait(locked_units)
        if refund_amount > locked_ait:
            _er._logger.error(
                "Refund for job_id=%s clamped from %s to the locked %s AIT (contract_id=%s)",
                job_id,
                refund_amount,
                locked_ait,
                contract_id,
            )
            refund_amount = locked_ait
    tx_hash = await _er._submit_refund_tx(
        _er._to_canonical(contract.client_address) if contract else "",
        _er._to_canonical(contract.agent_address) if contract else "",
        refund_amount,
        job_id,
        contract_id,
    )
    if not tx_hash:
        mgr.evict_contract(contract_id)
        _er._logger.error(
            "Escrow refund NOT settled on-chain: contract_id=%s job_id=%s buyer=%s amount=%s. "
            "The refund was rolled back so it can be retried.",
            contract_id,
            job_id,
            contract.client_address if contract else None,
            refund_amount,
        )
        return {
            "success": False,
            "contract_id": contract_id,
            "job_id": job_id,
            "message": "Escrow refund could not be settled on-chain; the buyer was not refunded",
            "refund_tx_hash": None,
        }
    refunded_at = _er.datetime.now(_er.UTC)
    try:

        def _write_refunded_row(session: _er.Session) -> None:
            record = session.get(_er.Escrow, job_id)
            if record:
                record.status = "refunded"
                record.state = _er.EscrowState.REFUNDED.value
                if record.contract_id is None:
                    record.contract_id = contract_id
                record.refunded_at = refunded_at
                record.refund_tx_hash = tx_hash
                # Record what moved, not just that something did; a NULL here
                # makes every reader fall back to reporting the whole lock.
                record.refunded_amount = _er.ait_to_units(refund_amount)

        await txn.write(_write_refunded_row)
    except Exception as e:
        _er._logger.warning("Failed to update refunded_at for job %s: %s", job_id, e)
    _er._logger.info("Escrow refunded: contract_id=%s job_id=%s tx=%s", contract_id, job_id, tx_hash)
    return {
        "success": True,
        "contract_id": contract_id,
        "job_id": job_id,
        "message": message,
        "refund_tx_hash": tx_hash,
    }
