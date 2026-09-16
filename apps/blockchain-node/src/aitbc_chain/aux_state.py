"""Non-account side-effect table propagation for state sync.

The account state root covers ``account`` rows only — by design. Tables
like ``stake``, ``bond`` and ``governance_*`` are written by RPC paths
(submit-time) and tx application, but never reach followers: a
``governance vote`` on a follower read zero voting power, bond-gated
checks diverged per node, proposal state existed only on the hub.

These tables ride alongside ``/rpc/state/snapshot`` (all rows) and
``/rpc/state/delta`` (rows touched inside the lookback window). They must
NEVER be folded into ``compute_state_root_full`` — the state root is
account-only by design; changing it invalidates every sealed block's root.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlmodel import select

from .base_models import Bond, GovernanceProposal, GovernanceVote, Stake, _to_ait_address
from .logger import get_logger

logger = get_logger(__name__)


class _AuxSpec:
    """How one side-effect table serializes/upserts across sync."""

    def __init__(
        self,
        model: type[Any],
        key_fields: tuple[str, ...],
        fields: tuple[str, ...],
        ts_field: str,
        address_fields: tuple[str, ...] = (),
        datetime_fields: tuple[str, ...] = (),
    ) -> None:
        self.model = model
        self.key_fields = key_fields
        self.fields = fields
        self.ts_field = ts_field
        self.address_fields = address_fields
        self.datetime_fields = datetime_fields


AUX_TABLES: dict[str, _AuxSpec] = {
    "stakes": _AuxSpec(
        Stake,
        key_fields=("id",),
        fields=("id", "address", "amount", "locked_until", "status", "created_at", "updated_at"),
        ts_field="updated_at",
        address_fields=("address",),
        datetime_fields=("locked_until", "created_at", "updated_at"),
    ),
    "bonds": _AuxSpec(
        Bond,
        key_fields=("bond_id",),
        fields=(
            "bond_id",
            "provider",
            "amount",
            "locked_until",
            "status",
            "created_tx_hash",
            "released_tx_hash",
            "slashed_tx_hash",
            "created_at",
            "updated_at",
        ),
        ts_field="updated_at",
        address_fields=("provider",),
        datetime_fields=("locked_until", "created_at", "updated_at"),
    ),
    "governance_proposals": _AuxSpec(
        GovernanceProposal,
        key_fields=("proposal_id",),
        fields=(
            "proposal_id",
            "proposer_address",
            "title",
            "description",
            "category",
            "status",
            "votes_for",
            "votes_against",
            "votes_abstain",
            "quorum_required",
            "passing_threshold",
            "execution_payload",
            "voting_starts",
            "voting_ends",
            "executed_at",
            "execution_tx_hash",
            "created_at",
            "updated_at",
        ),
        ts_field="updated_at",
        address_fields=("proposer_address",),
        datetime_fields=("voting_starts", "voting_ends", "executed_at", "created_at", "updated_at"),
    ),
    "governance_votes": _AuxSpec(
        GovernanceVote,
        key_fields=("proposal_id", "voter_address"),
        fields=("proposal_id", "voter_address", "vote_type", "voting_power", "reason", "created_at"),
        ts_field="created_at",
        address_fields=("voter_address",),
        datetime_fields=("created_at",),
    ),
}


def serialize_aux_rows(
    session: Any,
    chain_id: str,
    changed_since: datetime | None = None,
    max_rows: int | None = None,
) -> dict[str, Any]:
    """Serialize side-effect tables for a sync payload.

    ``changed_since=None`` ships every row (snapshot path). Otherwise only
    rows whose timestamp column is at-or-after the cutoff are shipped
    (delta path). Returns ``{"tables": {name: [row, ...]}, "truncated":
    bool}`` — ``truncated=True`` when any table exceeds ``max_rows`` so the
    caller can fall back to a full snapshot instead of shipping a partial
    table.
    """
    out: dict[str, list[dict[str, Any]]] = {}
    truncated = False
    for name, spec in AUX_TABLES.items():
        stmt = select(spec.model).where(spec.model.chain_id == chain_id)
        if changed_since is not None:
            stmt = stmt.where(getattr(spec.model, spec.ts_field) >= changed_since)
        rows = session.exec(stmt.order_by(getattr(spec.model, spec.ts_field))).all()
        if max_rows is not None and len(rows) > max_rows:
            truncated = True
        for row in rows:
            item: dict[str, Any] = {}
            for f in spec.fields:
                v = getattr(row, f)
                if isinstance(v, datetime):
                    v = v.isoformat()
                item[f] = v
            out.setdefault(name, []).append(item)
    return {"tables": out, "truncated": truncated}


def _parse_dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def upsert_aux_rows(session: Any, chain_id: str, tables: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    """Upsert side-effect rows shipped by a peer's sync response.

    Keyed on each table's natural unique key (stake by ``id`` — the hub's
    row id is the canonical stake handle; bond by ``bond_id``; proposal by
    ``proposal_id``; vote by ``(proposal_id, voter_address)``). Address
    fields are case-normalized with ``_to_ait_address``. Rows missing a key
    field are skipped loudly — the payload comes from our own peer and a
    malformed row means a bug, not data to guess at.
    """
    counts: dict[str, int] = {}
    for name, spec in AUX_TABLES.items():
        rows = tables.get(name) or []
        applied = 0
        for row in rows:
            key_values: dict[str, Any] = {}
            for k in spec.key_fields:
                v = row.get(k)
                if k in spec.address_fields and isinstance(v, str) and v:
                    try:
                        v = _to_ait_address(v)
                    except (TypeError, ValueError):
                        pass
                key_values[k] = v
            if any(v is None or v == "" for v in key_values.values()):
                logger.warning("Skipping %s row with missing key fields: %r", name, row)
                continue
            cond = [spec.model.chain_id == chain_id]
            cond += [getattr(spec.model, k) == v for k, v in key_values.items()]
            existing = session.exec(select(spec.model).where(*cond)).first()
            data: dict[str, Any] = {}
            for f in spec.fields:
                v = row.get(f)
                if f in spec.address_fields and isinstance(v, str) and v:
                    try:
                        v = _to_ait_address(v)
                    except (TypeError, ValueError):
                        pass
                elif f in spec.datetime_fields:
                    v = _parse_dt(v)
                data[f] = v
            if existing is not None:
                for f, v in data.items():
                    # A peer that omits a field (older version, or a
                    # legitimately null optional) must not null out a local
                    # value — these tables only ever transition None->value.
                    if v is None:
                        continue
                    setattr(existing, f, v)
            else:
                missing = [f for f in spec.fields if f in spec.datetime_fields and data[f] is None]
                if "locked_until" in missing or "voting_starts" in missing or "voting_ends" in missing:
                    logger.warning("Skipping %s row missing required datetime fields: %r", name, missing)
                    continue
                insert_data = {k: v for k, v in data.items() if v is not None or k in spec.key_fields}
                session.add(spec.model(chain_id=chain_id, **insert_data))
            applied += 1
        counts[name] = applied
    return counts
