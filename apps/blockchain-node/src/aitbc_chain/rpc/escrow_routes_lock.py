"""Escrow funding-lock build/submit/verify path for the escrow RPC split (#1867 pure-move).

Import ``aitbc_chain.rpc.escrow_routes`` first (it wires these
modules into the ``escrow_routes`` facade); this module is not meant to be
imported directly. All facade-owned names are reached via ``_er.`` so
monkeypatching ``escrow_routes.<name>`` stays visible."""

from __future__ import annotations

import asyncio

import httpx

from . import escrow_routes as _er


def _lock_tx_payload(
    job_id: str,
    provider: str,
    *,
    energy_quote_id: str | None,
    energy_quote_digest: str | None,
    settlement_route: str | None,
    settlement_asset: str | None,
    settlement_unit_scale: int | None,
) -> dict[str, _er.Any]:
    """ESCROW_LOCK payload with the optional energy/settlement fields."""
    payload: dict[str, _er.Any] = {
        "action": "escrow_lock",
        "job_id": job_id,
        "provider": _er._to_canonical(provider),
    }
    if energy_quote_id:
        payload["energy_quote_id"] = energy_quote_id
    if energy_quote_digest:
        payload["energy_quote_digest"] = energy_quote_digest
    if settlement_route:
        payload["settlement_route"] = settlement_route
    if settlement_asset:
        payload["settlement_asset"] = settlement_asset
    if settlement_unit_scale is not None:
        payload["settlement_unit_scale"] = settlement_unit_scale
    return payload


def _build_lock_tx(
    job_id: str,
    buyer: str,
    provider: str,
    amount_dec: _er.Decimal,
    nonce: int,
    fee: int | None = None,
    *,
    energy_quote_id: str | None = None,
    energy_quote_digest: str | None = None,
    settlement_route: str | None = None,
    settlement_asset: str | None = None,
    settlement_unit_scale: int | None = None,
) -> tuple[dict[str, _er.Any], int]:
    """Build the canonical ESCROW_LOCK transaction dict and return it with the compute-unit amount."""
    amount_units = _er.ait_to_units(amount_dec)
    if amount_units <= 0:
        raise ValueError("escrow amount must be positive")
    if not _er._NODE_WALLET:
        raise ValueError("NODE_WALLET_ADDRESS / GENESIS_WALLET_ADDRESS not configured")
    if _er._to_canonical(buyer) == _er._to_canonical(_er._NODE_WALLET):
        raise ValueError("escrow buyer cannot be the node wallet")
    if _er._to_canonical(provider) == _er._to_canonical(_er._NODE_WALLET):
        raise ValueError("escrow provider cannot be the node wallet")
    if fee is None:
        fee = _er._fee_for(amount_units)
    payload = _lock_tx_payload(
        job_id,
        provider,
        energy_quote_id=energy_quote_id,
        energy_quote_digest=energy_quote_digest,
        settlement_route=settlement_route,
        settlement_asset=settlement_asset,
        settlement_unit_scale=settlement_unit_scale,
    )
    tx: dict[str, _er.Any] = {
        "from": _er._to_canonical(buyer),
        "to": _er._to_canonical(_er._NODE_WALLET),
        "amount": amount_units,
        "fee": fee,
        "nonce": nonce,
        "type": "ESCROW_LOCK",
        "chain_id": _er._chain_id(),
        "payload": payload,
    }
    return tx, amount_units


async def _submit_lock_tx(signed_lock_tx: dict[str, _er.Any]) -> str:
    """Submit a signed ESCROW_LOCK transaction and return its hash."""
    tx = dict(signed_lock_tx)
    if "signature" not in tx and "sig" in tx:
        tx["signature"] = tx.pop("sig")
    resp = await _er.SharedHttpClient.post(f"{_er._HUB_RPC_URL}/transactions/market", json=tx, timeout=10.0)
    if resp.status_code not in (200, 201):
        raise _er.HTTPException(
            status_code=400, detail=f"ESCROW_LOCK transaction submission failed: {resp.status_code} {resp.text[:200]}"
        )
    result = resp.json()
    tx_hash = result.get("transaction_hash")
    if not tx_hash:
        raise _er.HTTPException(status_code=400, detail="ESCROW_LOCK transaction accepted but no transaction_hash returned")
    _er._logger.info(
        "ESCROW_LOCK TX submitted: hash=%s from=%s to=%s amount=%s", tx_hash, tx.get("from"), tx.get("to"), tx.get("amount")
    )
    return str(tx_hash)


# A lost submit response is ambiguous: /transactions/market can legitimately
# outlive the client timeout (its bounded peer-fanout wait alone is ~8s), so a
# ReadTimeout does not prove the lock was rejected — the tx may already sit in
# the hub mempool or have sealed while only the response was lost. These bound
# the post-timeout adoption probes; each underlying probe carries its own
# short timeout and answers "unknown" rather than blocking.
_LOCK_ADOPT_ATTEMPTS = 2
_LOCK_ADOPT_DELAY_SECONDS = 1.0


async def _submit_or_adopt_lock(signed_lock_tx: dict[str, _er.Any], job_id: str) -> str:
    """Submit the ESCROW_LOCK, adopting the admitted tx when the reply is lost.

    On ``httpx.TimeoutException`` the create probes the mempool and the sealed
    set for this job's lock before failing — the same adoption the pre-submit
    ``_pending_identical_lock_hash``/``_find_existing_lock`` checks perform,
    repeated because the timed-out request may have been admitted in the
    interim. A hit funds the contract instead of orphaning the lock behind a
    502 (#2986); a miss re-raises so the create fails exactly as before.
    """
    try:
        return await _er._submit_lock_tx(signed_lock_tx)
    except httpx.TimeoutException:
        for attempt in range(_LOCK_ADOPT_ATTEMPTS):
            if attempt:
                await asyncio.sleep(_LOCK_ADOPT_DELAY_SECONDS)
            adopted = await _er._pending_identical_lock_hash(signed_lock_tx, job_id) or await _er._find_existing_lock(job_id)
            if adopted:
                _er._logger.warning(
                    "ESCROW_LOCK submit timed out for job_id=%s; adopted admitted lock %s",
                    job_id,
                    adopted,
                )
                return adopted
        raise


def _canonical_lock_fields(lock_tx: dict[str, _er.Any]) -> dict[str, _er.Any]:
    """Normalize the two lock-transaction shapes for field comparison.

    A sealed ``transactions`` row uses ``sender``/``recipient``/``value``; a
    mempool entry carries the submitted body (``from``/``to``/``amount``).
    ``type`` and ``payload`` are spelled the same in both.
    """
    return {
        "from": lock_tx.get("from", lock_tx.get("sender")),
        "to": lock_tx.get("to", lock_tx.get("recipient")),
        "amount": lock_tx.get("amount", lock_tx.get("value")),
        "type": lock_tx.get("type"),
        "payload": lock_tx.get("payload"),
    }


def _assert_lock_matches_contract(
    lock_tx: dict[str, _er.Any], *, job_id: str, buyer: str, amount_units: int, tx_hash: str
) -> None:
    """Refuse a lock whose fields do not carry this contract's facts (HTTP 409).

    A mismatch is permanent — the sealed/mempool tx says what it says — so this
    is a conflict, not a retryable deferral.
    """
    fields = _er._canonical_lock_fields(lock_tx)
    problems = []
    if fields["type"] != "ESCROW_LOCK":
        problems.append("type")
    if (fields["payload"] or {}).get("job_id") != job_id:
        problems.append("payload.job_id")
    if _er._to_canonical(str(fields["from"] or "")) != _er._to_canonical(buyer):
        problems.append("from")
    if _er._to_canonical(str(fields["to"] or "")) != _er._to_canonical(_er._NODE_WALLET):
        problems.append("to")
    try:
        if int(fields["amount"] or 0) != amount_units:
            problems.append("amount")
    except (TypeError, ValueError):
        problems.append("amount")
    if problems:
        raise _er.HTTPException(
            status_code=409,
            detail=f"ESCROW_LOCK {tx_hash} for job_id={job_id} does not match this contract ({', '.join(problems)})",
        )


def _sealed_lock_payload(lock_tx: dict[str, _er.Any]) -> dict[str, _er.Any] | None:
    """The payload of a sealed ``transactions`` row, parsed when stored as JSON text."""
    payload = lock_tx.get("payload")
    if isinstance(payload, str):
        try:
            payload = _er.json.loads(payload)
        except ValueError:
            return None
    return payload if isinstance(payload, dict) else None


def _is_same_escrow_lock(sealed: dict[str, _er.Any], submitted_tx: dict[str, _er.Any] | None) -> bool:
    """True when the sealed lock carries the identical escrow binding as the
    lock this create submitted.

    Dead-envelope retries sign a fresh ESCROW_LOCK each attempt (new nonce →
    new hash), so the first-sealed envelope is rarely the submitted one. The
    payload is the escrow's identity — action, job_id, provider, energy
    quote and market binding — while ``from``/``to``/``amount`` are checked
    separately by ``_assert_lock_matches_contract``. Identical payload plus
    those fields means the sealed lock funds exactly this escrow; anything
    else is a genuinely different lock and stays a 409.
    """
    if not submitted_tx:
        return False
    sealed_payload = _sealed_lock_payload(sealed)
    submitted_payload = submitted_tx.get("payload")
    if not isinstance(submitted_payload, dict) or sealed_payload != submitted_payload:
        return False
    return True


async def _verify_funding_lock(
    tx_hash: str,
    *,
    job_id: str,
    buyer: str,
    amount_units: int,
    submitted_tx: dict[str, _er.Any] | None = None,
) -> dict[str, _er.Any]:
    """Return the ESCROW_LOCK this create's hash points at; refuse if unverifiable.

    ``_submit_lock_tx`` returns the hash mempool admission computed — a mempool
    entry can still be evicted before it seals, so FUNDED must rest on a
    transaction the node can still see, carrying this contract's fields
    (ESC-FUND-1). The sealed ``transactions`` row wins; a mempool-held tx is
    sufficient because admission already verified its signature and the
    settlement gates re-check the sealed row before any payout. Absence
    everywhere is retryable (HTTP 425, like ``_ensure_lock_sealed``); a field
    mismatch is permanent (409).

    A *different* sealed hash for the same job is adopted, not refused, when
    it carries the identical escrow binding (``_is_same_escrow_lock``): the
    retry's own envelope died in the mempool while an earlier same-escrow
    lock sealed, and 409ing here strands the sealed funds with no escrow
    row — the funding-side twin of the release hash drift the settlement
    reconciler already re-adopts (AUDIT-COORD-LOCK-HASH-DIVERGENCE-STRANDS-ESCROW-1).
    """
    sealed = await _er._find_existing_lock_tx(job_id)
    if sealed is not None:
        sealed_hash = str(sealed.get("tx_hash") or "")
        if sealed_hash != tx_hash and not _is_same_escrow_lock(sealed, submitted_tx):
            raise _er.HTTPException(
                status_code=409,
                detail=(
                    f"a different ESCROW_LOCK sealed for job_id={job_id} (tx {sealed.get('tx_hash')}); "
                    "refusing to fund against the submitted hash"
                ),
            )
        _er._assert_lock_matches_contract(sealed, job_id=job_id, buyer=buyer, amount_units=amount_units, tx_hash=tx_hash)
        return sealed

    from ..mempool import compute_mempool_entry_hash

    try:
        r = await _er.SharedHttpClient.get(
            f"{_er._HUB_RPC_URL}/mempool?chain_id={_er._chain_id()}&limit={_er._FUNDING_LOCK_MEMPOOL_LIMIT}", timeout=5.0
        )
        if r.status_code == 200:
            for tx in r.json().get("transactions") or []:
                if isinstance(tx, dict) and compute_mempool_entry_hash(tx) == tx_hash:
                    verified = dict(tx)
                    verified["tx_hash"] = tx_hash
                    _er._assert_lock_matches_contract(
                        verified, job_id=job_id, buyer=buyer, amount_units=amount_units, tx_hash=tx_hash
                    )
                    return verified
    except _er.HTTPException:
        raise
    except _er._HTTP_PROBE_ERRORS as e:
        _er._logger.warning("mempool funding-lock probe failed for job_id=%s: %s", job_id, e)
    raise _er.HTTPException(
        status_code=425,
        detail=(
            f"lock tx {tx_hash} for job_id={job_id} is neither sealed nor present in the hub mempool; "
            "retry after it re-lands or resubmit"
        ),
        headers={"Retry-After": "5"},
    )


def _same_lock_binding(pending_tx: dict[str, _er.Any], submitted_tx: dict[str, _er.Any]) -> bool:
    """True when two lock envelopes carry the identical escrow binding.

    The escrow's identity is ``type`` + ``chain_id`` + canonical ``from`` /
    ``to`` / ``amount`` + the full ``payload`` dict (action, job_id, provider,
    energy quote and market binding). ``nonce``, ``fee``, ``signature`` and
    ``tx_hash`` are envelope mechanics — a re-signed retry differs only in
    those, which is exactly the drift this comparison must ignore
    (CHAIN-ESCROW-DOUBLE-LOCK-IDENTICAL-BINDING-1, #2673).
    """
    pending_fields = _canonical_lock_fields(pending_tx)
    submitted_fields = _canonical_lock_fields(submitted_tx)
    if pending_fields["type"] != submitted_fields["type"]:
        return False
    pending_payload = _sealed_lock_payload(pending_tx)
    submitted_payload = submitted_tx.get("payload")
    if not isinstance(submitted_payload, dict) or pending_payload != submitted_payload:
        return False
    if _er._to_canonical(str(pending_fields["from"] or "")) != _er._to_canonical(str(submitted_fields["from"] or "")):
        return False
    if _er._to_canonical(str(pending_fields["to"] or "")) != _er._to_canonical(str(submitted_fields["to"] or "")):
        return False
    try:
        if int(pending_fields["amount"] or 0) != int(submitted_fields["amount"] or 0):
            return False
    except (TypeError, ValueError):
        return False
    return pending_tx.get("chain_id") == submitted_tx.get("chain_id")


async def _pending_identical_lock_hash(tx_to_submit: dict[str, _er.Any], job_id: str) -> str | None:
    """Hash of a mempool-held ESCROW_LOCK carrying this create's exact binding.

    Dead-envelope retries re-sign a fresh lock each attempt; while the earlier
    envelope is still pending, submitting the retry's lock puts two
    payload-equal locks in the mempool and both can seal — double-funding the
    escrow (#2673). Adopting the pending hash lets ``_verify_funding_lock``
    fund against the envelope already in flight, and the create's own signed
    envelope simply never broadcasts. Returns ``None`` when no identical
    pending lock exists or the probe cannot answer — the caller then submits
    normally and the admission dedup gate is the backstop.
    """
    from ..mempool import compute_mempool_entry_hash

    try:
        r = await _er.SharedHttpClient.get(
            f"{_er._HUB_RPC_URL}/mempool?chain_id={_er._chain_id()}&limit={_er._FUNDING_LOCK_MEMPOOL_LIMIT}",
            timeout=5.0,
        )
        if r.status_code != 200:
            return None
        body = r.json() or {}
        count = body.get("count")
        if isinstance(count, int) and count >= _er._FUNDING_LOCK_MEMPOOL_LIMIT:
            return None
        txs = body.get("transactions")
        if not isinstance(txs, list):
            return None
    except _er._HTTP_PROBE_ERRORS as e:
        _er._logger.warning("pending-lock adoption probe failed for job_id=%s: %s", job_id, e)
        return None
    for tx in txs:
        if not isinstance(tx, dict) or tx.get("type") != "ESCROW_LOCK":
            continue
        payload = tx.get("payload")
        if not isinstance(payload, dict) or payload.get("job_id") != job_id:
            continue
        if _same_lock_binding(tx, tx_to_submit):
            return compute_mempool_entry_hash(tx)
    return None


async def _pending_lock_tx_hashes() -> set[str] | None:
    """Hashes of transactions still held in the hub mempool; ``None`` when the
    probe could not be answered completely.

    Same view ``_verify_funding_lock`` funds against — the mempool the lock
    was submitted to. ``None`` means "unknown", never "absent": callers must
    keep the state they cannot prove dead. A truncated answer (count at the
    limit) is a failure too, since the unseen tail could hold the hash being
    judged.
    """
    from ..mempool import compute_mempool_entry_hash

    try:
        r = await _er.SharedHttpClient.get(
            f"{_er._HUB_RPC_URL}/mempool?chain_id={_er._chain_id()}&limit={_er._FUNDING_LOCK_MEMPOOL_LIMIT}",
            timeout=5.0,
        )
        if r.status_code != 200:
            return None
        body = r.json() or {}
        count = body.get("count")
        if isinstance(count, int) and count >= _er._FUNDING_LOCK_MEMPOOL_LIMIT:
            return None
        txs = body.get("transactions")
        if not isinstance(txs, list):
            return None
        return {compute_mempool_entry_hash(tx) for tx in txs if isinstance(tx, dict)}
    except _er._HTTP_PROBE_ERRORS as e:
        _er._logger.warning("pending-lock mempool probe failed: %s", e)
        return None


async def _refuse_v2_lock(job_id: str) -> None:
    """Refuse route settlement for a lock sealed before the v3 custody height.

    A v2-era lock has no per-escrow custody account at apply time, so a route
    re-drive pays value+fee out of the settlement authority with no apply-time
    dedup — the late-seal double-pay. The demote-only sweeper clears the dead
    marks, and the coordinator retry paths re-drive whatever looks unsettled;
    without this guard the first retry after deploy would replay every v2 row
    on its own. Repair of these rows goes through the operator path only.

    Probe semantics: the sealed-lock gate runs immediately before this, so a
    ``None`` here means the era re-read flaked between the two calls — while
    the hub is unreachable the settlement submit fails anyway, so failing open
    cannot mint a dead record. A lock that *is* returned must carry its
    ``block_height``; anything else is a malformed response and refuses. With
    ``state_transition_v3_height == 0`` (v3 never activated on this chain) no
    block height is below it and the guard is inert.
    """
    lock_tx = await _er._find_existing_lock_tx(job_id)
    if lock_tx is None:
        _er._logger.warning(
            "v2-era check could not re-read the lock for job_id=%s after the sealed-lock gate passed; allowing",
            job_id,
        )
        return
    block_height = lock_tx.get("block_height")
    if not isinstance(block_height, int):
        raise _er.HTTPException(
            status_code=409,
            detail=(
                f"escrow lock for job_id={job_id} returned without a readable block_height; "
                "routes do not settle locks of unverifiable era — retry or repair manually"
            ),
        )
    if block_height < _er.settings.state_transition_v3_height:
        raise _er.HTTPException(
            status_code=409,
            detail=(
                f"escrow lock for job_id={job_id} sealed at block {block_height}, below "
                f"state_transition_v3_height={_er.settings.state_transition_v3_height} (v2-era); "
                "routes do not settle these rows — operator repair only"
            ),
        )


async def _ensure_lock_sealed(job_id: str) -> None:
    """Refuse the settlement while the job's ESCROW_LOCK is not sealed in a block.

    Admission does not check escrow state: a release/refund evaluated before its
    lock's block is dropped at production ("No ESCROW_LOCK found", or the v3
    escrow-balance check), while this route would still have marked the row
    settled at RPC acceptance and served the dead hash forever (S-8). The sealed
    ``transaction`` table is the same view production consults, so whatever the
    gate defers would have been dropped anyway. HTTP 425 tells every existing
    caller "not yet, retry": the coordinator leaves the payment escrowed and
    re-attempts on its next sweep; the row stays unmarked either way.
    """
    lock_tx, probe_ok = await _er._find_existing_lock_tx_status(job_id)
    if not probe_ok:
        # The lookup itself failed — that is "unknown", not "absent". A 425
        # here would tell the coordinator the lock is unsealed and spend its
        # bounded 425-deferral budget on what is really an unavailable probe
        # (#2295: hub RPC restart window produced minutes of false 425s on a
        # confirmed lock). 503 keeps the retry semantics without the lie.
        # Curated message (job_id only, no exception text) — kept out of an
        # f-string inline so the 5xx hardening audit sees the named detail.
        detail = (
            f"escrow lock lookup for job_id={job_id} is unavailable; retry — the lock's sealed state could not be determined"
        )
        raise _er.HTTPException(status_code=503, detail=detail, headers={"Retry-After": "5"})
    if lock_tx is None:
        raise _er.HTTPException(
            status_code=425,
            detail=(
                f"escrow lock for job_id={job_id} is not yet sealed in a block "
                "(absent or still in mempool); retry after the ESCROW_LOCK lands"
            ),
            headers={"Retry-After": "5"},
        )
