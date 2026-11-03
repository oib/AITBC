"""#902: the x3600 balance migration is retired.

The v0.5.10 hard-fork script rewrites balances by x3600 — the current
unit is 36,000,000 (docs/getting-started/unit-system.md), so the script
cannot apply to the live unit. Its remaining failure modes (partial
commit + rerun squares every balance, one-second backup window, no
chain_id scoping) leave with it.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_the_3600x_migration_is_gone():
    assert not (REPO / "scripts" / "migration" / "scale_balances_3600x.py").exists()


def test_current_unit_is_not_3600():
    unit_doc = REPO / "docs" / "getting-started" / "unit-system.md"
    assert "36,000,000" in unit_doc.read_text()
