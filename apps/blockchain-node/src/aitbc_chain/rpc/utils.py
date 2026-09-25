"""
Utility functions for blockchain RPC endpoints.
"""

import json
import math
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from aitbc.constants import DATA_DIR

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
    """Get chain_id from parameter or use default from settings"""
    if not chain_id:
        return settings.chain_id or "ait-mainnet"
    return chain_id


def validate_chain_id(chain_id: str) -> bool:
    """Validate that chain_id is in supported_chains list."""
    return chain_id in get_supported_chains()


def get_supported_chains() -> list[str]:
    """Get list of supported chain IDs"""
    chains = [chain.strip() for chain in settings.supported_chains.split(",") if chain.strip()]
    if not chains and settings.chain_id:
        return [settings.chain_id]
    return chains


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
_ADMIN_NONCE_TTL_SECS = 600


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


def _check_request_freshness(sign_payload: dict[str, Any]) -> bool:
    """Replay guard for admin-signed payloads.

    Requires ``issued_at`` within the skew window, a ``target_chain_id``
    matching this node's chain, and a single-use ``nonce``. ``target_node_id``
    is optional but verified when present — all three fields are part of the
    signed message, so they cannot be stripped or swapped without
    invalidating the signature.
    """
    issued = _parse_issued_at(sign_payload.get("issued_at"))
    if issued is None or abs(time.time() - issued) > _ADMIN_MAX_SKEW_SECS:
        _logger.warning("Rejected admin request: missing, non-finite or stale issued_at")
        return False
    local_chain = settings.chain_id or "ait-mainnet"
    target_chain = sign_payload.get("target_chain_id")
    if not isinstance(target_chain, str) or not target_chain or target_chain != local_chain:
        _logger.warning("Rejected admin request: target_chain_id '%s' does not match chain '%s'", target_chain, local_chain)
        return False
    target_node = sign_payload.get("target_node_id")
    if target_node is not None:
        local_node = settings.p2p_node_id or settings.proposer_id or ""
        # Fail closed: a request naming a target node cannot be honoured by a
        # node with no configured identity — it cannot prove it is the target.
        if not local_node or str(target_node) != local_node:
            _logger.warning("Rejected admin request: target_node_id '%s' does not match this node", target_node)
            return False
    nonce = sign_payload.get("nonce")
    if not isinstance(nonce, str) or not nonce:
        _logger.warning("Rejected admin request: missing nonce")
        return False
    if _nonce_seen(nonce):
        _logger.warning("Rejected admin request: nonce already used")
        return False
    return True


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
    if not admin_address or not admin_signature:
        return False

    admins = get_bridge_admin_addresses()
    if not admins:
        _logger.warning("No bridge_admin_addresses configured; rejecting admin request")
        return False

    if admin_address.lower() not in admins:
        _logger.warning("Admin address %s is not in bridge_admin_addresses", admin_address)
        return False

    sign_payload = {k: v for k, v in payload.items() if k != "admin_signature"}
    if not verify_request_signature(admin_address, admin_signature, sign_payload):
        return False
    return _check_request_freshness(sign_payload)
