"""#2778: edge input bounds — body cap, limit validation, bounded selects."""

from __future__ import annotations

from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
EDGE = REPO / "apps" / "edge" / "src" / "aitbc_edge"


def test_app_has_request_body_cap() -> None:
    src = (EDGE / "main.py").read_text()
    assert "RequestValidationMiddleware" in src
    assert "max_request_size" in src


def test_limit_params_are_query_bounded() -> None:
    for rel in ("routers/metrics.py", "routers/gpu.py"):
        src = (EDGE / rel).read_text()
        assert "Query(ge=1, le=" in src, f"{rel} limit param is unbounded"


def test_unbounded_selects_are_capped() -> None:
    db_src = (EDGE / "services" / "database_service.py").read_text()
    assert ".limit(MAX_LIST_ROWS)" in db_src
    island_src = (EDGE / "services" / "island_service.py").read_text()
    assert ".limit(MAX_LIST_ROWS)" in island_src
    # region filter must happen in SQL, not after loading all rows
    assert 'extra_data["region"].as_string()' in island_src
