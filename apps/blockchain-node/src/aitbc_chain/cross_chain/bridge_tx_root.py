"""#1940 F5 — transaction-derived bridge lock root contract.

One canonical interpretation of a sealed ``BRIDGE_LOCK`` shared by the
producer (``consensus/poa.py`` / ``poa_tx_pipeline.py``), the importer
(``sync_block_import.py`` / ``state_transition*.py``) and the proof builder
(``cross_chain/bridge_transfer.py``). Below the history-gated activation
(``bridge_state_root_tx_only_enabled``) every legacy path — including the
``CrossChainTransfer``-dependent root derivation — is byte-identical.

New-era rules (all enforced through this module so the three consumers can
never diverge):

- The gate resolves from ``chain_parameter_history`` ONLY, at
  ``block_height - 1``: enabling executed in block H first affects H+1, and
  a same-block governance change cannot alter the contract halfway through
  preprocessing/application/root building. ``chain_parameter`` rows with
  ``applied_height NULL`` never retroactively activate old blocks.
- Canonical lock fields come from ``bridge_credit.bridge_lock_message`` —
  the actual authority-signed projection (payload-first). No unsigned
  ``payload.recipient`` fallback; recipient case is preserved.
- ``transfer_id`` need NOT equal ``tx_hash``: arbitrary signed lock ids are
  valid. The trie key is the authoritative ``tx_hash``.
- The signed amount must equal the effective outer debit
  (``value`` if present, else ``amount``, else 0; both present must be
  strict ints and equal) — a lock may never certify one amount while
  debiting another.
- Type resolution uses ``pure_state_transition._determine_tx_type``
  exactly (top-level ``TRANSFER``/empty falls through to ``payload.type``).
  A stored-row type that disagrees with the body on a ``BRIDGE_LOCK``
  refuses rather than silently reinterpreting the same hash.

Residual (documented, not a defect): the native producer's amount-based
admission may conservatively refuse a value-only model dump that the
importer would normalize into an acceptable body. A refused or failed
producer lock never enters ``processed_txs`` and therefore never enters
the derived root — there is no certifiable debit split. This is an
input-shape/liveness residual, not a consensus divergence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from sqlmodel import select

from ..state.bridge_credit import bridge_lock_message
from ..state.pure_state_transition import _determine_tx_type
from .bridge_leaf import lock_leaf_v2_active, lock_leaf_value

if TYPE_CHECKING:
    from sqlmodel import Session

    from ..state.merkle_patricia_trie import MerklePatriciaTrie

# Chain-parameter name resolved through chain_parameter_history only.
BRIDGE_TX_ROOT_PARAMETER = "bridge_state_root_tx_only_enabled"

# The history resolver accepts exactly these spellings; anything else —
# including "yes"/"no" — is an invalid value and means inactive.
_TRUE_VALUES = frozenset({"true", "1"})


def _strict_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True)
class CanonicalLock:
    """The signed, canonical description of one BRIDGE_LOCK."""

    tx_hash: str
    transfer_id: str
    source_chain: str
    target_chain: str
    amount: int
    target_recipient: str
    sender: str
    asset: str


def tx_only_root_active(session: Session, chain_id: str, block_height: int) -> bool:
    """Whether the tx-derived bridge-root contract governs ``block_height``.

    HISTORY ONLY: the latest ``chain_parameter_history`` row at or below
    ``block_height - 1`` decides. ``block_height <= 0`` is always inactive.
    Missing or unrecognised values mean False — the current-value
    ``chain_parameter`` row is deliberately never consulted, so a
    ``applied_height NULL`` row cannot retroactively activate sealed
    history.
    """
    if not _strict_int(block_height) or block_height <= 0:
        return False
    from ..base_models import ChainParameterHistory

    value = session.exec(
        select(ChainParameterHistory.value)
        .where(
            ChainParameterHistory.chain_id == chain_id,
            ChainParameterHistory.parameter == BRIDGE_TX_ROOT_PARAMETER,
            ChainParameterHistory.applied_height <= block_height - 1,
        )
        .order_by(ChainParameterHistory.applied_height.desc())  # type: ignore[attr-defined]
        .limit(1)
    ).first()
    if value is None:
        return False
    return str(value).strip().lower() in _TRUE_VALUES


def effective_lock_debit(body: dict[str, Any]) -> int:
    """The outer debit a lock body would actually take.

    ``value`` wins when present, else ``amount``, else 0. When both keys
    exist they must be strict ints and equal — a divergent pair is an
    alias conflict, not a choice. Raises ``ValueError`` on any violation.
    """
    has_value = "value" in body
    has_amount = "amount" in body
    value = body.get("value")
    amount = body.get("amount")
    if has_value and has_amount:
        if not _strict_int(value) or not _strict_int(amount) or value != amount:
            raise ValueError("BRIDGE_LOCK amount/value alias conflict")
        return cast(int, value)
    if has_value:
        if not _strict_int(value):
            raise ValueError("BRIDGE_LOCK value must be an integer")
        return cast(int, value)
    if has_amount:
        if not _strict_int(amount):
            raise ValueError("BRIDGE_LOCK amount must be an integer")
        return cast(int, amount)
    return 0


def canonical_lock_fields(body: dict[str, Any], tx_hash: str, chain_id: str, height: int) -> CanonicalLock:
    """Canonical signed fields for one BRIDGE_LOCK body.

    ``body`` is the delivered/normalized transaction dict; ``tx_hash`` is
    the authoritative hash (trie key and ``bound_tx_hash``). Raises
    ``ValueError`` on any contract violation — callers map that to a
    rejection, never to a skipped lock.
    """
    tx_type = _determine_tx_type(body)
    if tx_type != "BRIDGE_LOCK":
        raise ValueError(f"not a BRIDGE_LOCK transaction (resolved {tx_type})")
    message = bridge_lock_message(body, tx_hash)
    transfer_id = message.get("transfer_id")
    target_chain = message.get("target_chain")
    source_chain = message.get("source_chain")
    amount = message.get("amount")
    target_recipient = message.get("target_recipient")
    if not isinstance(transfer_id, str) or not transfer_id:
        raise ValueError("BRIDGE_LOCK missing transfer_id")
    if not isinstance(target_chain, str) or not target_chain:
        raise ValueError("BRIDGE_LOCK missing target_chain")
    if source_chain != chain_id:
        raise ValueError(f"BRIDGE_LOCK source_chain {source_chain!r} does not match apply chain {chain_id!r}")
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
        raise ValueError("BRIDGE_LOCK amount must be a non-negative integer")
    recipient = target_recipient if isinstance(target_recipient, str) else ""
    if lock_leaf_v2_active(height) and not recipient:
        raise ValueError("BRIDGE_LOCK missing target_recipient")
    sender = message.get("sender")
    asset = message.get("asset")
    return CanonicalLock(
        tx_hash=str(tx_hash),
        transfer_id=transfer_id,
        source_chain=str(source_chain),
        target_chain=target_chain,
        amount=amount,
        target_recipient=recipient,
        sender=str(sender or ""),
        asset=str(asset) if asset else "native",
    )


def assert_lock_debit(fields: CanonicalLock, effective_value: Any) -> None:
    """The certified signed amount must equal the effective outer debit."""
    if not _strict_int(effective_value) or effective_value != fields.amount:
        raise ValueError(f"BRIDGE_LOCK signed amount {fields.amount} does not match effective debit {effective_value!r}")


def resolve_lock_type(body: dict[str, Any], stored_type: Any = None) -> str:
    """Effective type for a delivered body plus its stored row type.

    ``_determine_tx_type`` semantics exactly: top-level ``TRANSFER`` or an
    absent/empty type falls through to ``payload.type``. When EITHER side
    resolves ``BRIDGE_LOCK`` the two must agree — a stored ``TRANSFER``
    must not hide a payload-typed lock, and a stored ``BRIDGE_LOCK`` must
    not be reinterpreted as something else. Non-lock disagreements keep the
    historical stored-wins precedence of ``_tx_type``.
    """
    body_type = _determine_tx_type(body)
    stored = str(stored_type).strip().upper() if stored_type else ""
    if (body_type == "BRIDGE_LOCK" or stored == "BRIDGE_LOCK") and stored and stored != body_type:
        raise ValueError(f"BRIDGE_LOCK type conflict: stored={stored} body={body_type}")
    return stored or body_type


def build_tx_bridge_trie(bodies: list[dict[str, Any]], chain_id: str, height: int) -> MerklePatriciaTrie:
    """Bridge event trie over the delivered lock bodies — no service rows.

    Keys are the authoritative ``tx_hash`` values; values are the existing
    ``lock_leaf_value`` leaves (V1/V2 recipient binding unchanged). A
    duplicate lock hash or any contract violation raises ``ValueError`` —
    the caller rejects the whole block rather than minting a partial root.
    """
    from ..state.merkle_patricia_trie import MerklePatriciaTrie

    trie = MerklePatriciaTrie()
    seen: set[str] = set()
    for body in bodies:
        if not isinstance(body, dict) or _determine_tx_type(body) != "BRIDGE_LOCK":
            continue
        tx_hash = str(body.get("tx_hash") or "")
        if not tx_hash:
            raise ValueError("BRIDGE_LOCK missing tx_hash")
        if tx_hash in seen:
            raise ValueError(f"duplicate BRIDGE_LOCK tx_hash {tx_hash}")
        seen.add(tx_hash)
        fields = canonical_lock_fields(body, tx_hash, chain_id, height)
        leaf = lock_leaf_value(fields.transfer_id, fields.amount, fields.target_chain, fields.target_recipient, height)
        trie.put(tx_hash.encode(), leaf.encode())
    return trie


def stored_lock_body(row: Any) -> dict[str, Any]:
    """Reconstruct the signed body for a sealed ``Transaction`` row.

    The actual ``envelope`` wins when present — including a single old
    served-envelope wrapper (empty top-level signature, real signed
    envelope nested), hoisted exactly once like the import normalizer.
    Otherwise the body is rebuilt from the row's semantic columns plus its
    ``payload`` dict, whose fields are first-class for the payload-first
    signed projection. Never reads or writes ``CrossChainTransfer``.
    """
    envelope = getattr(row, "envelope", None)
    if isinstance(envelope, dict) and envelope:
        body = dict(envelope)
        nested = body.get("envelope")
        if not body.get("signature") and isinstance(nested, dict) and nested.get("signature"):
            body = dict(nested)
        # The sealed row's tx_hash is authoritative — producer envelopes
        # commonly carry none, and a conflicting embedded hash must never
        # re-key the trie leaf. Always override; never mutate stored JSON.
        body["tx_hash"] = str(getattr(row, "tx_hash", "") or "")
        return body
    payload = getattr(row, "payload", None)
    rebuilt: dict[str, Any] = {
        "from": getattr(row, "sender", ""),
        "to": getattr(row, "recipient", ""),
        "amount": getattr(row, "value", 0),
        "value": getattr(row, "value", 0),
        "fee": getattr(row, "fee", 0),
        "nonce": getattr(row, "nonce", 0),
        "type": getattr(row, "type", "") or "",
        "payload": dict(payload) if isinstance(payload, dict) else {},
        "tx_hash": getattr(row, "tx_hash", ""),
        "chain_id": getattr(row, "chain_id", ""),
    }
    # Column-dump payload fields are first-class: surface them at top level
    # too so a body built either way resolves identically.
    for key, val in rebuilt["payload"].items():
        rebuilt.setdefault(key, val)
    return rebuilt
