"""v5 bridge-credit authorization: signature-bound pre-registered credits.

``BRIDGE_RELEASE``/``BRIDGE_REFUND`` are mint-style credits issued internally
by the bridge service after it verifies a source-chain proof off-chain. Before
v5, consensus only checked the ``bridge_release``/``bridge_refund``
pseudo-sender — a string any proposer can choose. From
``state_transition_v5_height`` every credit must additionally carry
``bridge_signature``: a secp256k1 signature over the credit's semantic fields
(transfer id, chains, recipient, amounts, proof, and the transaction hash) that
recovers to the configured bridge release authority. A forged or copied credit
can no longer mint merely by choosing the right pseudo-sender.
"""

from __future__ import annotations

import json
import os
from typing import Any

from ..config import settings

BRIDGE_CREDIT_TX_TYPES = frozenset({"BRIDGE_RELEASE", "BRIDGE_REFUND"})
BRIDGE_SIGNATURE_FIELD = "bridge_signature"


def _payload_dict(tx_data: dict[str, Any]) -> dict[str, Any]:
    payload = tx_data.get("payload")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            return {}
    return payload if isinstance(payload, dict) else {}


def bridge_credit_message(tx_data: dict[str, Any], tx_hash: str = "") -> dict[str, Any]:
    """Canonical signed message for a bridge credit transaction.

    Fixed-field projection so the issuer (a ``Transaction`` row whose semantic
    fields live in ``payload``) and every validator (which may see the same
    credit as a flat mempool dict) reconstruct identical bytes. Every
    value-bearing field is bound: ``credited_value`` is the amount apply
    actually credits (envelope ``value``, falling back to ``amount``), so a
    copied signature cannot be re-pointed at a different payout, and
    ``bound_tx_hash`` prevents replaying the same signed content under a new
    hash. (Field names deliberately avoid ``signature``/``sig``/``tx_hash``/
    ``value`` — the signing helper strips those keys, which would leave the
    recoverable message different from the signed one.)
    """
    payload = _payload_dict(tx_data)

    def _field(name: str) -> Any:
        value = payload.get(name)
        if value is None:
            value = tx_data.get(name)
        return value

    return {
        "type": _field("type"),
        "transfer_id": _field("transfer_id"),
        "source_chain": _field("source_chain"),
        "source_sender": _field("source_sender"),
        "target_chain": _field("target_chain"),
        "asset": _field("asset"),
        "proof": _field("proof"),
        "recipient": tx_data.get("to") or payload.get("recipient"),
        "amount": _field("amount"),
        "lock_tx_hash": _field("lock_tx_hash"),
        "credited_value": tx_data.get("value", tx_data.get("amount")),
        "fee": tx_data.get("fee", 0),
        "nonce": tx_data.get("nonce"),
        "bound_tx_hash": tx_hash or tx_data.get("tx_hash") or "",
    }


def bridge_refund_lock_hash(tx_data: dict[str, Any]) -> str:
    """The sealed ``BRIDGE_LOCK`` hash a ``BRIDGE_REFUND`` claims to repay.

    Issuers store it inside ``payload`` (row shape); flat mempool dicts may
    carry it at top level. Empty string when absent — the v6 gate fails closed
    on that.
    """
    return str(_payload_dict(tx_data).get("lock_tx_hash") or tx_data.get("lock_tx_hash") or "").strip()


def validate_bridge_refund_lock(lock: dict[str, Any] | None, tx_data: dict[str, Any]) -> str | None:
    """Check a ``BRIDGE_REFUND`` against the lock it names (v6).

    ``lock`` is a resolved record ``{exists, sender, amount, refunded}`` — the
    sequential path builds it from the ``Transaction`` row, the pure path
    receives it via ``bridge_lock_context`` so neither needs DB access in the
    predicate itself. Returns ``None`` when the binding holds, else a reason
    string for the rejection.
    """
    if lock is None or not lock.get("exists"):
        return "BRIDGE_REFUND payload.lock_tx_hash does not name a sealed BRIDGE_LOCK on this chain"
    if lock.get("refunded"):
        return "BRIDGE_REFUND names a BRIDGE_LOCK that was already refunded"
    payload = _payload_dict(tx_data)
    recipient = tx_data.get("to") or payload.get("recipient") or ""
    amount = payload.get("amount", tx_data.get("amount", tx_data.get("value")))
    from aitbc.crypto.signature_recovery import canonical_address

    try:
        if canonical_address(str(lock.get("sender") or "")) != canonical_address(str(recipient)):
            return "BRIDGE_REFUND recipient does not match the BRIDGE_LOCK sender"
    except Exception:
        return "BRIDGE_REFUND recipient does not match the BRIDGE_LOCK sender"
    try:
        if int(lock.get("amount") or 0) != int(amount or 0):
            return "BRIDGE_REFUND amount does not match the BRIDGE_LOCK value"
    except (TypeError, ValueError):
        return "BRIDGE_REFUND amount does not match the BRIDGE_LOCK value"
    return None


def bridge_credit_signature(tx_data: dict[str, Any]) -> str:
    """Extract the bridge authority signature, wherever the credit carries it.

    Pre-registered ``Transaction`` rows store it inside ``payload`` (there is no
    signature column); flat mempool dicts carry it at top level.
    """
    sig = _payload_dict(tx_data).get(BRIDGE_SIGNATURE_FIELD)
    if sig:
        return str(sig)
    return str(tx_data.get(BRIDGE_SIGNATURE_FIELD) or "")


def sign_bridge_credit(tx_data: dict[str, Any], tx_hash: str, private_key: str) -> str:
    """Sign the semantic fields of a bridge credit with the authority key."""
    from aitbc.crypto.crypto import sign_transaction_data

    return sign_transaction_data(bridge_credit_message(tx_data, tx_hash), private_key)


def verify_bridge_credit_signature(tx_data: dict[str, Any], tx_hash: str, authority: str) -> bool:
    """Verify a credit's bridge signature recovers to ``authority``."""
    from aitbc.crypto.crypto import recover_signer
    from aitbc.crypto.signature_recovery import canonical_address

    signature = bridge_credit_signature(tx_data)
    if not signature or not authority:
        return False
    recovered = recover_signer(bridge_credit_message(tx_data, tx_hash), signature)
    if not recovered:
        return False
    try:
        return canonical_address(recovered) == canonical_address(authority)
    except Exception:
        return False


def bridge_credit_private_key() -> str | None:
    """Signing key for internally issued bridge credits.

    ``BRIDGE_RELEASE_PRIVATE_KEY`` wins; the operator settlement key
    ``ESCROW_RELEASE_PRIVATE_KEY`` is the transitional fallback — it resolves
    to the same address that ``escrow_settlement_authority`` already publishes
    on-chain, so existing deployments need no new key provisioning.
    """
    key = (getattr(settings, "bridge_release_private_key", "") or os.getenv("BRIDGE_RELEASE_PRIVATE_KEY", "")).strip()
    if not key:
        key = os.getenv("ESCROW_RELEASE_PRIVATE_KEY", "").strip()
    return key or None


def bridge_release_authority_env() -> str | None:
    """Context-free authority resolution (env/settings only).

    The on-chain ``bridge_release_authority`` parameter is authoritative for
    consensus — callers with a session must resolve through
    ``state_transition._bridge_release_authority`` and pass the result. This
    fallback exists so callers without DB access still resolve deterministically
    on a correctly configured node; the escrow settlement env is the
    transitional default because the same operator key signs credits.
    """
    from aitbc.crypto.signature_recovery import canonical_address

    raw = (getattr(settings, "bridge_release_authority", "") or os.getenv("BRIDGE_RELEASE_AUTHORITY", "")).strip()
    if raw:
        return canonical_address(raw)
    raw = (settings.escrow_settlement_authority or os.getenv("ESCROW_RELEASE_ADDRESS", "")).strip()
    return canonical_address(raw) if raw else None
