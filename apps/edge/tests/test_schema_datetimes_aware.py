"""#1386: remaining edge schema datetime defaults must be timezone-aware.

metrics.py and database.py still used naive ``datetime.utcnow`` after the
serve.py/gpu.py/island.py sweep in f0df2459b — persisted rows would mix naive
and aware ISO strings. All schema defaults now use ``datetime.now(UTC)``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from aitbc_edge.schemas.database import EdgeDatabase
from aitbc_edge.schemas.metrics import EdgeMetrics


def test_metrics_and_database_schema_defaults_are_timezone_aware():
    now = datetime.now(UTC)
    instances = [
        EdgeMetrics(metric_id="m1", gpu_id="g1"),
        EdgeDatabase(database_id="db1", island_id="isl-1", capacity_gb=10),
    ]
    for instance in instances:
        model = type(instance)
        for field_name in ("created_at", "updated_at"):
            value = getattr(instance, field_name, None)
            if value is not None:
                assert value.tzinfo is not None, f"{model.__name__}.{field_name} is naive"
                assert abs((value - now).total_seconds()) < 60
