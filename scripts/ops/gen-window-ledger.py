#!/usr/bin/env python3
"""Generate the bc-2 reset window ledger skeleton from the runbook.

Parses the step tables in ``docs/deployment/bc2-reset-runbook.md``
(A-rows, B0–B5, C1–C7, the §D abort rows) plus the anchored ids that
live outside tables (FF1, PONR, F1–F3) and emits a fill-in markdown
ledger — one block per step with slots for the operator's verbatim go
line, the host ``date`` read, evidence, and verdict.

Because the skeleton is generated from the runbook file itself, a
runbook edit that adds or renames a step id fails the test in
``tests/test_gen_window_ledger.py`` instead of silently drifting.

Stdlib only. The emitted ledger is staging material (default
``tasks/window-ledgers/``) — filled ledgers are operator records, never
committed.

    gen-window-ledger.py [--runbook PATH] [--output PATH]
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_RUNBOOK = REPO / "docs" / "deployment" / "bc2-reset-runbook.md"
DEFAULT_OUTDIR = REPO / "tasks" / "window-ledgers"

# Steps that live outside the lettered tables. class_words drives the
# verbatim-line requirement; order is the emission order (interleaved
# into the parsed sequence by STEP_ORDER below).
EXTRA_STEPS: dict[str, dict] = {
    "FF1": {
        "title": "fast-forward every host to the named reset commit (no restart)",
        "class_words": ["operator-named"],
        "source": '"First window action — code convergence" bullet',
        "stop": "a dirty or non-ff host is skip+record, not a stop; the ledger records its HEAD and dirty paths",
    },
    "PONR": {
        "title": "first block above height 0 sealed on bc-2 — the point of no return",
        "class_words": ["event", "ungated"],
        "source": "§D — recorded event, not an action",
        "stop": "n/a — after this row there is no abort",
    },
    "F1": {
        "title": "post-PONR unfreeze — timers restored, market/exchange reopened, B1 env reverted",
        "class_words": ["operator-named"],
        "source": "§D paragraph + §F + §H row",
        "stop": "investigate — post-PONR findings are fix-forward",
    },
    "F1a": {
        "title": "maintenance notice taken down — own sub-item (modifies public content)",
        "class_words": ["operator-named"],
        "source": "§D F1 sub-item + §F",
        "stop": "investigate",
    },
    "F2": {
        "title": "reset record written in TOPOLOGY/",
        "class_words": ["ungated"],
        "source": "§F",
        "stop": "note",
    },
    "F3": {
        "title": ".pre-reset copies + offline backups retired (>=7 days after the cut)",
        "class_words": ["per-item word"],
        "source": "§F + §H row",
        "stop": "each item waits for its own word — an absent line means do not delete",
    },
}

GATED = ("operator-named", "per-item")
STEP_ORDER_PREFIX = ("A", "FF1", "B", "C", "PONR", "F", "ABORT")

VERBATIM = 'operator line: > "<verbatim — quote exactly, never paraphrase>"'
OPERATOR_CLASSES = ("operator", "operator-named", "per-item")


@dataclass
class Step:
    sid: str
    title: str
    class_words: list[str]
    evidence: str
    source: str = ""
    stop: str = ""
    gated: bool = field(init=False)

    def __post_init__(self) -> None:
        self.gated = any(w in " ".join(self.class_words) for w in GATED)


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_runbook(text: str) -> list[Step]:
    """Extract step rows from the runbook's markdown tables."""
    steps: list[Step] = []
    in_abort_table = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("## D."):
            in_abort_table = True
        elif line.startswith("## "):
            in_abort_table = False
        if not line.startswith("|") or "---" in line:
            continue
        cells = _cells(line)
        if not cells or cells[0] in ("#", "step", "reached", "unit", "item", "host", "decision"):
            continue
        sid = cells[0]
        if in_abort_table:
            # §D rows: "freeze only (§B)", "C1 services stopped", …
            if sid.startswith("C5+"):
                continue  # the PONR row — no abort past it
            ref = re.search(r"(B\d*|C\d+|freeze)", sid)
            steps.append(
                Step(
                    sid=f"ABORT@{ref.group(0) if ref else sid.split()[0]}",
                    title=f"abort if reached {sid.split('(')[0].strip()}",
                    class_words=["operator-named"],
                    evidence=f"abort action: {cells[1]}",
                    source="§D abort table",
                    stop="each abort is its own operator-named action",
                )
            )
            continue
        if not re.fullmatch(r"[ABC]\d+", sid):
            continue
        if len(cells) < 4:
            # 3-cell rows are the proposal/line-shapes table — same
            # leading id cell, but not step definitions
            continue
        title = re.sub(r"\s+", " ", cells[1])[:90]
        blob = " ".join(cells[1:]).lower()
        classes = [
            w for w in ("operator-named", "per-item word", "ungated", "standing", "validator-interrupting") if w in blob
        ]
        classes.append("operator" if "operator" in blob and "operator-named" not in blob else "")
        # evidence column = the cell right after the one carrying the
        # class word (column order differs between the A, B and C tables)
        evidence = ""
        for i, cell in enumerate(cells[1:], start=1):
            if any(
                w in cell.lower() for w in ("operator", "ungated", "per-item", "standing", "director", "coder", "repo", "done")
            ):
                evidence = cells[i + 1] if i + 1 < len(cells) else ""
                break
        steps.append(
            Step(sid=sid, title=title, class_words=[c for c in classes if c], evidence=re.sub(r"\s+", " ", evidence)[:160])
        )
    return steps


def ordered(steps: list[Step]) -> list[Step]:
    """Emission order: A1…A13, FF1, B0…B5, C1…C7, PONR, F1, F1a, F2, F3, ABORT@*."""
    by_id = {s.sid: s for s in steps}
    by_id.update(
        {
            sid: Step(sid, m["title"], m["class_words"], "", source=m.get("source", ""), stop=m.get("stop", ""))
            for sid, m in EXTRA_STEPS.items()
        }
    )

    def key(s: Step) -> tuple[int, int, str]:
        m = re.fullmatch(r"([A-Z]+)(\d*)([a-z]?)(?:@(.+))?", s.sid)
        letter, num, sub, at = m.groups()
        rank = {p: i for i, p in enumerate(("A", "FF", "B", "C", "PONR", "F", "ABORT"))}.get(
            "PONR" if s.sid == "PONR" else letter, 99
        )
        at_key = {"freeze": "0"}.get(at, f"1{at}") if at else ""
        return (rank, int(num or 0), sub + at_key)

    return sorted(by_id.values(), key=key)


def emit(steps: list[Step], runbook_sha: str, runbook_rel: str) -> str:
    out = [
        "# bc-2 reset window ledger — <window date>",
        "",
        f"Generated from `{runbook_rel}` (sha256 `{runbook_sha[:16]}…`) —",
        "regenerate after any runbook edit; a filled ledger is never committed.",
        "",
        "## Baseline — record before the first gated step",
        "",
        "- window named (A13): `<date>`  ·  reset commit (A7): `<sha>`",
        "- host `date -u` reads: hub `__` hub1 `__` node0 `__` node1 `__` node2 `__`",
        "- PID/AET snapshot: `systemctl show -p ActiveEnterTimestamp,MainPID` per `aitbc-*` unit per host → `<file>`",
        "",
        "**Phase-0 fresh-start check** — every `aitbc-*` unit's",
        "`ActiveEnterTimestamp` must predate the baseline: a newer timestamp",
        "means a prior run already completed → **STOP and report; do not",
        "restart again.**  [ ] recorded",
        "",
        "---",
        "",
    ]
    for s in steps:
        out.append(f"## STEP {s.sid} — {s.title}")
        out.append(f"- class: {', '.join(s.class_words) or 'see runbook'}")
        if s.source:
            out.append(f"- source: {s.source}")
        if s.gated:
            out.append(f"- {VERBATIM}")
        else:
            out.append("- operator line: n/a (ungated — record who ran it anyway if a human acted)")
        out.append("- host `date`: `__`")
        if s.sid == "C5":
            out.append(
                "- **fresh-start check before starting**: no `aitbc-blockchain-node` unit may have a timestamp newer than baseline → [ ]"
            )
        if s.evidence:
            out.append(f"- evidence (runbook): {s.evidence}")
        out.append("- evidence pasted: `__`")
        if s.stop:
            out.append(f"- stop rule: {s.stop}")
        out.append("- verdict: PASS / FAIL / SKIP")
        out.append("")
    return "\n".join(out)


def lint(steps: list[Step]) -> list[str]:
    """Rule a gated row can violate: it must carry the verbatim-line slot."""
    return [s.sid for s in steps if s.gated and VERBATIM not in emit([s], "x", "x")]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runbook", default=str(DEFAULT_RUNBOOK))
    ap.add_argument(
        "--output", default=None, help="default: tasks/window-ledgers/bc2-window-ledger.md (staging, never committed)"
    )
    args = ap.parse_args(argv)

    text = Path(args.runbook).read_text()
    steps = ordered(parse_runbook(text))
    if not steps:
        print("no steps parsed — runbook table format changed?", file=sys.stderr)
        return 2
    out_path = Path(args.output) if args.output else DEFAULT_OUTDIR / "bc2-window-ledger.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        emit(
            steps,
            hashlib.sha256(text.encode()).hexdigest(),
            str(Path(args.runbook).relative_to(REPO) if Path(args.runbook).is_relative_to(REPO) else args.runbook),
        )
    )
    gated = sum(1 for s in steps if s.gated)
    print(f"wrote {out_path} — {len(steps)} steps ({gated} gated, verbatim slots attached)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
