"""No tracked file may name an individual machine in the operator's fleet.

This repository is public. The project's own service names are meant to be here --
`README.md` advertises the public island, and the chain IDs are protocol values --
but *which host plays which role*, what it is called internally, and what address
it sits on are operational details that belong in the operator's private notes.

The scrub this pins was done twice. The first pass introduced the `<hub-node>` /
`<node1>` / `<node2>` / `<replica-node>` placeholder convention in
`docs/releases/STATUS.md` and stopped partway, so `docs/DESIGN_CYCLE.md` carried
placeholders on one line and the un-scrubbed prose two lines down for weeks. A
half-finished scrub reads as a finished one, which is why this is a test and not
a note: the rule has to be checkable by someone who was not there.

Two rules, both chosen so that this file does not itself republish what it
guards:

* the internal infrastructure names have no generic meaning, so their mere
  presence is the defect and they can be listed here safely;
* an individual machine's FQDN is recognised by its *shape* -- a host-ordinal
  label in front of a real domain -- so no real domain is written down.

The third rule covers addresses, and has to be inverted to obey the same
constraint. An address is not a meaningless token and has no distinguishing
shape, so it cannot be written here without publishing it -- and a digest would
not help, because private address space is small enough to recover a SHA-256
preimage by enumeration in seconds. It therefore pins the addresses the repo
*already* contains, which are public by definition, and fails on any other one.

That makes it an inventory rather than a policy: it does not know which
addresses are the operator's, only which ones were here when it was written.
Extending `ALLOWED_ADDRESS_PREFIXES` is a deliberate act, and that is the point.
The checkpoint was missing when a fleet address reappeared in
`docs/infrastructure/PRODUCTION_ARCHITECTURE.md` after an earlier scrub had
removed it, inside a table the scrub's own commit subject claimed to have dropped.

Only private, loopback, link-local, multicast and documentation ranges are in
scope. Routable addresses are not covered -- no allowlist of public space would
stay maintainable -- so an operator address outside those ranges still relies on
review.
"""

from __future__ import annotations

import ipaddress
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

# Names of specific machines and of the hosting they run on. None of these is a
# word that legitimate code or documentation needs.
INTERNAL_HOST_TOKENS = ["at1", "ns3", "netcup"]

# A host-ordinal label in front of a registrable domain: `hub1.example-corp.net`.
# RFC 2606 reserves `example.*` for documentation, so those are the intended form
# and are excluded. `${VAR}`-style placeholders never match -- that is the point
# of parameterising `scripts/monitoring/fleet-config-check.sh`.
# The lookbehind matters: `ait-island1.<domain>` is a chain ID, and without it
# the `island1.` tail matches and the whole protocol value is reported as a host.
PER_HOST_FQDN = re.compile(
    r"(?<![\w-])(?:hub|node|at|ns|buyer-[a-z0-9-]*?)\d+"
    r"\.(?!example\b)[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}\b",
    re.IGNORECASE,
)

# Historical incident records keep bare ordinals (`node1`, `hub2`). They carry no
# domain, address or provider, and rewriting years of changelog would churn
# thousands of lines to disclose nothing. Current-state docs use placeholders.
# `oracle1`/`oracle2` and `island1`/`island2` deliberately are NOT in the pattern
# above. Each was checked rather than assumed: the oracle pair belongs to external
# infrastructure the v0.7.2 plan assumed and then explicitly rescoped away, so it
# was never built; the island pair appears only as endpoints in `trade
# register-chain` examples. Neither names a machine. Add a name here only after
# checking the same way.
ALLOWED_FQDN_SUFFIXES: tuple[str, ...] = ()

# Every in-scope address already present in the repo, collapsed to its /24. These
# are textbook and documentation values (RFC 1918 examples, RFC 5737 blocks, the
# loopback and cloud-metadata addresses); they are listed because they are here,
# not because they are approved as a class. A new prefix is a review prompt, not
# an accusation -- if it is genuinely a documentation value, add it.
ALLOWED_ADDRESS_PREFIXES = frozenset(
    {
        "0.0.0.",
        "10.0.0.",
        "10.0.1.",
        "10.0.2.",
        "10.1.0.",
        "10.1.1.",
        "10.1.2.",
        "10.2.0.",
        "10.3.0.",
        "10.4.0.",
        "10.255.255.",
        "127.0.0.",
        "169.254.169.",
        "192.0.2.",
        "192.168.1.",
        "198.51.100.",
        "203.0.113.",
    }
)

# A bare dotted quad. The guards keep `1.2.3.4` inside a version string or a
# longer dotted path from being read as an address.
IPV4_LITERAL = re.compile(r"(?<![\w.])\d{1,3}(?:\.\d{1,3}){3}(?![\w.])")


def _address_is_uninteresting(value: str) -> bool:
    """True when a matched quad is out of scope, or already pinned."""
    try:
        address = ipaddress.IPv4Address(value)
    except ValueError:
        return True  # not an address at all, e.g. `999.1.1.1`
    in_scope = (
        address.is_private or address.is_loopback or address.is_link_local or address.is_unspecified or address.is_multicast
    )
    if not in_scope:
        return True
    return value.rsplit(".", 1)[0] + "." in ALLOWED_ADDRESS_PREFIXES


def tracked_text_files() -> list[Path]:
    out = subprocess.run(
        ["git", "-C", str(REPO), "grep", "-lI", "--", ""],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode not in (0, 1):  # 1 == no match, which is fine
        out = subprocess.run(["git", "-C", str(REPO), "ls-files"], capture_output=True, text=True, check=True)
    return [REPO / line for line in out.stdout.splitlines() if line]


def _scan(
    pattern: re.Pattern[str],
    ignore: Callable[[str], bool] | None = None,
) -> list[str]:
    hits: list[str] = []
    for path in tracked_text_files():
        if path.resolve() == Path(__file__).resolve():
            continue  # this file names the tokens in order to forbid them
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            for match in pattern.finditer(line):
                if match.group(0).lower().endswith(ALLOWED_FQDN_SUFFIXES):
                    continue
                if ignore is not None and ignore(match.group(0)):
                    continue
                rel = path.relative_to(REPO)
                hits.append(f"{rel}:{number}: {match.group(0)}  --  {line.strip()[:110]}")
    return hits


@pytest.mark.parametrize("token", INTERNAL_HOST_TOKENS)
def test_no_internal_infrastructure_host_is_named(token: str) -> None:
    """`at1` is the container host, `ns3`/`netcup` are the two perimeters."""
    hits = _scan(re.compile(rf"\b{re.escape(token)}\b", re.IGNORECASE))
    assert not hits, (
        f"{token!r} names a machine in the operator's fleet; use a role word or a "
        "`<placeholder>` instead:\n  " + "\n  ".join(hits)
    )


def test_no_fqdn_names_an_individual_fleet_host() -> None:
    """`buyer-hub1.<domain>` in an example payload is still that host's address."""
    hits = _scan(PER_HOST_FQDN)
    assert not hits, (
        "a per-host FQDN names one machine; use `example.net` (RFC 2606), a shell "
        "variable, or a `<placeholder>`:\n  " + "\n  ".join(hits)
    )


def test_no_unpinned_address_appears() -> None:
    """A fleet address is caught by not being in the inventory, never by name."""
    hits = _scan(IPV4_LITERAL, ignore=_address_is_uninteresting)
    assert not hits, (
        "this address is not one the repository already documented. If it names a "
        "machine, replace it with an RFC 5737 documentation address "
        "(`192.0.2.x`, `198.51.100.x`, `203.0.113.x`) or a placeholder; if it is "
        "genuinely a new example, add its /24 to ALLOWED_ADDRESS_PREFIXES:\n  " + "\n  ".join(hits)
    )
