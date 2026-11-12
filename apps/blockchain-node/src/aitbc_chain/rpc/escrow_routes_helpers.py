"""Shared escrow helpers: auth, settlement keys, nonce floors, and finder lookups for the escrow RPC split (#1867 pure-move).

Import ``aitbc_chain.rpc.escrow_routes`` first (it wires these
modules into the ``escrow_routes`` facade); this module is not meant to be
imported directly. All facade-owned names are reached via ``_er.`` so
monkeypatching ``escrow_routes.<name>`` stays visible."""

from __future__ import annotations

from . import escrow_routes as _er


def _chain_id() -> str:
    """This node's chain id, resolved lazily per call.

    Resolved per call rather than at import so a misconfigured process fails at
    the request site (503 via the ChainIdNotConfigured handler), not at module
    load, and so tests can set the id after import.
    """
    return _er.resolve_chain_id()


def _energy_operator_address() -> str:
    """Return the operator address that must have signed protected energy quotes.

    Read per call rather than pinned at import so the gate follows a config
    change on restart-free reloads and so tests can set it. Empty means the
    check is skipped. The same variable configures the coordinator's
    ``settings.energy_operator_address``, so setting it turns both gates on
    together. Deployment state today: hub's coordinator env and hub1's rpc
    env carry it; hub's rpc env does not, so this gate stays off on the
    node that actually serves protected creates.
    """
    return _er.os.getenv("ENERGY_OPERATOR_ADDRESS", "").strip()


def _energy_max_rate_age_seconds() -> int:
    """Return the freshness window applied to a protected quote's rate.

    Read per call rather than pinned at import, same pattern as
    ``_energy_operator_address``. The variable name matches the
    coordinator's ``settings.energy_max_rate_age_seconds`` so one operator
    setting aligns the issuance, funding, and node gates. Unset,
    non-integer, or non-positive values fall back to the shared
    ``DEFAULT_MAX_RATE_AGE_SECONDS`` (86400s) — the operator policy the
    coordinator already runs on hub.
    """
    try:
        value = int(_er.os.getenv("ENERGY_MAX_RATE_AGE_SECONDS", ""))
    except ValueError:
        return _er._FALLBACK_MAX_RATE_AGE_SECONDS
    return value if value > 0 else _er._FALLBACK_MAX_RATE_AGE_SECONDS


def _settled_leg_ait(stored_units: int | None, settled_at: _er.Any, locked_units: int) -> str:
    """Return one settled leg of an escrow as AIT.

    ``released_amount``/``refunded_amount`` are NULL on rows written before metered
    settlement and on rows rebuilt by a node that did not serve the release. Both
    are healed from the chain by ``backfill_settlement_legs`` on the way in, so
    this is the last resort for an escrow whose settlement txns this node has not
    synced. It reports the whole lock, which is the right order of magnitude but
    overstates a release by the platform fee the provider never received.
    """
    if stored_units is not None:
        return str(_er.units_to_ait(stored_units))
    return str(_er.units_to_ait(locked_units)) if settled_at else "0"


def get_node_wallet_address() -> str:
    """Return the node wallet that custodies escrow locks.

    This is the address ``_build_lock_tx`` requires as the ESCROW_LOCK ``to``.
    It is deliberately not the consensus ``proposer_id``: the proposer signs
    blocks and is per-node, while the node wallet holds escrow and is shared
    across the nodes that settle for a chain. ``/health`` advertises it so
    clients do not have to guess which of the two to lock against.
    """
    return _er._NODE_WALLET


def verify_rpc_api_key(api_key: str | None = _er.Security(_er._api_key_header)) -> str:
    """Require a valid X-API-Key header for all escrow RPC routes."""
    if not _er._RPC_API_KEY:
        raise _er.HTTPException(
            status_code=_er.status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Escrow RPC is not configured for authentication",
        )
    if api_key is None or not _er.hmac.compare_digest(api_key.encode(), _er._RPC_API_KEY.encode()):
        _er._logger.warning("Rejected escrow RPC request: missing or invalid X-API-Key")
        raise _er.HTTPException(
            status_code=_er.status.HTTP_403_FORBIDDEN,
            detail="Forbidden: missing or invalid API key",
        )
    return api_key


def rpc_peer_key_accepted(api_key: str | None) -> bool:
    """True when ``api_key`` is this node's RPC key, a configured peer-node
    key, or a live issued join key.

    Shared by the HTTP dependency below and the /subscribe/ws handshake
    (#1702), which carries the key inside the WebSocket message instead of
    an X-API-Key header.
    """
    if not api_key:
        return False
    if _er._RPC_API_KEY and _er.hmac.compare_digest(api_key.encode(), _er._RPC_API_KEY.encode()):
        return True
    if any(_er.hmac.compare_digest(api_key.encode(), k.encode()) for k in _er._RPC_API_PEER_KEYS):
        return True
    from .peer_keys import is_issued_key

    return is_issued_key(api_key)


def verify_rpc_peer_key(api_key: str | None = _er.Security(_er._api_key_header)) -> str:
    """Accept this node's own RPC key, a configured peer-node key, or an
    issued join key.

    Node-to-hub internal routes (subscription register/heartbeat/lease
    revocation). Distinct from ``verify_rpc_api_key`` so a leaked peer key
    only ever reaches lease state, never the control plane.

    Issued keys come from ``POST /rpc/join`` (see ``peer_keys.py``) and are
    bound to a single node_id — the subscription routes enforce that binding,
    so an issued key can only ever manage its own lease.
    """
    if _er.rpc_peer_key_accepted(api_key):
        return api_key or ""
    _er._logger.warning("Rejected peer RPC request: missing or invalid X-API-Key")
    raise _er.HTTPException(
        status_code=_er.status.HTTP_403_FORBIDDEN,
        detail="Forbidden: missing or invalid API key",
    )


def rpc_fleet_key_accepted(api_key: str | None) -> bool:
    """True when ``api_key`` is this node's RPC key or a configured
    ``BLOCKCHAIN_RPC_API_KEY_PEERS`` fleet key — never an issued join key.

    Bulk/state-disclosure routes accept fleet keys only: an issued join key
    is self-serve (POST /rpc/join is anonymous, rate-limited) and must not
    unlock a full chain export (#1871).
    """
    if not api_key:
        return False
    if _er._RPC_API_KEY and _er.hmac.compare_digest(api_key.encode(), _er._RPC_API_KEY.encode()):
        return True
    return any(_er.hmac.compare_digest(api_key.encode(), k.encode()) for k in _er._RPC_API_PEER_KEYS)


def verify_rpc_export_key(api_key: str | None = _er.Security(_er._api_key_header)) -> str:
    """Require a fleet RPC key (this node's admin key or a configured peer
    key) — issued join keys are rejected.

    Used by bulk/state-disclosure routes such as ``/rpc/export-chain``.
    ``force_sync`` callers keep working: each peer authenticates with its
    own ``BLOCKCHAIN_RPC_API_KEY``, which the exporting node accepts via
    its ``BLOCKCHAIN_RPC_API_KEY_PEERS`` list.
    """
    if _er.rpc_fleet_key_accepted(api_key):
        return api_key or ""
    _er._logger.warning("Rejected export RPC request: missing, invalid, or join-scoped X-API-Key")
    raise _er.HTTPException(
        status_code=_er.status.HTTP_403_FORBIDDEN,
        detail="Forbidden: missing or invalid API key",
    )


def _resolve_chain_account(address: str) -> str | None:
    """Return the canonical 0x form of ``address`` if it is valid.

    v0.25.5: do not require the account to exist.  The block state transition
    creates recipient accounts on first credit, so a provider can be paid even
    if it has never transacted before.
    """
    try:
        return _er._to_canonical(address)
    # intentional silent failure
    except Exception:  # nosec B110
        pass
    return None


async def _get_account_nonce(address: str) -> int:
    """Fetch current nonce for an account from the chain."""
    try:
        r = await _er.SharedHttpClient.get(f"{_er._HUB_RPC_URL}/accounts/{address}")
        if r.status_code == 200:
            return int(r.json().get("nonce", 0))
    except Exception:
        pass
    return 0


def _compute_tx_signing_hash(tx: dict[str, _er.Any]) -> str:
    """Return the keccak hash the RPC verifies for a transaction signature."""
    canonical = _er.json.dumps(_er._unsigned_tx_fields(tx), sort_keys=True, separators=(",", ":")).encode()
    return "0x" + _er.keccak(canonical).hex()


def _to_canonical(address: str) -> str:
    """Return the canonical EIP-55 0x form of an address, falling back to input."""
    evm = _er.canonical_address(address)
    if evm.startswith("0x"):
        return evm
    return str(address)


def _optional_agent_binding(body: dict[str, _er.Any]) -> tuple[str | None, str | None]:
    buyer_agent_id = body.get("buyer_agent_id")
    provider_agent_id = body.get("provider_agent_id")
    for key, value in (("buyer_agent_id", buyer_agent_id), ("provider_agent_id", provider_agent_id)):
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip():
            raise _er.HTTPException(status_code=400, detail=f"{key} must be a non-empty string")
    return (
        buyer_agent_id.strip() if isinstance(buyer_agent_id, str) else None,
        provider_agent_id.strip() if isinstance(provider_agent_id, str) else None,
    )


def _check_stored_agent_binding(row: _er.Escrow, buyer_agent_id: str | None, provider_agent_id: str | None) -> None:
    if buyer_agent_id and row.buyer_agent_id and row.buyer_agent_id != buyer_agent_id:
        raise _er.HTTPException(
            status_code=409,
            detail=f"escrow for job {row.job_id} is already bound to buyer agent {row.buyer_agent_id}",
        )
    if provider_agent_id and row.provider_agent_id and row.provider_agent_id != provider_agent_id:
        raise _er.HTTPException(
            status_code=409,
            detail=f"escrow for job {row.job_id} is already bound to provider agent {row.provider_agent_id}",
        )


def _escrow_agent_fields(db_record: _er.Escrow | None) -> dict[str, str]:
    if db_record is None:
        return {}
    out: dict[str, str] = {}
    if db_record.buyer_agent_id:
        out["buyer_agent_id"] = db_record.buyer_agent_id
    if db_record.provider_agent_id:
        out["provider_agent_id"] = db_record.provider_agent_id
    return out


def _get_settlement_key() -> str:
    """Return the configured non-treasury escrow release key, falling back to treasury."""
    if _er._ESCROW_RELEASE_PRIVATE_KEY:
        return _er._ESCROW_RELEASE_PRIVATE_KEY
    if _er._GENESIS_WALLET_PRIVATE_KEY:
        _er._logger.warning(
            "ESCROW_RELEASE: ESCROW_RELEASE_PRIVATE_KEY is not set; signing payouts with the "
            "treasury key. Configure a dedicated settlement key to decouple settlement from the treasury."
        )
    return _er._GENESIS_WALLET_PRIVATE_KEY


def _get_settlement_address() -> str | None:
    """Return the canonical settlement address for ESCROW_RELEASE signing.

    The address must be the one the signing key actually controls: the RPC
    verifies the signature against the transaction ``from`` field, so a
    key/address mismatch produces a 403 and the provider is never paid. When
    ``ESCROW_RELEASE_ADDRESS`` is set it is checked against the address derived
    from the signing key and a mismatch is refused rather than submitted.
    """
    key = _er._get_settlement_key()
    if not key:
        return None
    try:
        derived = _er.canonical_address(_er.derive_ethereum_address(key))
    except Exception as e:
        _er._logger.error("ESCROW_RELEASE: failed to derive settlement address: %s", e)
        return None
    if not _er._ESCROW_RELEASE_ADDRESS:
        return derived
    configured = _er.canonical_address(_er._ESCROW_RELEASE_ADDRESS)
    if configured != derived:
        _er._logger.error(
            "ESCROW_RELEASE: settlement key/address mismatch - ESCROW_RELEASE_ADDRESS is %s but the "
            "configured signing key controls %s. Refusing to submit a transaction the RPC would "
            "reject; fix ESCROW_RELEASE_PRIVATE_KEY / ESCROW_RELEASE_ADDRESS in the node environment.",
            configured,
            derived,
        )
        return None
    return configured


def _settlement_signing_ready() -> bool:
    """True when this node can sign settlement legs: a key resolves (the
    dedicated ESCROW_RELEASE_PRIVATE_KEY or the genesis fallback) and the
    derived address matches ESCROW_RELEASE_ADDRESS when one is configured."""
    return bool(_er._get_settlement_key()) and _er._get_settlement_address() is not None


def _require_settlement_signing(job_id: str, op: str) -> None:
    """Refuse a settlement-capable escrow op on a node that cannot sign it.

    A node without the settlement key can still accept and submit the buyer's
    ESCROW_LOCK, yet can never serve the release or refund — every
    settlement-shaped op must fail before money moves. The 503 names the
    settlement node's RPC URL when the node knows it (HUB_RPC_URL), so a
    wrong-routed caller can fix the routing instead of retrying here.
    """
    if _er._settlement_signing_ready():
        return
    _er._logger.warning(
        "%s: refusing job_id=%s - settlement key/address is missing or mismatched",
        op,
        job_id,
    )
    _er.escrow_settlement_refused_total.labels(op=op.removeprefix("ESCROW_").lower()).inc()
    detail = "Settlement key/address is not configured correctly on this node"
    hub_rpc = _er.os.getenv("HUB_RPC_URL", "").strip().rstrip("/")
    if hub_rpc:
        detail += f"; the settlement node is at {hub_rpc}"
    raise _er.HTTPException(status_code=503, detail=detail)


def _fee_for(amount: int) -> int:
    """Default network fee for an escrow transaction.

    v0.25.6: use a 1% fee with a dust floor rather than the flat
    DEFAULT_TX_FEE_UNITS. For small escrow amounts (e.g. 0.01 AIT)
    the flat fee was equal to the value, which burned the entire
    payment if the lock was applied.
    """
    return max(36, amount // 100)


async def _find_existing_lock_tx(job_id: str) -> dict[str, _er.Any] | None:
    """Return the sealed ESCROW_LOCK transaction row for ``job_id``, if any."""
    try:
        r = await _er.SharedHttpClient.get(
            f"{_er._HUB_RPC_URL}/transactions?transaction_type=ESCROW_LOCK&job_id={job_id}&limit={_er._RELEASE_LOOKUP_LIMIT}"
        )
        if r.status_code != 200:
            return None
        for tx in r.json() or []:
            if isinstance(tx, dict) and (tx.get("payload") or {}).get("job_id") == job_id:
                return tx
    except Exception as e:
        _er._logger.warning("ESCROW_LOCK: settled-lock lookup failed for job_id=%s: %s", job_id, e)
    return None


async def _find_existing_lock(job_id: str) -> str | None:
    """Return the hash of an ESCROW_LOCK already on-chain for ``job_id``, if any.

    The create endpoint must be idempotent like the release/refund paths: a retry
    whose first attempt already mined must see the settled lock instead of
    submitting a second ESCROW_LOCK for the same job.
    """
    lock_tx = await _er._find_existing_lock_tx(job_id)
    settled_hash = (lock_tx or {}).get("tx_hash")
    return str(settled_hash) if settled_hash else None


async def _find_existing_release(job_id: str) -> str | None:
    """Return the hash of an ESCROW_RELEASE already on-chain for ``job_id``, if any.

    A retry must never pay twice. Once a first attempt is mined the nonce check rejects
    a replay, which looks like a failure even though the provider was paid -- so a
    reconciler that trusted the failure alone would retry forever. This lookup tells the
    two apart, and lets a retry return the transaction that already settled.

    The query filters on payload job_id server-side. An unfiltered scan was not merely
    slow: /transactions returns rows oldest-first and truncates to ``limit``, so a bounded
    scan silently missed recent settlements -- exactly the ones a retry asks about.
    """
    try:
        r = await _er.SharedHttpClient.get(
            f"{_er._HUB_RPC_URL}/transactions?transaction_type=ESCROW_RELEASE&job_id={job_id}&limit={_er._RELEASE_LOOKUP_LIMIT}"
        )
        if r.status_code != 200:
            return None
        for tx in r.json() or []:
            # Re-check the payload: an older node without the job_id filter would
            # otherwise return unrelated releases and settle the wrong job.
            if (tx.get("payload") or {}).get("job_id") == job_id:
                settled_hash = tx.get("tx_hash")
                return str(settled_hash) if settled_hash else None
    except Exception as e:
        _er._logger.warning("ESCROW_RELEASE: settled-release lookup failed for job_id=%s: %s", job_id, e)
    return None


async def _find_existing_refund(job_id: str) -> str | None:
    """Return the hash of an ESCROW_REFUND already on-chain for ``job_id``, if any.

    Refund retries must be idempotent in the same way as releases: once a refund lands,
    a later attempt must return the settled transaction rather than build a new one.
    """
    try:
        r = await _er.SharedHttpClient.get(
            f"{_er._HUB_RPC_URL}/transactions?transaction_type=ESCROW_REFUND&job_id={job_id}&limit={_er._RELEASE_LOOKUP_LIMIT}"
        )
        if r.status_code != 200:
            return None
        for tx in r.json() or []:
            if (tx.get("payload") or {}).get("job_id") == job_id:
                settled_hash = tx.get("tx_hash")
                return str(settled_hash) if settled_hash else None
    except Exception as e:
        _er._logger.warning("ESCROW_REFUND: settled-refund lookup failed for job_id=%s: %s", job_id, e)
    return None


def _fee_sweep_enabled() -> bool:
    return _er.os.getenv("ESCROW_FEE_SWEEP_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


def _fee_sweep_recipient() -> str | None:
    """Env-side fee recipient for sweep signing. Consensus re-checks the ``to``
    against the on-chain ``escrow_fee_recipient`` parameter at apply height;
    when they disagree the sweep is refused and stays visible in the metric."""
    raw = _er.os.getenv("ESCROW_FEE_RECIPIENT", "").strip()
    return _er._to_canonical(raw) if raw else None


async def _find_existing_fee_sweep(job_id: str) -> str | None:
    """Return the hash of an ESCROW_FEE_SWEEP already on-chain for ``job_id``, if any.

    Same dedupe contract as _find_existing_release/_find_existing_refund: a
    sealed sweep makes every later attempt a no-op, which is what lets the
    retry path offer the leg again safely.
    """
    try:
        r = await _er.SharedHttpClient.get(
            f"{_er._HUB_RPC_URL}/transactions?transaction_type=ESCROW_FEE_SWEEP&job_id={job_id}&limit={_er._RELEASE_LOOKUP_LIMIT}"
        )
        if r.status_code != 200:
            return None
        for tx in r.json() or []:
            if (tx.get("payload") or {}).get("job_id") == job_id:
                settled_hash = tx.get("tx_hash")
                return str(settled_hash) if settled_hash else None
    except Exception as e:  # noqa: BLE001 - probe containment: lookup failure must not fail the release
        _er._logger.warning("ESCROW_FEE_SWEEP: settled-sweep lookup failed for job_id=%s: %s", job_id, e)
    return None


async def _find_existing_receipt_claim(job_id: str) -> str | None:
    """Return the hash of a RECEIPT_CLAIM already on-chain for ``job_id``, if any.

    Same dedupe contract as _find_existing_release/_find_existing_fee_sweep: a
    sealed claim makes every later attempt a no-op.
    """
    try:
        r = await _er.SharedHttpClient.get(
            f"{_er._HUB_RPC_URL}/transactions?transaction_type=RECEIPT_CLAIM&job_id={job_id}&limit={_er._RELEASE_LOOKUP_LIMIT}"
        )
        if r.status_code != 200:
            return None
        for tx in r.json() or []:
            if (tx.get("payload") or {}).get("job_id") == job_id:
                settled_hash = tx.get("tx_hash")
                return str(settled_hash) if settled_hash else None
    except Exception as e:  # noqa: BLE001 - probe containment: lookup failure must not fail the release
        _er._logger.warning("RECEIPT_CLAIM: settled-claim lookup failed for job_id=%s: %s", job_id, e)
    return None


async def _mempool_nonce_floor(sender: str, sealed: int) -> int:
    """max(sealed, the sender's highest pending mempool nonce + 1).

    A probe miss (non-200, unreachable, malformed answer) degrades to ``sealed``;
    the submit retry covers the admitted-but-unlisted window."""
    try:
        r = await _er.SharedHttpClient.get(
            f"{_er._HUB_RPC_URL}/mempool?chain_id={_er._chain_id()}&limit={_er._FUNDING_LOCK_MEMPOOL_LIMIT}", timeout=5.0
        )
        if r.status_code != 200:
            return sealed
        pending_nonces = [
            tx["nonce"]
            for tx in r.json().get("transactions") or []
            if isinstance(tx, dict)
            and str(tx.get("from") or tx.get("sender") or "").lower() == sender.lower()
            and isinstance(tx.get("nonce"), int)
            and not isinstance(tx.get("nonce"), bool)
        ]
        if pending_nonces:
            return int(max(sealed, max(pending_nonces) + 1))
    except Exception as e:  # noqa: BLE001 - probe containment: a mempool miss degrades to the sealed nonce
        _er._logger.warning("mempool nonce probe failed for %s: %s", sender, e)
    return sealed


async def _settlement_next_nonce(sender: str) -> int:
    """Next free nonce for the settlement sender: the sealed account nonce plus
    any txs the sender already holds in the proposer mempool. The release a
    claim follows occupies the sealed-nonce slot, so an in-request claim must
    queue behind it — the mempool lookahead admits the +1."""
    return await _er._mempool_nonce_floor(sender, await _er._get_account_nonce(sender))


async def _get_account_nonce_strict(address: str) -> int | None:
    """Sealed nonce, or None when the read fails — unlike _get_account_nonce,
    which silently degrades to 0. Fine for reads, wrong for signing: a missed
    probe at nonce 0 is a guaranteed refusal for a used settlement key."""
    try:
        r = await _er.SharedHttpClient.get(f"{_er._HUB_RPC_URL}/accounts/{address}")
        if r.status_code == 200:
            return int(r.json().get("nonce", 0))
    except Exception:
        pass
    return None


async def _settlement_signing_nonce(sender: str) -> int | None:
    """Nonce for settlement signing: sealed account nonce plus the mempool
    lookahead, or None when the sealed read failed so a submitter never signs
    at nonce 0 on a missed probe (#781)."""
    sealed = await _er._get_account_nonce_strict(sender)
    if sealed is None:
        return None
    return await _er._mempool_nonce_floor(sender, sealed)


def _is_nonce_refusal(resp: _er.Any) -> bool:
    """The node refused the tx on its nonce — 'nonce slot (addr, n) already
    occupied' or 'Invalid nonce' in the response detail. Same refusal class as
    the coordinator's #779 _is_nonce_refusal, matched on the HTTP body here."""
    s = resp.text.lower()
    return "nonce slot" in s or "invalid nonce" in s


def _escrow_busy(job_id: str) -> _er.HTTPException:
    """The reply when another worker is mid-release/refund on this escrow (#780).

    425 with Retry-After, like the not-yet-sealed lock: every existing caller already
    treats it as "try again shortly" without spending a release attempt.
    """
    _er._logger.warning("Escrow %s is busy: another worker holds its release/refund lock", job_id)
    return _er.HTTPException(
        status_code=425,
        detail=f"Escrow for job_id={job_id} is being released or refunded by another request; retry shortly",
        headers={"Retry-After": "5"},
    )


async def _find_contract_id(mgr: _er.Any, job_id: str) -> str | None:
    """Find contract_id by job_id, loading from DB if missing."""
    for cid, contract in mgr.escrow_contracts.items():
        if contract.job_id == job_id:
            return str(cid)
    # Load from DB on demand before giving up.
    try:
        contract = await mgr.get_or_load_contract(job_id)
        if contract:
            return str(contract.contract_id)
    except Exception as e:
        _er._logger.warning("Failed to load contract for job %s: %s", job_id, e)
    return None
