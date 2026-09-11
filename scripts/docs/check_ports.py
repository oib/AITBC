#!/usr/bin/env python3
"""Check that port tables across docs/ and skills/ agree with the authoritative list.

docs/reference/SERVICE_PORTS.md is the single source of truth for live service
ports. Other documents duplicate those numbers freely and drift: on 2026-09-11 a
sweep found 13 wrong rows in docs/ and 120 stale port references in skills/,
including a firewall table driving `ufw allow` and a table listing 8203 for two
different services. Nothing caught it because the link checker only resolves
paths, not values.

This started out reading markdown TABLE ROWS only, which left a hole big enough
to drive the dev scripts through: start-aitbc-dev.sh and start-aitbc-full.sh
carried a shell array of ports from a previous layout -- coordinator on 8000,
RPC on 8003, wallet on 8002 -- and every health check they ran reported NOT
RUNNING regardless of the real state. A port in a shell array is not a markdown
table row, so this script saw nothing. It now also reads ports written inline:
`host:port`, `port NNNN`, and `"NNNN:Service Name"` array entries, in markdown
prose and in the operator shell scripts under scripts/ and dev/.

A line that genuinely needs a non-authoritative port can say so with a trailing
`check-ports: ignore` comment.

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

# Markdown is scanned in full; shell scripts are scanned for inline ports only.
SCAN_ROOTS = ("docs", "skills")
SCRIPT_ROOTS = ("scripts", "dev")
SCRIPT_SUFFIXES = (".sh",)

# An escape hatch for a line that deliberately names a non-live port.
IGNORE_MARKER = "check-ports: ignore"

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

# Ports written outside a table. Each alternative must make it unambiguous that
# the number is a port, otherwise every year and version number becomes a hit.
INLINE_RES = (
    # localhost:8203, 127.0.0.1:8203, $HOST:8203, example.net:8203
    re.compile(r"(?:[A-Za-z0-9_.$@{}-]+):(\d{4})\b"),
    # "port 8203", "on port 8203"
    re.compile(r"\bports?\s+(\d{4})\b", re.I),
)
# Shell array entries: "8203:Coordinator API"
ARRAY_RE = re.compile(r"\"(\d{4}):([A-Za-z][A-Za-z0-9 /_()-]*)\"")

# Environment assignments name their own service, so they do not need the
# nearest-name guess: MARKETPLACE_URL=http://localhost:8102 is about the
# marketplace even when the word "edge" sits closer to the digits.
ENV_RE = re.compile(
    r"\b([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*?)_(?:URL|PORT|ENDPOINT)\s*=\s*"
    r"[\"']?(?:[^\s\"']*[:=])?(\d{4})\b"
)

# How far from the number a service name may sit and still be taken to describe
# it. Wide enough for `echo "  - Coordinator API: http://localhost:8203"`,
# narrow enough that a name at the far end of a paragraph line is not claimed.
# A service name has to sit close to the port for the pairing to mean anything.
NAME_PROXIMITY = 40

# Inline checking is limited to AITBC's own service range. Without this, every
# "governance database on 5432" or "explorer behind nginx on 3000" line reads as
# a contradiction, because a nearby service name is all this has to go on.
INLINE_PORT_RANGE = range(8000, 8300)


def canon(name: str) -> str:
    n = " ".join(name.strip().lower().split())
    return ALIASES.get(n, n)


def name_index(authority: dict[str, int]) -> list[tuple[str, str]]:
    """Searchable (literal, canonical) service names, longest first.

    Longest first matters: "wallet" is an alias of "wallet daemon", and a
    shorter name must not win inside a longer one.
    """
    names = {n: n for n in authority}
    for alias, target in ALIASES.items():
        if target in authority:
            names.setdefault(alias, target)
    return sorted(names.items(), key=lambda kv: -len(kv[0]))


def inline_hits(line: str, authority: dict[str, int], names: list[tuple[str, str]]):
    """Yield (canonical_name, port) for ports written outside a table.

    Each port is attributed to the nearest service name on the same line. A port
    with no name near it is not a claim about that service, so it is skipped
    rather than guessed at.
    """
    low = line.lower()

    # Longest name first, discarding any match that overlaps one already taken,
    # so "Agent Coordinator API" is read as the agent coordinator rather than as
    # a coordinator-api sighting that happens to share two words.
    found: list[tuple[int, str]] = []
    taken: list[tuple[int, int]] = []
    for literal, canonical in names:
        for m in re.finditer(r"(?<![a-z0-9_-])" + re.escape(literal) + r"(?![a-z0-9_-])", low):
            if any(m.start() < end and start < m.end() for start, end in taken):
                continue
            taken.append((m.start(), m.end()))
            found.append((m.start(), canonical))

    for m in ARRAY_RE.finditer(line):
        canonical = canon(m.group(2))
        if canonical in authority:
            yield canonical, int(m.group(1))

    seen: set[tuple[int, int]] = set()
    for m in ENV_RE.finditer(line):
        seen.add((m.start(2), m.end(2)))
        canonical = canon(m.group(1).replace("_", " "))
        port = int(m.group(2))
        if canonical in authority and port in INLINE_PORT_RANGE:
            yield canonical, port

    if not found:
        return

    for rx in INLINE_RES:
        for m in rx.finditer(line):
            span = (m.start(1), m.end(1))
            if span in seen:
                continue
            seen.add(span)
            pos = m.start(1)
            port = int(m.group(1))
            if port not in INLINE_PORT_RANGE:
                continue
            # Only a name written BEFORE the port counts ("Exchange API: ...
            # 8001"). A name appearing after it is almost always part of a URL
            # path -- http://host:8202/rpc/gpu/register names the RPC port and
            # a GPU endpoint on it, which is not a claim about the GPU service.
            before = [(pos - p, c) for p, c in found if p <= pos]
            if not before:
                continue
            dist, canonical = min(before)
            if dist <= NAME_PROXIMITY and canonical in authority:
                yield canonical, port


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

    names = name_index(authority)

    bad: list[tuple[str, int, str, int, int]] = []
    checked = 0

    def scan(path: Path, tables: bool) -> None:
        nonlocal checked
        rel = path.relative_to(repo).as_posix()
        for i, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if IGNORE_MARKER in line:
                continue

            claims: list[tuple[str, int]] = []
            if tables:
                m = ROW_RE.match(line)
                if m:
                    claims.append((canon(m.group(1)), int(m.group(2))))
            if not claims:
                claims.extend(inline_hits(line, authority, names))

            for name, port in claims:
                if name not in authority:
                    continue
                checked += 1
                if authority[name] != port:
                    bad.append((rel, i, name, port, authority[name]))

    for root in SCAN_ROOTS:
        base = repo / root
        if not base.exists():
            continue
        for md in sorted(base.rglob("*.md")):
            rel = md.relative_to(repo).as_posix()
            if rel.startswith(SKIP_DIRS) or md == authority_file:
                continue
            scan(md, tables=True)

    for root in SCRIPT_ROOTS:
        base = repo / root
        if not base.exists():
            continue
        for sh in sorted(base.rglob("*")):
            if sh.suffix not in SCRIPT_SUFFIXES or not sh.is_file():
                continue
            scan(sh, tables=False)

    if not bad:
        print(f"Checked {checked} port reference(s) against SERVICE_PORTS.md. All consistent.")
        return 0

    print(f"Checked {checked} port reference(s). Found {len(bad)} contradicting SERVICE_PORTS.md:\n")
    for rel, i, name, got, want in bad:
        print(f"  {rel}:{i}  {name}: {got} -> should be {want}")
    print("\nEither fix the reference, or update docs/reference/SERVICE_PORTS.md if the port\ngenuinely moved. A line that deliberately names a non-live port can carry a\ntrailing `check-ports: ignore` comment.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
