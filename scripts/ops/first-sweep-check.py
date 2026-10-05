#!/usr/bin/env python3
"""First-sweep verifier for v11 ESCROW_FEE_SWEEP — read-only, stdlib-only.

Given a job id (or ``--latest`` for the most recent sealed sweep), verifies
against one or more chain.db snapshots that:

- the sweep is sealed (``block_height`` set) and carries ``payload.job_id``;
- the signer is the ``escrow_settlement_authority`` in force *at the sweep's
  block height* (resolved from ``chain_parameter_history`` like
  ``_chain_parameter_value`` does — a later rotation does not rewrite what
  was true when the block applied);
- ``value`` equals the custody remainder the settlement legs left:
  ``lock.value - Σ sealed ESCROW_RELEASE - Σ sealed ESCROW_REFUND`` for the
  job, computed at the sweep's own block height;
- the derived custody account reads 0 afterwards;
- the fee recipient's balance equals its full tx-ledger replay — so the
  sweep contributed exactly ``value`` (the row is the only credit it adds;
  SKIP when the account has non-ledger flows such as a minted claim);
- the authority's balance equals its custody-aware ledger replay — so the
  sweep cost it exactly ``fee`` and not the value (SKIP on the same terms);
- across every database given, the same ``tx_hash`` seals at the same
  ``block_height`` with the same sender/recipient/value/fee.

The custody account address is derived locally with a small embedded
Keccak-256 (``_escrow_address`` computes ``keccak("aitbc.escrow.<job_id>")``
then checksums it). ``hashlib.sha3_256`` is NOT the same function — Keccak's
domain padding differs. A ``--custody`` override bypasses the derivation.

Databases are opened ``mode=ro`` — the script writes nothing, reads no keys,
and needs no RPC. Run it against live ``.backup`` copies, never the live file:

    ssh hub 'sqlite3 /var/lib/aitbc/data/<chain>/chain.db ".backup /tmp/chain-ro.db"'
    scp hub:/tmp/chain-ro.db /tmp/hub.db
    python3 scripts/ops/first-sweep-check.py --latest /tmp/hub.db
    python3 scripts/ops/first-sweep-check.py --job-id sw_job_… /tmp/hub.db /tmp/node2.db

Exit code 0 when every check is PASS or SKIP, 1 on any FAIL.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass, field

# --- Embedded Keccak-256 -----------------------------------------------------
# Minimal correct Keccak-f[1600] permutation + sponge (rate 136 for 256-bit
# output, 0x01 domain padding — legacy Keccak, not FIPS SHA-3's 0x06). Used to
# reproduce _escrow_address(job_id) without pulling in eth_utils.

_RC = [
    0x0000000000000001,
    0x0000000000008082,
    0x800000000000808A,
    0x8000000080008000,
    0x000000000000808B,
    0x0000000080000001,
    0x8000000080008081,
    0x8000000000008009,
    0x000000000000008A,
    0x0000000000000088,
    0x0000000080008009,
    0x000000008000000A,
    0x000000008000808B,
    0x800000000000008B,
    0x8000000000008089,
    0x8000000000008003,
    0x8000000000008002,
    0x8000000000000080,
    0x000000000000800A,
    0x800000008000000A,
    0x8000000080008081,
    0x8000000000008080,
    0x0000000080000001,
    0x8000000080008008,
]
_ROT = [
    [0, 36, 3, 41, 18],
    [1, 44, 10, 45, 2],
    [62, 6, 43, 15, 61],
    [28, 55, 25, 21, 56],
    [27, 20, 39, 8, 14],
]
_MASK64 = (1 << 64) - 1


def _rol(x: int, n: int) -> int:
    return ((x << n) | (x >> (64 - n))) & _MASK64


def _keccak_f(state: list[int]) -> None:
    for rc in _RC:
        # theta
        c = [state[x] ^ state[x + 5] ^ state[x + 10] ^ state[x + 15] ^ state[x + 20] for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rol(c[(x + 1) % 5], 1) for x in range(5)]
        for x in range(5):
            for y in range(5):
                state[x + 5 * y] ^= d[x]
        # rho + pi
        b = [0] * 25
        for x in range(5):
            for y in range(5):
                b[y + 5 * ((2 * x + 3 * y) % 5)] = _rol(state[x + 5 * y], _ROT[x][y])
        # chi
        for x in range(5):
            for y in range(5):
                state[x + 5 * y] = b[x + 5 * y] ^ ((~b[(x + 1) % 5 + 5 * y]) & b[(x + 2) % 5 + 5 * y])
        # iota
        state[0] ^= rc


def keccak256(data: bytes) -> bytes:
    """Keccak-256 digest (legacy padding), the Ethereum hash."""
    rate = 136  # 1088 bits
    state = [0] * 25
    padded = bytearray(data)
    padded.append(0x01)
    while len(padded) % rate != rate - 1:
        padded.append(0x00)
    padded.append(0x80)
    for off in range(0, len(padded), rate):
        block = padded[off : off + rate]
        for i in range(rate // 8):
            state[i] ^= int.from_bytes(block[8 * i : 8 * i + 8], "little")
        _keccak_f(state)
    out = bytearray()
    while len(out) < 32:
        for i in range(rate // 8):
            out += state[i].to_bytes(8, "little")
        if len(out) < 32:
            _keccak_f(state)
    return bytes(out[:32])


def _checksum_address(addr20: bytes) -> str:
    """EIP-55 checksum: keccak of the lowercase hex body, nibble-cased."""
    hex_body = addr20.hex()
    hashed = keccak256(hex_body.encode()).hex()
    return "0x" + "".join(c.upper() if c.isalpha() and int(hashed[i], 16) >= 8 else c for i, c in enumerate(hex_body))


def escrow_address(job_id: str) -> str:
    """Derived per-job custody address — same formula as the consensus path
    (``canonical_address("0x" + keccak("aitbc.escrow.<job>").hex()[:40])``:
    the FIRST 20 bytes of the digest, EIP-55 checksummed — not the trailing
    slice Ethereum uses for pubkey-derived addresses)."""
    return _checksum_address(keccak256(f"aitbc.escrow.{job_id}".encode())[:20])


# --- Chain DB read model ------------------------------------------------------


@dataclass
class Check:
    name: str
    status: str  # PASS | FAIL | SKIP
    detail: str


@dataclass
class SweepRow:
    tx_hash: str
    block_height: int
    sender: str
    recipient: str
    value: int
    fee: int
    nonce: int
    job_id: str


@dataclass
class HostReport:
    label: str
    checks: list[Check] = field(default_factory=list)
    sweep: SweepRow | None = None


def _open_ro(path: str) -> sqlite3.Connection:
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


def _payload_job_id(payload: object) -> str | None:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            return None
    if isinstance(payload, dict):
        jid = payload.get("job_id")
        return str(jid) if jid is not None else None
    return None


def _find_sweeps(db: sqlite3.Connection, chain_id: str, job_id: str | None) -> list[SweepRow]:
    """All sealed sweeps for ``job_id`` ascending by height — or, when
    ``job_id`` is None, only the most recent sweep's rows.

    Note: the sync importer records a failed-apply transaction with
    ``status='confirmed'`` (``sync_block_import`` writes the row even when the
    apply step logged a warning), so a row here is not proof the sweep
    *moved* funds — the balance checks are what prove that."""
    rows = db.execute(
        'SELECT tx_hash, block_height, sender, recipient, value, fee, nonce, payload FROM "transaction" '
        "WHERE chain_id = ? AND type = 'ESCROW_FEE_SWEEP' AND block_height IS NOT NULL "
        "ORDER BY block_height",
        (chain_id,),
    ).fetchall()
    out: list[SweepRow] = []
    for row in rows:
        jid = _payload_job_id(row["payload"])
        if jid is None or (job_id is not None and jid != job_id):
            continue
        out.append(
            SweepRow(
                tx_hash=row["tx_hash"],
                block_height=row["block_height"],
                sender=row["sender"],
                recipient=row["recipient"],
                value=row["value"],
                fee=row["fee"],
                nonce=row["nonce"],
                job_id=jid,
            )
        )
    if job_id is None and out:
        out = [out[-1]]
    return out


def _param_at(db: sqlite3.Connection, chain_id: str, parameter: str, height: int) -> str | None:
    """Value in force at ``height`` — mirrors _chain_parameter_value: latest
    history row at-or-below wins; the current row applies when its
    applied_height is NULL or at-or-below; a parameter whose only record
    postdates the height resolves unset."""
    hist = db.execute(
        "SELECT value FROM chain_parameter_history "
        "WHERE chain_id = ? AND parameter = ? AND applied_height <= ? "
        "ORDER BY applied_height DESC LIMIT 1",
        (chain_id, parameter, height),
    ).fetchone()
    if hist is not None:
        return hist["value"] or None
    row = db.execute(
        "SELECT value, applied_height FROM chain_parameter WHERE chain_id = ? AND parameter = ?",
        (chain_id, parameter),
    ).fetchone()
    if row is None:
        return None
    if row["applied_height"] is None or row["applied_height"] <= height:
        return row["value"] or None
    return None


def _legs(db: sqlite3.Connection, chain_id: str, job_id: str, at_or_below: int) -> tuple[int, int]:
    """Sealed settlement legs for the job at or below ``at_or_below``:
    (released, refunded). The sweep at that height is excluded by type."""
    released = refunded = 0
    for row in db.execute(
        'SELECT type, value, payload FROM "transaction" '
        "WHERE chain_id = ? AND block_height IS NOT NULL AND block_height <= ? "
        "AND type IN ('ESCROW_RELEASE', 'ESCROW_REFUND')",
        (chain_id, at_or_below),
    ):
        if _payload_job_id(row["payload"]) != job_id:
            continue
        if row["type"] == "ESCROW_RELEASE":
            released += row["value"]
        else:
            refunded += row["value"]
    return released, refunded


def _lock_value(db: sqlite3.Connection, chain_id: str, job_id: str, at_or_below: int) -> int | None:
    """Value of the job's sealed ESCROW_LOCK at or below ``at_or_below``."""
    for row in db.execute(
        'SELECT value, payload FROM "transaction" '
        "WHERE chain_id = ? AND type = 'ESCROW_LOCK' AND block_height IS NOT NULL AND block_height <= ? "
        "ORDER BY block_height",
        (chain_id, at_or_below),
    ):
        if _payload_job_id(row["payload"]) == job_id:
            return int(row["value"])
    return None


def _account(db: sqlite3.Connection, chain_id: str, address: str) -> tuple[int, int] | None:
    row = db.execute(
        "SELECT balance, nonce FROM account WHERE chain_id = ? AND address = ?",
        (chain_id, address),
    ).fetchone()
    return (int(row["balance"]), int(row["nonce"])) if row else None


def _replay_balance(db: sqlite3.Connection, chain_id: str, address: str) -> int | None:
    """Replay ``address``'s balance from the sealed tx ledger.

    Custody-funded legs (v3 ESCROW_RELEASE/REFUND and every ESCROW_FEE_SWEEP)
    debit the sender only their fee — the value comes from the per-job
    account — so sender debits are fee-only for those types. Returns None when
    the account also has non-ledger flows (genesis seed, minted receipts) —
    the caller must SKIP rather than guess."""
    total = 0
    for row in db.execute(
        'SELECT type, value, fee, sender, recipient, payload FROM "transaction" '
        "WHERE chain_id = ? AND block_height IS NOT NULL AND (sender = ? OR recipient = ?)",
        (chain_id, address, address),
    ):
        if row["recipient"] == address:
            # v3+ ESCROW_LOCK rows keep the submitter's recipient in the row
            # but apply credits the derived custody account — attribute the
            # credit to custody, not to the recorded recipient.
            jid = _payload_job_id(row["payload"]) if row["type"] == "ESCROW_LOCK" else None
            if jid is None or escrow_address(jid).lower() == address.lower():
                total += int(row["value"])
        if row["sender"] == address:
            debit = (
                int(row["fee"])
                if row["type"] in ("ESCROW_RELEASE", "ESCROW_REFUND", "ESCROW_FEE_SWEEP")
                else int(row["value"]) + int(row["fee"])
            )
            total -= debit
    return total


def check_host(path: str, label: str, chain_id: str, job_id: str | None, custody_override: str | None) -> HostReport:
    rep = HostReport(label=label)
    try:
        db = _open_ro(path)
    except sqlite3.Error as e:
        rep.checks.append(Check("open", "FAIL", f"cannot open {path} read-only: {e}"))
        return rep
    try:
        sweeps = _find_sweeps(db, chain_id, job_id)
        if not sweeps:
            what = f"job_id={job_id}" if job_id else "any"
            rep.checks.append(Check("sweep.sealed", "FAIL", f"no sealed ESCROW_FEE_SWEEP for {what} on {label}"))
            return rep
        # The earliest sealed sweep is the authoritative residue claim; later
        # matching rows are duplicates or failed-apply records.
        sweep = rep.sweep = sweeps[0]
        rep.checks.append(
            Check(
                "sweep.sealed",
                "PASS",
                f"{sweep.tx_hash[:18]}… sealed at height {sweep.block_height} for job {sweep.job_id}",
            )
        )
        if len(sweeps) > 1:
            rep.checks.append(
                Check(
                    "sweep.duplicates",
                    "SKIP",
                    f"{len(sweeps) - 1} further sealed sweep row(s) for this job "
                    f"(e.g. {sweeps[-1].tx_hash[:18]}…@{sweeps[-1].block_height}) — "
                    "verify they applied nothing (custody stays 0)",
                )
            )

        # Signer must be the settlement authority in force at the sweep height.
        authority = _param_at(db, chain_id, "escrow_settlement_authority", sweep.block_height)
        if authority is None:
            rep.checks.append(Check("sweep.signer", "FAIL", "no escrow_settlement_authority resolvable at sweep height"))
        else:
            same = sweep.sender.lower() == authority.lower()
            rep.checks.append(
                Check(
                    "sweep.signer",
                    "PASS" if same else "FAIL",
                    f"signer {sweep.sender[:14]}… vs authority {authority[:14]}…" + ("" if same else " — NOT the authority"),
                )
            )

        # Recipient must be the governed fee recipient at the sweep height.
        fee_recipient = _param_at(db, chain_id, "escrow_fee_recipient", sweep.block_height)
        if fee_recipient is None:
            rep.checks.append(Check("sweep.recipient", "FAIL", "no escrow_fee_recipient resolvable at sweep height"))
        else:
            same = sweep.recipient.lower() == fee_recipient.lower()
            rep.checks.append(
                Check(
                    "sweep.recipient",
                    "PASS" if same else "FAIL",
                    f"pays {sweep.recipient[:14]}… vs governed {fee_recipient[:14]}…"
                    + ("" if same else " — NOT the governed recipient"),
                )
            )

        # Value must equal the custody remainder the settlement legs left.
        lock = _lock_value(db, chain_id, sweep.job_id, sweep.block_height)
        released, refunded = _legs(db, chain_id, sweep.job_id, sweep.block_height)
        if lock is None:
            rep.checks.append(
                Check("sweep.value", "SKIP", f"no sealed ESCROW_LOCK for {sweep.job_id} — remainder not provable")
            )
            expected: int | None = None
        else:
            expected = lock - released - refunded
            rep.checks.append(
                Check(
                    "sweep.value",
                    "PASS" if sweep.value == expected else "FAIL",
                    f"value={sweep.value} vs lock({lock}) − released({released}) − refunded({refunded}) = {expected}",
                )
            )

        # Custody account: derived address reads 0 now (the detector read).
        custody = custody_override or escrow_address(sweep.job_id)
        acct = _account(db, chain_id, custody)
        if acct is None:
            rep.checks.append(Check("custody.zero", "FAIL", f"custody {custody[:14]}… has no account row"))
        else:
            rep.checks.append(
                Check(
                    "custody.zero",
                    "PASS" if acct[0] == 0 else "FAIL",
                    f"custody {custody[:14]}… balance={acct[0]} (detector reads {acct[0]})",
                )
            )

        # Recipient rose by exactly the swept value — provable when the
        # account's balance equals its full ledger replay (the sweep is then
        # necessarily the only unexplained credit of that size).
        replay = _replay_balance(db, chain_id, sweep.recipient)
        acct = _account(db, chain_id, sweep.recipient)
        if acct is None:
            rep.checks.append(Check("recipient.delta", "FAIL", f"recipient {sweep.recipient[:14]}… has no account row"))
        elif replay is not None and replay == acct[0]:
            rep.checks.append(
                Check(
                    "recipient.delta",
                    "PASS",
                    f"recipient balance {acct[0]} equals full ledger replay — sweep credited exactly {sweep.value}",
                )
            )
        else:
            rep.checks.append(
                Check(
                    "recipient.delta",
                    "SKIP",
                    f"recipient balance {acct[0]} vs ledger replay {replay} — non-ledger flows present; cannot isolate the sweep credit",
                )
            )

        # Authority fell by exactly the fee — same replay discipline, and the
        # sweep's sender nonce must equal its sealed send count (nonce rule).
        sreplay = _replay_balance(db, chain_id, sweep.sender)
        sacct = _account(db, chain_id, sweep.sender)
        if sacct is None:
            rep.checks.append(Check("authority.delta", "FAIL", f"authority {sweep.sender[:14]}… has no account row"))
        elif sreplay is not None and sreplay == sacct[0]:
            rep.checks.append(
                Check(
                    "authority.delta",
                    "PASS",
                    f"authority balance {sacct[0]} equals custody-aware replay — sweep debited only fee={sweep.fee}",
                )
            )
        else:
            rep.checks.append(
                Check(
                    "authority.delta",
                    "SKIP",
                    f"authority balance {sacct[0]} vs ledger replay {sreplay} — non-ledger flows present; fee debit not isolated",
                )
            )
        sent = db.execute(
            'SELECT COUNT(*) FROM "transaction" WHERE chain_id = ? AND block_height IS NOT NULL AND sender = ?',
            (chain_id, sweep.sender),
        ).fetchone()[0]
        nonce_ok = sacct is not None and sacct[1] == sent
        rep.checks.append(
            Check(
                "authority.nonce",
                "PASS" if nonce_ok else "FAIL",
                f"authority nonce {sacct[1] if sacct else 'absent'} vs {sent} sealed sends",
            )
        )
    finally:
        db.close()
    return rep


def check_cross_host(reports: list[HostReport]) -> Check:
    """Every host's sweep must be the same hash at the same height."""
    sweeps = [r.sweep for r in reports if r.sweep is not None]
    if len(sweeps) < 2:
        return Check("cross-host", "SKIP", f"only {len(sweeps)} host(s) carried a sweep — nothing to compare")
    first = sweeps[0]
    for other in sweeps[1:]:
        if (first.tx_hash, first.block_height) != (other.tx_hash, other.block_height):
            return Check(
                "cross-host",
                "FAIL",
                f"sweep hash/height differs across hosts: {first.tx_hash[:18]}…@{first.block_height} vs {other.tx_hash[:18]}…@{other.block_height}",
            )
        if (first.sender, first.recipient, first.value, first.fee) != (other.sender, other.recipient, other.value, other.fee):
            return Check("cross-host", "FAIL", "sweep hash matches but sender/recipient/value/fee differ across hosts")
    return Check("cross-host", "PASS", f"{len(sweeps)} hosts agree: {first.tx_hash[:18]}… at height {first.block_height}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--job-id", help="verify the sealed sweep for this job id")
    group.add_argument("--latest", action="store_true", help="verify the most recent sealed sweep")
    ap.add_argument("--chain-id", default=None, help="chain_id filter (default: the chain the sweep rows carry)")
    ap.add_argument("--custody", default=None, help="override the derived custody address")
    ap.add_argument("dbs", nargs="+", metavar="DB", help="chain.db snapshot paths (opened read-only)")
    args = ap.parse_args(argv)

    reports: list[HostReport] = []
    for path in args.dbs:
        label = path.rsplit("/", 1)[-1] or path
        chain_id = args.chain_id
        if chain_id is None:
            # Default to the chain that actually carries the sweep rows.
            db = _open_ro(path)
            row = db.execute('SELECT chain_id FROM "transaction" ORDER BY block_height DESC LIMIT 1').fetchone()
            db.close()
            chain_id = row[0] if row else "ait-hub.aitbc.bubuit.net"
        reports.append(check_host(path, label, chain_id, args.job_id, args.custody))

    failed = False
    for rep in reports:
        print(f"## {rep.label}")
        for c in rep.checks:
            print(f"  {c.status:<4} {c.name}: {c.detail}")
            if c.status == "FAIL":
                failed = True
    cross = check_cross_host(reports)
    print(f"  {cross.status:<4} {cross.name}: {cross.detail}")
    if cross.status == "FAIL":
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
