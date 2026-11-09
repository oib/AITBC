"""ServiceConfig uniqueness pin — #1397 (POOLHUB-DB-1).

models.py:151 comments "Add unique constraint for miner_id + service_type" but
``__table_args__`` is a no-op ``({"schema": None},)``. The create route does
select-then-insert, so a concurrent pair of POSTs can both insert; afterwards
every ``scalar_one_or_none`` lookup for that miner+service_type raises
MultipleResultsFound and the config endpoints 500 permanently.
"""

from __future__ import annotations

import pytest
from sqlalchemy import UniqueConstraint

from poolhub.models import ServiceConfig


@pytest.mark.xfail(
    strict=True,
    reason="ServiceConfig.__table_args__ is a no-op — no UniqueConstraint(miner_id, service_type); fix tracked in #1397",
)
def test_service_config_enforces_unique_miner_service_type():
    """(miner_id, service_type) must be unique — one config row per miner per service."""
    uniques = [constraint for constraint in ServiceConfig.__table__.constraints if isinstance(constraint, UniqueConstraint)]
    covered = {tuple(sorted(col.name for col in constraint.columns)) for constraint in uniques}
    assert ("miner_id", "service_type") in covered, (
        "ServiceConfig has no UniqueConstraint(miner_id, service_type) — "
        "duplicate rows make every scalar_one_or_none lookup raise; see #1397"
    )
