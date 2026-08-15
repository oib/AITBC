"""Repo-wide test setup, imported by pytest before any test module (V23-69).

Its one job is to stop the *deployed machine's* configuration from leaking into the test
process. `cli/aitbc_cli/commands/coin_requests.py` reads `/etc/aitbc/blockchain.env` and
friends into `os.environ` at import time — deliberately, because the CLI needs those values
before it imports storage — and importing that module during collection puts the hub's real
`BLOCKCHAIN_RPC_URL`, `GENESIS_*` and `AGENT_DB_PATH` in front of every test that runs
afterwards.

That made the suite depend on which machine it ran on. Tests asserting a config default read
the hub's value instead and failed here while passing in a clean container; the reverse is
worse, since a test can pass against deployed state that a CI box would never have. Both stayed
invisible while the app suites were not collected at all.
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile

# Read by `_load_env_file`. Set before collection imports anything, so the env files are
# never read in-process. Deployments do not set it and are unaffected.
os.environ.setdefault("AITBC_SKIP_ENV_FILES", "1")

# Same job, second leak, and a worse one (V23-73). Every service resolves its database path
# from `DATA_DIR`, which defaults to /var/lib/aitbc — the deployed machine's data directory.
# Nothing in the test process moved it, so `gpu_service`, `trading_service` and
# `marketplace_service` built their engines against the live service databases at import time,
# `init_db()` ran `create_all` on them through the FastAPI lifespan, and
# `test_get_consumer_gpu_profiles` asserted on rows that production happened to hold. The
# blockchain suite went further and *created* directories there: `chain-a/` and `chain-sig/`,
# named after test-only chain IDs, sitting in the deployed data directory with real chain
# databases beside them.
#
# `DATA_DIR` already reads `AITBC_DATA_DIR`, so pointing that one variable at a temporary
# directory moves every derived path at once — including any service added later, which is the
# reason to fix it here rather than in a conftest per app. `setdefault`, so a deliberate
# override still wins.
_TEST_DATA_DIR = tempfile.mkdtemp(prefix="aitbc-tests-data-")
atexit.register(shutil.rmtree, _TEST_DATA_DIR, True)
os.makedirs(os.path.join(_TEST_DATA_DIR, "data"), exist_ok=True)
os.environ.setdefault("AITBC_DATA_DIR", _TEST_DATA_DIR)

# What the guard below is guarding against: the path `DATA_DIR` would have resolved to without
# the line above. Spelled out here rather than read from `aitbc.constants`, because importing
# that module is what freezes `DATA_DIR` — and by the time the guard runs, it holds the
# override. Mirrors the default in aitbc/constants.py.
_DEPLOYED_DATA_DIR = os.path.join(os.environ["AITBC_HOME"], "data") if os.environ.get("AITBC_HOME") else "/var/lib/aitbc"


def pytest_sessionfinish(session, exitstatus):  # noqa: ANN001, ANN201, ARG001
    """Fail the run if anything in it bound an engine to a deployed database.

    The default above is a safety net, not a guarantee: a service can reach a deployed path
    without going through `DATABASE_URL` at all — its own variable, a settings object, a
    hard-coded string. Rather than enumerate the ways, this looks at what the session actually
    built. Every SQLAlchemy engine alive at the end of the run is checked, so a new service, or
    an old one that changes how it resolves its URL, is covered without anyone remembering to
    add it here.

    Checked at session finish rather than as a test, because a test would have to import the
    storage modules to inspect them, and importing them early is what binds the engine in the
    first place — the guard would decide the answer it was meant to measure.
    """
    import gc

    from sqlalchemy.engine import Engine
    from sqlalchemy.ext.asyncio import AsyncEngine

    deployed = os.path.realpath(_DEPLOYED_DATA_DIR)
    found: set[str] = set()
    for obj in gc.get_objects():
        if not isinstance(obj, Engine | AsyncEngine):
            continue
        database = obj.url.database
        if database and os.path.realpath(database).startswith(deployed):
            found.add(str(obj.url))

    if found:
        session.exitstatus = 1
        writer = session.config.get_terminal_writer()
        writer.line("")
        writer.line("Test run bound engines to deployed databases:", red=True, bold=True)
        for url in sorted(found):
            writer.line(f"    {url}", red=True)
        writer.line(
            "Point the service at a throwaway file from its tests/conftest.py, the way "
            "apps/governance/tests/conftest.py does (V23-73).",
            red=True,
        )
