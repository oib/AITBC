"""CI-FAKEASYNC-GATE-SCOPE-AND-EXEMPTION-1 — the fake-async ratchet covers
every route file in the repo (not only apps/*/src) and its exemption only
matches real task-scheduling calls, not any call mentioning "asyncio".
"""

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ci" / "check-fake-async.py"


@pytest.fixture(scope="module")
def check():
    spec = importlib.util.spec_from_file_location("check_fake_async", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(tmp_path: Path, rel: str, body: str) -> Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    return p


def test_non_apps_route_file_is_in_scope(check):
    assert check._route_file("apps/blockchain-explorer/routers/alerts.py")
    assert check._route_file("aitbc/routers/x.py")
    assert check._route_file("cli/pkg/routes/y.py")
    assert not check._route_file("apps/x/tests/routers/test_r.py")
    assert not check._route_file("apps/x/src/services/svc.py")


def test_task_scheduling_call_still_exempts(check, tmp_path):
    p = _write(
        tmp_path,
        "routers/a.py",
        "import asyncio\n\nasync def h():\n    asyncio.create_task(work())\n",
    )
    assert check.violations(p) == []


def test_other_asyncio_calls_no_longer_exempt(check, tmp_path):
    p = _write(
        tmp_path,
        "routers/b.py",
        "import asyncio, time\n\nasync def h():\n    asyncio.iscoroutinefunction(work)\n    time.sleep(1)\n",
    )
    assert check.violations(p) == [(3, "h")]


def test_explorer_handlers_no_longer_fake_async(check):
    assert check.violations(REPO_ROOT / "apps/blockchain-explorer/routers/alerts.py") == []
    assert check.violations(REPO_ROOT / "apps/blockchain-explorer/routers/export.py") == []
