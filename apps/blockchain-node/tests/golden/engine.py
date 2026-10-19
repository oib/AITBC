"""Golden-vector engine: replay case inputs through the real sequential apply path.

The recorder mirrors ``ChainSync._append_block``'s sequential branch exactly —
the same account auto-creation, nonce override, value normalization,
``StateTransition.apply_transaction`` call, ``Transaction`` row insert and
post-block state/bridge/aux root handling — but against a scratch chain.db
created by ``init_db`` under a scratch ``AITBC_DATA_DIR``, and it *records*
outputs instead of rejecting on root mismatches.

Nothing here signs, reads wallet material, or touches a live database. Inputs
are case JSONs (pre-state rows + a block + its transactions) or the extracted
real-history stream; outputs are deterministic JSON records consumed by
``runner.py`` and ``test_golden_vectors.py``.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlmodel import Session, select

from aitbc_chain.base_models import (
    Account,
    Block,
    ChainParameter,
    CrossChainTransfer,
    Transaction,
    _to_ait_address,
    record_chain_parameter_history,
)
from aitbc_chain.database import get_engine, init_db, shutdown_db
from aitbc_chain.state import side_root_shadow, state_root_utils
from aitbc_chain.state.merkle_patricia_trie import MerklePatriciaTrie
from aitbc_chain.state.state_transition import (
    StateTransition,
    get_block_version,
    get_state_transition,
    use_account_nonce_override,
)
from aitbc_chain.cross_chain.bridge_leaf import lock_leaf_value, unknown_lock_leaf
from aitbc_chain.mempool import compute_tx_hash

# Bridge pseudo-senders never get an Account row (same as _append_block).
_PSEUDO_SENDERS = frozenset({"bridge_release", "bridge_refund"})
_PSEUDO_RECIPIENTS = frozenset({"bridge_lock"})


def init_chain(chain_id: str) -> None:
    """Create the scratch chain DB exactly as a node start would."""
    init_db(chain_id)
    # Same reset import_block performs before an import batch — a second
    # profile run in one process must not inherit prior tx-hash state.
    get_state_transition().reset_processed_cache()


def reset_chain(chain_id: str) -> None:
    """Drop the scratch chain's DB and re-create the schema — deterministic
    baseline so a second profile run over the same chain id starts empty."""
    import shutil

    from aitbc.constants import DATA_DIR

    shutdown_db(chain_id)
    shutil.rmtree(DATA_DIR / "data" / chain_id, ignore_errors=True)
    init_db(chain_id)
    get_state_transition().reset_processed_cache()


def open_session(chain_id: str) -> Session:
    return Session(get_engine(chain_id))


def seed_rows(session: Session, table: str, rows: list[dict[str, Any]]) -> None:
    """Insert raw pre-state rows. Column names are checked against the real
    schema (a typo fails loudly, unknown tables fail); dict/list values are
    JSON-encoded as the JSON columns store them."""
    conn = session.connection().connection
    info = list(conn.execute(f'PRAGMA table_info("{table}")'))
    if not info:
        raise ValueError(f"prestate: unknown table {table!r}")
    cols = {r[1] for r in info}
    # NOT NULL columns the case didn't name get a deterministic sentinel —
    # ``*_at``/timestamp columns take the epoch, numeric take 0, text takes ''.
    # Integer primary keys (r[5]) are skipped: SQLite auto-assigns them and a
    # sentinel would collide on the second row.
    required = {r[1]: (r[2] or "").upper() for r in info if r[3] and r[4] is None and not r[5]}
    for row in rows:
        row = dict(row)
        unknown = set(row) - cols
        if unknown:
            raise ValueError(f"prestate: {table} has no columns {sorted(unknown)}")
        for col, decl in required.items():
            if col not in row:
                if col.endswith("_at") or "TIME" in decl or "DATE" in decl:
                    row[col] = "1970-01-01 00:00:00.000000"
                elif "INT" in decl or "REAL" in decl or "NUM" in decl:
                    row[col] = 0
                else:
                    row[col] = ""
        names = sorted(row)
        sql = f'INSERT INTO "{table}" ({", ".join(names)}) VALUES ({", ".join(":" + n for n in names)})'  # nosec B608 - names are schema-checked
        params = {n: (json.dumps(v) if isinstance(v, (dict, list)) else v) for n, v in row.items()}
        conn.execute(sql, params)
    session.flush()


def seed_genesis(session: Session, chain_id: str, genesis_state: dict[str, Any]) -> None:
    """Seed block 0 + the initial account set + chain parameters.

    The block row comes from the snapshot. The account set comes from the
    extractor's inference: when the genesis document's hash matches sealed
    block 0 the doc's allocations are honoured; ``bootstrap_accounts`` (the
    inferred off-ledger credits — on this chain the whole effective initial
    set, since the doc postdates a re-genesis) are always seeded on top,
    skipping addresses an allocation already covered."""
    conn = session.connection().connection
    cols = {r[1] for r in conn.execute('PRAGMA table_info("block")')}
    block0 = {k: v for k, v in genesis_state["block0"].items() if k in cols}
    block0.setdefault("chain_id", chain_id)
    block0.setdefault("height", 0)
    seed_rows(session, "block", [block0])
    seeded: set[str] = set()
    if genesis_state.get("source", {}).get("doc_allocations_applied"):
        for alloc in genesis_state.get("allocations", []):
            session.add(
                Account(
                    chain_id=chain_id,
                    address=alloc["address"],
                    balance=int(alloc["balance"]),
                    nonce=int(alloc.get("nonce", 0)),
                )
            )
            seeded.add(str(alloc["address"]).lower())
    for boot in genesis_state.get("bootstrap_accounts", []):
        if str(boot["address"]).lower() in seeded:
            continue
        session.add(
            Account(
                chain_id=chain_id,
                address=boot["address"],
                balance=int(boot["balance"]),
                nonce=int(boot.get("nonce", 0)),
            )
        )
    if genesis_state.get("source", {}).get("doc_allocations_applied"):
        for name, value in (genesis_state.get("parameters") or {}).items():
            stored_value = "" if value is None else str(value)
            session.add(ChainParameter(chain_id=chain_id, parameter=str(name), value=stored_value, applied_height=0))
            record_chain_parameter_history(session, chain_id, str(name), stored_value, None, 0)
    session.commit()


def _apply_tx_preamble(session: Session, chain_id: str, tx_data: dict[str, Any], block_version: int) -> tuple[str, str]:
    """The ``_append_block`` sequential preamble, verbatim: account
    auto-creation (v>=2), live-nonce substitution, amount->value copy."""
    sender_addr = _to_ait_address(tx_data.get("from", ""))
    recipient_addr = _to_ait_address(tx_data.get("to", ""))
    int(tx_data.get("amount", 0) or 0)
    int(tx_data.get("fee", 0) or 0)
    raw_from = tx_data.get("from", "")
    raw_to = tx_data.get("to", "")
    sender_acct = None
    if raw_from not in _PSEUDO_SENDERS:
        sender_acct = session.get(Account, (chain_id, sender_addr))
        if sender_acct is None and block_version >= 2:
            sender_acct = Account(chain_id=chain_id, address=sender_addr, balance=0, nonce=0)
            session.add(sender_acct)
            session.flush()
    if raw_to not in _PSEUDO_RECIPIENTS:
        recipient_acct = session.get(Account, (chain_id, recipient_addr))
        if recipient_acct is None and block_version >= 2:
            recipient_acct = Account(chain_id=chain_id, address=recipient_addr, balance=0, nonce=0)
            session.add(recipient_acct)
            session.flush()
    if raw_from not in _PSEUDO_SENDERS and sender_acct is not None and use_account_nonce_override(tx_data, block_version):
        tx_data["nonce"] = sender_acct.nonce
    if "value" not in tx_data and "amount" in tx_data:
        tx_data["value"] = tx_data["amount"]
    return sender_addr, recipient_addr


def _store_tx_row(session: Session, chain_id: str, tx_data: dict[str, Any], height: int) -> None:
    """The ``db_tx`` insert _append_block performs for every tx, accepted or
    refused (mirrors the sequential branch — no envelope reconstruction)."""
    tx_type = (tx_data.get("type") or "TRANSFER").upper()
    session.add(
        Transaction(
            chain_id=chain_id,
            tx_hash=tx_data.get("tx_hash", ""),
            block_height=height,
            sender=tx_data.get("from", ""),
            recipient=tx_data.get("to", ""),
            payload=tx_data.get("payload", {}),
            envelope=dict(tx_data),
            type=tx_type,
            value=tx_data.get("value", tx_data.get("amount", 0)),
            fee=tx_data.get("fee", 0),
            nonce=tx_data.get("nonce", 0),
            status="confirmed",
        )
    )


def _touched_addresses(tx_data: dict[str, Any], sender_addr: str, recipient_addr: str) -> set[str]:
    """Addresses whose account rows the tx plausibly moved — for the focused
    per-tx account snapshot. Everything else is covered by the table digests."""
    out = {a for a in (sender_addr, recipient_addr) if a}
    payload = tx_data.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {}
    for key in ("address", "user_address", "staker_address", "creator_address", "provider", "recipient", "sender"):
        val = payload.get(key)
        if isinstance(val, str) and val:
            out.add(_to_ait_address(val))
    return out


def _account_snapshot(session: Session, chain_id: str, addresses: set[str]) -> dict[str, Any]:
    snap: dict[str, Any] = {}
    for addr in sorted(addresses):
        acct = session.get(Account, (chain_id, addr))
        snap[addr] = {"balance": acct.balance, "nonce": acct.nonce} if acct else "absent"
    return snap


def _derive_bridge_root(session: Session, chain_id: str, block_data: dict[str, Any], txs: list[dict[str, Any]]) -> str:
    """The derivation half of ``ChainSync._derive_bridge_state_root`` — always
    computed (never short-circuited by a sealed value) so the record shows both
    the sealed root and what local state would derive."""
    trie = MerklePatriciaTrie()
    lock_txs = [tx for tx in txs if (tx.get("type") or (tx.get("payload") or {}).get("type", "")).upper() == "BRIDGE_LOCK"]
    if not lock_txs:
        return "0x" + bytes(trie.get_root()).hex()
    block_height = int(block_data.get("height") or 0)
    transfer_ids = [tx.get("tx_hash", "") for tx in lock_txs]
    records = session.exec(
        select(CrossChainTransfer).where(
            CrossChainTransfer.source_chain == chain_id,
            CrossChainTransfer.transfer_id.in_(transfer_ids),
        )
    ).all()
    record_map = {r.transfer_id: r for r in records}
    for tx in lock_txs:
        tx_hash = tx.get("tx_hash", "")
        record = record_map.get(tx_hash)
        value = (
            unknown_lock_leaf(tx_hash)
            if record is None
            else lock_leaf_value(record.transfer_id, record.amount, record.target_chain, record.recipient, block_height)
        )
        trie.put(tx_hash.encode(), value.encode())
    return "0x" + bytes(trie.get_root()).hex()


def _normalize_tx(chain_id: str, raw_tx: dict[str, Any]) -> dict[str, Any]:
    """The ``_append_block`` normalization verbatim: envelope hoisting,
    from/to and amount aliases, default signature/chain_id, tx_hash
    fallback."""
    norm = dict(raw_tx)
    nested = norm.get("envelope")
    if not norm.get("signature") and isinstance(nested, dict) and nested.get("signature"):
        kept_hash = norm.get("tx_hash")
        norm = dict(nested)
        if kept_hash:
            norm["tx_hash"] = kept_hash
    if "from" not in norm and "sender" in norm:
        norm["from"] = norm["sender"]
    if "to" not in norm and "recipient" in norm:
        norm["to"] = norm["recipient"]
    if "amount" not in norm and "value" in norm:
        norm["amount"] = norm["value"]
    if "signature" not in norm:
        norm["signature"] = ""
    if "chain_id" not in norm:
        norm["chain_id"] = chain_id
    if not norm.get("tx_hash"):
        norm["tx_hash"] = compute_tx_hash(norm)
    return norm


def apply_block(
    session: Session,
    st: StateTransition,
    chain_id: str,
    block_data: dict[str, Any],
    txs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply one block's transactions the way ``_append_block``'s sequential
    branch does, then commit — recording every observable output instead of
    rejecting on a root mismatch."""
    height = int(block_data["height"])
    block_version = get_block_version(block_data, height)
    conn = session.connection().connection  # raw DBAPI conn for the digests
    txs = [_normalize_tx(chain_id, t) for t in txs]

    tx_outputs: list[dict[str, Any]] = []
    for tx_data in txs:
        sender_addr, recipient_addr = _apply_tx_preamble(session, chain_id, tx_data, block_version)
        success, reason = st.apply_transaction(
            session,
            chain_id,
            tx_data,
            tx_data.get("tx_hash", ""),
            block_version=block_version,
            block_height=height,
        )
        _store_tx_row(session, chain_id, tx_data, height)
        session.flush()
        tx_outputs.append(
            {
                "tx_hash": tx_data.get("tx_hash", ""),
                "type": (tx_data.get("type") or "TRANSFER").upper(),
                "verdict": "accepted" if success else "rejected",
                "reason": reason or "",
                "accounts": _account_snapshot(session, chain_id, _touched_addresses(tx_data, sender_addr, recipient_addr)),
                "committed_fingerprint": side_root_shadow.committed_fingerprint(conn)["fingerprint"],
            }
        )

    computed_state_root = state_root_utils.compute_state_root_full(session, chain_id)
    sealed_state_root = block_data.get("state_root")
    derived_bridge_root = _derive_bridge_root(session, chain_id, block_data, txs)
    sealed_bridge_root = block_data.get("bridge_state_root")
    computed_aux = side_root_shadow.committed_fingerprint(conn)["fingerprint"]
    sealed_aux = block_data.get("aux_state_root")

    # Block row persisted with the same fields _append_block stores: sealed
    # roots verbatim, aux only at v14+ when the sealed block carried one.
    block_metadata = block_data.get("block_metadata")
    if isinstance(block_metadata, dict):
        block_metadata = json.dumps(block_metadata, sort_keys=True)
    ts = block_data.get("timestamp")
    session.add(
        Block(
            chain_id=chain_id,
            height=height,
            hash=block_data.get("hash", ""),
            parent_hash=block_data.get("parent_hash", ""),
            proposer=block_data.get("proposer", ""),
            timestamp=datetime.fromisoformat(ts) if isinstance(ts, str) else ts or datetime(1970, 1, 1),
            tx_count=int(block_data.get("tx_count") or len(txs)),
            state_root=sealed_state_root,
            bridge_state_root=sealed_bridge_root or derived_bridge_root,
            aux_state_root=(str(sealed_aux) if block_version >= 14 and sealed_aux else None),
            block_metadata=block_metadata,
            signature=block_data.get("signature", ""),
        )
    )
    session.commit()

    return {
        "height": height,
        "block_version": block_version,
        "txs": tx_outputs,
        "state_root": {"sealed": sealed_state_root, "computed": computed_state_root},
        "state_root_match": bool(sealed_state_root) and sealed_state_root == computed_state_root,
        "bridge_state_root": {"sealed": sealed_bridge_root, "derived": derived_bridge_root},
        "aux_state_root": {
            "sealed": sealed_aux,
            "computed_fingerprint": computed_aux,
            "match": None if not sealed_aux else sealed_aux == computed_aux,
        },
    }
