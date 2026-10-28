"""
Utility functions for blockchain RPC endpoints.
"""

import json
import math
import sqlite3
import time
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from aitbc.constants import DATA_DIR

from ..base_models import _to_ait_address
from ..chain_id import ChainIdNotConfigured, resolve_chain_id
from ..config import settings
from ..logger import get_logger

_logger = get_logger(__name__)

_poa_proposers: dict[str, Any] = {}

# The two payload actions that make a GPU_MARKET transaction a purchasable
# listing. The same transaction type also carries job settlements
# ("software_job"), cancellations and ratings; those have no offer payload at
# all -- no service_type, no model, price 0 -- so anything that means "an offer"
# has to say so here rather than trusting the type alone.
OFFER_ACTIONS = ("offer", "software_offer")


def _as_id_list(value: Any) -> list[str]:
    """A payload field that may hold one id, a list of ids, or nothing."""
    if not value:
        return []
    if not isinstance(value, list):
        value = [value]
    return [str(v) for v in value]


def withdrawn_listing_ids(rows: Iterable[tuple[Any, str | None, dict[str, Any]]]) -> set[str]:
    """Listing ids (``tx_<id>``) that their own seller has withdrawn.

    ``rows`` is every confirmed GPU_MARKET transaction as ``(id, sender,
    payload)``. A listing is withdrawn two ways: a cancellation (``action``
    ``cancel``/``cancelled``, or ``status`` ``cancelled``) names it in
    ``order_id``/``order_ids``, or a later offer names it in ``replaces``.

    Either takes effect only when its sender is the seller of the listing it
    names. Admission checks the signature against ``from`` and nothing else,
    and consensus has no GPU_MARKET branch, so any funded account can put any
    listing id into a cancel or a ``replaces`` list and confirm it; without
    this comparison that hid another seller's offer from every reader. A
    reference to a listing the sender does not own, or to an id that is not a
    confirmed GPU_MARKET row, is ignored.

    A cancellation also withdraws its own row, so it never reads as an offer.
    """
    parsed = [(tx_id, _to_ait_address(sender or ""), payload) for tx_id, sender, payload in rows]
    seller = {f"tx_{tx_id}": who for tx_id, who, _ in parsed}
    withdrawn: set[str] = set()
    for tx_id, who, payload in parsed:
        is_cancel = (
            payload.get("action", "") in ("cancel", "cancelled") or str(payload.get("status", "")).lower() == "cancelled"
        )
        if is_cancel:
            withdrawn.add(f"tx_{tx_id}")
            named = [*_as_id_list(payload.get("order_id")), *_as_id_list(payload.get("order_ids"))]
        else:
            named = _as_id_list(payload.get("replaces"))
        if not who:
            continue
        withdrawn.update(listing_id for listing_id in named if seller.get(listing_id) == who)
    return withdrawn


# Credit types the bridge lifecycle writes straight into the mempool via
# mempool.add() (cross_chain/bridge_transfer.py), bypassing public submission
# entirely: they credit the recipient with no sender debit and no sender
# account. Nothing client-submitted may carry them, so both public intake
# paths — REST admission and gossip ingest — refuse them. Keep in step with
# the credit branches in state/state_transition.py and
# state/pure_state_transition.py.
PREREGISTERED_CREDIT_TX_TYPES = frozenset({"BRIDGE_RELEASE", "BRIDGE_REFUND"})


def _resolved_tx_type(tx_data: dict[str, Any]) -> str:
    """Resolve the type a transaction is applied under.

    Mirrors ``state.state_transition._tx_type`` without the DB record: the
    top-level ``type`` wins, except a missing or ``TRANSFER`` top-level type
    yields to ``payload["type"]``. Intake must refuse a type under the same
    resolution consensus applies it, or a ``TRANSFER`` envelope carrying a
    credit ``payload.type`` would pass the door and still take the credit
    branch.
    """
    tx_type = tx_data.get("type") or "TRANSFER"
    if not isinstance(tx_type, str):
        tx_type = "TRANSFER"
    tx_type = tx_type.upper()
    if tx_type == "TRANSFER":
        payload = tx_data.get("payload")
        if isinstance(payload, dict):
            payload_type = payload.get("type")
            if isinstance(payload_type, str) and payload_type:
                tx_type = payload_type.upper()
    return tx_type


def gossip_transaction_drop_reason(tx_data: dict[str, Any]) -> str | None:
    """Return why a gossip-delivered transaction must be dropped, or None.

    The ``transactions`` gossip topics are public-publish by design — any
    connected peer may inject a transaction envelope — so mempool ingest must
    enforce the same signature policy as REST submission instead of trusting
    the transport. Every transaction is verified against ``from`` and nothing
    unsigned is admitted, because the consensus signature check only fires
    when a signature is present — an unsigned ``TRANSFER`` naming any funded
    sender would otherwise be mineable. The old V23-90 unsigned-offer
    exemption is closed: listing paths resolve a signing wallet for
    ``SHOP_WALLET_ADDRESS``.

    Pre-registered credit types are refused outright: the bridge writes them
    into the mempool internally, so no gossiped copy is legitimate.
    """
    if _resolved_tx_type(tx_data) in PREREGISTERED_CREDIT_TX_TYPES:
        return "internal_tx_type"
    sender = tx_data.get("from")
    signature = tx_data.get("signature") or tx_data.get("sig")
    if not signature:
        return "missing_signature"
    if not verify_transaction_signature(tx_data, signature, sender or ""):
        return "invalid_signature"
    if _resolved_tx_type(tx_data) == "MESSAGE":
        # Same envelope gate as REST admission — a broken forum claim is junk.
        from ..messaging_index import admission_error

        message_error = admission_error(tx_data.get("payload"), sender or "")
        if message_error:
            from ..messaging_metrics import note_admission_rejected

            note_admission_rejected(message_error)
            return "invalid_aitbc_msg"
    return None


def _unsigned_tx_fields(tx_data: dict[str, Any]) -> dict[str, Any]:
    """Return the fields that go into the signed transaction message.

    Excludes the signature itself, gossip-attached ``tx_hash``, and the
    internal ``value`` alias when ``amount`` is present.
    """
    excluded = {"signature", "sig", "tx_hash"}
    if "amount" in tx_data:
        excluded.add("value")
    return {k: v for k, v in tx_data.items() if k not in excluded}


def verify_transaction_signature(tx_data: dict[str, Any], signature: str, sender: str) -> bool:
    """Verify that a transaction was signed by the claimed sender.

    Uses Ethereum-style signature recovery (secp256k1) to recover the
    signer's address from the signature and compare it to the sender field.

    The signed message is the keccak256 hash of the canonical JSON encoding
    of the transaction fields (excluding the signature field itself).
    """
    if not signature or not sender:
        return False

    message = json.dumps(_unsigned_tx_fields(tx_data), sort_keys=True, separators=(",", ":")).encode()

    try:
        from eth_utils import keccak

        from aitbc.crypto.signature_recovery import SignatureMalformed, verify_signature

        try:
            return verify_signature(keccak(message), signature, sender)
        except SignatureMalformed as e:
            # V23-04: distinguishable from a recovered-wrong-address False below.
            _logger.warning("Malformed transaction signature (encoding fault): %s", e)
            return False
    except Exception as e:
        _logger.warning("Signature verification failed: %s", e)
        return False


def sign_transaction_data(tx_data: dict[str, Any], private_key: str) -> str:
    """Sign a transaction dict with a secp256k1 private key.

    Produces the same 65-byte hex signature that ``verify_transaction_signature``
    expects. The signed message is the keccak256 hash of the canonical JSON
    encoding of the transaction fields, excluding the ``signature`` field and the
    internal ``value`` alias when ``amount`` is present.
    """
    import json

    from eth_keys import keys
    from eth_utils import keccak

    message = json.dumps(_unsigned_tx_fields(tx_data), sort_keys=True, separators=(",", ":")).encode()
    msg_hash = keccak(message)
    pk_hex = private_key.removeprefix("0x")
    pk = keys.PrivateKey(bytes.fromhex(pk_hex))
    sig = pk.sign_msg_hash(msg_hash)
    return sig.to_hex()


def verify_request_signature(sender: str, signature: str, message_data: dict[str, Any]) -> bool:
    """Verify a generic request signature (for bridge, staking, etc.).

    The signed message is the keccak256 hash of the canonical JSON encoding
    of the provided message_data dict.
    """
    if not signature or not sender:
        return False

    message = json.dumps(message_data, sort_keys=True, separators=(",", ":")).encode()

    try:
        from eth_utils import keccak

        from aitbc.crypto.signature_recovery import SignatureMalformed, verify_signature

        try:
            return verify_signature(keccak(message), signature, sender)
        except SignatureMalformed as e:
            _logger.warning("Malformed request signature (encoding fault): %s", e)
            return False
    except Exception as e:
        _logger.warning("Request signature verification failed: %s", e)
        return False


def set_poa_proposer(proposer: Any, chain_id: str | None = None) -> None:
    """Set the global PoA proposer instance"""
    if chain_id is None:
        chain_id = getattr(getattr(proposer, "_config", None), "chain_id", None) or get_chain_id(None)
    _poa_proposers[chain_id] = proposer


def get_poa_proposer(chain_id: str | None = None) -> Any:
    """Get the global PoA proposer instance"""
    chain_id = get_chain_id(chain_id)
    return _poa_proposers.get(chain_id)


def get_chain_id(chain_id: str | None = None) -> str:
    """Get chain_id from parameter or the configured default.

    Raises ``ChainIdNotConfigured`` when no chain id is configured instead
    of returning a hard-coded fallback.
    """
    return resolve_chain_id(chain_id)


def validate_chain_id(chain_id: str) -> bool:
    """Validate that chain_id is in supported_chains list."""
    return chain_id in get_supported_chains()


def get_supported_chains() -> list[str]:
    """Get list of supported chain IDs"""
    chains = [chain.strip() for chain in settings.supported_chains.split(",") if chain.strip()]
    if not chains and settings.chain_id:
        return [settings.chain_id]
    return chains


def _require_supported_chain(chain_id: str) -> None:
    """Refuse a chain_id outside supported_chains — shared by every mempool intake branch."""
    supported_chains = get_supported_chains()
    if not chain_id:
        raise ValueError("transaction.chain_id is required")
    if supported_chains and chain_id not in supported_chains:
        raise ValueError(f"unsupported chain_id '{chain_id}'. Supported chains: {supported_chains}")


def get_chain_db(chain_id: str | None = None) -> Any:
    """Get chain-specific database engine"""
    from ..database import get_engine

    resolved_chain_id = get_chain_id(chain_id)
    if not validate_chain_id(resolved_chain_id):
        raise HTTPException(status_code=400, detail=f"Chain {resolved_chain_id} not in supported_chains")
    return get_engine(resolved_chain_id)


def normalize_transaction_data(tx_data: dict[str, Any], chain_id: str) -> dict[str, Any]:
    """Normalize and validate transaction data"""
    sender = tx_data.get("from")
    recipient = tx_data.get("to")
    if not isinstance(sender, str) or not sender.strip():
        raise ValueError("transaction.from is required")
    if not isinstance(recipient, str) or not recipient.strip():
        raise ValueError("transaction.to is required")

    try:
        amount = int(tx_data["amount"])
    except KeyError as exc:
        raise ValueError("transaction.amount is required") from exc
    except (TypeError, ValueError) as exc:
        raise ValueError("transaction.amount must be an integer") from exc

    try:
        fee = int(tx_data.get("fee", 36))
    except (TypeError, ValueError) as exc:
        raise ValueError("transaction.fee must be an integer") from exc

    try:
        nonce = int(tx_data.get("nonce", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("transaction.nonce must be an integer") from exc

    if amount < 0:
        raise ValueError("transaction.amount must be non-negative")
    if fee < 0:
        raise ValueError("transaction.fee must be non-negative")
    if nonce < 0:
        raise ValueError("transaction.nonce must be non-negative")

    payload = tx_data.get("payload", {})
    if payload is None:
        payload = {}

    tx_type = tx_data.get("type", "TRANSFER")
    if tx_type:
        tx_type = tx_type.upper()

    # Ensure payload is a dict
    if isinstance(payload, str):
        try:
            import json

            payload = json.loads(payload)
        except Exception:
            payload = {}

    if not isinstance(payload, dict):
        payload = {}

    return {
        "chain_id": chain_id,
        "type": tx_type,
        "from": sender.strip(),
        "to": recipient.strip(),
        "amount": amount,
        "value": amount,  # Add value field for state transition compatibility
        "fee": fee,
        "nonce": nonce,
        "payload": payload,
        "signature": tx_data.get("signature"),
    }


def get_bridge_admin_addresses() -> set[str]:
    """Return the configured bridge admin addresses as a lowercase set."""
    return {a.strip().lower() for a in settings.bridge_admin_addresses.split(",") if a.strip()}


_ADMIN_MAX_SKEW_SECS = 300
# Slightly longer than the 600 s freshness span (±300 s) so a nonce spent at
# the earliest acceptable instant still covers the body's latest one.
_ADMIN_NONCE_TTL_SECS = 660


def _parse_issued_at(value: Any) -> float | None:
    """Epoch seconds for an issued_at given as a number or ISO-8601 string.

    Non-finite numbers are rejected: ``json`` accepts ``NaN``/``Infinity``
    literals, and ``abs(now - nan) > SKEW`` is False, which would otherwise
    let a NaN-signed payload stay "fresh" forever.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        ts = float(value)
        return ts if math.isfinite(ts) else None
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        try:
            ts = dt.timestamp()
        except (OverflowError, OSError):
            return None
        return ts if math.isfinite(ts) else None
    return None


def _nonce_db_path() -> Path:
    """Nonce store shared by every RPC worker process on this node.

    A dedicated file next to the chain databases — deliberately NOT a table
    in ``chain.db``: ``/rpc/import-chain`` can wipe the chain database, and a
    replay cache wiped along with it would silently reopen the window.
    """
    return DATA_DIR / "data" / "admin_nonces.db"


def _nonce_seen(nonce: str) -> bool:
    """Register ``nonce`` in the shared store; True when already used.

    The PRIMARY KEY constraint makes check-and-insert atomic across the
    hub's four gunicorn workers — an in-memory dict would give each worker
    its own cache and let one captured request replay once per worker. The
    file also survives service restarts, which an in-memory cache does not.
    """
    db_path = _nonce_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    conn = sqlite3.connect(db_path, timeout=5)
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS admin_nonce (nonce TEXT PRIMARY KEY, expires_at REAL NOT NULL)")
        conn.execute("DELETE FROM admin_nonce WHERE expires_at <= ?", (now,))
        conn.commit()
        try:
            conn.execute(
                "INSERT INTO admin_nonce (nonce, expires_at) VALUES (?, ?)",
                (nonce, now + _ADMIN_NONCE_TTL_SECS),
            )
            conn.commit()
            return False
        except sqlite3.IntegrityError:
            return True
    finally:
        conn.close()


def _request_freshness_error(sign_payload: dict[str, Any]) -> str | None:
    """Return why a signed payload fails the replay guard, or None when fresh.

    Same checks as ``_check_request_freshness`` (which logs and wraps this).
    Reasons are written for the operator reading a 403 detail — in particular
    the ``target_chain_id`` mismatch message spells out that the field binds
    the *serving* node's own chain id, not the chain the payload is about
    (Refs #679: registration payloads for a companion island must carry the
    destination node's chain id here).
    """
    issued = _parse_issued_at(sign_payload.get("issued_at"))
    if issued is None or abs(time.time() - issued) > _ADMIN_MAX_SKEW_SECS:
        return "missing, non-finite or stale issued_at (must be within ±5 min of node time)"
    try:
        local_chain = resolve_chain_id()
    except ChainIdNotConfigured:
        # Fail closed: with no configured chain this node cannot prove the
        # request targets it.
        return "no chain id configured on this node"
    target_chain = sign_payload.get("target_chain_id")
    if not isinstance(target_chain, str) or not target_chain:
        return "missing target_chain_id (must be the chain id of the node this request is sent to)"
    if target_chain != local_chain:
        return (
            f"target_chain_id '{target_chain}' does not match this node's chain '{local_chain}' — "
            "target_chain_id binds the node serving the request (its own chain id), "
            "not the chain the payload is about; set it to the destination node's chain id"
        )
    target_node = sign_payload.get("target_node_id")
    if target_node is not None:
        local_node = settings.p2p_node_id or settings.proposer_id or ""
        # Fail closed: a request naming a target node cannot be honoured by a
        # node with no configured identity — it cannot prove it is the target.
        if not local_node or str(target_node) != local_node:
            return f"target_node_id '{target_node}' does not match this node"
    nonce = sign_payload.get("nonce")
    if not isinstance(nonce, str) or not nonce:
        return "missing nonce"
    if _nonce_seen(nonce):
        return "nonce already used"
    return None


def _check_request_freshness(sign_payload: dict[str, Any]) -> bool:
    """Replay guard for admin-signed payloads.

    Requires ``issued_at`` within the skew window, a ``target_chain_id``
    matching this node's chain, and a single-use ``nonce``. ``target_node_id``
    is optional but verified when present — all three fields are part of the
    signed message, so they cannot be stripped or swapped without
    invalidating the signature.
    """
    reason = _request_freshness_error(sign_payload)
    if reason is not None:
        _logger.warning("Rejected admin request: %s", reason)
        return False
    return True


_LEGACY_ACCEPT_WARNED: set[str] = set()


def record_guard_outcome(endpoint: str, *, guarded: bool) -> None:
    """Count one replay-guarded request whose signature already verified.

    Called strictly after the signature (and freshness, when guarded) check
    passed, so unauthenticated traffic cannot inflate the old-form reading.
    ``guarded=True`` counts ``new_form``; ``guarded=False`` counts
    ``legacy_accepted`` and logs one WARNING per endpoint per process so the
    journal shows old-form signers are still live. Never raises into the
    request path — the counter must not break the routes it watches.
    """
    from .. import metrics

    form = "new_form" if guarded else "legacy_accepted"
    try:
        metrics.replay_guard_requests_total.labels(endpoint=endpoint, form=form).inc()
    except Exception:  # pragma: no cover - metrics must never break a route
        _logger.exception("replay-guard counter increment failed")
    if not guarded and endpoint not in _LEGACY_ACCEPT_WARNED:
        _LEGACY_ACCEPT_WARNED.add(endpoint)
        _logger.warning(
            "[REPLAY-GUARD] legacy unsigned-window body accepted on %s — an old-form signer is live "
            "(counted in blockchain_replay_guard_requests_total{form=legacy_accepted})",
            endpoint,
        )


def apply_replay_guard_fields(
    request_data: dict[str, Any],
    sign_data: dict[str, Any],
    *,
    require_guard: bool,
    label: str,
    endpoint: str,
) -> tuple[dict[str, Any], bool]:
    """Attach ``issued_at``/``nonce`` from the request body to the signed dict.

    Shared replay-guard plumbing (SEC-REPLAY-1/-2): a signed dict without a
    freshness field and nonce is replayable verbatim. When either field is
    present in the request both ride inside the signed dict — they cannot be
    stripped without breaking the signature — and the caller must run the
    freshness check (returns ``guarded=True``). When neither is present the
    legacy form stands unless ``require_guard`` (the operator flag) refuses it.
    """
    issued_at = request_data.get("issued_at")
    nonce = request_data.get("nonce")
    if issued_at is not None or nonce is not None:
        sign_data["issued_at"] = issued_at
        sign_data["nonce"] = nonce
        return sign_data, True
    if require_guard:
        from .. import metrics

        try:
            metrics.replay_guard_requests_total.labels(endpoint=endpoint, form="legacy_refused").inc()
        except Exception:  # pragma: no cover - metrics must never break a route
            _logger.exception("replay-guard counter increment failed")
        raise HTTPException(
            status_code=400,
            detail=f"{label} require a replay-guarded signature (issued_at + nonce)",
        )
    return sign_data, False


def check_signed_request_freshness(sign_data: dict[str, Any], *, nonce_key: str) -> None:
    """Reject a guarded body whose signed freshness/nonce fails.

    ``issued_at`` must parse and sit within ``_ADMIN_MAX_SKEW_SECS``;
    ``nonce`` must be a non-empty string first-seen under ``nonce_key`` in the
    shared sqlite store (the key carries the endpoint prefix and sender, so
    nonces cannot collide across endpoints or accounts).
    """
    issued = _parse_issued_at(sign_data.get("issued_at"))
    if issued is None or abs(time.time() - issued) > _ADMIN_MAX_SKEW_SECS:
        raise HTTPException(status_code=403, detail="Signature requires a fresh issued_at (±5 min)")
    nonce = sign_data.get("nonce")
    if not isinstance(nonce, str) or not nonce:
        raise HTTPException(status_code=403, detail="Signature requires a nonce")
    if _nonce_seen(nonce_key):
        raise HTTPException(status_code=403, detail="Nonce already used — this signed body cannot be replayed")


def verify_signed_request_with_freshness(
    sender: str,
    signature: Any,
    sign_data: dict[str, Any],
    *,
    guarded: bool,
    nonce_key: str,
) -> None:
    """Verify ``signature`` over ``sign_data``, then spend the nonce if guarded.

    Freshness runs strictly after signature verification: an unauthenticated
    caller must not be able to burn a nonce ahead of its legitimate use.
    """
    if not verify_request_signature(sender, signature, sign_data):
        raise HTTPException(status_code=403, detail="Invalid sender signature")
    if guarded:
        check_signed_request_freshness(sign_data, nonce_key=nonce_key)


def verify_admin_signature(payload: dict[str, Any], admin_address: str | None, admin_signature: str | None) -> bool:
    """Verify that an administrative request was signed by a configured bridge admin.

    The signed message is the canonical JSON of ``payload`` excluding the
    ``admin_signature`` field. The recovered signer must match
    ``admin_address`` and that address must appear in ``bridge_admin_addresses``.

    The signed payload must also carry ``issued_at`` (ISO-8601 or epoch
    seconds, within ±5 minutes of node time), a ``target_chain_id`` matching
    this node's chain, and a unique ``nonce`` — a captured signature cannot
    be replayed once its window closes. ``target_node_id`` is optional but
    must match this node when present, binding the signature to its intended
    destination. Nonces are recorded in a sqlite file shared by all RPC
    worker processes.
    """
    reason = admin_signature_failure(payload, admin_address, admin_signature)
    if reason is None:
        return True
    _logger.warning("Rejected admin request: %s", reason)
    return False


def admin_signature_failure(payload: dict[str, Any], admin_address: str | None, admin_signature: str | None) -> str | None:
    """Return the rejection reason for an admin-signed request, or None when valid.

    Same checks and ordering as ``verify_admin_signature`` — signature first,
    freshness (nonce spend) after — but the reason string is meant for the
    403 detail so callers see *which* guard tripped instead of a generic
    "invalid admin signature" (Refs #679).
    """
    if not admin_address or not admin_signature:
        return "missing admin_address or admin_signature"

    admins = get_bridge_admin_addresses()
    if not admins:
        return "no bridge_admin_addresses configured on this node"

    if admin_address.lower() not in admins:
        return f"admin address {admin_address} is not in bridge_admin_addresses"

    sign_payload = {k: v for k, v in payload.items() if k != "admin_signature"}
    if not verify_request_signature(admin_address, admin_signature, sign_payload):
        return "admin signature does not verify over the payload"
    return _request_freshness_error(sign_payload)


def require_admin_signature(payload: dict[str, Any], admin_address: str | None, admin_signature: str | None) -> None:
    """Raise HTTPException(403) naming the reason when the admin signature fails."""
    reason = admin_signature_failure(payload, admin_address, admin_signature)
    if reason is None:
        return
    _logger.warning("Rejected admin request: %s", reason)
    raise HTTPException(status_code=403, detail=f"Invalid or unauthorized admin signature: {reason}")
