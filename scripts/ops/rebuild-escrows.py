#!/usr/bin/env python3
"""Read-only escrow reconciliation proof for a local chain.db (SD-1).

Design: ``docs/design/escrow-rebuild-from-chain.md``. The sealed
``transaction`` table is canonical; the ``escrow`` table is a derived cache
written only on the node that served ``POST /rpc/escrow/lock`` (plus the lazy
read-path healers), so row counts legitimately differ per node. This tool
derives the expected row for every job_id with a sealed ESCROW_LOCK, compares
it with the stored table, and prints the reconciliation proof (per-job
invariants R1-R5, global invariants G1-G4).

READ-ONLY BY CONSTRUCTION. There is no write mode and no write path: the only
connection this program ever opens is SQLite ``mode=ro`` plus
``PRAGMA query_only=ON``, so the kernel itself refuses any write. There is no
``--apply``/``--write`` flag, no ``ATTACH``, and no second connection
function. A write mode (per the design's §6) must be a separate change gated
on this proof passing.

Usage:

    venv/bin/python scripts/ops/rebuild-escrows.py --db /path/to/chain.db
    venv/bin/python scripts/ops/rebuild-escrows.py --db chain.db \
        --job-id <id> --report /tmp/escrow-recon.json

Exit status: 0 = proof clean (derived state fully matches stored rows),
1 = at least one invariant failed, 2 = usage error / unreadable database.

Output prints shortened job ids and tx hashes and amounts in compute-units
(36,000,000 units = 1 AIT). It never prints key material — there is none in
the chain database anyway — and never follows into files outside ``--db``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import urllib.parse
from typing import Any

LEG_TYPES = ("ESCROW_LOCK", "ESCROW_RELEASE", "ESCROW_REFUND", "ESCROW_FEE_SWEEP")
EXPECTED_ACTION = {
    "ESCROW_LOCK": "escrow_lock",
    "ESCROW_RELEASE": "escrow_release",
    "ESCROW_REFUND": "escrow_refund",
    "ESCROW_FEE_SWEEP": "escrow_fee_sweep",
}
# Fields the chain supplies exactly; a stored non-NULL value differing from the
# derived one is an R5 conflict (the write gate's abort condition).
EXACT_FIELDS = (
    "chain_id",
    "buyer",
    "provider",
    "amount",
    "status",
    "lock_tx_hash",
    "release_tx_hash",
    "refund_tx_hash",
    "released_amount",
    "refunded_amount",
    "energy_quote_id",
    "energy_quote_digest",
    "energy_settlement_route",
    "energy_settlement_asset",
    "energy_settlement_unit_scale",
)
# Stored values written at RPC time that the chain cannot reproduce — the
# derived row carries NULL; a populated stored value is reported as
# informational only (it would be lost by a rebuild, so it is listed, never
# counted as a conflict).
NON_DERIVABLE_FIELDS = (
    "job_tx_hash",
    "billed_legs",
    "energy_quote_snapshot",
    "energy_net_floor_units",
    "energy_provider_credit_units",
    "energy_fee_basis_points",
)
# Timestamps: the design derives them from the including block's timestamp,
# while existing rows were written with node-local row-insert times, so a
# populated stored value legitimately differs. Reported as deltas, not R5
# conflicts.
TIMESTAMP_FIELDS = ("created_at", "released_at", "refunded_at")

_EVM_RE = re.compile(r"^0x[0-9a-f]{40}$")
_CANON = None
_KECCAK = None


def _canonicalizers():
    """Load canonical_address + keccak lazily so --help works without deps."""
    global _CANON, _KECCAK
    if _CANON is None:
        try:
            from aitbc.crypto.signature_recovery import canonical_address as canon
        except Exception:
            # Same lenient semantics as aitbc.crypto.signature_recovery's
            # canonical_address(strict=False): EIP-55 for 0x+40-hex, else
            # lowercased pass-through.
            from eth_utils import to_checksum_address

            def canon(value: str) -> str:
                lowered = value.strip().lower()
                return to_checksum_address(lowered) if _EVM_RE.fullmatch(lowered) else lowered

        from eth_utils import keccak

        _CANON, _KECCAK = canon, keccak
    return _CANON, _KECCAK


def _connect_ro(db_path: str) -> sqlite3.Connection:
    """Open the chain database strictly read-only.

    The ONLY connection this program creates: a ``mode=ro`` URI — SQLite
    refuses to open it writable, so no later code path can modify the file.
    ``PRAGMA query_only=ON`` adds a second refusal layer. ``immutable=1`` is
    deliberately absent: a live chain.db holds its newest pages in the WAL
    and immutable mode would read a stale snapshot.
    """
    if not os.path.isfile(db_path):
        raise FileNotFoundError(db_path)
    uri = "file:" + urllib.parse.quote(os.path.abspath(db_path)) + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA query_only=ON")
    return conn


def _short(value: Any, keep: int = 10, tail: int = 4) -> str:
    """Shorten an identifier for display: ``0x1234abcd…wxyz``."""
    s = "" if value is None else str(value)
    return s if len(s) <= keep + tail + 1 else f"{s[:keep]}…{s[-tail:]}"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return row is not None


def _payload_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _recorded_block_version(block_metadata: Any) -> int | None:
    """Mirror get_recorded_block_version: stamp in block_metadata or None."""
    parsed = _payload_dict(block_metadata)
    version = parsed.get("state_transition_version")
    try:
        return int(version) if version is not None else None
    except (TypeError, ValueError):
        return None


def _escrow_address(job_id: str) -> str:
    canon, keccak = _canonicalizers()
    return canon("0x" + keccak(f"aitbc.escrow.{job_id}".encode()).hex()[:40])


def _load_blocks(conn: sqlite3.Connection) -> dict[tuple[str, int], dict[str, Any]]:
    rows = conn.execute("SELECT chain_id, height, hash, parent_hash, timestamp, block_metadata FROM block").fetchall()
    return {
        (r[0], r[1]): {
            "hash": r[2],
            "parent_hash": r[3],
            "timestamp": r[4],
            "metadata": r[5],
        }
        for r in rows
    }


def _canonical_heights(blocks: dict[tuple[str, int], dict[str, Any]]) -> set[tuple[str, int]]:
    """Blocks reachable by walking parent_hash back from each chain's tip."""
    by_hash = {(cid, b["hash"]): (cid, h) for (cid, h), b in blocks.items()}
    canonical: set[tuple[str, int]] = set()
    tips: dict[str, tuple[str, int]] = {}
    for cid, height in blocks:
        if cid not in tips or height > tips[cid][1]:
            tips[cid] = (cid, height)
    for tip in tips.values():
        cur: tuple[str, int] | None = tip
        while cur is not None and cur not in canonical:
            canonical.add(cur)
            parent = blocks[cur]["parent_hash"]
            cur = by_hash.get((cur[0], parent))
    return canonical


def _load_legs(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    placeholders = ",".join("?" for _ in LEG_TYPES)
    # The IN-list is a fixed-size placeholder string, never user data — the
    # interpolated `placeholders` is built from the LEG_TYPES constant above.
    rows = conn.execute(
        f"SELECT id, chain_id, tx_hash, block_height, sender, recipient, payload, value, type"  # nosec B608 - placeholders only, values bound
        f' FROM "transaction" WHERE block_height IS NOT NULL AND type IN ({placeholders})',
        LEG_TYPES,
    ).fetchall()
    legs = []
    for r in rows:
        payload = _payload_dict(r[6])
        legs.append(
            {
                "id": r[0],
                "chain_id": r[1],
                "tx_hash": r[2],
                "block_height": r[3],
                "sender": r[4],
                "recipient": r[5],
                "payload": payload,
                "value": r[7] or 0,
                "type": r[8],
                "job_id": payload.get("job_id"),
            }
        )
    return legs


def _load_escrow_rows(conn: sqlite3.Connection) -> dict[tuple[str, str], dict[str, Any]]:
    cols = (
        "job_id, chain_id, buyer, provider, amount, status, created_at, released_at, refunded_at,"
        " lock_tx_hash, job_tx_hash, release_tx_hash, refund_tx_hash, released_amount, refunded_amount,"
        " billed_legs, protected, energy_quote_snapshot, energy_quote_id, energy_quote_digest,"
        " energy_settlement_route, energy_settlement_asset, energy_settlement_unit_scale,"
        " energy_net_floor_units, energy_provider_credit_units, energy_fee_basis_points"
    )
    names = [c.strip() for c in cols.split(",")]
    # Older chain.db files predate billed_legs/energy_* — intersect the wanted
    # columns with the table's real schema and leave the rest NULL.
    existing = {r[1] for r in conn.execute("PRAGMA table_info(escrow)").fetchall()}
    wanted = [c for c in names if c in existing]
    rows = conn.execute(f"SELECT {','.join(wanted)} FROM escrow").fetchall()  # nosec B608 - fixed literal column list
    return {(r[1], r[0]): {**dict.fromkeys(names), **dict(zip(wanted, r, strict=True))} for r in rows}


def _load_accounts(conn: sqlite3.Connection) -> dict[tuple[str, str], int]:
    rows = conn.execute("SELECT chain_id, address, balance FROM account").fetchall()
    return {(r[0], r[1]): r[2] for r in rows}


def _derive_job(
    chain_id: str,
    job_id: str,
    job_legs: list[dict[str, Any]],
    blocks: dict[tuple[str, int], dict[str, Any]],
    canonical: set[tuple[str, int]],
) -> dict[str, Any]:
    """Derive the expected escrow row for one job from its sealed legs.

    Field mapping follows design §3: the *latest* sealed lock wins; release and
    refund legs are summed independently; timestamps come from the including
    block, never from ``transaction.created_at`` (a node-local insert time).
    """
    canon, _ = _canonicalizers()
    locks = [t for t in job_legs if t["type"] == "ESCROW_LOCK"]
    releases = [t for t in job_legs if t["type"] == "ESCROW_RELEASE"]
    refunds = [t for t in job_legs if t["type"] == "ESCROW_REFUND"]
    sweeps = [t for t in job_legs if t["type"] == "ESCROW_FEE_SWEEP"]
    ordered = sorted(job_legs, key=lambda t: (t["block_height"], t["id"]))
    lock = max(locks, key=lambda t: (t["block_height"], t["id"]))
    payload = lock["payload"]

    def _block_ts(tx: dict[str, Any]) -> Any:
        block = blocks.get((tx["chain_id"], tx["block_height"]))
        return block["timestamp"] if block else None

    released = sum(t["value"] for t in releases)
    refunded = sum(t["value"] for t in refunds)
    swept = sum(t["value"] for t in sweeps)
    status = "released" if releases else ("refunded" if refunds else "locked")
    settled = bool(releases or refunds)
    lock_version = _recorded_block_version(blocks.get((chain_id, lock["block_height"]), {}).get("metadata"))
    # Custody accumulates every v3 lock's value (a re-lock parks more funds at
    # the same derived address), so G3 must sum all version>=3 locks — the
    # "latest lock wins" rule is for the row's fields, not the balance.
    v3_locked = sum(
        t["value"]
        for t in locks
        if (_recorded_block_version(blocks.get((chain_id, t["block_height"]), {}).get("metadata")) or 0) >= 3
    )
    anomalies = [
        f"action {p.get('action')!r} on {t['type']} tx {_short(t['tx_hash'])}"
        for t in ordered
        if (p := t["payload"]).get("action") not in (None, EXPECTED_ACTION[t["type"]])
    ]
    off_canonical = [_short(t["tx_hash"]) for t in ordered if (chain_id, t["block_height"]) not in canonical]
    return {
        "job_id": job_id,
        "chain_id": chain_id,
        "buyer": canon(payload.get("buyer") or lock["sender"] or ""),
        "provider": canon(payload.get("provider") or ""),
        "amount": lock["value"],
        "status": status,
        "created_at": _block_ts(lock),
        "released_at": _block_ts(releases[-1]) if releases else None,
        "refunded_at": _block_ts(refunds[-1]) if (refunds and not releases) else None,
        "lock_tx_hash": lock["tx_hash"],
        "release_tx_hash": releases[-1]["tx_hash"] if releases else None,
        "refund_tx_hash": refunds[-1]["tx_hash"] if refunds else None,
        "released_amount": released if settled else None,
        "refunded_amount": refunded if settled else None,
        "energy_quote_id": payload.get("energy_quote_id"),
        "energy_quote_digest": payload.get("energy_quote_digest"),
        "energy_settlement_route": payload.get("settlement_route"),
        "energy_settlement_asset": payload.get("settlement_asset"),
        "energy_settlement_unit_scale": payload.get("settlement_unit_scale"),
        "protected_inferred": bool(payload.get("energy_quote_id") or payload.get("energy_quote_digest")),
        "swept": swept,
        "v3_locked": v3_locked,
        "lock_version": lock_version,
        "lock_count": len(locks),
        "release_legs": len(releases),
        "refund_legs": len(refunds),
        "sweep_legs": len(sweeps),
        "action_anomalies": anomalies,
        "off_canonical_txs": off_canonical,
        "escrow_addr": _escrow_address(job_id) if (lock_version or 0) >= 3 else None,
    }


def _compare(derived: dict[str, Any], stored: dict[str, Any] | None) -> dict[str, Any]:
    """Compare one derived row against its stored row."""
    canon, _ = _canonicalizers()
    result: dict[str, Any] = {"conflicts": [], "deltas": [], "extra_data": []}
    if stored is None:
        return result
    for field in EXACT_FIELDS:
        dval = derived[field]
        sval = stored.get(field)
        if field in ("buyer", "provider") and sval is not None:
            sval = canon(str(sval))
        if sval is None or sval == dval:
            continue
        result["conflicts"].append({"field": field, "stored": sval, "derived": dval})
    for field in TIMESTAMP_FIELDS:
        sval, dval = stored.get(field), derived[field]
        if sval is not None and dval is not None and str(sval) != str(dval):
            result["deltas"].append({"field": field, "stored": str(sval), "derived": str(dval)})
    if stored.get("protected") is not None and bool(stored["protected"]) != derived["protected_inferred"]:
        result["deltas"].append(
            {"field": "protected", "stored": stored["protected"], "derived": derived["protected_inferred"]}
        )
    for field in NON_DERIVABLE_FIELDS:
        if stored.get(field) is not None:
            result["extra_data"].append(field)
    return result


def reconcile(conn: sqlite3.Connection, job_filter: str | None = None) -> tuple[dict[str, Any], list[str]]:
    """Run the full reconciliation. Returns (report, invariant_failures)."""
    failures: list[str] = []
    tables = {name: _table_exists(conn, name) for name in ("block", "transaction", "escrow", "account")}
    report: dict[str, Any] = {"tables": tables, "chains": {}, "checks": {}, "scoped_to_job": job_filter}
    if not (tables["block"] and tables["transaction"]):
        report["checks"]["fatal"] = "block/transaction tables absent — cannot derive anything"
        return report, ["fatal: block/transaction tables absent"]

    blocks = _load_blocks(conn)
    canonical = _canonical_heights(blocks)
    legs = _load_legs(conn)
    # Sealed = block_height set AND the block row exists (design §2).
    sealed = [t for t in legs if (t["chain_id"], t["block_height"]) in blocks]
    unsealed_dangling = [t for t in legs if (t["chain_id"], t["block_height"]) not in blocks]
    stored_rows = _load_escrow_rows(conn) if tables["escrow"] else {}
    accounts = _load_accounts(conn) if tables["account"] else {}

    by_job: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for tx in sealed:
        if tx["job_id"]:
            by_job.setdefault((tx["chain_id"], tx["job_id"]), []).append(tx)
    if job_filter:
        by_job = {k: v for k, v in by_job.items() if k[1] == job_filter}
        stored_rows = {k: v for k, v in stored_rows.items() if k[1] == job_filter}

    lock_jobs = {k for k, ts in by_job.items() if any(t["type"] == "ESCROW_LOCK" for t in ts)}
    # R1: settlement legs with no sealed lock for their job_id.
    orphan_legs = [
        {"job_id": k[1], "chain_id": k[0], "txs": [_short(t["tx_hash"]) for t in ts if t["type"] != "ESCROW_LOCK"]}
        for k, ts in by_job.items()
        if k not in lock_jobs
    ]
    if orphan_legs:
        failures.append(f"R1: {len(orphan_legs)} job(s) have settlement legs but no sealed lock")

    derived: dict[tuple[str, str], dict[str, Any]] = {}
    compares: dict[tuple[str, str], dict[str, Any]] = {}
    for key in sorted(lock_jobs):
        cid, jid = key
        d = _derive_job(cid, jid, by_job[key], blocks, canonical)
        derived[key] = d
        compares[key] = _compare(d, stored_rows.get(key))

    # R2/R3/R4 per job.
    r2_bad = [k for k, d in derived.items() if (d["released_amount"] or 0) + (d["refunded_amount"] or 0) > d["amount"]]
    r3_bad = [
        k
        for k, d in derived.items()
        if d["status"] != ("released" if d["release_legs"] else ("refunded" if d["refund_legs"] else "locked"))
        or (d["release_legs"] and d["refunded_at"] is not None)
    ]
    r4_bad = [k for k, d in derived.items() if d["off_canonical_txs"]]
    if r2_bad:
        failures.append(f"R2: {len(r2_bad)} job(s) settled more than locked")
    if r3_bad:
        failures.append(f"R3: {len(r3_bad)} job(s) violate the status mapping")
    if r4_bad:
        failures.append(f"R4: {len(r4_bad)} job(s) reference non-canonical blocks")

    # R5: stored-vs-derived exact-field conflicts (abort-class per design §5).
    r5_conflicts = {k: c["conflicts"] for k, c in compares.items() if c["conflicts"]}
    if r5_conflicts:
        failures.append(f"R5: {len(r5_conflicts)} stored row(s) contradict chain-derived fields")

    missing_rows = [k for k in lock_jobs if k not in stored_rows]
    orphan_rows = [k for k in stored_rows if k not in lock_jobs]
    if job_filter:
        orphan_rows = [k for k in orphan_rows if k[1] == job_filter]

    # G1: Σ locked = Σ released + Σ refunded + Σ swept + Σ residual.
    g1 = {
        "locked": sum(d["amount"] for d in derived.values()),
        "released": sum(d["released_amount"] or 0 for d in derived.values()),
        "refunded": sum(d["refunded_amount"] or 0 for d in derived.values()),
        "swept": sum(d["swept"] for d in derived.values()),
    }
    g1["residual"] = g1["locked"] - g1["released"] - g1["refunded"] - g1["swept"]
    if g1["residual"] < 0 or min(g1.values()) < 0:
        failures.append("G1: negative component in the locked=released+refunded+swept+residual identity")

    # G2: stored row count == distinct sealed-lock job count.
    if tables["escrow"]:
        # Count equality alone is not enough: a missing row cancelled by an
        # orphan row would pass a bare count while the sets clearly differ.
        if len(stored_rows) != len(lock_jobs) or missing_rows or orphan_rows:
            failures.append(
                f"G2: {len(stored_rows)} stored rows vs {len(lock_jobs)} sealed-lock jobs "
                f"({len(missing_rows)} missing, {len(orphan_rows)} orphan)"
            )
    else:
        failures.append("G2: escrow table absent")

    # G3: custody balance == Σ v3-locked − released − refunded − swept.
    g3_checked = g3_skipped = 0
    g3_bad: list[dict[str, Any]] = []
    if tables["account"]:
        for k, d in derived.items():
            if (d["lock_version"] or 0) < 3:
                g3_skipped += 1
                continue
            g3_checked += 1
            expected = d["v3_locked"] - (d["released_amount"] or 0) - (d["refunded_amount"] or 0) - d["swept"]
            actual = accounts.get((k[0], d["escrow_addr"]))
            if actual != expected:
                g3_bad.append({"job_id": k[1], "expected": expected, "actual": actual})
        if g3_bad:
            failures.append(f"G3: {len(g3_bad)} custody balance(s) disagree with derived settlement")
    else:
        g3_skipped = len(derived)

    # G4: buyer/provider accounts exist.
    g4_missing = []
    if tables["account"]:
        for k, d in derived.items():
            for field in ("buyer", "provider"):
                if (k[0], d[field]) not in accounts:
                    g4_missing.append({"job_id": k[1], "party": field, "address": _short(d[field])})
        if g4_missing:
            failures.append(f"G4: {len(g4_missing)} party account(s) missing")

    report["legs_dangling_block"] = len(unsealed_dangling)
    report["counts"] = {
        "sealed_legs": len(sealed),
        "sealed_locks": sum(1 for t in sealed if t["type"] == "ESCROW_LOCK"),
        "releases": sum(1 for t in sealed if t["type"] == "ESCROW_RELEASE"),
        "refunds": sum(1 for t in sealed if t["type"] == "ESCROW_REFUND"),
        "sweeps": sum(1 for t in sealed if t["type"] == "ESCROW_FEE_SWEEP"),
        "distinct_jobs": len(lock_jobs),
        "stored_rows": len(stored_rows),
        "missing_rows": len(missing_rows),
        "orphan_rows": len(orphan_rows),
        "conflicting_rows": len(r5_conflicts),
    }
    report["checks"] = {
        "R1": {"status": "FAIL" if orphan_legs else "PASS", "orphan_leg_jobs": orphan_legs},
        "R2": {"status": "FAIL" if r2_bad else "PASS", "violations": [_short(k[1]) for k in r2_bad]},
        "R3": {"status": "FAIL" if r3_bad else "PASS", "violations": [_short(k[1]) for k in r3_bad]},
        "R4": {"status": "FAIL" if r4_bad else "PASS", "violations": [_short(k[1]) for k in r4_bad]},
        "R5": {
            "status": "FAIL" if r5_conflicts else "PASS",
            "conflicts": {k[1]: c for k, c in r5_conflicts.items()},
        },
        "G1": {"status": "PASS" if g1["residual"] >= 0 else "FAIL", **g1},
        "G2": {
            "status": (
                "PASS"
                if tables["escrow"] and len(stored_rows) == len(lock_jobs) and not missing_rows and not orphan_rows
                else "FAIL"
            ),
            "stored": len(stored_rows),
            "expected": len(lock_jobs),
        },
        "G3": {
            "status": ("SKIP" if g3_checked == 0 else ("FAIL" if g3_bad else "PASS")),
            "checked": g3_checked,
            "skipped": g3_skipped,
            "mismatches": g3_bad,
        },
        "G4": {"status": "FAIL" if g4_missing else "PASS", "missing": g4_missing},
    }
    report["jobs"] = {
        k[1]: {
            "chain_id": k[0],
            "status": d["status"],
            "amount": d["amount"],
            "released": d["released_amount"],
            "refunded": d["refunded_amount"],
            "swept": d["swept"],
            "locks": d["lock_count"],
            "lock_version": d["lock_version"],
            "row": "present" if k in stored_rows else "MISSING",
            "conflicts": compares[k]["conflicts"],
            "deltas": compares[k]["deltas"],
            "extra_data": compares[k]["extra_data"],
            "action_anomalies": d["action_anomalies"],
            "off_canonical_txs": d["off_canonical_txs"],
        }
        for k, d in derived.items()
    }
    # Full ids in the JSON report — several production job ids share the same
    # first/last characters, so shortened keys would silently collapse rows.
    report["missing_rows"] = sorted(k[1] for k in missing_rows)
    report["orphan_rows"] = [{"job_id": k[1], "chain_id": k[0]} for k in orphan_rows]
    return report, failures


# The deferred-residue conflict class (A4/R5): the stored row holds the billed
# net amount of the primary release leg while the sealed legs also carried the
# ~2.5% deferred-residue leg, so derived released_amount > stored; the stored
# release_tx_hash names the primary leg while the derivation takes the latest
# sealed leg. Only that shape is ever eligible for an UPDATE in the write
# phase — anything touching another field, or shrinking the released amount,
# is manual review.
_DEFERRED_RESIDUE_FIELDS = {"released_amount", "released_at", "release_tx_hash", "status"}


def _build_write_plan(report: dict[str, Any]) -> dict[str, Any]:
    """Translate the reconcile report into the A7 write-phase dry run.

    Returns the ordered list of what the write phase WOULD do on this host —
    this program never performs it. Classes (design §5): ``insert`` for
    missing rows derived from sealed transactions, ``update`` for the
    deferred-residue conflict class only, ``manual_review`` for any other
    conflict, ``report_only`` for orphans and dangling legs. An R2 double
    settlement aborts the plan entirely: it is stop-and-escalate, never
    repaired by a tool.
    """
    jobs = report.get("jobs", {})
    plan: dict[str, Any] = {
        "abort": [],
        "insert": [],
        "update": [],
        "manual_review": [],
        "report_only": [],
        "unchanged": 0,
    }
    r2 = report.get("checks", {}).get("R2", {})
    if r2.get("status") == "FAIL":
        plan["abort"].append(
            f"R2 double settlement on {len(r2.get('violations', []))} job(s): the write phase refuses to "
            "run on this host — escalate per SD-1, never auto-repair"
        )
    for jid in report.get("missing_rows", []):
        job = jobs.get(jid, {})
        plan["insert"].append(
            {
                "job_id": jid,
                "table": "escrow",
                "class": "missing",
                "derived": {
                    k: job.get(k) for k in ("status", "amount", "released", "refunded", "swept", "locks", "lock_version")
                },
            }
        )
    for jid, job in sorted(jobs.items()):
        if job["row"] == "MISSING":
            continue
        conflicts = job.get("conflicts", [])
        if not conflicts:
            plan["unchanged"] += 1
            continue
        fields = {c["field"] for c in conflicts}
        bump = next((c for c in conflicts if c["field"] == "released_amount"), None)
        deferred_residue = (
            fields <= _DEFERRED_RESIDUE_FIELDS
            and bump is not None
            and isinstance(bump["stored"], int)
            and isinstance(bump["derived"], int)
            and bump["derived"] > bump["stored"]
        )
        entry = {
            "job_id": jid,
            "table": "escrow",
            "class": "deferred-residue" if deferred_residue else "foreign-field",
            "set": [{"field": c["field"], "stored": c["stored"], "derived": c["derived"]} for c in conflicts],
        }
        (plan["update"] if deferred_residue else plan["manual_review"]).append(entry)
    for item in report.get("orphan_rows", []):
        plan["report_only"].append({"job_id": item["job_id"], "chain_id": item["chain_id"], "class": "orphan-row"})
    if report.get("legs_dangling_block"):
        plan["report_only"].append({"class": "dangling-legs", "count": report["legs_dangling_block"]})
    return plan


def _print_write_plan(plan: dict[str, Any]) -> None:
    print("write-phase dry run (classes only — no writes performed or possible):")
    for reason in plan["abort"]:
        print(f"  ABORT: {reason}")
    if plan["abort"]:
        print("  plan aborted: the write phase cannot run until the abort reason is resolved")
        return
    print(f"  step 1 — INSERT missing rows derived from sealed txs: {len(plan['insert'])}")
    for item in plan["insert"]:
        d = item["derived"]
        print(
            f"    job={_short(item['job_id'])} INSERT escrow:"
            f" status={d['status']} amount={d['amount']} released={d['released']}"
            f" refunded={d['refunded']} swept={d['swept']} locks={d['locks']} lock_version={d['lock_version']}"
        )
    print(f"  step 2 — UPDATE deferred-residue conflicts (released_amount := sum of sealed legs): {len(plan['update'])}")
    for item in plan["update"]:
        sets = "; ".join(f"{s['field']} {_short(s['stored'])} -> {_short(s['derived'])}" for s in item["set"])
        print(f"    job={_short(item['job_id'])} UPDATE escrow: {sets}")
    if plan["manual_review"]:
        print(
            f"  manual review — conflicts outside the deferred-residue class, never auto-written: {len(plan['manual_review'])}"
        )
        for item in plan["manual_review"]:
            sets = "; ".join(f"{s['field']} {_short(s['stored'])} -> {_short(s['derived'])}" for s in item["set"])
            print(f"    job={_short(item['job_id'])} {sets}")
    print(f"  report-only (never repaired by the tool): {len(plan['report_only'])} item(s)")
    for item in plan["report_only"]:
        print(f"    {item}")
    print(f"  unchanged rows verified identical to chain derivation: {plan['unchanged']}")
    print("  order on approval: snapshot file, class-1 inserts, class-2 updates, re-run this proof;")
    print("  rollback is restoring the snapshot. Host order per design: node2 -> node0 -> node1 -> hub1 -> hub.")


def _print_report(db_path: str, report: dict[str, Any], failures: list[str]) -> None:
    counts = report.get("counts", {})
    print(f"SD-1 escrow reconciliation — {db_path}")
    print("connection: sqlite file:?mode=ro + PRAGMA query_only=ON (read-only, WAL-aware)")
    if report.get("scoped_to_job"):
        print(f"scope: job {_short(report['scoped_to_job'])} only")
    if "fatal" in report.get("checks", {}):
        print(f"FATAL: {report['checks']['fatal']}")
        return
    print(
        "counts: sealed_locks={sealed_locks} releases={releases} refunds={refunds} sweeps={sweeps} "
        "jobs={distinct_jobs} rows={stored_rows} missing={missing_rows} orphans={orphan_rows} "
        "conflicts={conflicting_rows}".format(**counts)
    )
    if report["legs_dangling_block"]:
        print(f"note: {report['legs_dangling_block']} tx(s) name a block_height with no block row")
    for name in ("R1", "R2", "R3", "R4", "R5", "G1", "G2", "G3", "G4"):
        check = report["checks"][name]
        status = check["status"]
        detail = ""
        if name == "G1":
            detail = (
                f" locked={check['locked']} released={check['released']} refunded={check['refunded']}"
                f" swept={check['swept']} residual={check['residual']}"
            )
        elif name == "G2":
            detail = f" stored={check['stored']} expected={check['expected']}"
        elif name == "G3":
            detail = f" checked={check['checked']} skipped={check['skipped']}"
        print(f"  {name}: {status}{detail}")
    for jid in report["missing_rows"]:
        print(f"  MISSING-ROW job={_short(jid)}")
    for item in report["orphan_rows"]:
        print(f"  ORPHAN-ROW job={_short(item['job_id'])} chain={item['chain_id']}")
    for job, check_conflicts in report["checks"]["R5"]["conflicts"].items():
        for c in check_conflicts:
            print(f"  CONFLICT job={_short(job)} field={c['field']} stored={c['stored']} derived={c['derived']}")
    for item in report["checks"]["G3"]["mismatches"]:
        print(f"  G3-MISMATCH job={_short(item['job_id'])} expected={item['expected']} actual={item['actual']}")
    for item in report["checks"]["G4"]["missing"]:
        print(f"  G4-MISSING job={_short(item['job_id'])} {item['party']}={item['address']}")
    extra = [
        (j, info)
        for j, info in report["jobs"].items()
        if info["extra_data"] or info["deltas"] or info["action_anomalies"] or info["locks"] > 1
    ]
    for j, info in extra:
        shown = _short(j)
        if info["extra_data"]:
            print(f"  INFO job={shown} non-derivable stored fields: {','.join(info['extra_data'])}")
        if info["locks"] > 1:
            print(f"  INFO job={shown} re-locked {info['locks']}x (latest lock wins)")
        for anomaly in info["action_anomalies"]:
            print(f"  INFO job={shown} action anomaly: {anomaly}")
    verdict = "CLEAN" if not failures else "RED"
    print(f"proof: {verdict} ({len(failures)} invariant failure(s))")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Derive expected escrow rows from sealed chain transactions and prove the stored "
            "escrow table against them (SD-1). READ-ONLY BY CONSTRUCTION: the database is opened "
            "mode=ro with PRAGMA query_only=ON — there is no write flag, no writable "
            "connection and no ATTACH anywhere in this tool."
        )
    )
    parser.add_argument("--db", required=True, help="path to the local chain.db (opened read-only)")
    parser.add_argument("--job-id", help="restrict the proof to one job_id (globals are scoped too)")
    parser.add_argument("--report", help="also write the JSON report to this path")
    parser.add_argument(
        "--plan",
        action="store_true",
        help="print the write-phase dry run (per-class insert/update/manual-review list) — no writes",
    )
    args = parser.parse_args(argv)

    try:
        conn = _connect_ro(args.db)
    except (FileNotFoundError, sqlite3.Error) as e:
        print(f"error: cannot open {args.db} read-only: {e}", file=sys.stderr)
        return 2
    try:
        report, failures = reconcile(conn, args.job_id)
    finally:
        conn.close()
    _print_report(args.db, report, failures)
    if args.plan:
        plan = _build_write_plan(report)
        report["write_plan"] = plan
        _print_write_plan(plan)
    if args.report:
        try:
            with open(args.report, "w") as fh:
                json.dump(report, fh, indent=2, default=str)
        except OSError as e:
            print(f"error: cannot write report to {args.report}: {e}", file=sys.stderr)
            return 2
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
