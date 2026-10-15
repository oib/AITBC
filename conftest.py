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
import importlib.util
import os
import shutil
import sys
import tempfile


def pytest_addoption(parser):
    """Keep `--reruns` invocations parseable on hosts without the test tier.

    `addopts` no longer carries `--reruns` — retries are per-test
    `pytest.mark.flaky` marks — but scripts and muscle memory still pass the
    flag, which only pytest-rerunfailures defines. Production installs may
    lack the plugin, and without it pytest aborts collection with
    "unrecognized arguments". When the plugin is not importable, register the
    options as no-ops so parsing succeeds; reruns simply do not happen on
    those hosts.
    """
    if importlib.util.find_spec("pytest_rerunfailures") is None:
        parser.addoption(
            "--reruns",
            action="store",
            default="0",
            help="no-op: pytest-rerunfailures is not installed",
        )
        parser.addoption(
            "--reruns-delay",
            action="store",
            default="0",
            help="no-op: pytest-rerunfailures is not installed",
        )


# Read by `_load_env_file`. Set before collection imports anything, so the env files are
# never read in-process. Deployments do not set it and are unaffected.
os.environ.setdefault("AITBC_SKIP_ENV_FILES", "1")

# Same job, second leak, and a worse one (V23-73). Every service resolves its database path
# from `DATA_DIR`, which defaults to /var/lib/aitbc — the deployed machine's data directory.
# Nothing in the test process moved it, so `gpu_service`, `trading_service` and
# `market_service` built their engines against the live service databases at import time,
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


# The deployed-path set, shared by the env rewrite below and the session-finish
# guard. These are the roots aitbc/constants.py falls back to when its own env
# vars are unset, plus the variants an exported AITBC_HOME would derive
# (<home>/data|config|logs — mirrors constants.py). A value counts as deployed
# when its realpath IS one of these or sits INSIDE one — realpath resolves
# symlinks and strips trailing slashes.
#
# AITBC_TEST_DEPLOYED_DIRS extends — never replaces — the set, os.pathsep-
# separated, so tests can declare fake deployed roots under /tmp without the
# suite ever touching real /etc or /var. It can only widen what counts as
# deployed, so it cannot weaken the check.
def _deployed_paths() -> tuple[str, ...]:
    roots = ["/var/lib/aitbc", "/etc/aitbc", "/var/log/aitbc"]
    home = os.environ.get("AITBC_HOME")
    if home:
        roots += [os.path.join(home, sub) for sub in ("data", "config", "logs")]
    roots += [p for p in os.environ.get("AITBC_TEST_DEPLOYED_DIRS", "").split(os.pathsep) if p]
    return tuple(os.path.realpath(p) for p in roots)


_DEPLOYED_PATHS = _deployed_paths()


def _is_deployed_path(value: str) -> bool:
    real = os.path.realpath(value)
    return any(real == root or real.startswith(root + os.sep) for root in _DEPLOYED_PATHS)


# Values _redirect_env replaces below, printed by pytest_report_header so the
# rewrite is visible in every run's header rather than silent.
_AMBIENT_REPLACED: list[str] = []


def _redirect_env(var: str, scratch: str) -> None:
    """Point `var` at `scratch` unless a deliberate non-deployed value is set.

    Unset gets the scratch default. An ambient value resolving to a deployed
    path — a leaked service env on a live node — is replaced and recorded for
    the header. Anything else is a deliberate override and keeps winning,
    which is the reason this isn't a plain assignment.
    """
    current = os.environ.get(var)
    if current is None:
        os.environ[var] = scratch
    elif _is_deployed_path(current):
        _AMBIENT_REPLACED.append(f"{var}={current}")
        os.environ[var] = scratch


_redirect_env("AITBC_DATA_DIR", _TEST_DATA_DIR)

# CONFIG_DIR and LOG_DIR freeze from the env at the same import (aitbc.constants); a suite
# that binds them to /etc/aitbc or /var/log/aitbc first would trip the wallet conftest's
# early-binding guard in every combined run. Redirect them here so constants can only ever
# bind scratch paths, whichever suite's import lands first.
for _sub, _env in (("config", "AITBC_CONFIG_DIR"), ("logs", "AITBC_LOG_DIR")):
    os.makedirs(os.path.join(_TEST_DATA_DIR, _sub), exist_ok=True)
    _redirect_env(_env, os.path.join(_TEST_DATA_DIR, _sub))


def pytest_report_header(config):  # noqa: ANN001, ANN201, ARG001
    """Surface ambient deployed paths the env rewrite replaced."""
    if not _AMBIENT_REPLACED:
        return None
    return "aitbc-tests: ambient env pointing at deployed paths replaced with scratch: " + "; ".join(_AMBIENT_REPLACED)


def _deployed_engine_urls() -> set[str]:
    """URLs of every SQLAlchemy engine bound to a deployed path right now."""
    import gc

    try:
        from sqlalchemy.engine import Engine
        from sqlalchemy.ext.asyncio import AsyncEngine
    except ImportError:
        # No SQLAlchemy means no engines were ever built -- nothing to check.
        return set()

    found: set[str] = set()
    for obj in gc.get_objects():
        if not isinstance(obj, Engine | AsyncEngine):
            continue
        try:
            url = obj.url
        except AttributeError:
            # `gc.get_objects()` walks everything, including objects that are not finished.
            # An `AsyncEngine` whose `__init__` raised, or that is mid-collection, has no
            # `sync_engine` yet, and `.url` proxies to it -- so asking raises rather than
            # answers. An engine that cannot say where it points cannot be checked, and
            # taking down the session teardown to say so is strictly worse than skipping it.
            continue
        database = url.database
        if database and _is_deployed_path(database):
            found.add(str(url))
    return found


def _deployed_constants_bindings() -> set[str]:
    """aitbc.constants paths bound to a deployed location.

    constants freezes DATA_DIR/CONFIG_DIR/LOG_DIR at first import — if that happened
    before this conftest ran (an unusual plugin or -p load order), the env rewrite
    above was already too late. Reads sys.modules only; does not import the module
    to ask.
    """
    constants = sys.modules.get("aitbc.constants")
    if constants is None:
        return set()
    found: set[str] = set()
    for name in ("DATA_DIR", "CONFIG_DIR", "LOG_DIR"):
        bound = getattr(constants, name, None)
        if bound is not None and _is_deployed_path(str(bound)):
            found.add(f"aitbc.constants.{name} = {bound}")
    return found


def pytest_sessionfinish(session, exitstatus):  # noqa: ANN001, ANN201, ARG001
    """Fail the run if anything in it bound an engine or a constants path to a deployed location.

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
    found = _deployed_engine_urls() | _deployed_constants_bindings()

    if found:
        session.exitstatus = 1
        writer = session.config.get_terminal_writer()
        writer.line("")
        writer.line("Test run bound engines or constants paths to deployed locations:", red=True, bold=True)
        for url in sorted(found):
            writer.line(f"    {url}", red=True)
        writer.line(
            "Point the service at a throwaway file from its tests/conftest.py, the way "
            "apps/governance/tests/conftest.py does (V23-73).",
            red=True,
        )
