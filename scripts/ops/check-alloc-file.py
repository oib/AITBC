#!/usr/bin/env python3
"""check-alloc-file.py — check a bc-2 allocation file against the decided figures (RESET-ALLOC-FILE-1).

Runbook A2 requires "file parses; totals match the operator's final figures".
``build-genesis.py`` enforces file *shape* (JSON list, EIP-55 addresses, no
duplicates, integer balances) and optionally a caller-supplied total, but
nothing knows the decided figures — this script is that check. Read-only by
construction: the only filesystem access is ``open()`` on the two input files.

Inputs
------
--allocations FILE   candidate file in builder format: JSON list of
                     ``{address, balance, nonce?}`` in base units. The real
                     operator file drops in unchanged.
--classes FILE       optional class manifest (JSON object) mapping each
                     account class to its public addresses:

                       {
                         "treasury": "0x…",
                         "service_floats": {"aiengine": "0x…", …},
                         "executors": ["0x…", "0x…"],
                         "authorities": {"bond_slash": "0x…", …},
                         "ops_float": "0x…",
                         "retired": ["0x…", "0x…", "0x…"],
                         "faucet": "0x…"
                       }

                     Dict values may also be bare lists of addresses. The
                     two bond accounts are NOT manifest entries — the script
                     derives them itself (env override + keccak fallback,
                     mirroring ``aitbc_chain.database._bond_*_address``).
--require-classes    strict mode for the runbook read: refuse to run when
                     --classes is absent, so a vacuous address-independent
                     pass cannot count as the A2 check.

Without --classes the script still checks every address-independent
property (parse, shape, checksum, duplicates, integer balances, total
supply, exactly one treasury-amount row, bond accounts present at 0) and
reports class checks as skipped.

Output: a per-class table plus PASS/FAIL. Prints public addresses and
amounts only. Exit status: 0 = PASS, 1 = FAIL or unreadable input,
2 = usage error.

    venv/bin/python scripts/ops/check-alloc-file.py \
        --allocations allocations.json --classes classes.json --require-classes
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Decided allocation figures — operator-confirmed final 20 Oct 2026.
# ONE EDIT POINT: every number the check asserts lives in this dict. A mirror
# test (tests/unit/test_check_alloc_file.py) asserts the same numbers still
# appear in docs/deployment/bc2-reset-runbook.md's A2 row, so a figure change
# is a single edit here — never scattered through code.
# ---------------------------------------------------------------------------
PARAMS: dict[str, int] = {
    "units_per_ait": 36_000_000,
    "treasury_ait": 100_000_000,
    "float_ait": 256,  # floats outside treasury
    "service_accounts": 11,
    "service_ait_each": 1,
    "retired_accounts": 3,
    "faucet_ait": 0,
    "bond_accounts": 2,
    "supply_ait": 100_000_256,
}

UNITS_PER_AIT = PARAMS["units_per_ait"]
TREASURY_UNITS = PARAMS["treasury_ait"] * UNITS_PER_AIT
FLOAT_UNITS = PARAMS["float_ait"] * UNITS_PER_AIT
SERVICE_UNITS = PARAMS["service_ait_each"] * UNITS_PER_AIT
EXPECTED_TOTAL_UNITS = PARAMS["supply_ait"] * UNITS_PER_AIT

# Manifest keys that name one address (str) vs a collection (list or dict).
_SINGLE_CLASSES = ("treasury", "ops_float", "faucet")
_LIST_CLASSES = ("executors", "retired")
_DICT_CLASSES = ("service_floats", "authorities")
# Classes whose balances belong to the 256-AIT float band outside treasury.
_FLOAT_CLASSES = ("service_floats", "executors", "authorities", "ops_float")
# Classes whose members must sit at balance 0 (bond is derived, not listed).
_ZERO_CLASSES = ("retired", "faucet")


def _chain_modules():
    """Lazy imports — keeps this file importable under pytest on a host where
    aitbc_chain/eth_utils are not already on sys.path."""
    repo_root = Path(__file__).resolve().parents[2]
    for p in (str(repo_root), str(repo_root / "apps" / "blockchain-node" / "src")):
        if p not in sys.path:
            sys.path.insert(0, p)
    from aitbc.crypto.signature_recovery import canonical_address
    from eth_utils import keccak

    return canonical_address, keccak


def _bond_addresses() -> list[str]:
    """The two init-created bond accounts — env override with the keccak
    fallback, mirroring ``aitbc_chain.database._bond_escrow_address`` /
    ``_bond_burn_address`` (database.py:389-403). Derived, never read from
    the class manifest."""
    canonical_address, keccak = _chain_modules()
    out = []
    for env_name, seed in (("BOND_ESCROW_ADDRESS", b"aitbc.bond.escrow"), ("BOND_BURN_ADDRESS", b"aitbc.bond.burn")):
        env = os.getenv(env_name, "")
        out.append(canonical_address(env) if env else canonical_address("0x" + keccak(seed).hex()[:40]))
    return out


def _load_json(path: str, *, what: str, problems: list[str]) -> Any:
    try:
        return json.loads(Path(path).read_text())
    except OSError as exc:
        problems.append(f"cannot read {what} at {path}: {exc}")
    except json.JSONDecodeError as exc:
        problems.append(f"{what} at {path} is not valid JSON: {exc}")
    return None


def _checksum(addr: Any) -> str | None:
    """EIP-55 form of ``addr``, or None when malformed/not checksummed —
    the same rule the builder enforces (genesis_builder._require_checksum_address)."""
    canonical_address, _ = _chain_modules()
    try:
        canonical = canonical_address(str(addr or "").strip(), strict=True)
    except Exception:
        return None
    return canonical if canonical == str(addr).strip() else None


def _check_rows(allocs: Any, problems: list[str]) -> dict[str, dict[str, Any]]:
    """Shape + checksum + duplicate checks; returns address -> row for the
    well-formed subset (callers must not trust it when problems exist)."""
    if not isinstance(allocs, list) or not allocs:
        problems.append("allocations file must be a non-empty JSON list")
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for i, alloc in enumerate(allocs):
        if not isinstance(alloc, dict):
            problems.append(f"allocations[{i}]: not an object")
            continue
        address = _checksum(alloc.get("address"))
        if address is None:
            problems.append(f"allocations[{i}].address: not an EIP-55 checksummed EVM address: {alloc.get('address')!r}")
            continue
        for field in ("balance", "nonce"):
            value = alloc.get(field, 0)
            if isinstance(value, bool) or not isinstance(value, int):
                problems.append(f"allocations[{i}].{field}: not an integer: {value!r}")
                continue
            if value < 0:
                problems.append(f"allocations[{i}].{field}: negative: {value}")
        if address.lower() in rows:
            problems.append(f"allocations[{i}].address: duplicated address {address}")
        else:
            rows[address.lower()] = {
                "address": address,
                "balance": alloc.get("balance"),
                "nonce": alloc.get("nonce", 0),
            }
    return rows


def _manifest_addresses(classes: dict[str, Any], problems: list[str]) -> dict[str, dict[str, str]]:
    """Flatten the manifest to {class: {lower-address: checksummed}} with a
    checksum check on every manifest address too."""
    out: dict[str, dict[str, str]] = {}
    for cls in _SINGLE_CLASSES + _LIST_CLASSES + _DICT_CLASSES:
        raw = classes.get(cls)
        if raw is None:
            out[cls] = {}
            continue
        items = [raw] if cls in _SINGLE_CLASSES else (list(raw.values()) if isinstance(raw, dict) else list(raw))
        entries: dict[str, str] = {}
        for item in items:
            addr = _checksum(item)
            if addr is None:
                problems.append(f"classes.{cls}: not an EIP-55 checksummed EVM address: {item!r}")
            elif addr.lower() in entries:
                problems.append(f"classes.{cls}: duplicated address {addr}")
            else:
                entries[addr.lower()] = addr
        out[cls] = entries
    return out


def _fmt(units: Any) -> str:
    """units -> ``N units (M AIT)``; never prints anything but amounts."""
    if not isinstance(units, int):
        return repr(units)
    whole, rem = divmod(units, UNITS_PER_AIT)
    return f"{units} units ({whole}.{rem:08d} AIT)" if rem else f"{units} units ({whole} AIT)"


def _check_independent(rows: dict[str, dict[str, Any]], problems: list[str], table: list[list[str]]) -> None:
    """Address-independent checks: supply, treasury-amount uniqueness, bond
    accounts derived and present at 0."""
    total = sum(r["balance"] for r in rows.values() if isinstance(r["balance"], int))
    table.append(["supply", "1 total", _fmt(total), "PASS" if total == EXPECTED_TOTAL_UNITS else "FAIL"])
    if total != EXPECTED_TOTAL_UNITS:
        off = total - EXPECTED_TOTAL_UNITS
        problems.append(f"allocation total {_fmt(total)} != expected {_fmt(EXPECTED_TOTAL_UNITS)} (off by {off:+d} units)")

    treasury_rows = [r for r in rows.values() if r["balance"] == TREASURY_UNITS]
    ok = len(treasury_rows) == 1
    table.append(
        [
            "treasury",
            "exactly 1 row at treasury amount",
            f"{len(treasury_rows)} row(s)",
            "PASS" if ok else "FAIL",
        ]
    )
    if not ok:
        problems.append(
            f"{len(treasury_rows)} allocation row(s) at the treasury amount {_fmt(TREASURY_UNITS)}, want exactly 1"
        )

    bonds = _bond_addresses()
    missing = [a for a in bonds if a.lower() not in rows]
    nonzero = [
        a
        for a in bonds
        if a.lower() in rows and isinstance(rows[a.lower()]["balance"], int) and rows[a.lower()]["balance"] != 0
    ]
    ok = not missing and not nonzero
    table.append(
        [
            "bond",
            f"{PARAMS['bond_accounts']} derived accounts at 0",
            f"present={PARAMS['bond_accounts'] - len(missing)} nonzero={len(nonzero)}",
            "PASS" if ok else "FAIL",
        ]
    )
    for a in missing:
        problems.append(f"bond account {a} missing from the allocation set (init rows win — must exist at balance 0)")
    for a in nonzero:
        problems.append(f"bond account {a} has balance {_fmt(rows[a.lower()]['balance'])}, want 0")


def _row_balance(rows: dict[str, dict[str, Any]], address: str) -> int | None:
    """The integer balance of ``address``'s row, or None (absent or
    malformed — the row-level check owns the malformed flag)."""
    row = rows.get(address.lower())
    return row["balance"] if row is not None and isinstance(row["balance"], int) else None


def _check_treasury(
    rows: dict[str, dict[str, Any]], treasury: dict[str, str], problems: list[str], table: list[list[str]]
) -> None:
    ok = len(treasury) == 1
    if not ok:
        problems.append(f"classes.treasury lists {len(treasury)} addresses, want exactly 1")
    else:
        t_addr = next(iter(treasury.values()))
        balance = _row_balance(rows, t_addr)
        ok = balance == TREASURY_UNITS
        if balance is None and t_addr.lower() not in rows:
            problems.append(f"treasury {t_addr} absent from the allocation file")
        elif balance != TREASURY_UNITS:
            problems.append(f"treasury {t_addr} balance {_fmt(balance)} != {_fmt(TREASURY_UNITS)}")
    table.append(["treasury", "1 address at treasury amount", f"{len(treasury)} listed", "PASS" if ok else "FAIL"])


def _check_service(
    rows: dict[str, dict[str, Any]], service: dict[str, str], problems: list[str], table: list[list[str]]
) -> None:
    """Service floats: exact count, each at the per-account amount."""
    missing = [a for a in service.values() if a.lower() not in rows]
    wrong = [a for a in service.values() if (b := _row_balance(rows, a)) is not None and b != SERVICE_UNITS]
    ok = len(service) == PARAMS["service_accounts"] and not missing and not wrong
    table.append(
        [
            "service_floats",
            f"{PARAMS['service_accounts']} @ {_fmt(SERVICE_UNITS)}",
            f"listed={len(service)} missing={len(missing)} wrong={len(wrong)}",
            "PASS" if ok else "FAIL",
        ]
    )
    if len(service) != PARAMS["service_accounts"]:
        problems.append(f"classes.service_floats lists {len(service)} addresses, want {PARAMS['service_accounts']}")
    for a in missing:
        problems.append(f"service account {a} absent from the allocation file")
    for a in wrong:
        problems.append(f"service account {a} balance {_fmt(rows[a.lower()]['balance'])} != {_fmt(SERVICE_UNITS)}")


def _check_presence(
    rows: dict[str, dict[str, Any]], classes: dict[str, dict[str, str]], problems: list[str], table: list[list[str]]
) -> None:
    """Remaining float/retired classes: presence, and the count where a
    figure pins one; balances fold into the band check separately."""
    for cls, want in (
        ("executors", None),
        ("authorities", None),
        ("ops_float", None),
        ("retired", PARAMS["retired_accounts"]),
    ):
        entries = classes[cls]
        missing = [a for a in entries.values() if a.lower() not in rows]
        count_ok = want is None or len(entries) == want
        ok = count_ok and not missing
        label = f"{want} addresses" if want is not None else "present"
        table.append([cls, label, f"listed={len(entries)} missing={len(missing)}", "PASS" if ok else "FAIL"])
        if want is not None and len(entries) != want:
            problems.append(f"classes.{cls} lists {len(entries)} addresses, want {want}")
        for a in missing:
            problems.append(f"{cls} account {a} absent from the allocation file")


def _check_zero_classes(
    rows: dict[str, dict[str, Any]], classes: dict[str, dict[str, str]], problems: list[str], table: list[list[str]]
) -> None:
    """Listed zero-class members must exist at balance 0."""
    for cls in _ZERO_CLASSES:
        entries = classes[cls]
        if not entries:
            table.append([cls, "at 0", "not listed", "SKIP"])
            continue
        missing = [a for a in entries.values() if a.lower() not in rows]
        bad = [a for a in entries.values() if (b := _row_balance(rows, a)) is not None and b != 0]
        ok = not missing and not bad
        table.append(
            [
                cls,
                "all present at 0",
                f"present={len(entries) - len(missing)}/{len(entries)} nonzero={len(bad)}",
                "PASS" if ok else "FAIL",
            ]
        )
        for a in missing:
            problems.append(f"{cls} account {a} absent from the allocation file")
        for a in bad:
            problems.append(f"{cls} account {a} must sit at balance 0, has {_fmt(rows[a.lower()]['balance'])}")


def _check_float_band(
    rows: dict[str, dict[str, Any]], classes: dict[str, dict[str, str]], problems: list[str], table: list[list[str]]
) -> None:
    """Every float-class balance sums to the 256-AIT band outside treasury."""
    float_total = sum(b for cls in _FLOAT_CLASSES for a in classes[cls] if (b := _row_balance(rows, a)) is not None)
    ok = float_total == FLOAT_UNITS
    table.append(["float band", _fmt(FLOAT_UNITS), _fmt(float_total), "PASS" if ok else "FAIL"])
    if not ok:
        problems.append(
            f"float-class total {_fmt(float_total)} != {_fmt(FLOAT_UNITS)} (off by {float_total - FLOAT_UNITS:+d} units)"
        )


def _check_strays(
    rows: dict[str, dict[str, Any]], classes: dict[str, dict[str, str]], problems: list[str], table: list[list[str]]
) -> None:
    """Every allocation must belong to a listed class or a bond account —
    an unclassified funded row is a check failure, not a pass."""
    classified = {low for entries in classes.values() for low in entries}
    classified.update(a.lower() for a in _bond_addresses())
    stray = [r["address"] for low, r in rows.items() if low not in classified]
    table.append(["stray rows", "0", str(len(stray)), "PASS" if not stray else "FAIL"])
    for a in stray:
        problems.append(f"allocation {a} belongs to no listed class or bond account")


def _check_classes(
    rows: dict[str, dict[str, Any]], classes: dict[str, dict[str, str]], problems: list[str], table: list[list[str]]
) -> None:
    """Per-class membership/count/amount checks against the manifest."""
    seen: dict[str, str] = {}
    for cls, entries in classes.items():
        for low, addr in entries.items():
            if low in seen:
                problems.append(f"address {addr} listed in both {seen[low]} and {cls}")
            else:
                seen[low] = cls

    _check_treasury(rows, classes["treasury"], problems, table)
    _check_service(rows, classes["service_floats"], problems, table)
    _check_presence(rows, classes, problems, table)
    _check_zero_classes(rows, classes, problems, table)
    _check_float_band(rows, classes, problems, table)
    _check_strays(rows, classes, problems, table)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--allocations", required=True, help="candidate allocation file: JSON list of {address, balance, nonce?}")
    p.add_argument("--classes", help="class manifest: JSON object mapping classes to public addresses")
    p.add_argument(
        "--require-classes",
        action="store_true",
        help="refuse to run without --classes — the runbook A2 read must not pass vacuously",
    )
    args = p.parse_args(argv)

    if args.require_classes and not args.classes:
        print("refused: --require-classes is set but no --classes manifest was supplied", file=sys.stderr)
        return 2

    problems: list[str] = []
    table: list[list[str]] = []

    allocs = _load_json(args.allocations, what="allocations", problems=problems)
    classes_raw: dict[str, Any] | None = None
    if args.classes:
        classes_raw = _load_json(args.classes, what="classes", problems=problems)
        if classes_raw is not None and not isinstance(classes_raw, dict):
            problems.append("classes file must be a JSON object")
            classes_raw = None

    rows = _check_rows(allocs, problems) if allocs is not None else {}
    _check_independent(rows, problems, table)
    if args.classes:
        classes = _manifest_addresses(classes_raw or {}, problems)
        _check_classes(rows, classes, problems, table)
    else:
        table.append(["class checks", "--classes manifest", "not supplied", "SKIP"])

    width = max(len(row[0]) for row in table)
    for cls, expected, found, verdict in table:
        print(f"  {cls:<{width}}  {verdict:<4}  expected: {expected} | found: {found}")

    if problems:
        print(f"alloc-file check: FAIL ({len(problems)} problem(s))")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("alloc-file check: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
