"""Phase-0 pin for JOBS-LIST-CACHE-KEY-1 (#806).

The two client-scoped list endpoints are wrapped in @cached("job_list"):
``GET /v1/jobs`` and ``GET /v1/jobs/history``. A job a client creates right
after a list call is invisible for the TTL, and create/cancel/complete
never invalidate.

Desired behaviour (pinned here): the endpoints are not cache-wrapped at
all — the filters are client-scoped and cheap, the simplest correct fix is
dropping @cached. This FAILS on current main (both handlers are wrapped);
that is the bug demonstration.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from coordinator_api.contexts.infrastructure.routers import client


def _is_cached(fn) -> bool:
    # fastapi_cache/decorators and the local @cached leave __wrapped__ /
    # a marker on the decorated handler.
    return hasattr(fn, "__wrapped__") or hasattr(fn, "__cache_key__")


def test_jobs_list_is_not_cached():
    assert not _is_cached(client.list_jobs), "GET /v1/jobs still wrapped in @cached — new jobs invisible until TTL"


def test_jobs_history_is_not_cached():
    assert not _is_cached(client.get_job_history), "GET /v1/jobs/history still wrapped in @cached"
