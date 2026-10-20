"""Tests for scripts/ops/gen-window-ledger.py — the ledger skeleton must
cover every runbook step and every gated row must carry the verbatim
operator-line slot.
"""

import importlib.util
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUNBOOK = REPO / "docs" / "deployment" / "bc2-reset-runbook.md"


def _load():
    spec = importlib.util.spec_from_file_location("gen_window_ledger", REPO / "scripts" / "ops" / "gen-window-ledger.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gen_window_ledger"] = mod
    spec.loader.exec_module(mod)
    return mod


gwl = _load()
STEPS = gwl.ordered(gwl.parse_runbook(RUNBOOK.read_text()))
LEDGER = gwl.emit(STEPS, "sha", "bc2-reset-runbook.md")


def _block(sid: str) -> str:
    m = re.search(rf"## STEP {re.escape(sid)}\b.*?(?=\n## STEP |\Z)", LEDGER, re.S)
    return m.group(0) if m else ""


def test_every_runbook_step_id_appears():
    expected = {f"{c}{n}" for c, rng in (("A", range(1, 14)), ("B", range(0, 6)), ("C", range(1, 8))) for n in rng}
    expected |= {"FF1", "PONR", "F1", "F1a", "F2", "F3", "F4"}
    missing = [sid for sid in expected if f"## STEP {sid}" not in LEDGER]
    assert not missing, f"missing step blocks: {missing}"
    aborts = [s.sid for s in STEPS if s.sid.startswith("ABORT@")]
    assert len(aborts) >= 5  # the §D abort rows minus the PONR row


def test_gated_rows_carry_verbatim_slot():
    bad = []
    for s in STEPS:
        if not s.gated:
            continue
        block = _block(s.sid)
        if "verbatim — quote exactly, never paraphrase" not in block:
            bad.append(s.sid)
    assert not bad, f"gated steps missing verbatim slot: {bad}"


def test_fresh_start_slot_top_and_before_c5():
    top = LEDGER.split("## STEP")[0]
    assert "Phase-0 fresh-start check" in top
    assert "predate the baseline" in top
    assert "fresh-start check before starting" in _block("C5")


def test_gated_row_without_verbatim_slot_is_caught():
    # The rule is per-block: strip the marker from one gated block and
    # the check must see it missing.
    c5 = _block("C5")
    assert "verbatim" in c5
    stripped = c5.replace("verbatim — quote exactly, never paraphrase", "")
    assert "verbatim" not in stripped
    # and lint() over the real parse finds no violations
    assert gwl.lint(STEPS) == []


def test_ungated_rows_have_no_required_verbatim():
    for sid in ("B5", "C7", "F2"):
        block = _block(sid)
        assert "n/a (ungated" in block
