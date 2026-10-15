"""Root-conftest deployed-path protection, exercised end-to-end in a subprocess.

A real ``pytest`` run against a temp dir that loads a copy of the repo's root
``conftest.py``, so the env rewrite, the ``pytest_report_header`` warning and
the ``aitbc.constants`` binding are observed exactly the way a real run sees
them. "Deployed" here means fake roots under ``tmp_path`` declared through
``AITBC_TEST_DEPLOYED_DIRS`` — the documented escape hatch, which extends the
deployed-path set and can never shrink it — so nothing here touches or creates
real ``/etc`` or ``/var`` paths.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFTEST = REPO_ROOT / "conftest.py"
_HEADER_MARK = "ambient env pointing at deployed paths replaced"
_SCRATCH_MARK = "aitbc-tests-data-"

_PROBE = """\
import json
import os

import aitbc.constants as constants


def test_record_bindings() -> None:
    with open(os.environ["ENVPROOF_OUT"], "w") as fh:
        json.dump(
            {name: str(getattr(constants, name)) for name in ("DATA_DIR", "CONFIG_DIR", "LOG_DIR")},
            fh,
        )
"""

# The outer run's own conftest already rewrote these into os.environ — the
# subprocess must see a clean shell, not the outer session's scratch values.
_STRIPPED = (
    "AITBC_DATA_DIR",
    "AITBC_CONFIG_DIR",
    "AITBC_LOG_DIR",
    "AITBC_HOME",
    "AITBC_TEST_DEPLOYED_DIRS",
)


def _run_pytest(tmp_path: Path, env_extra: dict[str, str]) -> tuple[subprocess.CompletedProcess[str], dict[str, str]]:
    work = Path(tempfile.mkdtemp(dir=tmp_path))
    shutil.copy(CONFTEST, work / "conftest.py")
    (work / "test_probe.py").write_text(_PROBE)
    out = work / "bound.json"
    env = {k: v for k, v in os.environ.items() if k not in _STRIPPED}
    env.update({"PYTHONPATH": str(REPO_ROOT), "ENVPROOF_OUT": str(out)})
    env.update(env_extra)
    proc = subprocess.run(
        # not -q: quiet mode suppresses the session header, and seeing the
        # pytest_report_header warning is the point of the exercise.
        [sys.executable, "-m", "pytest", "."],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return proc, json.loads(out.read_text())


def test_ambient_deployed_paths_are_replaced_and_warned(tmp_path: Path) -> None:
    fake = tmp_path / "fake-deployed"
    proc, bound = _run_pytest(
        tmp_path,
        {
            "AITBC_TEST_DEPLOYED_DIRS": os.pathsep.join(str(fake / d) for d in ("varlib", "etcconf", "varlog")),
            "AITBC_DATA_DIR": str(fake / "varlib"),
            "AITBC_CONFIG_DIR": str(fake / "etcconf"),
            # sitting INSIDE a deployed root counts as deployed, not only an exact match
            "AITBC_LOG_DIR": str(fake / "varlog" / "sub"),
        },
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    # The deployed-looking paths were never created or written.
    assert not fake.exists()
    # The header names every replaced variable.
    assert _HEADER_MARK in proc.stdout
    for var in ("AITBC_DATA_DIR", "AITBC_CONFIG_DIR", "AITBC_LOG_DIR"):
        assert var in proc.stdout
    # And constants bound scratch subdirs, not the deployed values.
    for name, sub in (("DATA_DIR", None), ("CONFIG_DIR", "config"), ("LOG_DIR", "logs")):
        assert _SCRATCH_MARK in bound[name]
        assert str(fake) not in bound[name]
        if sub is not None:
            assert bound[name].endswith(os.sep + sub)


def test_deliberate_override_to_non_deployed_path_is_kept(tmp_path: Path) -> None:
    mine = tmp_path / "mine"
    proc, bound = _run_pytest(
        tmp_path,
        {
            "AITBC_DATA_DIR": str(mine / "d"),
            "AITBC_CONFIG_DIR": str(mine / "c"),
            "AITBC_LOG_DIR": str(mine / "l"),
        },
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _HEADER_MARK not in proc.stdout
    assert bound == {
        "DATA_DIR": str(mine / "d"),
        "CONFIG_DIR": str(mine / "c"),
        "LOG_DIR": str(mine / "l"),
    }


def test_unset_vars_get_scratch_defaults(tmp_path: Path) -> None:
    proc, bound = _run_pytest(tmp_path, {})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _HEADER_MARK not in proc.stdout
    assert _SCRATCH_MARK in bound["DATA_DIR"]
    assert bound["CONFIG_DIR"].endswith(os.sep + "config")
    assert bound["LOG_DIR"].endswith(os.sep + "logs")
