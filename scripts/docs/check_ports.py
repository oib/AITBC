#!/usr/bin/env python3
"""Check that port references across docs, skills, scripts, examples, and website
agree with the authoritative list in docs/reference/SERVICE_PORTS.md.

The original implementation only read markdown table rows, which left a hole big
enough to drive stale port arrays through the dev start scripts. It now reads:

- markdown table rows
- inline prose references like `host:port` and `port NNNN`
- inline backticks (e.g. `localhost:8003`) and fenced code blocks
- shell array entries `NNNN:Service Name`
- environment assignments `SERVICE_PORT=NNNN` / `SERVICE_URL=...:NNNN`
- comments and echoes up to three lines before a port as attribution context
- unattributed AITBC-range ports that are no longer in the authority

The authority is PARSED from SERVICE_PORTS.md rather than hardcoded here, so
updating that file is enough when a port moves. Rows under "Legacy /
not-implemented" and "Services without a listening port" are deliberately not
treated as authority.

A line that genuinely needs a non-authoritative port can say so with a trailing
`check-ports: ignore` comment.

Exit codes:
    0 - every port reference agrees with the authority
    1 - one or more rows, inline references, or stray ports contradict it
"""

import re
import sys
from pathlib import Path

# Markdown and example docs are scanned for both tables and inline references.
SCAN_ROOTS = ("docs", "skills", "examples", "website")

# Operator shell scripts and markdown readmes under scripts/dev are scanned for
# inline references and stray port numbers.
SCRIPT_ROOTS = ("scripts", "dev")
SCRIPT_SUFFIXES = (".sh", ".md")

# An escape hatch for a line that deliberately names a non-live port.
IGNORE_MARKER = "check-ports: ignore"

# Historical records are expected to name the ports of their own era.
# The following legacy/one-off trees are temporarily skipped while the active
# deployment, development, and documentation files are being reconciled. They
# will be re-audited in a dedicated follow-up pass.
SKIP_DIRS = (
    "docs/releases/",
    "docs/archive/",
    "docs/audit/",
    "scripts/plan/",
    "scripts/maintenance/",
    "scripts/workflow/",
    "dev/testing/tests/",
)

# Sections of SERVICE_PORTS.md that do NOT define live ports.
NON_AUTHORITATIVE_SECTIONS = ("legacy", "not-implemented", "without a listening port")

# How many previous non-ignored lines to keep when attributing a port to a
# nearby service name.
LOOKBACK = 3

# Names that denote the same service. Keys and values are lowercased table labels.
ALIASES = {
    "wallet": "wallet daemon",
    "wallet api": "wallet daemon",
    "exchange": "exchange api",
    "marketplace": "marketplace service",
    "explorer api": "blockchain explorer",
    "blockchain explorer api": "blockchain explorer",
    "blockchain node": "blockchain rpc",
    "blockchain rpc url": "blockchain rpc",
    "p2p network": "blockchain p2p",
    "blockchain p2p (gossip relay)": "blockchain p2p",
    "edge api": "edge service",
    "gpu": "gpu service",
    "governance": "governance service",
    "edge": "edge service",
    "whisper": "whisper service",
    "ffmpeg": "ffmpeg service",
    "trading": "trading service",
    "rpc": "blockchain rpc",
    "p2p": "blockchain p2p",
    "rpc bind": "blockchain rpc",
    "p2p bind": "blockchain p2p",
    "coordinator bind": "coordinator api",
    "coordinator api bind": "coordinator api",
    "api gateway bind": "api gateway",
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

# Ports inside the AITBC service range that are not attributed to any current
# service are reported as stale. 8000-8299 covers the public and internal tiers.
INLINE_PORT_RANGE = range(8000, 8300)

# How far from the number a service name may sit and still be taken to describe
# it on the same line.
NAME_PROXIMITY = 60

# How far into the preceding LOOKBACK lines a service name may sit and still
# attribute the port.
CONTEXT_PROXIMITY = 160


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


def _service_positions(text: str, names: list[tuple[str, str]]) -> list[tuple[int, str]]:
    """Return (position, canonical) for every service name found in text."""
    low = text.lower()
    found: list[tuple[int, str]] = []
    taken: list[tuple[int, int]] = []
    for literal, canonical in names:
        pattern = r"(?<![a-z0-9_-])" + re.escape(literal) + r"(?![a-z0-9_-])"
        for m in re.finditer(pattern, low):
            if any(m.start() < end and start < m.end() for start, end in taken):
                continue
            taken.append((m.start(), m.end()))
            found.append((m.start(), canonical))
    return found


def _stray_ports(
    line: str, authority: dict[str, int], used_positions: set[tuple[int, int]]
) -> list[tuple[int, int]]:
    """Port-looking references that are not attributed to any current service.

    Only `host:port` or `port NNNN` patterns are reported, so this does not
    trip over unrelated four-digit numbers like amounts or line counts.
    """
    clean = line.replace("`", "")
    stale: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set(used_positions)
    for rx in INLINE_RES:
        for m in rx.finditer(clean):
            span = (m.start(1), m.end(1))
            if span in seen:
                continue
            seen.add(span)
            port = int(m.group(1))
            if port not in INLINE_PORT_RANGE:
                continue
            if port in authority.values():
                continue
            stale.append((port, m.start(1)))
    return stale


def inline_hits(
    line: str, authority: dict[str, int], names: list[tuple[str, str]], prev_lines: list[str]
):
    """Yield (canonical_name, port, position) for ports written outside a table.

    Service names are looked up in the current line and in the previous
    LOOKBACK lines, so a comment like `echo "Testing marketplace..."` above a
    `curl http://localhost:8002/...` line still attributes the port correctly.

    Backticks (single and triple fence markers) are stripped from the search
    text so that inline and fenced code ports are not invisible.
    """
    clean = line.replace("`", "")
    low = clean.lower()

    # ARRAY and ENV patterns do not need name proximity; they name themselves.
    for m in ARRAY_RE.finditer(clean):
        canonical = canon(m.group(2))
        if canonical in authority:
            yield canonical, int(m.group(1)), m.start(1)

    seen: set[tuple[int, int]] = set()
    for m in ENV_RE.finditer(clean):
        seen.add((m.start(2), m.end(2)))
        canonical = canon(m.group(1).replace("_", " "))
        port = int(m.group(2))
        if canonical in authority and port in INLINE_PORT_RANGE:
            yield canonical, port, m.start(2)

    # Context lines that themselves contain an explicit port reference are most
    # often a neighbouring table row or shell array entry and would mis-attribute
    # the current port to the previous service. Keep only context lines that are
    # prose/comment without their own port reference.
    context = [
        l.replace("`", "")
        for l in prev_lines
        if not any(rx.search(l) for rx in INLINE_RES) and not ARRAY_RE.search(l)
    ]
    search_text = "\n".join(context) + "\n" + clean
    context_offset = sum(len(l) + 1 for l in context)
    positions = _service_positions(search_text, names)

    for rx in INLINE_RES:
        for m in rx.finditer(clean):
            span = (m.start(1), m.end(1))
            if span in seen:
                continue
            seen.add(span)
            pos = m.start(1)
            port = int(m.group(1))
            if port not in INLINE_PORT_RANGE:
                continue

            port_abs = context_offset + pos

            # Prefer a name on the same line, before or after the port.
            same_line = [
                (p, c) for p, c in positions if p >= context_offset and p <= port_abs
            ]
            if same_line:
                dist, canonical = min(same_line, key=lambda x: abs(port_abs - x[0]))
                if abs(port_abs - dist) <= NAME_PROXIMITY and canonical in authority:
                    yield canonical, port, pos
                    continue

            # Fall back to a name in the preceding LOOKBACK context.
            context_hits = [
                (p, c) for p, c in positions if p < context_offset and p <= port_abs
            ]
            if context_hits:
                dist, canonical = min(context_hits, key=lambda x: port_abs - x[0])
                if (port_abs - dist) <= CONTEXT_PROXIMITY and canonical in authority:
                    yield canonical, port, pos


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
        prev: list[str] = []
        for i, line in enumerate(
            path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
        ):
            if IGNORE_MARKER in line:
                prev.append(line)
                if len(prev) > LOOKBACK:
                    prev.pop(0)
                continue

            claims: list[tuple[str, int, int]] = []
            if tables:
                m = ROW_RE.match(line)
                if m:
                    claims.append((canon(m.group(1)), int(m.group(2)), m.start(2)))
            if not claims:
                claims.extend(inline_hits(line, authority, names, prev))

            used_positions: set[tuple[int, int]] = {pos for _, _, pos in claims}

            if not claims:
                for port, _ in _stray_ports(line, authority, used_positions):
                    bad.append((rel, i, "stale port", port, 0))

            for name, port, _ in claims:
                if name not in authority:
                    continue
                checked += 1
                if authority[name] != port:
                    bad.append((rel, i, name, port, authority[name]))

            prev.append(line)
            if len(prev) > LOOKBACK:
                prev.pop(0)

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
        for f in sorted(base.rglob("*")):
            if f.suffix not in SCRIPT_SUFFIXES or not f.is_file():
                continue
            rel = f.relative_to(repo).as_posix()
            if rel.startswith(SKIP_DIRS):
                continue
            scan(f, tables=f.suffix == ".md")

    if not bad:
        print(f"Checked {checked} port reference(s) against SERVICE_PORTS.md. All consistent.")
        return 0

    print(f"Checked {checked} port reference(s). Found {len(bad)} contradicting SERVICE_PORTS.md:\n")
    for rel, i, name, got, want in bad:
        if want == 0:
            print(f"  {rel}:{i}  {name}: {got} (not an AITBC service port)")
        else:
            print(f"  {rel}:{i}  {name}: {got} -> should be {want}")
    print(
        "\nEither fix the reference, or update docs/reference/SERVICE_PORTS.md if the port\n"
        "genuinely moved. A line that deliberately names a non-live port can carry a\n"
        "trailing `check-ports: ignore` comment."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
