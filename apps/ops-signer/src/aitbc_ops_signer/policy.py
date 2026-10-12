"""Request policy: allow-list, amount caps, memo requirement.

All policy lives here and only here -- the caller (agent) can propose a
payment but cannot influence any bound. Refusals return a stable reason
code for the audit line; nothing about the refusal leaks configuration
contents (no list entries, no cap values beyond the public design doc).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Task ids look like S-10, BR-8, SEC-2, K-4, O-9, KC-3, ACT-1, M-2.
MEMO_PATTERN = re.compile(r"^[A-Z]{1,8}-[0-9]{1,4}$")

_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


class Refused(Exception):
    """A policy refusal. Carries the audit reason code."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class PaymentRequest:
    to: str
    amount_units: int
    memo: str
    dry_run: bool = False


def normalize_address(addr: str) -> str:
    """Lowercase hex comparison -- the chain treats addresses case-insensitively."""
    if not isinstance(addr, str) or not _ADDRESS_RE.match(addr.strip()):
        raise Refused("bad_address")
    return "0x" + addr.strip()[2:].lower()


def load_allowlist(path: str | Path) -> frozenset[str]:
    """Parse the allow-list: one 0x address per line, '#' comments, blanks ok.

    A malformed line refuses the whole file -- a broken list must fail
    closed, not silently shrink to a subset the operator did not write.
    """
    out: set[str] = set()
    try:
        lines = Path(path).read_text().splitlines()
    except OSError:
        raise Refused("allowlist_unreadable") from None
    for lineno, raw in enumerate(lines, 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if not _ADDRESS_RE.match(line):
            raise Refused(f"allowlist_malformed_line_{lineno}")
        out.add("0x" + line[2:].lower())
    return frozenset(out)


def parse_request(payload: dict) -> PaymentRequest:
    """Validate the wire shape. Anything off-shape refuses."""
    if not isinstance(payload, dict):
        raise Refused("malformed")
    if payload.get("op") != "sign_payment":
        raise Refused("unknown_op")
    amount = payload.get("amount_units")
    if isinstance(amount, bool) or not isinstance(amount, int):
        raise Refused("bad_amount")
    memo = payload.get("memo")
    if not isinstance(memo, str) or not MEMO_PATTERN.match(memo):
        raise Refused("bad_memo")
    return PaymentRequest(
        to=normalize_address(payload.get("to") or ""),
        amount_units=amount,
        memo=memo,
        dry_run=bool(payload.get("dry_run", False)),
    )


def check_amount(req: PaymentRequest, *, max_per_tx: int) -> None:
    if req.amount_units <= 0:
        raise Refused("bad_amount")
    if req.amount_units > max_per_tx:
        raise Refused("over_tx_cap")


def check_recipient(req: PaymentRequest, allowlist: frozenset[str]) -> None:
    if req.to not in allowlist:
        raise Refused("not_allowlisted")
