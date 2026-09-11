#!/usr/bin/env python3
"""Check that port tables across docs/ and skills/ agree with the authoritative list.

docs/reference/SERVICE_PORTS.md is the single source of truth for live service
ports. Other documents duplicate those numbers freely and drift: on 2026-09-11 a
sweep found 13 wrong rows in docs/ and 120 stale port references in skills/,
including a firewall table driving `ufw allow` and a table listing 8203 for two
different services. Nothing caught it because the link checker only resolves
paths, not values.

The authority is PARSED from SERVICE_PORTS.md rather than hardcoded here, so
updating that file is enough -- this script needs no edit when a port moves.
Rows under "Legacy / not-implemented" and "Services without a listening port"
are deliberately not treated as authority.

Exit codes:
    0 - every port row agrees with the authority
    1 - one or more rows contradict it
"""

import re
import sys
from pathlib import Path

SCAN_ROOTS = ("docs", "skills")

# Historical records are expected to name the ports of their own era.
SKIP_DIRS = ("docs/releases/", "docs/archive/", "docs/audit/")

# Sections of SERVICE_PORTS.md that do NOT define live ports.
NON_AUTHORITATIVE_SECTIONS = ("legacy", "not-implemented", "without a listening port")

# Names that denote the same service. Keys and values are lowercased table labels.
ALIASES = {
    "wallet": "wallet daemon",
    "wallet api": "wallet daemon",
    "exchange": "exchange api",
    "marketplace": "marketplace service",
    "explorer api": "blockchain explorer",
    "blockchain explorer api": "blockchain explorer",
    "blockchain node": "blockchain rpc",
    "p2p network": "blockchain p2p",
    "blockchain p2p (gossip relay)": "blockchain p2p",
    "edge api": "edge service",
    "gpu": "gpu service",
    "governance": "governance service",
    "edge": "edge service",
    "whisper": "whisper service",
    "ffmpeg": "ffmpeg service",
    "trading": "trading service",
}

ROW_RE = re.compile(r"^\|\s*([A-Za-z][A-Za-z0-9 /_()-]*?)\s*\|\s*(\d{4})\s*\|")
HEADING_RE = re.compile(r"^##+\s*(.+?)\s*$")


def canon(name: str) -> str:
    n = " ".join(name.strip().lower().split())
    return ALIASES.get(n, n)


def load_authority(path: Path) -> dict[str, int]:
    """Parse live service -> port from the authoritative reference."""
    ports: dict[str, int] = {}
    live = True
    for line in path.read_text(encoding="utf-8").splitlines():
        h = HEADING_RE.match(line)
        if h:
            live = not any(s in h.group(1).lower() for s in NON_AUTHORITATIVE_SECTIONS)
            continue
        if not live:
            continue
        m = ROW_RE.match(line)
        if m:
            ports.setdefault(canon(m.group(1)), int(m.group(2)))
    return ports


def main() -> int:
    repo = Path(__file__).resolve().parents[2]
    authority_file = repo / "docs" / "reference" / "SERVICE_PORTS.md"
    if not authority_file.exists():
        print(f"Authority file missing: {authority_file}")
        return 1

    authority = load_authority(authority_file)
    if not authority:
        print(f"Parsed no ports from {authority_file} -- has its table format changed?")
        return 1

    bad: list[tuple[str, int, str, int, int]] = []
    checked = 0

    for root in SCAN_ROOTS:
        base = repo / root
        if not base.exists():
            continue
        for md in sorted(base.rglob("*.md")):
            rel = md.relative_to(repo).as_posix()
            if rel.startswith(SKIP_DIRS) or md == authority_file:
                continue
            for i, line in enumerate(md.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                m = ROW_RE.match(line)
                if not m:
                    continue
                name, port = canon(m.group(1)), int(m.group(2))
                if name not in authority:
                    continue
                checked += 1
                if authority[name] != port:
                    bad.append((rel, i, name, port, authority[name]))

    if not bad:
        print(f"Checked {checked} port row(s) against SERVICE_PORTS.md. All consistent.")
        return 0

    print(f"Checked {checked} port row(s). Found {len(bad)} contradicting SERVICE_PORTS.md:\n")
    for rel, i, name, got, want in bad:
        print(f"  {rel}:{i}  {name}: {got} -> should be {want}")
    print("\nEither fix the row, or update docs/reference/SERVICE_PORTS.md if the port genuinely moved.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
