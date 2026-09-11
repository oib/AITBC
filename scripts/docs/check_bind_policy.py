#!/usr/bin/env python3
"""Check that every bind-all service is authorized by the network policy.

AITBC runs no host firewall, so a service bound to 0.0.0.0 is reachable by
anyone who can route to the host -- the bind address is the entire access
control. Two documents describe this:

    docs/reference/SERVICE_PORTS.md   what each service ACTUALLY binds
    docs/deployment/NETWORK_POLICY.md what is ALLOWED to be reachable

This script fails when the first contains a bind-all service that the second
does not authorize. That is the drift that matters: adding a service whose code
defaults to 0.0.0.0 is silent, and on a firewall-less host it is a decision to
publish the service, made by omission.

The check deliberately does not compare two copies of the same table. The policy
names only its authorized surfaces; SERVICE_PORTS.md is the sole place binds are
recorded, so there is no duplicated table to drift in the first place.

Exit codes:
    0 - every bind-all service is authorized
    1 - an unauthorized bind-all service, or a document format change
"""

import re
import sys
from pathlib import Path

PORTS_DOC = Path("docs/reference/SERVICE_PORTS.md")
POLICY_DOC = Path("docs/deployment/NETWORK_POLICY.md")

# Heading under which the policy lists what may be internet-reachable.
AUTHORIZED_HEADING = "authorized public surfaces"

# Heading listing bind-all services that are known and accepted for now. These
# warn instead of failing, so the gate holds the line against NEW exposures
# without wedging CI on the existing backlog. Pinning a bind and deleting its
# row here ratchets the policy forward; it cannot silently slip back.
DEVIATION_HEADING = "known deviations"

# Headings in SERVICE_PORTS.md that do not describe live bind state.
NON_LIVE = ("legacy", "not-implemented", "without a listening port")

HEADING_RE = re.compile(r"^##+\s*(.+?)\s*$")
# A table row whose cells include a 4-digit port and a bind address.
BIND_ROW_RE = re.compile(r"^\|\s*([A-Za-z][^|]*?)\s*\|(.+)$")
BIND_ALL_RE = re.compile(r"`0\.0\.0\.0`")
PORT_CELL_RE = re.compile(r"^\s*(\d{4})\s*$")


def canon(name: str) -> str:
    return " ".join(name.strip().lower().split())


def bind_all_services(path: Path) -> dict[str, int]:
    """Service -> port for every row recording a 0.0.0.0 bind."""
    found: dict[str, int] = {}
    live = True
    for line in path.read_text(encoding="utf-8").splitlines():
        h = HEADING_RE.match(line)
        if h:
            live = not any(s in h.group(1).lower() for s in NON_LIVE)
            continue
        if not live or "---|" in line:
            continue
        m = BIND_ROW_RE.match(line)
        if not m or not BIND_ALL_RE.search(m.group(2)):
            continue
        cells = list(m.group(2).split("|"))
        ports = [int(p.group(1)) for c in cells if (p := PORT_CELL_RE.match(c))]
        if ports:
            found[canon(m.group(1))] = ports[0]
    return found


def _table_ports(path: Path, heading: str) -> set[int]:
    """Ports named in the table under a given policy heading."""
    ports: set[int] = set()
    inside = False
    for line in path.read_text(encoding="utf-8").splitlines():
        h = HEADING_RE.match(line)
        if h:
            inside = heading in h.group(1).lower()
            continue
        if not inside or not line.startswith("|"):
            continue
        for cell in line.split("|"):
            ports.update(int(n) for n in re.findall(r"\b(\d{2,5})\b", cell))
    return ports


def main() -> int:
    repo = Path(__file__).resolve().parents[2]
    ports_doc, policy_doc = repo / PORTS_DOC, repo / POLICY_DOC

    for doc in (ports_doc, policy_doc):
        if not doc.exists():
            print(f"Missing document: {doc.relative_to(repo)}")
            return 1

    allowed = _table_ports(policy_doc, AUTHORIZED_HEADING)
    acknowledged = _table_ports(policy_doc, DEVIATION_HEADING)
    if not allowed:
        print(
            f"Parsed no authorized surfaces from {POLICY_DOC} -- "
            f"has the '{AUTHORIZED_HEADING}' section been renamed or emptied?"
        )
        return 1

    bind_all = bind_all_services(ports_doc)
    unauthorized = {n: p for n, p in bind_all.items() if p not in allowed}
    known = {n: p for n, p in unauthorized.items() if p in acknowledged}
    new = {n: p for n, p in unauthorized.items() if p not in acknowledged}

    if known:
        print(f"{len(known)} known deviation(s) still binding 0.0.0.0 (tracked in {POLICY_DOC}):")
        for name, port in sorted(known.items(), key=lambda kv: kv[1]):
            print(f"  - {name} ({port})")
        print()

    if not new:
        print(f"Checked {len(bind_all)} bind-all service(s) against {POLICY_DOC}. No unacknowledged exposures.")
        return 0

    unauthorized = new

    print(f"Checked {len(bind_all)} bind-all service(s). {len(unauthorized)} newly unauthorized by {POLICY_DOC}:\n")
    for name, port in sorted(unauthorized.items(), key=lambda kv: kv[1]):
        print(f"  {name} ({port}) binds 0.0.0.0 but is not an authorized public surface")
    print(
        "\nWith no host firewall these are reachable from anywhere that can route\n"
        "to the host. Pin the bind in the systemd unit and update\n"
        f"{PORTS_DOC}, or -- if the exposure is intended -- add the service to the\n"
        f"authorized surfaces in {POLICY_DOC} as a deliberate, reviewed decision.\n"
        "Adding it to 'Known deviations' only defers the work; do that solely when\n"
        "the bind cannot be pinned in this change."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
