#!/usr/bin/env python3
"""env-set-plan.py — per-host env-edit plan + anchored verify sheet for the bc-2 env set (RESET-ENVAPPLY-1).

Runbook C3 applies the environment set on every unit of five hosts. This
tool turns `docs/deployment/bc2-environment-set.json` (the structured copy
of the environment-set doc) into:

- `plan`   — the exact list of edits per host (file, name, old status,
             new intent), read-only, reviewable before the human edit step.
- `verify` — a PASS/FAIL sheet comparing the target env files to the set,
             plus `--sheet` to print the anchored greps themselves.

Hard rules
----------
- Never writes an env file (or anything else): the only filesystem access
  is `open(path)` in read mode on `--local` inputs.
- Names are read through `aitbc system env-names` on live hosts
  (names-only by design); `--local DIR` reads a copied directory of env
  files in-process.
- A name's old value is printed only when its row is `class: "public"`
  AND the name passes the secret-name filter below. Everything else —
  `secret`, `operator`, `wiring`, `carry`, and any name that trips the
  filter regardless of its label — is presence-only ("<present>").
- `verify` prints counts and PASS/FAIL only, never a value.
- Live mode (`--host`) is names-only: presence checks via `env-names`
  JSON; no value is ever read over ssh. Literal `NAME=value` verify needs
  `--local` on a collected copy of the host's env files.

Row model (see the JSON's `schema` block):
  op     set | drop | drop-if-matches | keep | none
  scope  carrying | units:<csv> | files:<csv>
  class  public | secret | operator | wiring | carry
  value  scalar | {"<host>": scalar} | "operator-supplied"

  `carrying` rewrites every probed file currently declaring the name —
  it never creates a line. `units:` writes only files exclusive to those
  units' chains (a file shared by two units is never a unit-pin target);
  a name declared only in a shared file is reported as a note for the
  operator, and the write goes to the unit's own `<unit>.env`.

Exit status: 0 = ok / all PASS, 1 = FAIL rows or unreadable inputs,
2 = usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Secret-name filter — mirrors the tokens of the CLI's _field_name_denied
# (cli/aitbc_cli/commands/system.py). Deliberately conservative: a false hit
# only means a value stays presence-only, never that a secret prints.
# ---------------------------------------------------------------------------

_DENY_TOKENS = frozenset(
    {
        "pass",
        "password",
        "passwd",
        "pwd",
        "passphrase",
        "secret",
        "token",
        "key",
        "keys",
        "private",
        "credential",
        "credentials",
        "auth",
        "signing",
        "mnemonic",
        "seed",
        "dsn",
        "url",
        "uri",
        "secrets",
        "passwords",
        "tokens",
        "apikeys",
        "pw",
        "bearer",
        "cookie",
        "cookies",
        "privkey",
        "seedphrase",
        "salt",
    }
)
_DENY_NAMES = frozenset({"private_key", "secret", "password", "token", "mnemonic", "seed", "key", "api_key"})
_DENY_NORMALIZED = frozenset({"privatekey", "apikey", "secretkey", "passphrase", "passwd", "credential", "credentials"})
_DENY_SUFFIXES = (
    "password",
    "passwd",
    "passphrase",
    "pwd",
    "secret",
    "token",
    "private",
    "credential",
    "credentials",
    "mnemonic",
    "seed",
    "dsn",
    "secrets",
    "passwords",
    "tokens",
    "apikeys",
    "cookie",
    "cookies",
    "bearer",
    "authorization",
    "privkey",
    "seedphrase",
)
_DENY_TAIL = ("_url", "_uri", "_dsn")
_DENY_KEY_PREFIXES = ("private", "secret", "api", "auth", "signing", "access")
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _name_tokens(name: str) -> list[str]:
    return [t.lower() for t in re.split(r"[_-]+", _CAMEL_BOUNDARY.sub("_", name)) if t]


def name_looks_secret(name: str) -> bool:
    lowered = name.lower()
    normalized = lowered.replace("-", "").replace("_", "")
    tokens = _name_tokens(name)
    return (
        lowered in _DENY_NAMES
        or normalized in _DENY_NORMALIZED
        or lowered.endswith(_DENY_TAIL)
        or any(t in _DENY_TOKENS for t in tokens)
        or (normalized.endswith("key") and normalized[:-3] in _DENY_KEY_PREFIXES)
        or (len(tokens) == 1 and normalized.endswith(_DENY_SUFFIXES))
    )


def printable(row: dict[str, Any]) -> bool:
    """A row's host values may be shown only when explicitly public AND the
    name itself passes the secret filter — a mislabeled secret-looking name
    stays presence-only no matter what the row claims."""
    return row.get("class") == "public" and not name_looks_secret(row["name"])


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

_ASSIGNMENT = re.compile(r"^([A-Z_][A-Z0-9_]*)=(.*)$")


def read_env_file(path: Path) -> dict[str, str]:
    """Anchored name -> value map of one env file. Read mode only."""
    out: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = _ASSIGNMENT.match(line.rstrip("\n"))
                if m:
                    out[m.group(1)] = m.group(2)
    except OSError:
        pass
    return out


class HostView:
    """What the tool knows about one host's env files.

    files: path -> {name: value|None}  (None = names-only probe, live mode)
    unit_files: unit -> [paths] in chain order (live mode only; local mode
    synthesizes it from filenames that contain a unit name)
    """

    def __init__(self) -> None:
        self.files: dict[str, dict[str, str | None]] = {}
        self.unit_files: dict[str, list[str]] = {}
        self.unprobed_note: str | None = None

    def add_file(self, path: str, names_values: dict[str, str | None]) -> None:
        self.files.setdefault(path, {}).update(names_values)

    def all_paths(self) -> list[str]:
        return sorted(self.files)

    def carriers(self, name: str) -> list[str]:
        return sorted(p for p, names in self.files.items() if name in names)

    def presence(self, path: str, name: str) -> bool:
        return name in self.files.get(path, {})

    def value(self, path: str, name: str) -> str | None:
        return self.files.get(path, {}).get(name)


def load_local(directory: Path, units: list[str]) -> HostView:
    """Read every *.env in DIR. Values are kept — this is the operator's own
    copy of the env files, so `plan` may show them for public rows."""
    view = HostView()
    env_files = sorted(p for p in directory.iterdir() if p.suffix == ".env")
    if not env_files:
        raise SystemExit(f"no *.env files under {directory}")
    for path in env_files:
        view.add_file(str(path), dict(read_env_file(path)))
    for unit in units:
        owned = [str(p) for p in env_files if unit in p.name]
        if owned:
            view.unit_files[unit] = sorted(owned)
    return view


def _ssh(host: str, argv: list[str], timeout: int = 30) -> str:
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, *argv]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 10, check=False)
    if r.returncode != 0:
        raise SystemExit(f"ssh {host}: {r.stderr.strip() or r.stdout.strip() or 'failed'}")
    return r.stdout


def probe_host(host: str, units: list[str], aitbc_path: str) -> HostView:
    """Names-only live read: `aitbc --output json system env-names --service`
    per unit — the unit -> file map plus every declared name. Never a value."""
    view = HostView()
    for unit in units:
        try:
            out = _ssh(host, [aitbc_path, "--output", "json", "system", "env-names", "--service", unit])
        except SystemExit as e:
            print(f"note: {unit}: probe failed ({e})", file=sys.stderr)
            continue
        try:
            report = json.loads(out)
        except json.JSONDecodeError:
            print(f"note: {unit}: env-names output was not JSON — skipped", file=sys.stderr)
            continue
        files_in_chain: list[str] = []
        for entry in report if isinstance(report, list) else []:
            path = entry.get("file")
            if not path or entry.get("missing"):
                continue
            files_in_chain.append(path)
            view.add_file(path, dict.fromkeys(entry.get("names", [])))
        if files_in_chain:
            view.unit_files[unit] = files_in_chain
    view.unprobed_note = "files not in any probed unit's chain are not covered; extend --units"
    return view


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------


def _row_value_for(row: dict[str, Any], host: str) -> str | None:
    v = row.get("value")
    if isinstance(v, dict):
        return v.get(host)  # missing host key -> row does not apply
    return v if isinstance(v, str) else None


def _is_operator_supplied(row: dict[str, Any]) -> bool:
    return row.get("value") == "operator-supplied" or row.get("class") in {"operator", "secret", "wiring"}


def _unit_exclusive(view: HostView, unit: str) -> list[str]:
    """Files in `unit`'s chain that no other probed unit shares."""
    chain = view.unit_files.get(unit, [])
    others: set[str] = set()
    for u, paths in view.unit_files.items():
        if u != unit:
            others.update(paths)
    return [p for p in chain if p not in others]


def _own_env_file(view: HostView, unit: str) -> str | None:
    exclusive = _unit_exclusive(view, unit)
    for p in exclusive:
        if Path(p).stem == unit:
            return p
    return exclusive[-1] if exclusive else None


def resolve_targets(view: HostView, row: dict[str, Any]) -> tuple[list[str], list[str]]:
    """(target files, notes) for one row."""
    scope = row.get("scope", "carrying")
    name = row["name"]
    notes: list[str] = []
    if scope.startswith("files:"):
        return [p for p in scope[6:].split(",") if p], notes
    if scope.startswith("units:"):
        targets: list[str] = []
        for unit in scope[6:].split(","):
            exclusive = _unit_exclusive(view, unit)
            chain = view.unit_files.get(unit, [])
            carrying_here = [p for p in exclusive if name in view.files.get(p, {})]
            shared_here = [p for p in chain if p not in exclusive and name in view.files.get(p, {})]
            if shared_here:
                notes.append(
                    f"{unit}: {name} is declared in shared file(s) {', '.join(shared_here)} — "
                    "a shared write would leak into other units; operator moves the pin"
                )
            targets.extend(carrying_here)
            if not carrying_here:
                own = _own_env_file(view, unit)
                if own is None:
                    notes.append(f"{unit}: no unit-exclusive env file probed — cannot place {name}")
                else:
                    targets.append(own)
        return sorted(set(targets)), notes
    # carrying
    return view.carriers(name), notes


_ACTION = {"set": "EDIT", "drop": "DROP", "drop-if-matches": "DROP", "keep": "KEEP", "none": "SKIP"}


def _status_mark(present: bool, old: str | None, shown: bool) -> str:
    if not present:
        return "<unset>"
    if shown and old is not None:
        return str(old)
    return "<present>"


def _plan_target_line(view: HostView, row: dict[str, Any], path: str, host: str) -> tuple[str | None, int]:
    """One plan line for row x file — (line, extra-issues)."""
    name, op = row["name"], row.get("op", "set")
    present = view.presence(path, name)
    old = view.value(path, name)
    shown_value = _status_mark(present, old, printable(row))
    want = _row_value_for(row, host)
    prefix = f"  {path}\n    {name:<40}"
    if op == "drop-if-matches":
        match = row.get("match", "")
        if old is None and present:
            return f"{prefix} <present>          drop-if-matches {match} (live check pending)", 0
        if present and str(old).startswith(match):
            return f"{prefix} {shown_value:<20} DROP (matches {match})", 0
        return None, 0
    if op == "drop":
        return f"{prefix} {shown_value:<20} DROP", 0
    if op == "keep":
        return f"{prefix} {shown_value:<20} KEEP", 0
    # set
    if want is None and not _is_operator_supplied(row):
        return f"{prefix} {shown_value:<20} — (no value for host {host})", 1
    new_mark = "operator-supplied" if _is_operator_supplied(row) else (want if want is not None else "—")
    if _is_operator_supplied(row):
        action = "OPERATOR" if present else "OPERATOR-ADD"
    elif present and old is not None and want is not None and str(old) == want:
        action = "SAME"
    else:
        action = "EDIT" if present else "ADD"
    return f"{prefix} {shown_value:<20} -> {new_mark}   {action}", 0


def _plan_row(view: HostView, row: dict[str, Any], host: str) -> tuple[list[str], list[str], int]:
    """(lines, owed-names, issues) for one row."""
    name, op = row["name"], row.get("op", "set")
    targets, notes = resolve_targets(view, row)
    lines = [f"  note: {n}" for n in notes]
    issues = len(notes)
    owed = [name] if _is_operator_supplied(row) and op == "set" else []
    if op == "none":
        return lines, owed, issues
    if not targets:
        if op in {"drop", "drop-if-matches"}:
            return lines, owed, issues  # nothing carries it — already satisfied
        new_mark = "operator-supplied" if _is_operator_supplied(row) else _row_value_for(row, host)
        verb = "keep -> FAIL-if-still-absent" if op == "keep" else f"-> {new_mark}   ADD? (no target file resolved)"
        mark = "<absent>" if op == "keep" else "<unset>"
        lines.append(f"  {name:<42} {mark:<20} {verb}")
        return lines, owed, issues + 1
    for path in targets:
        line, extra = _plan_target_line(view, row, path, host)
        if line:
            lines.append(line)
        issues += extra
    return lines, owed, issues


def plan(view: HostView, rows: list[dict[str, Any]], host: str) -> tuple[list[str], int]:
    """Per-host plan lines. Prints old values only where `printable(row)` and
    the live mode actually read one (local inputs only — live is names-only)."""
    out: list[str] = [f"== {host} =="]
    issues = 0
    owed: list[str] = []
    for row in rows:
        if row.get("hosts") and host not in row["hosts"]:
            continue
        lines, row_owed, row_issues = _plan_row(view, row, host)
        out.extend(lines)
        owed.extend(row_owed)
        issues += row_issues
    if owed:
        out.append("  -- operator inputs still owed (presence-only, written at C3):")
        for n in sorted(set(owed)):
            out.append(f"    {n}")
    if view.unprobed_note:
        out.append(f"  note: {view.unprobed_note}")
    return out, issues


def _verify_target(view: HostView, row: dict[str, Any], path: str, host: str) -> tuple[str | None, bool]:
    """One PASS/FAIL line for row x file — (line, ok)."""
    name, op = row["name"], row.get("op", "set")
    present = view.presence(path, name)
    old = view.value(path, name)
    if op in {"drop", "drop-if-matches"}:
        if op == "drop-if-matches" and old is not None:
            ok = not str(old).startswith(row.get("match", ""))
        else:
            ok = not present
        return f"  {'PASS' if ok else 'FAIL'} {path} {name} count={0 if ok else 1} expect-absent", ok
    if op == "keep" or _is_operator_supplied(row):
        return f"  {'PASS' if present else 'FAIL'} {path} {name} present={int(present)}", present
    want = _row_value_for(row, host)
    if want is None:
        return None, True  # no expected value for this host
    if old is None:
        # names-only probe — literal verify needs the local copy
        return (
            f"  {'PASS' if present else 'FAIL'} {path} {name} present={int(present)} "
            "(presence-level: live read is names-only)",
            present,
        )
    ok = str(old) == want
    return f"  {'PASS' if ok else 'FAIL'} {path} {name} literal-match={int(ok)}", ok


def verify(view: HostView, rows: list[dict[str, Any]], host: str) -> tuple[list[str], int]:
    """PASS/FAIL per row x target — counts and presence only, never a value."""
    out: list[str] = [f"== {host} =="]
    fails = 0
    for row in rows:
        name, op = row["name"], row.get("op", "set")
        if row.get("hosts") and host not in row["hosts"] or op == "none":
            continue
        targets, _notes = resolve_targets(view, row)
        if not targets:
            ok = op in {"drop", "drop-if-matches"}
            tail = "absent everywhere (0 files)" if ok else "no target file resolved (0 carriers)"
            out.append(f"  {'PASS' if ok else 'FAIL'} {name:<42} {tail}")
            fails += 0 if ok else 1
            continue
        for path in targets:
            line, ok = _verify_target(view, row, path, host)
            if line:
                out.append(line)
            fails += 0 if ok else 1
    return out, fails


def sheet(view: HostView, rows: list[dict[str, Any]], host: str) -> list[str]:
    """The anchored greps themselves — for the operator to run/audit."""
    out: list[str] = [f"== {host} =="]
    for row in rows:
        name, op = row["name"], row.get("op", "set")
        if row.get("hosts") and host not in row["hosts"]:
            continue
        if op == "none":
            continue
        targets, _ = resolve_targets(view, row)
        for path in targets:
            if op == "set" and not _is_operator_supplied(row):
                want = _row_value_for(row, host)
                if want is not None:
                    out.append(f"  grep -c '^{name}={want}$' {path}   # expect 1")
                else:
                    out.append(f"  grep -c '^{name}=' {path}   # expect >=1")
            else:
                expect = ">=1" if op in {"set", "keep"} else "0"
                out.append(f"  grep -c '^{name}=' {path}   # expect {expect}")
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _load_set(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(f"cannot read the structured env set {path}: {e}") from e
    if not isinstance(data.get("rows"), list):
        raise SystemExit(f"{path}: no 'rows' list")
    return data


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="env-set-plan.py",
        description="Per-host env-edit plan + anchored verify sheet for the bc-2 env set. Read-only.",
    )
    ap.add_argument("mode", choices=["plan", "verify"], help="plan = proposed edits; verify = PASS/FAIL sheet")
    ap.add_argument("--set", dest="set_path", required=True, type=Path, help="structured env set JSON")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--local", type=Path, help="directory holding a copy of the host's env files")
    src.add_argument("--host", help="live host: names-only reads via `aitbc system env-names` over ssh")
    ap.add_argument("--units", help="comma list overriding the JSON's unit list")
    ap.add_argument("--aitbc-path", default="/opt/aitbc/venv/bin/aitbc", help="remote aitbc binary for --host")
    ap.add_argument("--name", dest="host_name", help="host label for --local output (default: 'local')")
    ap.add_argument("--sheet", action="store_true", help="verify mode: also print the anchored greps")
    args = ap.parse_args(argv)

    spec = _load_set(args.set_path)
    units = args.units.split(",") if args.units else list(spec.get("units", []))
    rows = spec["rows"]

    if args.local:
        view = load_local(args.local, units)
        host = args.host_name or "local"
    else:
        view = probe_host(args.host, units, args.aitbc_path)
        host = args.host

    rc = 0
    if args.mode == "plan":
        lines, issues = plan(view, rows, host)
        print("\n".join(lines))
        print(f"-- plan notes: {issues}")
    else:
        lines, fails = verify(view, rows, host)
        if args.sheet:
            print("\n".join(sheet(view, rows, host)))
            print()
        print("\n".join(lines))
        print(f"-- verify: {'PASS' if fails == 0 else 'FAIL'} ({fails} failing row(s))")
        rc = 1 if fails else 0
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
