"""Guard for the wallet conftest's environment isolation.

In a combined gate run (e.g. ``make test-critical``) other suites' modules may
import ``aitbc.constants`` before or after this directory's conftest — either
way the bound paths must resolve under the test scratch (``/tmp/aitbc-*``),
and ``DATA_DIR`` must be the data *root* (services append ``data/``), not a
directory already named ``data``.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_SCRATCH_PREFIX = str(Path(tempfile.gettempdir()).resolve()) + os.sep + "aitbc-"


def _under_scratch(path: Path) -> bool:
    return str(path.resolve()).startswith(_SCRATCH_PREFIX)


def test_constants_bind_scratch_paths() -> None:
    import aitbc.constants as constants

    for name in ("DATA_DIR", "CONFIG_DIR", "LOG_DIR"):
        bound = getattr(constants, name)
        assert _under_scratch(bound), f"aitbc.constants.{name} = {bound} — not a test scratch path"


def test_data_dir_is_the_root_not_a_data_subdir() -> None:
    """Services build ``DATA_DIR / 'data' / <svc>.db`` — if AITBC_DATA_DIR
    pointed at a dir named ``data``, the db parent ``data/data`` would not
    exist and sqlite open fails (the TEST-1 combined-gate regression)."""
    import aitbc.constants as constants

    assert constants.DATA_DIR.name != "data", (
        f"AITBC_DATA_DIR = {constants.DATA_DIR} ends in 'data' — service paths become data/data/…"
    )
    assert (constants.DATA_DIR / "data").is_dir(), (
        f"{constants.DATA_DIR}/data must exist — services append 'data/' without mkdir"
    )


def test_api_key_storage_path_is_scratch() -> None:
    path = os.environ.get("API_KEY_STORAGE_PATH", "")
    assert path.startswith(_SCRATCH_PREFIX), f"API_KEY_STORAGE_PATH = {path} — not a test scratch path"
