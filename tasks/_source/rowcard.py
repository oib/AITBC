#!/usr/bin/env python3
"""Row card: a register row as a fenced YAML block in its Gitea issue body (GITEA-TASKING-1, P1).

  rowcard.py ROW            print the card for ROW
  rowcard.py --self-test    parse(render(row)) == row for every open row and 50 closed rows; splice keeps outside text

The block sits between BEGIN and END markers. Text outside the markers is never rewritten (coders and other
sessions may have written it). The card carries every row field except `issue` (lossless, so `sync.py pull`
can rebuild the row); the owner/* and state/* labels carry owner and state for filtering.
"""

import json
import os
import sys
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
BEGIN = "<!-- aitbc-row:begin (written by tasks/_source/sync.py; text outside this block is kept) -->"
END = "<!-- aitbc-row:end -->"
OPEN, CLOSE = "```yaml\n", "\n```"
SKIP = ("issue",)


def fields(row):
    return {k: v for k, v in row.items() if k not in SKIP}


def render(row):
    y = yaml.safe_dump(fields(row), sort_keys=False, allow_unicode=True, width=10**6, default_flow_style=False)
    return f"{BEGIN}\n{OPEN}{y.rstrip(chr(10))}{CLOSE}\n{END}"


def _span(body):
    """(start, end) of the whole block in body, or None; the first END after the first BEGIN closes it."""
    b = body.find(BEGIN)
    if b < 0:
        return None
    e = body.find(END, b)
    return (b, e + len(END)) if e >= 0 else None


def parse(body):
    """The row fields from an issue body, or None when it has no (well-formed) card."""
    body = (body or "").replace("\r\n", "\n")
    sp = _span(body)
    if not sp:
        return None
    inner = body[sp[0] + len(BEGIN) : sp[1] - len(END)].strip("\n")
    if not (inner.startswith(OPEN) and inner.endswith(CLOSE)):
        return None
    try:
        data = yaml.safe_load(inner[len(OPEN) : -len(CLOSE)])
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


OWNERS = ("A", "B", "C", "operator")


def scoped(names, scope):
    """The labels of one exclusive scope (owner/..., state/...) among names."""
    return sorted(n for n in names if n.startswith(scope + "/"))


def expected_labels(row, names):
    """(owner label or None, state label or None) a row should carry, given the issue's current label names.

    needs-verify (the legacy label 58, or state/needs-verify) wins while the row is open; state/working is kept
    while the row is ready (coders set it, the register has no such field); otherwise held when not ready, else ready.
    A closed row carries no state label."""
    owner = f"owner/{row['owner']}" if row.get("owner") in OWNERS else None
    if row.get("status") == "closed":
        return owner, None
    if "needs-verify" in names or "state/needs-verify" in names:
        return owner, "state/needs-verify"
    if not row.get("ready"):
        return owner, "state/held"
    return owner, "state/working" if "state/working" in names else "state/ready"


def diff(card, row):
    """Field names that differ between a parsed card and a register row."""
    f = fields(row)
    return sorted(k for k in set(card) | set(f) if card.get(k) != f.get(k))


def splice(body, card):
    """Body with the card replaced (or appended); everything outside the block stays byte for byte."""
    body = (body or "").replace("\r\n", "\n")
    sp = _span(body)
    if sp:
        return body[: sp[0]] + card + body[sp[1] :]
    return (body.rstrip("\n") + "\n\n" if body.strip() else "") + card + "\n"


def self_test():
    rows = json.load(open(os.path.join(HERE, "tasks.json")))
    sample = [r for r in rows if r.get("status") != "closed"] + [r for r in rows if r.get("status") == "closed"][-50:]
    bad = []
    for r in sample:
        card = render(r)
        if parse(card) != fields(r):
            bad.append(f"{r['id']}: round trip differs")
        b1 = splice("Row: X\n\nfree text a coder wrote\n", card)
        if splice(b1, card) != b1 or not b1.startswith("Row: X\n\nfree text a coder wrote\n") or parse(b1) != fields(r):
            bad.append(f"{r['id']}: splice not idempotent or outside text changed")
    if parse("no card here") is not None or parse(BEGIN + "\nbroken\n" + END) is not None:
        bad.append("parse accepted a body without a well-formed card")
    print(f"self-test: {len(sample)} rows, {len(bad)} failure(s)")
    [print("  ", x) for x in bad]
    return not bad


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        sys.exit(0 if self_test() else 1)
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    rows = json.load(open(os.path.join(HERE, "tasks.json")))
    r = next((x for x in rows if x["id"] == sys.argv[1]), None)
    if r is None:
        sys.exit(f"{sys.argv[1]}: no such row")
    print(render(r))
