"""Phase-0 pin for JOBS-LIST-CACHE-KEY-1 (#806).

The two client-scoped list endpoints are wrapped in @cached("job_list"):
``GET /v1/jobs`` and ``GET /v1/jobs/history``. A job a client creates right
after a list call is invisible for the TTL, and create/cancel/complete
never invalidate.

Desired behaviour (pinned here): neither handler carries the @cached
decorator — the lists are client-scoped and cheap, so the simplest correct
fix is dropping it. Decorator presence is checked at source level because
every decorator in the stack sets __wrapped__, making a runtime check
ambiguous. FAILS on current main (both handlers are wrapped); that is the
bug demonstration.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from coordinator_api.contexts.infrastructure.routers import client

_SRC = Path(client.__file__).read_text()


def _decorators(fn_name: str) -> str:
    m = re.search(rf"((?:^\s*@.*\n)+)^\s*def {fn_name}\(", _SRC, re.M)
    return m.group(1) if m else ""


def test_jobs_list_is_not_cached():
    assert "@cached" not in _decorators("list_jobs"), "GET /v1/jobs still wrapped in @cached — new jobs invisible until TTL"


def test_jobs_history_is_not_cached():
    assert "@cached" not in _decorators("get_job_history"), "GET /v1/jobs/history still wrapped in @cached"
