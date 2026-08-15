"""The two `sys.path` rules that keep test module names unambiguous (V23-70).

Ten directories in this repo are called `tests`. Which module name pytest gives a file under
one of them depends on `sys.path`, so a single stray entry can rename every suite at once —
and rename them only *sometimes*, since a `sys.path.insert` inside a conftest takes effect
partway through collection. A file imported under two names becomes two module objects with
separate state, and then a fixture that patches a class attribute in one copy is invisible to
a test reading it from the other.

That is not hypothetical. `apps/exchange/tests/conftest.py` inserted `parents[2]` — `apps/`,
under a comment saying "repo root" — and ten agent-coordinator faucet tests began reporting
that no transaction had been signed when the endpoint had signed correctly. They passed when
run alone and failed in a full run, which is the combination that costs a day (V23-69).

Both rules below are about the same thing: never put a directory on `sys.path` that sits above
a `tests` package.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
APPS = REPO_ROOT / "apps"


def _app_test_dirs() -> list[Path]:
    return sorted(p for p in APPS.glob("*/tests") if p.is_dir())


def test_the_apps_directory_is_never_on_sys_path() -> None:
    """`apps/` is above every app's tests, so it renames all of them at once."""
    on_path = [entry for entry in sys.path if entry and Path(entry).resolve() == APPS]

    assert not on_path, (
        f"{APPS} is on sys.path. Every apps/*/tests module is renamed while it is there — "
        "put the individual app directory on the path instead, never apps/ itself."
    )


@pytest.mark.parametrize("tests_dir", _app_test_dirs(), ids=lambda p: p.parent.name)
def test_a_tests_package_never_has_its_app_root_on_sys_path(tests_dir: Path) -> None:
    """An app root on `sys.path` renames its own tests to `tests.*`.

    That collides with the repo-root `tests` package, which is already in `sys.modules` by the
    time any app suite is collected. The three apps that keep their modules at the app root
    need that entry, so they carry no `__init__.py` — this pins the pairing rather than the
    choice, since either half alone is fine and only the combination breaks.
    """
    app_root = tests_dir.parent
    root_on_path = any(entry and Path(entry).resolve() == app_root for entry in sys.path)
    is_package = (tests_dir / "__init__.py").exists()

    assert not (root_on_path and is_package), (
        f"{app_root} is on sys.path and {tests_dir}/__init__.py exists. Together these name "
        f"{tests_dir.parent.name}'s test modules `tests.*`, colliding with the repo-root "
        "`tests` package. Drop the __init__.py or drop the sys.path entry."
    )
