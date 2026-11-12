"""Market-signed submission paths (payment, refund, receipt claim, fee sweep) for the escrow RPC split (#1867 pure-move).

Import ``aitbc_chain.rpc.escrow_routes`` first (it wires these
modules into the ``escrow_routes`` facade); this module is not meant to be
imported directly. All facade-owned names are reached via ``_er.`` so
monkeypatching ``escrow_routes.<name>`` stays visible."""

from __future__ import annotations

from . import escrow_routes as _er


async def _submit_payment_tx(buyer: str, provider: str, amount: _er.Decimal, job_id: str, contract_id: str) -> str | None:
    """Submit an ESCROW_RELEASE transaction to the blockchain so payment is on-chain."""
    if amount <= 0:
        return None
    # The chain denominates value in whole compute-units.  Any positive
    # release that rounds down to zero units would otherwise leave the provider
    # unpaid, so round up to the smallest transferable unit (1 compute-unit).
    amount_int = max(_er.ait_to_units(amount), 1)
    try:
        # Never pay a job twice: if it already settled, hand back that transaction.
        existing_release = await _er._find_existing_release(job_id)
        if existing_release:
            _er._logger.info(
                "ESCROW_RELEASE already settled for job_id=%s (%s); not resubmitting",
                job_id,
                existing_release,
            )
            return existing_release

        settlement_key = _er._get_settlement_key()
        if not settlement_key:
            _er._logger.warning("ESCROW_RELEASE TX skipped: no settlement private key configured")
            return None

        settlement_address = _er._get_settlement_address()
        if not settlement_address:
            _er._logger.warning("ESCROW_RELEASE TX skipped: could not resolve settlement address")
            return None

        sender = settlement_address

        # v0.25.5: do not call POST /register-account.  The block proposer and
        # state transition now auto-create the recipient account on first credit,
        # so provider releases are deterministic and do not require direct RPC
        # writes outside consensus.

        # Re-resolve after creation; use canonical 0x form for the state layer.
        # Never fall back to the node wallet: a missing or unresolvable provider
        # means the release has no valid payee, and paying the node wallet would
        # be a custody bug.
        recipient = _er._resolve_chain_account(provider)
        if not recipient:
            _er._logger.error("ESCROW_RELEASE TX skipped: could not resolve recipient (provider=%s)", provider)
            return None

        tx = {
            "from": sender,
            "to": recipient,
            "amount": amount_int,
            "fee": max(36, amount_int // 100),
            "type": "ESCROW_RELEASE",
            "chain_id": _er._chain_id(),
            "payload": {
                "action": "escrow_release",
                "job_id": job_id,
                "contract_id": contract_id,
                "buyer_escrow_addr": buyer,
                "provider_escrow_addr": provider,
            },
        }
        # The payload carries no wall-clock timestamp on purpose: an identical retry
        # must hash identically so the mempool deduplicates it (mempool.add returns the
        # existing hash for a duplicate). Two concurrent release attempts would otherwise
        # build two different transactions sharing one nonce, and admission validates the
        # nonce against the account -- which has not advanced while the first is pending --
        # so both would be admitted and the provider paid twice. Settlement time is
        # recoverable from the including block; the local escrow row keeps released_at.
        # Sign with the configured non-genesis settlement key (or genesis as fallback).
        # #781: nonce is assigned per attempt at sealed+mempool lookahead
        # (_settlement_signing_nonce): two concurrent signers can no longer take
        # the same sealed nonce, and on a "nonce slot"/"Invalid nonce" refusal
        # the tx is re-signed (the nonce is inside the signature) and resubmitted
        # exactly once before the release reports unsettled.
        resp, _nonce = await _er._submit_market_signed(
            tx, sender=sender, settlement_key=settlement_key, job_id=job_id, label="ESCROW_RELEASE"
        )
        if resp is None:
            return None
        if resp.status_code in (200, 201):
            result = resp.json()
            raw_tx_hash = result.get("transaction_hash")
            actual_tx_hash: str | None = str(raw_tx_hash) if raw_tx_hash else None
            _er._logger.info(
                "ESCROW_RELEASE TX submitted: hash=%s amount=%s from=%s to=%s",
                actual_tx_hash,
                amount_int,
                sender,
                recipient,
            )
            return actual_tx_hash
        _er._logger.error(
            "ESCROW_RELEASE TX rejected %s for job_id=%s (provider %s was NOT paid on-chain): %s",
            resp.status_code,
            job_id,
            provider,
            resp.text[:200],
        )
    except Exception as e:
        _er._logger.error(
            "ESCROW_RELEASE TX submission failed for job_id=%s (provider %s was NOT paid on-chain): %s",
            job_id,
            provider,
            e,
        )
    return None


async def _submit_refund_tx(buyer: str, provider: str, amount: _er.Decimal, job_id: str, contract_id: str) -> str | None:
    """Submit an ESCROW_REFUND transaction to the blockchain so a refund is on-chain."""
    if amount <= 0:
        return None
    # The chain denominates value in whole compute-units. Round up to the
    # smallest transferable unit so a small refund is not lost.
    amount_int = max(_er.ait_to_units(amount), 1)
    try:
        existing_refund = await _er._find_existing_refund(job_id)
        if existing_refund:
            _er._logger.info(
                "ESCROW_REFUND already settled for job_id=%s (%s); not resubmitting",
                job_id,
                existing_refund,
            )
            return existing_refund

        settlement_key = _er._get_settlement_key()
        if not settlement_key:
            _er._logger.warning("ESCROW_REFUND TX skipped: no settlement private key configured")
            return None

        settlement_address = _er._get_settlement_address()
        if not settlement_address:
            _er._logger.warning("ESCROW_REFUND TX skipped: could not resolve settlement address")
            return None

        sender = settlement_address

        # v0.25.5: do not call POST /register-account.  Buyer and provider
        # accounts are created deterministically when the refund transaction is
        # mined.

        # Refunding the node wallet is a custody bug: it would pay the operator
        # instead of the buyer. Refuse and let the caller handle it.
        if _er._to_canonical(buyer) == _er._to_canonical(_er._NODE_WALLET):
            _er._logger.error("ESCROW_REFUND TX skipped: refund buyer is the node wallet (buyer=%s)", buyer)
            return None

        # Re-resolve after creation; use canonical 0x form for the state layer.
        # Never fall back to the node wallet; a missing buyer account is a bug.
        recipient = _er._resolve_chain_account(buyer)
        if not recipient:
            _er._logger.error("ESCROW_REFUND TX skipped: buyer account does not exist (buyer=%s)", buyer)
            return None

        tx = {
            "from": sender,
            "to": recipient,
            "amount": amount_int,
            "fee": max(36, amount_int // 100),
            "type": "ESCROW_REFUND",
            "chain_id": _er._chain_id(),
            "payload": {
                "action": "escrow_refund",
                "job_id": job_id,
                "contract_id": contract_id,
                "buyer_escrow_addr": buyer,
                "provider_escrow_addr": provider,
            },
        }
        # Identical retry must hash identically; no wall-clock timestamp in the payload.
        # #781: sealed+mempool nonce per attempt, one re-sign+resubmit on a nonce refusal.
        resp, _nonce = await _er._submit_market_signed(
            tx, sender=sender, settlement_key=settlement_key, job_id=job_id, label="ESCROW_REFUND"
        )
        if resp is None:
            return None
        if resp.status_code in (200, 201):
            result = resp.json()
            raw_tx_hash = result.get("transaction_hash")
            actual_tx_hash: str | None = str(raw_tx_hash) if raw_tx_hash else None
            _er._logger.info(
                "ESCROW_REFUND TX submitted: hash=%s amount=%s from=%s to=%s",
                actual_tx_hash,
                amount_int,
                sender,
                recipient,
            )
            return actual_tx_hash
        _er._logger.error(
            "ESCROW_REFUND TX rejected %s for job_id=%s (buyer %s was NOT refunded on-chain): %s",
            resp.status_code,
            job_id,
            buyer,
            resp.text[:200],
        )
    except Exception as e:
        _er._logger.error(
            "ESCROW_REFUND TX submission failed for job_id=%s (buyer %s was NOT refunded on-chain): %s",
            job_id,
            buyer,
            e,
        )
        raise
    return None


async def _escrow_custody_balance(job_id: str) -> int | None:
    """On-chain balance of the job's derived custody account, or None when it
    cannot be proven (RPC failure / unknown account) — callers must skip rather
    than guess."""
    from ..state.pure_state_transition import _escrow_address

    try:
        r = await _er.SharedHttpClient.get(f"{_er._HUB_RPC_URL}/accounts/{_escrow_address(job_id)}")
        if r.status_code == 200:
            return int(r.json().get("balance", 0))
    except Exception as e:  # noqa: BLE001 - probe containment: unproven balance means skip, never guess
        _er._logger.warning("ESCROW_FEE_SWEEP: custody balance lookup failed for job_id=%s: %s", job_id, e)
    return None


async def _submit_fee_sweep_tx(job_id: str, contract_id: str, residue_units: int) -> str | None:
    """Submit an ESCROW_FEE_SWEEP draining ``residue_units`` from the job's
    custody account to the fee recipient. Returns the tx hash, an existing
    hash when the job was already swept, or None — never raises, the release
    it follows is authoritative and must not see a sweep error."""
    if residue_units <= 0:
        return None
    try:
        existing = await _er._find_existing_fee_sweep(job_id)
        if existing:
            _er._logger.info(
                "ESCROW_FEE_SWEEP already settled for job_id=%s (%s); not resubmitting",
                job_id,
                existing,
            )
            return existing
        recipient = _er._fee_sweep_recipient()
        if not recipient:
            _er._logger.warning(
                "ESCROW_FEE_SWEEP skipped for job_id=%s: ESCROW_FEE_RECIPIENT is not configured "
                "(consensus requires the escrow_fee_recipient chain parameter)",
                job_id,
            )
            _er.escrow_fee_sweep_total.labels(result="skipped").inc()
            return None
        settlement_key = _er._get_settlement_key()
        settlement_address = _er._get_settlement_address()
        if not settlement_key or not settlement_address:
            _er._logger.warning("ESCROW_FEE_SWEEP skipped for job_id=%s: settlement key/address not configured", job_id)
            _er.escrow_fee_sweep_total.labels(result="skipped").inc()
            return None

        tx = {
            "from": settlement_address,
            "to": recipient,
            "amount": residue_units,
            "fee": _er._fee_for(residue_units),
            "type": "ESCROW_FEE_SWEEP",
            "chain_id": _er._chain_id(),
            "payload": {
                "action": "escrow_fee_sweep",
                "job_id": job_id,
                "contract_id": contract_id,
            },
        }
        # Same rule as release/refund: no wall-clock in the payload, an
        # identical retry at the same nonce must hash identically.
        # #781: sealed+mempool nonce per attempt, one re-sign+resubmit on a nonce refusal.
        resp, _nonce = await _er._submit_market_signed(
            tx,
            sender=settlement_address,
            settlement_key=settlement_key,
            job_id=job_id,
            label="ESCROW_FEE_SWEEP",
        )
        if resp is None:
            _er.escrow_fee_sweep_total.labels(result="error").inc()
            return None
        if resp.status_code in (200, 201):
            result = resp.json()
            raw_tx_hash = result.get("transaction_hash")
            actual_tx_hash: str | None = str(raw_tx_hash) if raw_tx_hash else None
            _er._logger.info(
                "ESCROW_FEE_SWEEP TX submitted: hash=%s residue=%s from=%s to=%s job_id=%s",
                actual_tx_hash,
                residue_units,
                settlement_address,
                recipient,
                job_id,
            )
            _er.escrow_fee_sweep_total.labels(result="submitted").inc()
            return actual_tx_hash
        _er._logger.error(
            "ESCROW_FEE_SWEEP TX rejected %s for job_id=%s residue=%s — release stands, sweep retries "
            "on the next settlement call: %s",
            resp.status_code,
            job_id,
            residue_units,
            resp.text[:200],
        )
        _er.escrow_fee_sweep_total.labels(result="rejected").inc()
    except Exception as e:  # noqa: BLE001 - submission failure must not fail the release; sweep retries
        _er._logger.error(
            "ESCROW_FEE_SWEEP TX submission failed for job_id=%s residue=%s — release stands, sweep "
            "retries on the next settlement call: %s",
            job_id,
            residue_units,
            e,
        )
        _er.escrow_fee_sweep_total.labels(result="error").inc()
    return None


async def _submit_market_signed(
    tx: dict[str, _er.Any],
    *,
    sender: str,
    settlement_key: str,
    job_id: str,
    label: str,
) -> tuple[_er.Any | None, int | None]:
    """Assign _settlement_signing_nonce, sign and POST /transactions/market.

    On a "nonce slot"/"Invalid nonce" refusal the nonce is re-read, the tx is
    re-signed (the nonce is inside the signature) and resubmitted exactly once
    (#781). Returns (response, nonce-used) — the caller decides what a
    rejection means; response is None on transport error which the caller's
    existing except path reports."""
    resp = None
    for attempt in (0, 1):
        nonce = await _er._settlement_signing_nonce(sender)
        if nonce is None:
            _er._logger.error("%s TX skipped for job_id=%s: account nonce probe failed", label, job_id)
            return None, None
        tx["nonce"] = nonce
        tx["signature"] = _er.sign_transaction_hash(_er._compute_tx_signing_hash(tx), settlement_key)
        resp = await _er.SharedHttpClient.post(f"{_er._HUB_RPC_URL}/transactions/market", json=tx, timeout=5.0)
        if resp.status_code in (200, 201):
            return resp, nonce
        if attempt == 0 and _er._is_nonce_refusal(resp):
            _er._logger.warning(
                "%s nonce %s refused for job_id=%s; re-reading chain+mempool and retrying once",
                label,
                nonce,
                job_id,
            )
            continue
        return resp, nonce
    return resp, nonce


async def _submit_receipt_claim_tx(
    receipt: dict[str, _er.Any] | None, job_id: str, contract_id: str, provider: str
) -> str | None:
    """Submit the RECEIPT_CLAIM that seals the job's signed receipt on-chain (#687).

    The claim carries the receipt's issuance record in ``payload.receipt``, so
    apply materialises the ``receipt`` row deterministically on every node —
    no service-local row is needed for the claim to validate, and the carried
    record never mints (``minted_amount`` stays NULL). Best-effort like the
    fee sweep: every failure logs and returns None; the release stands.
    """
    if not isinstance(receipt, dict):
        return None
    receipt_id = str(receipt.get("receipt_id") or "")
    signature = receipt.get("signature")
    attestations = receipt.get("attestations")
    if not receipt_id:
        _er._logger.warning("RECEIPT_CLAIM skipped for job_id=%s: supplied receipt has no receipt_id", job_id)
        return None
    if not isinstance(signature, dict) or not signature or not isinstance(attestations, list) or not attestations:
        _er._logger.warning(
            "RECEIPT_CLAIM skipped for job_id=%s: receipt %s is unsigned or carries no coordinator attestation",
            job_id,
            receipt_id,
        )
        return None
    try:
        existing = await _er._find_existing_receipt_claim(job_id)
        if existing:
            _er._logger.info(
                "RECEIPT_CLAIM already settled for job_id=%s (%s); not resubmitting",
                job_id,
                existing,
            )
            return existing
        settlement_key = _er._get_settlement_key()
        settlement_address = _er._get_settlement_address()
        if not settlement_key or not settlement_address:
            _er._logger.warning("RECEIPT_CLAIM skipped for job_id=%s: settlement key/address not configured", job_id)
            return None

        recipient = _er._resolve_chain_account(provider) or settlement_address
        nonce = await _er._settlement_signing_nonce(settlement_address)
        if nonce is None:
            _er._logger.warning("RECEIPT_CLAIM skipped for job_id=%s: account nonce probe failed", job_id)
            return None
        record_payload = {k: v for k, v in receipt.items() if k not in ("signature", "attestations")}
        tx = {
            "from": settlement_address,
            "to": recipient,
            "amount": 0,
            "fee": _er._fee_for(0),
            "nonce": nonce,
            "type": "RECEIPT_CLAIM",
            "chain_id": _er._chain_id(),
            "payload": {
                "action": "receipt_claim",
                "job_id": job_id,
                "contract_id": contract_id,
                "receipt_id": receipt_id,
                "receipt": {
                    "receipt_id": receipt_id,
                    "job_id": job_id,
                    "provider": provider,
                    "payload": record_payload,
                    "miner_signature": signature,
                    "coordinator_attestations": attestations,
                },
            },
        }
        # Same rule as release/refund/sweep: no wall-clock in the payload, an
        # identical retry at the same nonce must hash identically.
        signing_hash = _er._compute_tx_signing_hash(tx)
        tx["signature"] = _er.sign_transaction_hash(signing_hash, settlement_key)

        resp = await _er.SharedHttpClient.post(f"{_er._HUB_RPC_URL}/transactions/market", json=tx, timeout=5.0)
        if resp.status_code in (200, 201):
            result = resp.json()
            raw_tx_hash = result.get("transaction_hash")
            actual_tx_hash: str | None = str(raw_tx_hash) if raw_tx_hash else None
            _er._logger.info(
                "RECEIPT_CLAIM TX submitted: hash=%s receipt_id=%s from=%s job_id=%s",
                actual_tx_hash,
                receipt_id,
                settlement_address,
                job_id,
            )
            return actual_tx_hash
        _er._logger.error(
            "RECEIPT_CLAIM TX rejected %s for job_id=%s receipt_id=%s — release stands, claim retries "
            "on the next settlement call: %s",
            resp.status_code,
            job_id,
            receipt_id,
            resp.text[:200],
        )
    except Exception as e:  # noqa: BLE001 - submission failure must not fail the release; claim retries
        _er._logger.error(
            "RECEIPT_CLAIM TX submission failed for job_id=%s receipt_id=%s — release stands, claim "
            "retries on the next settlement call: %s",
            job_id,
            receipt_id,
            e,
        )
    return None


async def _retry_sweep_released_escrow(job_id: str, record: _er.Escrow, session) -> str | None:
    """Re-offer the sweep for an already-released job — the retry surface.

    The residue is derived from *sealed chain legs*, never the row's amount
    columns: a refund the row claims but that never sealed cannot poison the
    sum, and a NULL ``refunded_amount`` column simply means "no sealed
    refund" rather than "ambiguous, skip" (F2). The same fee-only proof the
    periodic pass applies gates the submit (D11): residue beyond the provable
    withheld platform fee is owed buyer change — a released-marked row whose
    release leg is dead while the change refund sealed produces exactly that
    shape, and custody equality alone cannot tell fee from change. Custody
    equality still gates too: a balance above the derived residue means an
    owed leg is still pending, below it means the account was touched; either
    way the job is skipped, never guessed."""
    if not _er._fee_sweep_enabled():
        return None
    from ..contracts.escrow import DEFAULT_FEE_BPS, recompute_release_proofs, settlement_legs_from_chain

    try:
        legs = settlement_legs_from_chain(session, job_id)
    except Exception as e:  # noqa: BLE001 - lookup failure defers the retry, never raises into release
        _er._logger.warning("ESCROW_FEE_SWEEP retry: sealed-leg lookup failed for job_id=%s: %s", job_id, e)
        legs = None
    if not legs:
        _er.escrow_fee_sweep_total.labels(result="skipped").inc()
        return None
    # Same floor the pass applies (A4d): a settlement leg below the fork
    # height makes the residue a pre-fork census matter — an operator
    # decision, not the retry's. NULL height fails closed: unproven is
    # unreadable, never assumed post-floor.
    min_height = legs.get("min_settlement_height")
    if legs.get("null_settlement_height") or min_height is None or min_height < _er.settings.escrow_fee_sweep_pass_min_height:
        _er._logger.info(
            "ESCROW_FEE_SWEEP deferred for job_id=%s: settlement leg below floor (min height %s < %s) — "
            "pre-fork residue is an operator decision",
            job_id,
            min_height,
            _er.settings.escrow_fee_sweep_pass_min_height,
        )
        _er.escrow_fee_sweep_total.labels(result="skipped").inc()
        return None
    lock_units = int(legs.get("locked_amount") or 0)
    expected = lock_units - int(legs.get("released_amount") or 0) - int(legs.get("refunded_amount") or 0)
    if expected <= 0:
        return None
    bps = record.energy_fee_basis_points if record.energy_fee_basis_points is not None else DEFAULT_FEE_BPS
    proof = recompute_release_proofs(
        legs.get("release_legs") or [],
        record.billed_legs,
        fee_bps=bps,
        protected=bool(record.protected),
        credit_units=record.energy_provider_credit_units,
        net_floor_units=record.energy_net_floor_units,
        lock_units=lock_units,
    )
    fee_bound = proof[1] if proof else None
    if fee_bound is None or expected > fee_bound:
        _er._logger.info(
            "ESCROW_FEE_SWEEP deferred for job_id=%s: residue %s exceeds provable fee bound %s — "
            "owed change is not treasury money",
            job_id,
            expected,
            fee_bound,
        )
        _er.escrow_fee_sweep_total.labels(result="skipped").inc()
        return None
    custody = await _er._escrow_custody_balance(job_id)
    if custody is None or custody != expected:
        if custody is not None:
            _er._logger.info(
                "ESCROW_FEE_SWEEP deferred for job_id=%s: custody %s != residue %s — an owed leg may still be pending",
                job_id,
                custody,
                expected,
            )
        _er.escrow_fee_sweep_total.labels(result="skipped").inc()
        return None
    return await _er._submit_fee_sweep_tx(job_id, job_id, expected)
