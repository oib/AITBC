"""V23-10: an app's test suite must not be able to go dark without anything noticing.

`3fc1333fe` (2026-07-07) renamed `apps/agent-coordinator/src/app` to `src/agent_app` and did
not update the tests, which import `from src.app...`. All three modules — including
`test_security_agent_coordinator.py` — failed at collection from that day on. Nothing
reported it: CI runs only `coordinator-api` and `blockchain-node`, so no other app's suite is
executed anywhere.

Running every app's suite in CI is the real fix and is not this test's job. This checks the
cheap half that would still have caught it on day one: every top-level package an app's tests
import must actually be importable from that app's root.
"""

import ast
import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[2]
APPS_DIR = REPO_ROOT / "apps"

# Checking the import graph, not resolving it: a name imported inside a `try` that the test
# is prepared to lose is not a broken suite.
PROBE = """
import importlib.util, json, sys
for entry in reversed({roots!r}):
    sys.path.insert(0, entry)
missing = [name for name in {names!r} if importlib.util.find_spec(name) is None]
print(json.dumps(missing))
"""


def _apps() -> list[Path]:
    return sorted(p for p in APPS_DIR.iterdir() if p.is_dir() and (p / "tests").is_dir())


def _import_roots(app: Path) -> list[Path]:
    """The paths pytest will put on sys.path for this app.

    Read from the app's own ``[tool.pytest.ini_options] pythonpath`` when it has one, rather
    than assumed: an app's config is what actually decides whether its tests can import, and
    ``apps/miner`` is the case that proves it — half-migrated to ``src/`` with
    ``production_miner.py`` still at the root, so neither root alone is right.
    """
    pyproject = app / "pyproject.toml"
    if pyproject.is_file():
        try:
            config = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            configured = config["tool"]["pytest"]["ini_options"]["pythonpath"]
        except (tomllib.TOMLDecodeError, KeyError, OSError):
            configured = None
        if configured:
            return [(app / entry).resolve() for entry in configured]

    src = app / "src"
    return [src if src.is_dir() else app]


def _top_level_imports(test_file: Path) -> set[str]:
    """Top-level module names imported at module scope.

    Module scope only — ``tree.body``, not ``ast.walk``. An import inside a test function is
    reached only when that test runs and often follows a deliberate ``sys.path`` insertion
    (``apps/marketplace``'s tests import ``gpu_service`` that way). Those do not decide
    whether the suite collects, which is what this is about.
    """
    try:
        tree = ast.parse(test_file.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return set()

    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


# V23-10 counted seven flat-layout apps. Checked against the tree, it is five.
#
#   archive  is not an app — three files under peertube-transcoder/, one of them
#            DEPRECATED.md. A deprecation graveyard counted as a flat-layout service.
#   miner    is half-migrated: src/miner_app/ exists and production_miner.py is still at the
#            root, which is why its own pytest pythonpath needed both entries.
#
# The finding's conclusion was that migrating the rest is "not a batch job" — take them one
# at a time when there is a reason to touch them. So this does not demand they be fixed; it
# pins the count so it cannot grow, and a migration is a deletion from this list.
FLAT_LAYOUT_APPS = frozenset({"blockchain-explorer", "exchange", "ffmpeg", "whisper", "zk-circuits"})


def test_no_new_app_adopts_the_flat_layout() -> None:
    """New apps use ``src/``. The known exceptions are grandfathered, and only shrink.

    v0.22's APP-54 found the concrete cost on ``exchange``: the flat layout is why it cannot
    use shared ``aitbc.auth`` and hand-rolls its own request handling and API-key check.
    """
    flat = {p.name for p in APPS_DIR.iterdir() if p.is_dir() and not (p / "src").is_dir() and any(p.glob("*.py"))}

    new = sorted(flat - FLAT_LAYOUT_APPS)
    assert not new, (
        f"new flat-layout app(s): {new}. Use the src/ layout — the test of whether the "
        f"migration is finished is 'can it import aitbc.auth?'. If this is deliberate, add it "
        f"to FLAT_LAYOUT_APPS with a reason."
    )

    migrated = sorted(FLAT_LAYOUT_APPS - flat)
    assert not migrated, f"{migrated} now use the src/ layout — remove them from FLAT_LAYOUT_APPS so the count keeps falling."


@pytest.mark.parametrize("app", _apps(), ids=lambda p: p.name)
def test_app_tests_import_packages_that_exist(app: Path) -> None:
    """Every package an app's tests import must resolve from that app's import root."""
    names: set[str] = set()
    for test_file in sorted((app / "tests").rglob("test_*.py")):
        names |= _top_level_imports(test_file)

    if not names:
        pytest.skip(f"{app.name} has no test imports to check")

    # `src` is never importable -- there is no src/__init__.py under either layout -- so
    # `from src.app...` is the specific mistake this exists to catch, and find_spec in a
    # subprocess would not necessarily agree about it.
    src_prefixed = {n for n in names if n == "src"}

    result = subprocess.run(
        [sys.executable, "-c", PROBE.format(roots=[str(r) for r in _import_roots(app)], names=sorted(names - src_prefixed))],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"probe failed for {app.name}: {result.stderr}"

    missing = set(json.loads(result.stdout))
    broken = sorted(missing | src_prefixed)

    assert not broken, (
        f"{app.name}: its tests import {broken}, which cannot be imported from "
        f"{[str(r.relative_to(REPO_ROOT)) for r in _import_roots(app)]}. The suite does not collect, so it is "
        f"not running -- and outside coordinator-api and blockchain-node, no CI job would "
        f"tell you. Fix the import or delete the test; do not leave it uncollectable."
    )
