"""A module imported at collection time must not vandalise sys.path for everyone else.

``cli_gap_analysis`` used to strip every ``packages/py/*/src`` entry out of
``sys.path`` on import, to win a name collision between the repo-root ``aitbc``
package and ``packages/py/aitbc-core/src/aitbc``.  Those entries are installed by
.pth files in site-packages, so nothing ever put them back -- and because
``tests/test_cli_docs_sync.py`` imports this module while pytest is still
collecting, every test collected after it lost ``aitbc_sdk``,
``aitbc_agent_core``, ``aitbc_agent_sdk`` and ``aitbc_crypto``.  The root suite
aborted with ModuleNotFoundError collection errors that reproduced only in a
large enough run.
"""

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# One package per .pth file under packages/py.  Note that aitbc_agent_sdk.pth
# exposes a package called aitbc_agent, not aitbc_agent_sdk.
PTH_PACKAGES = ["aitbc_agent_core", "aitbc_agent", "aitbc_crypto", "aitbc_sdk", "aitbc_errors"]


@pytest.mark.parametrize("name", PTH_PACKAGES)
def test_a_pth_installed_package_survives_importing_cli_gap_analysis(name):
    importlib.import_module("cli_gap_analysis")
    assert importlib.import_module(name) is not None


def test_cli_gap_analysis_wins_its_collision_without_evicting_the_package_trees():
    """Run in a subprocess so the result does not depend on collection order."""
    code = (
        "import json, sys\n"
        'before = [p for p in sys.path if "packages/py" in p]\n'
        "import cli_gap_analysis  # noqa: F401\n"
        'after = [p for p in sys.path if "packages/py" in p]\n'
        'print(json.dumps({"before": before, "after": after, "first": sys.path[0]}))\n'
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout.strip().splitlines()[-1])

    # Guard against the assertion below passing vacuously on a venv without the
    # .pth files installed.
    assert data["before"], "no packages/py entries on sys.path -- nothing to protect"
    assert data["after"] == data["before"]

    # The behaviour the eviction was there to get, which the insert alone provides.
    assert data["first"] == str(REPO)


def _modules_shipped_under_packages_py():
    """Top-level module names actually shipped by packages/py/*/src."""
    found = set()
    for pkg in sorted((REPO / "packages" / "py").iterdir()):
        src = pkg / "src"
        if not src.is_dir():
            continue
        for mod in src.iterdir():
            if mod.is_dir() and (mod / "__init__.py").is_file():
                found.add(mod.name)
    return found


def test_pth_packages_covers_every_package_under_packages_py():
    """A new package under packages/py must be added to PTH_PACKAGES.

    Without this, adding a package silently gets no coverage from the tests
    above -- which is how aitbc_errors could have shipped untested. It also
    catches the reverse: a package removed from disk but left in the list.
    """
    on_disk = _modules_shipped_under_packages_py()
    listed = set(PTH_PACKAGES)
    assert on_disk == listed, (
        f"PTH_PACKAGES is out of sync with packages/py.\n"
        f"  shipped but not listed: {sorted(on_disk - listed)}\n"
        f"  listed but not shipped: {sorted(listed - on_disk)}\n"
        f"Update PTH_PACKAGES in {__file__}."
    )
