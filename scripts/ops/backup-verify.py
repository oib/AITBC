#!/usr/bin/env python3
"""Restore-check a nightly aitbc-backup set, in scratch, read-only.

C's restore drill proved the backups restore by hand; nothing checks it
nightly. This script replays the drill for a whole generation:

- ``chain_*.db.gz``     sqlite3 ``.dump`` text -> rebuild via
                        ``zcat | sqlite3``, then ``PRAGMA integrity_check``
                        plus alembic head and row counts vs a baseline file.
- ``postgres_*.sql.gz`` plain-SQL ``pg_dump`` -> gunzip, require a pg_dump
                        header, list the roles in ``OWNER TO`` clauses.
- ``svc_*.gz``          binary ``.backup`` copies -> gunzip, open as sqlite,
                        ``PRAGMA integrity_check``.

The backup set is only read; all writes go to a scratch dir (default
``/var/tmp/backup-verify-<pid>``) which is removed at the end.

Exit codes: 0 clean, 1 at least one artefact failed, 2 unreadable input.

Usage:
    backup-verify.py [--set DIR] [--base /var/backups/aitbc]
                     [--baseline roles-baseline.json]
                     [--textfile /path/backup_verify.prom] [--scratch DIR]
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import gzip
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

OWNER_RE = re.compile(r"OWNER TO\s+\"?([A-Za-z0-9_]+)\"?;", re.IGNORECASE)


def _log(msg: str) -> None:
    print(f"backup-verify: {msg}")


def newest_set(base: Path) -> Path | None:
    candidates = sorted(p for p in base.iterdir() if p.is_dir())
    return candidates[-1] if candidates else None


def _sqlite(path: Path, sql: str) -> str:
    return subprocess.run(
        ["sqlite3", "-readonly", str(path), sql],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    ).stdout.strip()


def check_chain_dump(gz: Path, scratch: Path) -> list[str]:
    """Rebuild a .dump text export and integrity-check it.

    An aborted dump is a valid gzip of a truncated export: sqlite3 exits 0
    on it, the tail is "ROLLBACK; -- due to errors", and the rebuilt db is
    empty and integrity-clean — which used to report CLEAN on a broken
    snapshot (#910). Require the COMMIT trailer, reject the ROLLBACK one,
    and prove the rebuilt database actually holds blocks.
    """
    errors: list[str] = []
    dest = scratch / (gz.name.removesuffix(".gz"))
    with gzip.open(gz, "rb") as src:
        dump = src.read()
    tail = dump.decode("utf-8", errors="replace").rstrip().splitlines()[-1:] or [""]
    if any(line.startswith("ROLLBACK") for line in tail):
        return [f"{gz.name}: dump aborted with errors (ROLLBACK trailer)"]
    if b"COMMIT;" not in dump:
        errors.append(f"{gz.name}: dump has no COMMIT trailer (truncated?)")
    build = subprocess.run(
        ["sqlite3", str(dest)],
        input=dump,
        capture_output=True,
        timeout=300,
        check=False,
    )
    if build.returncode != 0:
        return [f"{gz.name}: rebuild failed: {build.stderr.decode(errors='replace').strip()[:120]}"]
    if _sqlite(dest, "PRAGMA integrity_check;") != "ok":
        errors.append(f"{gz.name}: integrity_check not ok")
    blocks = _sqlite(
        dest,
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name IN ('block','blocks');",
    )
    if blocks != "1":
        errors.append(f"{gz.name}: no block table in rebuilt db")
    else:
        count = _sqlite(dest, "SELECT COUNT(*) FROM blocks;") or _sqlite(dest, "SELECT COUNT(*) FROM block;")
        if not count.isdigit() or int(count) == 0:
            errors.append(f"{gz.name}: rebuilt db holds zero blocks")
    return errors


def check_svc_dump(gz: Path, scratch: Path) -> list[str]:
    """Binary .backup copies: gunzip, open as sqlite."""
    dest = scratch / (gz.name.removesuffix(".gz"))
    try:
        with gzip.open(gz, "rb") as src, open(dest, "wb") as out:
            out.write(src.read())
    except Exception as e:  # noqa: BLE001 - report, don't crash
        return [f"{gz.name}: gunzip failed: {e}"]
    if _sqlite(dest, "PRAGMA integrity_check;") != "ok":
        return [f"{gz.name}: integrity_check not ok"]
    return []


def check_pg_dump(gz: Path) -> tuple[list[str], list[str]]:
    """Parse a pg_dump header and collect OWNER TO roles."""
    try:
        head = gzip.open(gz, "rt", encoding="utf-8", errors="replace").read(65536)
    except Exception as e:  # noqa: BLE001
        return [f"{gz.name}: unreadable: {e}"], []
    if "PostgreSQL database dump" not in head:
        return [f"{gz.name}: no pg_dump header"], []
    roles = sorted(set(OWNER_RE.findall(head)))
    return [], roles


def alembic_head(db: Path) -> str | None:
    try:
        return _sqlite(db, "SELECT version_num FROM alembic_version;") or None
    except Exception:  # noqa: BLE001
        return None


def row_counts(db: Path, tables: list[str]) -> dict[str, int]:
    # Table names come from the operator-controlled baseline file only.
    return {t: int(_sqlite(db, f"SELECT COUNT(*) FROM {t};") or 0) for t in tables}  # nosec B608


_SET_TS = re.compile(r"(\d{8})_(\d{6})")


def _set_age_hours(set_dir: Path) -> float | None:
    """Age of a generation dir from its YYYYMMDD_HHMMSS name; None if unnamed."""
    m = _SET_TS.search(set_dir.name)
    if not m:
        return None
    ts = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    return (datetime.now(UTC) - ts).total_seconds() / 3600


def verify_set(
    set_dir: Path, scratch: Path, baseline: dict | None, max_age_hours: float | None = 36
) -> tuple[list[str], dict]:
    scratch.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    report: dict = {"set": set_dir.name, "chain": [], "svc": [], "pg": {}}
    age = _set_age_hours(set_dir)
    report["age_hours"] = age
    if max_age_hours is not None and age is not None and age > max_age_hours:
        errors.append(f"{set_dir.name}: backup set is {age:.0f}h old (max {max_age_hours}h)")
    for gz in sorted(set_dir.glob("chain_*.db.gz")):
        errs = check_chain_dump(gz, scratch)
        db = scratch / gz.name.removesuffix(".gz")
        entry = {"name": gz.name, "ok": not errs}
        if db.exists() and not errs:
            head = alembic_head(db)
            if head:
                entry["alembic_head"] = head
            if baseline and gz.name in baseline:
                counts = row_counts(db, baseline[gz.name])
                bad = {t: c for t, c in counts.items() if c < baseline[gz.name][t]}
                if bad:
                    errs.append(f"{gz.name}: row counts below baseline {bad}")
                entry["rows"] = counts
        report["chain"].append(entry)
        errors.extend(errs)
    for gz in sorted(set_dir.glob("svc_*.gz")):
        errs = check_svc_dump(gz, scratch)
        report["svc"].append({"name": gz.name, "ok": not errs})
        errors.extend(errs)
    for gz in sorted(set_dir.glob("postgres_*.sql.gz")):
        errs, roles = check_pg_dump(gz)
        report["pg"][gz.name] = {"ok": not errs, "roles": roles}
        errors.extend(errs)
    # An empty newest set must not read CLEAN: no chain dump means the backup
    # run itself never produced one — that is a failure, not "nothing found"
    # (#911).
    if not report["chain"]:
        errors.append(f"{set_dir.name}: no chain_*.db.gz artifacts in the newest set")
    return errors, report


def _write_textfile(path: Path, ok: int, report: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        "# HELP aitbc_backup_verify_success Last restore-check result (1=ok)\n"
        "# TYPE aitbc_backup_verify_success gauge\n"
        f'aitbc_backup_verify_success{{set="{report["set"]}"}} {ok}\n'
        "# TYPE aitbc_backup_verify_artifacts gauge\n"
        f'aitbc_backup_verify_artifacts{{set="{report["set"]}"}} '
        f"{len(report['chain']) + len(report['svc']) + len(report['pg'])}\n"
        "# TYPE aitbc_backup_verify_age_hours gauge\n"
        f'aitbc_backup_verify_age_hours{{set="{report["set"]}"}} '
        f"{report['age_hours'] if report.get('age_hours') is not None else 'nan'}\n"
    )
    os.replace(tmp, path)


def main() -> int:
    ap = argparse.ArgumentParser(description="Restore-check a nightly backup set")
    ap.add_argument("--set", type=Path, help="backup generation dir (default: newest under --base)")
    ap.add_argument("--base", type=Path, default=Path("/var/backups/aitbc"))
    ap.add_argument("--baseline", type=Path, help="JSON {artifact: {table: min_rows}}")
    ap.add_argument("--textfile", type=Path, help="node_exporter textfile output")
    ap.add_argument(
        "--max-age",
        type=float,
        default=36,
        metavar="HOURS",
        help="fail when the newest set's timestamp is older than this (default: 36)",
    )
    ap.add_argument("--scratch", type=Path, help="scratch dir (default: /var/tmp/backup-verify-<pid>)")
    args = ap.parse_args()

    set_dir = args.set or (newest_set(args.base) if args.base.is_dir() else None)
    if set_dir is None or not set_dir.is_dir():
        _log(f"cannot read a backup set (base={args.base})")
        return 2

    baseline = json.loads(args.baseline.read_text()) if args.baseline else None
    scratch_ctx = (
        tempfile.TemporaryDirectory(prefix="backup-verify-", dir=args.scratch.parent if args.scratch else None)
        if args.scratch is None
        else None
    )
    if args.scratch is not None:
        # A user-supplied dir may hold other files — rebuild inside an
        # mkdtemp child and delete only that child, never the dir itself
        # (#912). The old code rm -rf'd the whole --scratch dir.
        args.scratch.mkdir(parents=True, exist_ok=True)
        scratch = Path(tempfile.mkdtemp(prefix="backup-verify-", dir=args.scratch))
    else:
        scratch = Path(scratch_ctx.name)  # type: ignore[union-attr]
    try:
        errors, report = verify_set(set_dir, scratch, baseline, args.max_age)
    finally:
        if scratch_ctx is None and args.scratch and not os.environ.get("BV_KEEP_SCRATCH"):
            subprocess.run(["rm", "-rf", str(scratch)], check=False)

    ok = 0 if errors else 1
    for e in errors:
        _log(f"FAIL {e}")
    _log(
        f"{set_dir.name}: {len(report['chain'])} chain dumps, "
        f"{len(report['svc'])} svc dumps, {len(report['pg'])} pg dumps checked; "
        + ("CLEAN" if ok else f"{len(errors)} failure(s)")
    )
    if args.textfile:
        _write_textfile(args.textfile, ok, report)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
