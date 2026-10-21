"""Fixture tests for journal-errors-textfile.py render() (ATTEST-PROM-FOLLOW-1).

AITBCJournalErrors evaluates aitbc_journal_error_messages > 0, but the exporter
emitted that metric only for units with hits — a quiet window produced a .prom
with just the scan metrics and the alert could not distinguish "no errors"
from "exporter blind". render() now emits a bare zero anchor whenever no unit
has an error count."""

from __future__ import annotations

import importlib.util
from collections import Counter
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


exporter = _load("journal_errors_textfile", REPO / "scripts/monitoring/journal-errors-textfile.py")


def test_render_emits_zero_anchor_when_no_unit_has_errors():
    counts: Counter[tuple[int, str]] = Counter({(0, "aitbc-market.service"): 3})
    text = exporter.render(counts, 1700000000.0, True)
    assert "aitbc_journal_error_messages 0\n" in text
    assert "aitbc_journal_error_messages{unit=" not in text
    assert 'aitbc_journal_warning_messages{unit="aitbc-market.service"} 3' in text


def test_render_emits_zero_anchor_when_window_empty():
    text = exporter.render(Counter(), 1700000000.0, True)
    assert "aitbc_journal_error_messages 0\n" in text
    assert "aitbc_journal_scan_success 1\n" in text
    assert "aitbc_journal_scan_timestamp_seconds 1700000000\n" in text


def test_render_no_anchor_when_a_unit_has_errors():
    counts: Counter[tuple[int, str]] = Counter({(1, "aitbc-blockchain-node.service"): 7})
    text = exporter.render(counts, 1700000000.0, True)
    assert 'aitbc_journal_error_messages{unit="aitbc-blockchain-node.service"} 7' in text
    assert "aitbc_journal_error_messages 0\n" not in text
