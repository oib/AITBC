"""Protocol-owned escrow addresses and the queue helper for protocol transfers.

Staking and bounty balances used to be moved by the RPC handlers themselves:
the handler opened a session, did ``account.balance -= amount`` and committed.
That is the same defect class that froze the fleet on 2026-09-03. The block
header ``state_root`` is a full scan of the ``account`` table
(``state.state_root_utils.compute_state_root_full``), so any balance committed
outside block processing makes the computed root disagree with the parent
header and the proposer refuses to build with "Parent state mismatch".

The fix is the one the bond subsystem already uses: value moves only inside a
block, by an ordinary transfer to or from a protocol escrow address.

* A *lock* is a transfer ``user -> escrow``.
* A *release* is a transfer ``escrow -> user``.

Both are ordinary transfers as far as consensus is concerned, so they need no
new transaction type in the state transition: ``poa`` fills in the sender's
nonce from the account, the state transition creates the recipient on first
credit, and followers replay the identical transfer through
``sync_block_import``. The ``type`` field is descriptive only -- it exists so
the transaction is legible in explorers and logs.

The escrow addresses are derived from a keccak label and therefore have **no
private key**. Nobody can produce a signature that recovers to one, so a
release can never be forged through ``/rpc/transaction`` (which verifies the
signature against the sender before admitting anything to the mempool). Only
this node's own code can originate one. That is the same property that makes
pre-registered credit magic senders safe.
"""

from __future__ import annotations

import os
import re
from typing import Any

from eth_utils import keccak

from aitbc.crypto.signature_recovery import canonical_address

from .base_models import _to_ait_address
from .logger import get_logger

_logger = get_logger(__name__)


def _derive(env_var: str, label: bytes) -> str:
    configured = os.getenv(env_var, "")
    if configured:
        return canonical_address(configured)
    return canonical_address("0x" + keccak(label).hex()[:40])


# Consensus staking (/rpc/staking/stake) and the agent-economy stake records
# share one escrow: both hold user principal that is returned on withdrawal.
_STAKE_ESCROW_ADDRESS = _derive("STAKE_ESCROW_ADDRESS", b"aitbc.stake.escrow")
_BOUNTY_ESCROW_ADDRESS = _derive("BOUNTY_ESCROW_ADDRESS", b"aitbc.bounty.escrow")
_HTLC_ESCROW_ADDRESS = _derive("HTLC_ESCROW_ADDRESS", b"aitbc.htlc.escrow")


def stake_escrow_address() -> str:
    """AIT-form address of the staking escrow."""
    return _to_ait_address(_STAKE_ESCROW_ADDRESS)


def bounty_escrow_address() -> str:
    """AIT-form address of the bounty escrow."""
    return _to_ait_address(_BOUNTY_ESCROW_ADDRESS)


def htlc_escrow_address() -> str:
    """AIT-form address of the cross-chain HTLC escrow."""
    return _to_ait_address(_HTLC_ESCROW_ADDRESS)


def is_protocol_escrow(address: str) -> bool:
    """Return True if ``address`` is one of the keyless protocol escrows."""
    try:
        canonical = canonical_address(address)
    except (TypeError, ValueError):
        return False
    return canonical in {_STAKE_ESCROW_ADDRESS, _BOUNTY_ESCROW_ADDRESS, _HTLC_ESCROW_ADDRESS}


def queue_protocol_transfer(
    *,
    sender: str,
    recipient: str,
    amount: int,
    chain_id: str,
    tx_type: str,
    payload: dict[str, Any] | None = None,
    auth: dict[str, Any] | None = None,
) -> str:
    """Queue a protocol-initiated transfer and return its transaction hash.

    The balance change happens when the transaction is included in a block --
    never here. Callers must not touch the ``account`` table themselves.

    The transaction carries no top-level signature. That is deliberate and
    safe: the state transition only verifies a signature when one is present,
    and the public submit endpoint rejects anything whose signature does not
    recover to the sender, so an unsigned transfer cannot be injected from
    outside. The fee is 0 because these are protocol-internal movements of the
    user's own principal, matching BOND_RELEASE and BOND_SLASH.

    ``auth`` carries the authorization evidence the RPC layer verified into
    the block record: ``{"signer", "message", "signature"}`` where ``message``
    is the exact dict the signer signed (canonical JSON, keccak, secp256k1 —
    ``verify_request_signature``). ``validate_transaction`` re-verifies it
    when present, so the ledger records *who approved* a lock/release rather
    than trusting the serving node. Protocol-initiated transfers with no
    requesting user (e.g. AUTO_STAKE reinvestment) carry no auth.
    """
    if amount <= 0:
        raise ValueError(f"Protocol transfer amount must be positive, got {amount}")

    from .mempool import get_mempool

    sender_address = _to_ait_address(sender)
    tx_data: dict[str, Any] = {
        "from": sender_address,
        "to": _to_ait_address(recipient),
        "amount": int(amount),
        "fee": 0,
        # The sender's current account nonce at admission (#2457) so
        # pending/status surfaces show a real value instead of the old 0
        # placeholder. Consensus still rewrites it to the live nonce at
        # apply time (unsigned protocol writes are nonce-exempt), and peers
        # adopt the gossiped envelope verbatim, so the stamped value only
        # needs to be a faithful snapshot — never authoritative.
        "nonce": _sender_account_nonce(chain_id, sender_address),
        "type": tx_type,
        "payload": payload or {},
        "chain_id": chain_id,
    }
    if auth is not None:
        tx_data["payload"]["auth"] = dict(auth)
    tx_hash = get_mempool().add(tx_data, chain_id=chain_id)
    _relay_protocol_transfer(chain_id, tx_data)
    return tx_hash


def _sender_account_nonce(chain_id: str, address: str) -> int:
    """Current confirmed nonce of ``address`` on ``chain_id`` (#2457).

    Best-effort: an unreadable account table or missing row yields 0, which
    is exactly the placeholder value this replaced — stamping can never be
    worse than the status quo.
    """
    try:
        from sqlmodel import select

        from .base_models import Account
        from .database import session_scope

        with session_scope(chain_id) as session:
            account = session.exec(select(Account).where(Account.chain_id == chain_id, Account.address == address)).first()
            return int(account.nonce or 0) if account is not None else 0
    except Exception:  # noqa: BLE001 - display-only stamp; apply rewrites regardless
        return 0


def _relay_protocol_transfer(chain_id: str, tx_data: dict[str, Any]) -> None:
    """Best-effort peer fan-out for a queued protocol transfer (#2396).

    ``get_mempool().add`` writes only this host's local mempool — nothing
    republishes it. The REST submit path relays via ``_queue_peer_fanout``
    (#2361), but this helper bypassed it, so a stake/unstake/bounty request
    served by a non-proposing host returned a tx hash for a transaction no
    proposer ever saw. Schedule the same relay; the local entry remains as
    fallback for the case where this host does propose.
    """
    try:
        from .rpc.transactions import _queue_peer_fanout
    except ImportError:
        return
    try:
        _queue_peer_fanout(chain_id, tx_data)
    except (RuntimeError, ValueError, TypeError, AttributeError, KeyError) as e:
        _logger.debug("protocol transfer peer fan-out not scheduled: %s", e)


def protocol_transfers_active(session: Any, chain_id: str) -> bool:
    """Whether a protocol-escrow transfer queued now could seal.

    True only when the v17 ``payload.auth`` admission is armed for the
    block that would seal next. The BNT-2 surfaces refuse up front while
    this is False so a request can never again queue a transfer that sits
    pending forever — the same honesty the unconditional 410 gave at v9–16.
    """
    from sqlmodel import func, select

    from .models import Block
    from .state.state_transition import get_block_version_for_height

    head = session.exec(select(func.max(Block.height)).where(Block.chain_id == chain_id)).first()
    next_height = (head or 0) + 1
    return get_block_version_for_height(next_height) >= 17


# Payload keys are inlined into the SQL text below (a bound path cannot use
# the expression index, see _JOB_ID_INDEX_EXPRESSIONS in rpc/transactions.py),
# so only plain identifiers may reach the f-string. Callers pass fixed
# strings like "stake_id"/"agent_stake_id"/"bounty_id".
_PAYLOAD_KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _payload_text_expr(session: Any, payload_key: str) -> Any | None:
    """SQL expression for ``str(payload.get(payload_key, ""))`` semantics.

    Returns a ``literal_column`` comparing-ready text expression, or None on
    dialects/keys where the SQL form is unsafe — callers then keep the
    Python-side filter over the unfiltered candidate set (the old behaviour).

    ``->>``/``json_extract`` yield SQL NULL for a missing key, while the Python
    match treats missing as ``""`` — ``coalesce(..., '')`` keeps the two
    equivalent for the id values callers actually pass. A JSON ``null``
    payload value reads as SQL NULL too (``""`` here vs ``"None"`` in Python);
    no caller passes ``"None"``/``""`` as ``payload_value``, so the divergence
    is unreachable.
    """
    if not _PAYLOAD_KEY_RE.fullmatch(payload_key):
        return None
    from sqlalchemy import literal_column

    dialect = session.get_bind().dialect.name
    if dialect == "sqlite":
        # CAST keeps numeric payload values comparable as text, matching the
        # Python-side str() comparison.
        return literal_column(f"""coalesce(CAST(json_extract(payload, '$."{payload_key}"') AS TEXT), '')""")
    if dialect == "postgresql":
        return literal_column(f"""coalesce((payload ->> '{payload_key}'), '')""")
    return None


def _confirmed_lock_candidates(
    session: Any,
    chain_id: str,
    tx_type: str,
    payload_key: str,
    payload_value: Any,
) -> list[Any]:
    """Sealed transactions of ``tx_type`` tagged with the payload key/value.

    The payload predicate is pushed into SQL when the dialect supports the
    text extraction (#1519) so a lookup does not hydrate every sealed lock of
    the type; the Python ``str()`` comparison still runs on the (now small)
    candidate set, keeping semantics identical on every dialect.
    """
    from sqlmodel import select

    from .models import Transaction

    stmt = select(Transaction).where(
        Transaction.chain_id == chain_id,
        Transaction.type == tx_type,
        Transaction.block_height.is_not(None),  # type: ignore[union-attr]
    )
    expr = _payload_text_expr(session, payload_key)
    if expr is not None:
        stmt = stmt.where(expr == str(payload_value))
    candidates = session.exec(stmt).all()
    return [tx for tx in candidates if str((tx.payload or {}).get(payload_key, "")) == str(payload_value)]


def protocol_transfer_confirmed(
    session: Any,
    chain_id: str,
    tx_type: str,
    payload_key: str,
    payload_value: Any,
) -> bool:
    """Return True once the identified lock transaction is in a block.

    A release must never be queued against a lock that has not landed. The
    domain rows (``stake``, ``agent_stake``, ``bounty_contract``) are written by
    the RPC handler as soon as the lock is queued, because they are not part of
    the state root and so cannot desynchronise it -- but that means a row can
    exist while its funds are still in the mempool, or while the lock has been
    dropped outright (the proposer skips a transfer whose sender has since spent
    the balance). Releasing on the strength of the row alone would pay out of
    the shared escrow, taking principal that belongs to other stakers.

    Matching is by payload key rather than a stored hash so that no column has
    to be added to tables the migration chain cannot rebuild.
    """
    return bool(_confirmed_lock_candidates(session, chain_id, tx_type, payload_key, payload_value))


def confirmed_lock_txs(
    session: Any,
    chain_id: str,
    tx_type: str,
    payload_key: str,
    payload_value: Any,
) -> list[Any]:
    """Confirmed lock transactions tagged with ``payload_key == payload_value``.

    Returns the Transaction rows themselves so callers can name them in a
    release's ``lock_tx_hashes`` — the v4 consensus check resolves the release
    against these replicated records rather than node-local domain rows.
    """
    return _confirmed_lock_candidates(session, chain_id, tx_type, payload_key, payload_value)


def confirmed_lock_total(
    session: Any,
    chain_id: str,
    tx_type: str,
    payload_key: str,
    payload_value: Any,
) -> int:
    """Total value of the confirmed lock transfers tagged with this key.

    A stake can be topped up, so a single boolean is not enough to authorise a
    release: the escrow must actually hold the full principal being returned.
    Callers compare this against the record amount before queueing a release.
    """
    return sum(int(tx.value or 0) for tx in confirmed_lock_txs(session, chain_id, tx_type, payload_key, payload_value))


def tx_auth_signature(tx_data: dict[str, Any]) -> str | None:
    """The ``payload.auth.signature`` one-shot identity of an envelope, if any (#2480).

    Operator-signed protocol bodies sign business fields, not the envelope —
    nonce/fee changes mint a fresh tx hash for the same authorization, so the
    signature itself is the replay identity every dedup layer keys on.
    """
    payload = tx_data.get("payload")
    if not isinstance(payload, dict):
        return None
    auth = payload.get("auth")
    if not isinstance(auth, dict):
        return None
    signature = auth.get("signature")
    return str(signature) if signature else None


def _payload_auth_signature_expr(session: Any) -> Any | None:
    """SQL expression for ``str(payload.auth.signature)`` (#2480).

    Same contract as ``_payload_text_expr`` but for the nested auth object —
    every auth-bearing transfer stores ``payload.auth.signature``, including
    envelopes sealed before the ``auth_nonce`` schema existed, so one lookup
    covers the whole history.
    """
    from sqlalchemy import literal_column

    dialect = session.get_bind().dialect.name
    if dialect == "sqlite":
        return literal_column("""coalesce(CAST(json_extract(payload, '$.auth.signature') AS TEXT), '')""")
    if dialect == "postgresql":
        return literal_column("""coalesce((payload -> 'auth' ->> 'signature'), '')""")
    return None


# Types whose envelopes may carry ``payload.auth`` — mirrors the gossip
# admission sets in ``rpc/utils.py`` (kept here so the state layer can query
# sealed rows without importing the RPC package).
AUTH_PROTOCOL_TX_TYPES = (
    "STAKE_LOCK",
    "STAKE_RELEASE",
    "BOUNTY_LOCK",
    "BOUNTY_PAYOUT",
    "BOUNTY_REFUND",
    "STAKE_UNBOND",
    # A ``TRANSFER`` envelope can still resolve to one of the above through
    # ``payload.type``; its stored row keeps whichever label apply used.
    "TRANSFER",
)


def protocol_auth_signature_sealed(session: Any, chain_id: str, signature: str) -> bool:
    """True when a sealed transaction already carries this auth signature (#2480).

    The signature is the one-shot identity of an operator authorization:
    honest producers sign a unique ``auth_nonce`` per request, so a second
    sighting of the same ``payload.auth.signature`` is always a replay —
    whether it arrives at mempool admission or inside a proposed block.
    """
    from sqlmodel import col, select

    from .models import Transaction

    if not signature:
        return False
    stmt = select(Transaction).where(
        Transaction.chain_id == chain_id,
        Transaction.block_height.is_not(None),  # type: ignore[union-attr]
        col(Transaction.type).in_(AUTH_PROTOCOL_TX_TYPES),
    )
    expr = _payload_auth_signature_expr(session)
    if expr is not None:
        stmt = stmt.where(expr == str(signature))
    for tx in session.exec(stmt).all():
        auth = (tx.payload or {}).get("auth")
        if isinstance(auth, dict) and str(auth.get("signature") or "") == str(signature):
            return True
    return False


_BOUNTY_FLOW_TYPES = ("BOUNTY_LOCK", "BOUNTY_PAYOUT", "BOUNTY_REFUND")


def bounty_flow_state(
    session: Any,
    chain_id: str,
    bounty_id: str,
    *,
    before_height: int | None = None,
) -> tuple[int, int, set[str]]:
    """Sealed bounty money-flow totals for the v30 apply invariants (#2484).

    Returns ``(locked_total, outflow_total, paid_submissions)`` computed
    purely from replicated ``Transaction`` rows — never the node-local
    ``BountyContract`` domain row, which RPC handlers mutate outside block
    apply and which followers need not carry identically.

    ``locked_total`` sums ``BOUNTY_LOCK`` values (every top-up lock counts);
    ``outflow_total`` sums ``BOUNTY_PAYOUT`` + ``BOUNTY_REFUND`` values —
    the honest lifecycle pays XOR refunds the full remaining amount, so a
    combined bound is what actually protects the shared escrow from a
    signed payout+refund pair. ``paid_submissions`` collects the
    ``submission_id`` of every sealed payout for the one-payout-per-
    submission rule.

    ``before_height`` excludes rows stamped at or above it — the block
    currently being applied — so same-block applications are accounted by
    the caller's per-block accumulators instead of being counted twice
    (staged rows are session-visible on the proposer path).
    """
    from sqlmodel import col, select

    from .models import Transaction

    stmt = select(Transaction).where(
        Transaction.chain_id == chain_id,
        col(Transaction.type).in_(_BOUNTY_FLOW_TYPES),
        Transaction.block_height.is_not(None),  # type: ignore[union-attr]
    )
    expr = _payload_text_expr(session, "bounty_id")
    if expr is not None:
        stmt = stmt.where(expr == str(bounty_id))
    locked = 0
    outflow = 0
    submissions: set[str] = set()
    for tx in session.exec(stmt).all():
        if str((tx.payload or {}).get("bounty_id", "")) != str(bounty_id):
            continue
        if before_height is not None and tx.block_height is not None and int(tx.block_height) >= int(before_height):
            continue
        tx_type = str(tx.type or "")
        value = int(tx.value or 0)
        if tx_type == "BOUNTY_LOCK":
            locked += value
        elif tx_type in ("BOUNTY_PAYOUT", "BOUNTY_REFUND"):
            outflow += value
            if tx_type == "BOUNTY_PAYOUT":
                sub = (tx.payload or {}).get("submission_id")
                if sub is not None and str(sub):
                    submissions.add(str(sub))
    return locked, outflow, submissions
