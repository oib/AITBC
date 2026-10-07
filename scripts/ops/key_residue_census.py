#!/usr/bin/env python3
"""Scan files for retired addresses and retired key material — read-only.

KR-7 census tool (plan: TOPOLOGY/2026-10-07-kr7-residue-recensus-plan.md).
Walks the given files/directories and reports, per match: file, line number,
variable name, and *which retired address* matched — never the matched value.
It also derives the public address of every ``0x``-prefixed 64-hex literal and
every ``*_PRIVATE_KEY``/``*_KEY`` 64-hex value it finds and reports only the
derived address plus whether it is in the retired list — never the key.

Safety properties:

- Prints only variable names, file paths, line numbers, file modes and
  **public addresses**. Key text is never emitted.
- Never writes to disk or modifies anything it reads.
- Refuses to follow symlinks whose target is outside the given roots; the
  refusal itself is reported.
- Skips binary files (NUL byte in the first block).

Output (one finding per line, parseable):

    FILE <path> mode=0o644
    HIT-ADDR <path>:<line> var=<VAR|-> address=<retired-address>
    HIT-KEY <path>:<line> var=<VAR|-> derived=<address> retired=yes|no
    KEY-UNREADABLE <path>:<line> var=<VAR|-> (key derivation unavailable)
    SKIP-BINARY <path>
    REFUSED-SYMLINK <path> -> <target> (outside roots)

Exit status: 1 when any retired address or retired-derived key is found,
0 when clean, 2 on usage error or an unreadable file.
"""

from __future__ import annotations

import argparse
import os
import re
import stat
import sys
from pathlib import Path

ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}\b")
KEY_LITERAL = re.compile(r"0x[0-9a-fA-F]{64}\b")
KEY_VALUE = re.compile(r"(0x)?[0-9a-fA-F]{64}\s*$")
KEY_VAR = re.compile(r"(?:PRIVATE_KEY|KEY)[A-Z0-9_]*$", re.IGNORECASE)
VAR_ASSIGN = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=")


def normalize_address(value: str) -> str:
    """Lowercase 0x form; returns '' for non-addresses."""
    value = value.strip().lower()
    if not value.startswith("0x"):
        value = "0x" + value
    return value if re.fullmatch(r"0x[0-9a-f]{40}", value) else ""


def load_retired(paths: list[str], args: list[str]) -> set[str]:
    retired: set[str] = set()
    for path in paths:
        for line in Path(path).read_text().splitlines():
            line = line.split("#", 1)[0]
            for token in line.replace(",", " ").split():
                addr = normalize_address(token)
                if addr:
                    retired.add(addr)
    for token in args:
        addr = normalize_address(token)
        if not addr:
            raise SystemExit(f"not a 0x+40-hex address: {token!r}")
        retired.add(addr)
    return retired


def _derive_address(key_hex: str) -> str | None:
    """Derived address for a 64-hex private key, or None when eth_keys is absent."""
    try:
        from eth_keys import keys
    except ImportError:
        return None
    try:
        return str(keys.PrivateKey(bytes.fromhex(key_hex)).public_key.to_checksum_address()).lower()
    except Exception:
        return ""


def _var_before(line: str, pos: int) -> str:
    """Name of the VAR= whose assignment spans ``pos``, or '-' when none."""
    name = "-"
    for m in VAR_ASSIGN.finditer(line):
        if m.end() <= pos:
            name = m.group(1)
    return name


def scan_text(lines: list[str], retired: set[str], path: str, out, *, can_derive: bool) -> bool:
    """Emit findings for one file's lines. Returns True when a retired hit was found."""
    found = False
    seen_keys: set[tuple[int, str]] = set()
    for lineno, line in enumerate(lines, 1):
        # Retired addresses — report the address, never the line's value.
        for m in ADDRESS.finditer(line):
            addr = normalize_address(m.group(0))
            if addr in retired:
                found = True
                out(f"HIT-ADDR {path}:{lineno} var={_var_before(line, m.start())} address={addr}")
        # 0x-prefixed 64-hex literals — derive, report derived only.
        for m in KEY_LITERAL.finditer(line):
            key = (lineno, m.group(0).lower())
            if key in seen_keys:
                continue
            seen_keys.add(key)
            var = _var_before(line, m.start())
            derived = _derive_address(m.group(0)[2:]) if can_derive else None
            if derived is None:
                out(f"KEY-UNREADABLE {path}:{lineno} var={var} (key derivation unavailable)")
            elif derived == "":
                out(f"KEY-UNREADABLE {path}:{lineno} var={var} (invalid key literal)")
            else:
                is_retired = derived in retired
                found = found or is_retired
                out(f"HIT-KEY {path}:{lineno} var={var} derived={derived} retired={'yes' if is_retired else 'no'}")
        # *_PRIVATE_KEY / *_KEY assignments with a bare 64-hex value (no 0x).
        for m in VAR_ASSIGN.finditer(line):
            if not KEY_VAR.search(m.group(1)):
                continue
            value = line[m.end() :].strip()
            if not KEY_VALUE.fullmatch(value) or value.startswith("0x"):
                continue
            key = (lineno, "0x" + value.lower())
            if key in seen_keys:
                continue
            seen_keys.add(key)
            derived = _derive_address(value.removeprefix("0x")) if can_derive else None
            if derived is None:
                out(f"KEY-UNREADABLE {path}:{lineno} var={m.group(1)} (key derivation unavailable)")
            elif derived == "":
                out(f"KEY-UNREADABLE {path}:{lineno} var={m.group(1)} (invalid key literal)")
            else:
                is_retired = derived in retired
                found = found or is_retired
                out(f"HIT-KEY {path}:{lineno} var={m.group(1)} derived={derived} retired={'yes' if is_retired else 'no'}")
    return found


def _inside_roots(real: str, roots: list[str]) -> bool:
    return any(real == r or real.startswith(r + os.sep) for r in roots)


def iter_candidates(raw_roots: list[str], resolved_roots: list[str], out) -> tuple[list[str], bool]:
    """Resolve the roots to plain files; refuse out-of-root symlinks.

    ``raw_roots`` are the args as given (symlinks detected before resolution);
    ``resolved_roots`` are the same args realpath'd, the boundary a symlink
    target must stay inside to be followed.
    """
    files: list[str] = []
    error: list[bool] = []  # non-empty means at least one root was unreadable
    for root in raw_roots:
        if os.path.islink(root):
            real = os.path.realpath(root)
            # A link can never be inside itself: the boundary for a symlinked
            # root arg is the *other* given roots.
            boundary = [r for r in resolved_roots if r != real]
            if not _inside_roots(real, boundary):
                out(f"REFUSED-SYMLINK {root} -> {real} (outside roots)")
                continue
        real_root = os.path.realpath(root)
        if os.path.isfile(real_root):
            files.append(real_root)
            continue
        if not os.path.isdir(real_root):
            out(f"ERROR {root}: not a file or directory")
            error.append(True)
            continue
        for dirpath, dirnames, filenames in os.walk(real_root, followlinks=False):
            for d in list(dirnames):
                full = os.path.join(dirpath, d)
                if os.path.islink(full):
                    real = os.path.realpath(full)
                    if not _inside_roots(real, resolved_roots):
                        out(f"REFUSED-SYMLINK {full} -> {real} (outside roots)")
                        dirnames.remove(d)
            for f in filenames:
                full = os.path.join(dirpath, f)
                if os.path.islink(full):
                    real = os.path.realpath(full)
                    if not _inside_roots(real, resolved_roots):
                        out(f"REFUSED-SYMLINK {full} -> {real} (outside roots)")
                        continue
                    files.append(real)
                else:
                    files.append(full)
    return files, bool(error)


def scan_file(path: str, retired: set[str], out, *, can_derive: bool) -> tuple[bool, bool]:
    """Scan one file. Returns (retired_hit, error)."""
    try:
        st = os.stat(path)
        out(f"FILE {path} mode={oct(stat.S_IMODE(st.st_mode))}")
        with open(path, "rb") as fh:
            blob = fh.read()
        if b"\0" in blob[:4096]:
            out(f"SKIP-BINARY {path}")
            return False, False
        lines = blob.decode("utf-8", errors="replace").splitlines()
        return scan_text(lines, retired, path, out, can_derive=can_derive), False
    except OSError as exc:
        out(f"ERROR {path}: {exc.strerror or exc}")
        return False, True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only retired-key/address census.")
    parser.add_argument("roots", nargs="+", help="Files or directories to scan")
    parser.add_argument("--retired", action="append", default=[], help="Retired address (repeatable)")
    parser.add_argument("--retired-file", action="append", default=[], help="File listing retired addresses")
    args = parser.parse_args(argv)

    retired = load_retired(args.retired_file, args.retired)
    if not retired:
        parser.error("no retired addresses given (--retired / --retired-file)")

    resolved_roots = [os.path.realpath(r) for r in args.roots]
    can_derive = True
    try:
        import eth_keys  # noqa: F401
    except ImportError:
        can_derive = False
        print("warning: eth_keys unavailable — key literals report as KEY-UNREADABLE", file=sys.stderr)

    out = print
    files, error = iter_candidates(args.roots, resolved_roots, out)
    found = False
    for path in sorted(set(files)):
        hit, err = scan_file(path, retired, out, can_derive=can_derive)
        found = found or hit
        error = error or err
    if error:
        return 2
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
