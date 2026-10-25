"""Guard: coordinator-api alembic history must have exactly one head.

Two heads abort `alembic upgrade head` in ExecStartPre — the service then
refuses to start on any node that pulls the offending commit.
"""

from alembic.config import Config
from alembic.script import ScriptDirectory
from pathlib import Path

APP = Path(__file__).resolve().parents[1]


def test_single_alembic_head():
    cfg = Config(str(APP / "alembic.ini"))
    cfg.set_main_option("script_location", str(APP / "alembic"))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert len(heads) == 1, f"coordinator-api has {len(heads)} alembic heads: {heads}"
