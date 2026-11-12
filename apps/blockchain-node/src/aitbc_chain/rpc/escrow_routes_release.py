"""Escrow release read/settle path for the escrow RPC split (#1867 pure-move).

Import ``aitbc_chain.rpc.escrow_routes`` first (it wires these
modules into the ``escrow_routes`` facade); this module is not meant to be
imported directly. All facade-owned names are reached via ``_er.`` so
monkeypatching ``escrow_routes.<name>`` stays visible."""

from __future__ import annotations

from . import escrow_routes as _er


def _read_release_row(job_id: str) -> _er.Escrow | None:
    """The escrow row, healed from the chain and detached for the guards' reads."""
    with _er.session_scope() as session:
        record = session.get(_er.Escrow, job_id)
        if record is not None:
            # Heal before the guards read the row: a release whose change leg
            # was mined last reads back as a refund until it is reconciled,
            # and would be rejected here as already refunded.
            _er.backfill_settlement_legs(session, record)
            # backfill may commit and expire the row's attrs; refresh
            # reloads them so the expunged instance keeps its values for
            # the detached reads below.
            session.refresh(record)
            session.expunge(record)
        return record


async def _already_released_result(
    job_id: str, request: dict[str, _er.Any], record: _er.Escrow, released_at: _er.datetime
) -> dict[str, _er.Any]:
    """The stored result for a release that already happened, re-offering the follow-ups
    a retry exists for (custody-residue sweep, RECEIPT_CLAIM)."""
    # The DB may not have stored the release tx hash (legacy rows), so
    # look it up on-chain before returning a stale/empty job_tx_hash.
    existing_release = await _er._find_existing_release(job_id)
    if existing_release and not record.release_tx_hash:

        def _fill_release_hash() -> None:
            with _er.session_scope() as session:
                row = session.get(_er.Escrow, job_id)
                if row is not None:
                    row.release_tx_hash = existing_release
                    session.add(row)
                    session.commit()

        await _er.run_in_threadpool(_fill_release_hash)
    release_tx_hash = record.release_tx_hash or existing_release or record.job_tx_hash or ""
    # v11: re-offer the custody-residue sweep for an already-released
    # job — the retry surface for residue a pass or earlier attempt
    # left behind. Deduped on-chain; residue derived from sealed
    # chain legs, provable only. The sweep is itself async and reads the
    # expunged row's frozen attrs; it gets a fresh session for its
    # sealed-leg queries.
    with _er.session_scope() as session:
        await _er._retry_sweep_released_escrow(job_id, record, session)
    # #687: re-offer the RECEIPT_CLAIM for an already-released job —
    # the retry surface for a claim the earlier release call could
    # not land. Deduped on-chain; never fails this route.
    claim_tx_hash = await _er._submit_receipt_claim_tx(
        request.get("receipt"), job_id, getattr(record, "contract_id", None) or "", record.provider
    )
    return {
        "success": True,
        "contract_id": getattr(record, "contract_id", None) or "",
        "job_id": job_id,
        "message": "Escrow already released",
        "receipt_claim_tx_hash": claim_tx_hash,
        "released_amount": _er._settled_leg_ait(record.released_amount, record.released_at, record.amount),
        "refunded_amount": _er._settled_leg_ait(record.refunded_amount, None, record.amount),
        "refund_tx_hash": record.refund_tx_hash,
        "tx_hash": release_tx_hash,
        "released_at": released_at.isoformat(),
    }


@_er.dataclass(frozen=True)
class _ReleasePlan:
    """What the locked read found: the row (None if there is none) and the contract to settle."""

    escrow_record: _er.Escrow | None
    contract_id: str


async def _release_read_locked(
    mgr: _er.Any, job_id: str, request: dict[str, _er.Any]
) -> dict[str, _er.Any] | _er._ReleasePlan:
    """Read the row under the escrow's cross-worker lock (#780): the stored result for a
    release that already happened, else what the settle step needs.

    The sealed-lock and v2-era gates sit between this and the settle step, in the
    route, so they stay on the route's own error list in the published OpenAPI spec.
    """
    # Reconciliation/duplicate release handling: if the row is already released,
    # return the stored result without resubmitting.
    escrow_record: _er.Escrow | None = None
    try:
        record = await _er.run_in_threadpool(_er._read_release_row, job_id)
        escrow_record = record
        if record and record.refunded_at is not None:
            raise _er.HTTPException(
                status_code=409,
                detail=f"Escrow for job_id={job_id} has already been refunded",
            )
        if record and record.released_at is not None:
            return await _er._already_released_result(job_id, request, record, record.released_at)
        # ``settlement_failed`` is a demoted dead mark, not a settled row:
        # it reaches the gate below and re-drives like a locked row (the
        # v2-era guard still applies to its lock).
        if record is not None and record.status not in (None, "locked", "settlement_failed"):
            raise _er.HTTPException(
                status_code=409,
                detail=f"Escrow for job_id={job_id} is not locked (status={record.status})",
            )
    except _er.HTTPException:
        raise
    except Exception as e:
        _er._logger.warning("Failed to check escrow release state: %s", e)

    contract_id = await _er._find_contract_id(mgr, job_id)
    if contract_id is None:
        raise _er.HTTPException(status_code=404, detail=f"No escrow contract found for job_id={job_id}")
    return _er._ReleasePlan(escrow_record, contract_id)


async def _release_settle_locked(
    mgr: _er.Any,
    job_id: str,
    request: dict[str, _er.Any],
    requested_amount: _er.Decimal | None,
    plan: _er._ReleasePlan,
    txn: _er.EscrowMutation,
) -> dict[str, _er.Any]:
    """Settle the release on-chain and record it, still holding the escrow's lock (#780).

    The impl marks the cached contract JOB_COMPLETED before the guards run;
    any raise that follows must not leave that mark behind, or a later
    refund on this worker reads a completed job that never settled
    (ESCROW-CACHE-STUCK-JOB-COMPLETED-1, #833). Evict on every error exit —
    the rebuild then reads the row, which is the truth either way.
    """
    try:
        return await _er._release_settle_locked_impl(mgr, job_id, request, requested_amount, plan, txn)
    except Exception:
        if plan.contract_id in mgr.escrow_contracts:
            mgr.evict_contract(plan.contract_id)
        raise


async def _release_settle_locked_impl(
    mgr: _er.Any,
    job_id: str,
    request: dict[str, _er.Any],
    requested_amount: _er.Decimal | None,
    plan: _er._ReleasePlan,
    txn: _er.EscrowMutation,
) -> dict[str, _er.Any]:
    job_tx_hash = request.get("job_tx_hash")
    escrow_record = plan.escrow_record
    contract_id = plan.contract_id
    contract = mgr.escrow_contracts.get(contract_id)
    # #1929: a supplied job_tx_hash must resolve to a sealed software_job
    # record bound to this escrow before any settlement state is touched.
    # Verify-when-present — omitting the hash keeps the legacy path.
    if job_tx_hash:
        buyer = getattr(escrow_record, "buyer", "") or (contract.client_address if contract else "")
        provider = getattr(escrow_record, "provider", "") or (contract.agent_address if contract else "")
        await _er._verify_job_tx_proof(str(job_tx_hash), job_id, buyer, provider)
    if contract:
        for ms in contract.milestones:
            ms["completed"] = True
            ms["verified"] = True
        from ..contracts.escrow import EscrowState

        contract.state = EscrowState.JOB_COMPLETED
    # E1: fixed-duration protected rentals do not accept arbitrary metered overrides
    # and must release the full frozen gross amount.
    if escrow_record and escrow_record.protected:
        requested_amount = None
        # §4.3: enforce that the settlement asset and unit scale match the
        # frozen quote. A protected rental was priced in a specific asset at a
        # specific scale; releasing in a different asset or scale would
        # silently change the economic terms.
        if escrow_record.energy_settlement_asset and escrow_record.energy_settlement_asset != "AITBC":
            raise _er.HTTPException(
                status_code=422,
                detail=f"Protected escrow settlement asset {escrow_record.energy_settlement_asset} is not supported for native release",
            )
        if escrow_record.energy_settlement_unit_scale is not None:
            if escrow_record.energy_settlement_unit_scale != _er.UNITS_PER_AIT:
                raise _er.HTTPException(
                    status_code=422,
                    detail=f"Protected escrow settlement unit scale {escrow_record.energy_settlement_unit_scale} does not match native scale {_er.UNITS_PER_AIT}",
                )
        if contract and escrow_record.energy_fee_basis_points is not None:
            contract.fee_rate = _er.Decimal(escrow_record.energy_fee_basis_points) / _er.Decimal(10000)
        if contract and escrow_record.energy_provider_credit_units is not None:
            contract.energy_provider_credit_units = escrow_record.energy_provider_credit_units
            contract.energy_net_floor_units = escrow_record.energy_net_floor_units

    # A7e: a cached contract still carries protected=True even when the row
    # read failed (escrow_record is None). Signing then would drop the
    # credit/floor inputs the leg is provable under — underpaying the
    # provider and wedging the row. Refuse instead; a retried read heals it.
    if contract is not None and getattr(contract, "protected", False) and escrow_record is None:
        raise _er.HTTPException(
            status_code=409,
            detail="escrow row unavailable for a protected contract; refusing to release without the frozen quote terms",
        )

    ok, message = await mgr.release_payment(contract_id, requested_amount)
    if not ok:
        raise _er.HTTPException(status_code=400, detail=message)
    released_amount = contract.released_amount if contract else _er.Decimal(0)

    # E1: ensure the provider receives at least the frozen credit, never below
    # the energy floor. Bump the settled amount up to the exact signed target.
    if escrow_record and escrow_record.protected and escrow_record.energy_provider_credit_units is not None:
        target_ait = _er.units_to_ait(escrow_record.energy_provider_credit_units)
        if released_amount < target_ait:
            released_amount = target_ait
            if contract:
                contract.released_amount = target_ait
        if escrow_record.energy_net_floor_units is not None:
            floor_ait = _er.units_to_ait(escrow_record.energy_net_floor_units)
            if released_amount < floor_ait:
                mgr.evict_contract(contract_id)
                raise _er.HTTPException(
                    status_code=422,
                    detail="Protected escrow release would underpay the energy floor",
                )
    buyer_addr = contract.client_address if contract else ""
    provider_addr = contract.agent_address if contract else ""
    # What the buyer locked but the job did not consume. release_payment clamps an
    # over-estimate to the lock, so this is never negative.
    # sum()'s no-start-value overload types as "T | Literal[0]" (its empty-iterable
    # fallback is int 0), which mypy then propagates as "Decimal | int" through
    # billed_gross/unbilled_amount into the refund call below. Passing an explicit
    # Decimal start pins the type and makes an empty milestones list (which
    # create_contract never actually produces) return Decimal(0) instead of int 0.
    locked_total = (
        sum((_er.Decimal(str(ms["amount"])) for ms in contract.milestones), _er.Decimal(0)) if contract else _er.Decimal(0)
    )
    billed_gross = locked_total if requested_amount is None else min(requested_amount, locked_total)
    unbilled_amount = locked_total - billed_gross
    # A7d: the sealed leg value is derived on whole compute-units by the
    # same integer formula the settlement passes recompute with — the
    # Decimal AIT path can cross an exact .5 rounding boundary and would
    # leave the row permanently unproven.
    from ..contracts.escrow import DEFAULT_FEE_BPS, expected_release_units

    billed_units = _er.ait_to_units(billed_gross)
    # A7e: mirror the contract side — it only honors the row's quoted
    # fee rate when the row is protected (escrow.py create/load paths
    # all gate on record.protected). An unprotected row carrying
    # energy_fee_basis_points must bill the default rate.
    record_protected = bool(escrow_record.protected) if escrow_record else False
    fee_bps = (
        escrow_record.energy_fee_basis_points
        if record_protected and escrow_record is not None and escrow_record.energy_fee_basis_points is not None
        else DEFAULT_FEE_BPS
    )
    release_units = expected_release_units(
        billed_units,
        fee_bps=fee_bps,
        protected=record_protected,
        credit_units=escrow_record.energy_provider_credit_units if escrow_record else None,
    )
    if _er.ait_to_units(released_amount) != release_units:
        # Pathological divergence (e.g. an earlier milestone payout left
        # contract.released_amount above billable−fee): sign the
        # provable billed-derived value, not the contract's residue.
        _er._logger.warning(
            "Escrow release leg for job_id=%s: contract released_amount %s units != recomputed %s — signing the recomputed value",
            job_id,
            _er.ait_to_units(released_amount),
            release_units,
        )
    released_amount = _er.units_to_ait(release_units)
    # Reinvestment must be paid to the escrow's recorded provider; the caller must
    # not be able to name an arbitrary stake address (CHOKE-POINT).
    reinvest_address = provider_addr
    auto_reinvest_pct = request.get("auto_reinvest_pct")

    # Settle on-chain first; only a confirmed transaction counts as a release.
    tx_hash = await _er._submit_payment_tx(buyer_addr, provider_addr, released_amount, job_id, contract_id)
    if not tx_hash:
        mgr.evict_contract(contract_id)
        _er._logger.error(
            "Escrow release NOT settled on-chain: contract_id=%s job_id=%s provider=%s amount=%s. "
            "The release was rolled back so it can be retried.",
            contract_id,
            job_id,
            provider_addr,
            released_amount,
        )
        return {
            "success": False,
            "contract_id": contract_id,
            "job_id": job_id,
            "message": "Escrow release could not be settled on-chain; the provider was not paid",
            "released_amount": str(released_amount),
            "refunded_amount": "0",
            "refund_tx_hash": None,
            "tx_hash": None,
            "settlement_status": "unsettled",
            "released_at": None,
            "reinvest_amount": "0",
            "reinvest_stake_id": None,
        }

    # #687: seal the job's signed receipt on-chain with a RECEIPT_CLAIM. The
    # claim carries the issuance record, so every node materialises the same
    # row at apply; it queues behind the release's mempool nonce slot and is
    # best-effort — a claim failure never rolls the release back.
    claim_tx_hash = await _er._submit_receipt_claim_tx(request.get("receipt"), job_id, contract_id, provider_addr)

    # Owed change (F1b/A6): the change leg is never submitted in-request.
    # Signed now it would carry the release's own sealed nonce and collide
    # on the (sender, N) mempool slot; waited-for it would out-live the
    # caller's timeout on this block interval and invite a second
    # submission on retry. The settlement sweeper's change pass pays owed
    # change from sealed legs on a later tick — custody holds it, provably,
    # until then. The response reports it explicitly; nothing is marked.
    if unbilled_amount > 0:
        _er._logger.info(
            "Escrow change deferred to the change pass: job_id=%s buyer=%s owed=%s",
            job_id,
            buyer_addr,
            unbilled_amount,
        )

    # No settle-time sweep attempt: every settlement leg is signed at the
    # sealed authority nonce, so an in-request sweep can only lose the
    # mempool (sender, nonce) slot to the release/refund that precedes it
    # (F1). The residue is swept by the periodic pass in the settlement
    # sweeper and by the retry surface on the next release call — both
    # derive it from sealed chain legs, never from this request's legs.
    released_at = _er.datetime.now(_er.UTC)
    try:

        def _write_released_row(session: _er.Session) -> None:
            nonlocal released_at
            record = session.get(_er.Escrow, job_id)
            if record:
                # A settlement_failed row carries the dead hash from the mark
                # the sweeper demoted; this re-drive's hash must replace it or
                # the row would keep pointing at the corpse. Other statuses
                # keep fill-if-empty: a settled row's original hash is fact.
                was_failed = record.status == "settlement_failed"
                # A reconciliation retry re-releases an escrow that already settled,
                # and _submit_payment_tx hands back the transaction that settled it.
                # Keep the original timestamp: it is when the provider was actually
                # paid. Overwriting it would date the payment to the retry instead.
                if record.released_at is not None:
                    released_at = record.released_at
                else:
                    record.released_at = released_at
                record.status = "released"
                record.state = EscrowState.RELEASED.value
                if record.contract_id is None:
                    record.contract_id = contract_id
                record.released_amount = _er.ait_to_units(released_amount)
                # refunded_amount/refund_tx_hash stay untouched: the change
                # pass marks them only from a sealed ESCROW_REFUND leg.
                if tx_hash:
                    # A7: record the billed gross this submission consumed,
                    # keyed by the leg's own hash — the passes prove the
                    # sealed release by recomputing the route's fee rule
                    # from it. A dropped leg's entry orphans (its hash never
                    # seals); a same-hash dedup retry does not re-append.
                    # getattr: the row-update block must never fail on a
                    # missing attr — released_at is the load-bearing write.
                    entries = list(getattr(record, "billed_legs", None) or [])
                    if not any(e.get("tx_hash") == tx_hash for e in entries if isinstance(e, dict)):
                        entries.append({"tx_hash": tx_hash, "billed": billed_units})
                        record.billed_legs = entries
                if tx_hash and (not record.release_tx_hash or was_failed):
                    record.release_tx_hash = tx_hash
                if job_tx_hash:
                    record.job_tx_hash = job_tx_hash

        await txn.write(_write_released_row)
    except Exception as e:
        _er._logger.warning("Failed to update released_at/job_tx_hash in DB: %s", e)
    reinvest_stake_id = None
    reinvest_amount = _er.Decimal(0)
    if auto_reinvest_pct and reinvest_address and released_amount > 0:
        try:
            pct = _er.Decimal(str(auto_reinvest_pct))
            if 0 < pct <= 100:
                reinvest_amount_ait = (released_amount * pct / 100).quantize(_er.Decimal("0.00000001"))
                if reinvest_amount_ait > 0:
                    reinvest_amount_units = _er.ait_to_units(reinvest_amount_ait)
                    if reinvest_amount_units > 0:
                        reinvest_stake_id = _er._auto_stake(reinvest_address, reinvest_amount_units, _er._chain_id(), job_id)
                        reinvest_amount = reinvest_amount_ait
                    _er._logger.info(
                        "Escrow reinvestment: job_id=%s stake_id=%s amount=%s pct=%s",
                        job_id,
                        reinvest_stake_id,
                        reinvest_amount,
                        pct,
                    )
        except Exception as e:
            _er._logger.warning("Failed to auto-reinvest for job %s: %s", job_id, e)
    _er._logger.info("Escrow released: contract_id=%s job_id=%s tx=%s", contract_id, job_id, tx_hash)
    return {
        "success": True,
        "contract_id": contract_id,
        "job_id": job_id,
        "message": message,
        "released_amount": str(released_amount),
        "refunded_amount": "0",
        "refund_tx_hash": None,
        "change_owed_amount": str(unbilled_amount) if unbilled_amount > 0 else "0",
        "tx_hash": tx_hash,
        "receipt_claim_tx_hash": claim_tx_hash,
        "settlement_status": "settled" if tx_hash else "unsettled",
        "released_at": released_at.isoformat(),
        "reinvest_amount": str(reinvest_amount),
        "reinvest_stake_id": reinvest_stake_id,
    }
