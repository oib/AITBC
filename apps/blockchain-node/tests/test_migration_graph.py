"""Regression tests for the blockchain-node Alembic migration graph.

These read the graph through ``ScriptDirectory`` rather than shelling out, so
they do not import ``migrations/env.py`` and do not need a database.
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

_APP_ROOT = Path(__file__).resolve().parent.parent

_BACKFILL = "9f8e7d6c5b4a"
_ESCROW_CHAIN_ID = "c9a4f1e2b73d"
_ESCROW_STATUS_COLUMNS = "498540b266b4"


def _scripts() -> ScriptDirectory:
    return ScriptDirectory.from_config(Config(str(_APP_ROOT / "alembic.ini")))


def test_the_graph_has_exactly_one_head() -> None:
    """More than one head is not a style problem: it breaks deployment.

    ``alembic upgrade head`` refuses to run with multiple heads, so
    ``scripts/deployment/run-migrations.sh`` fails outright for this app --
    on every host, including ones whose schema is already correct.
    """
    heads = _scripts().get_heads()
    assert len(heads) == 1, f"expected one head, found {len(heads)}: {sorted(heads)}"


def test_the_escrow_backfill_runs_after_the_columns_it_writes() -> None:
    """The back-fill writes columns another migration adds, so it must follow it.

    It inserts ``escrow.chain_id`` (added by c9a4f1e2b73d) and ``escrow.status``
    / ``escrow.lock_tx_hash`` (added by 498540b266b4). It was originally chained
    to the branchpoint that predates both, which declared a dependency it does
    not have and omitted the two it does.
    """
    scripts = _scripts()
    ancestors = {rev.revision for rev in scripts.iterate_revisions(_BACKFILL, "base")}
    for required in (_ESCROW_CHAIN_ID, _ESCROW_STATUS_COLUMNS):
        assert required in ancestors, f"{_BACKFILL} must run after {required}, which adds columns it writes"
