"""Golden-corpus oracle: every case must reproduce its recorded outputs.

The corpus under ``tests/golden/`` is the RESET-VECTORS-1 oracle: consensus
behaviour recorded on the pre-collapse code so the reset release can be diffed
against it. These tests replay every case through the real sequential apply
path (``tests/golden/engine.py``) under each gate-pin profile and fail on any
divergence — the same check ``runner.py check`` performs, kept inside the
suite so the corpus guards every commit.

Record a new baseline only on purpose:

    python -m tests.golden.runner record --profile deployed   # and gates0
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# The app's own tests/ directory is on sys.path for the golden package — both
# the repo root and this app carry a `tests` package and the unqualified name
# would resolve to the wrong one.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Golden vectors replay full block sequences — the suite's structural head
# (~45 s across the six parametrized cases). Deselect with -m "not slow".
pytestmark = pytest.mark.slow
from golden import runner  # noqa: E402
from golden.profiles import PROFILES  # noqa: E402

EXPECTED = runner.EXPECTED_DIR


def _load_cases():
    return runner._load_cases(runner.CASES_DIR)


def _check_case(case: dict, profile: str) -> list[dict]:
    expected_path = EXPECTED / profile / "synthetic" / f"{case['case_id']}.json"
    if not expected_path.exists():
        pytest.fail(f"no recorded output for {case['case_id']} under {profile} — record first")
    result = runner.run_case(case, profile)
    diffs: list[dict] = []
    runner._diff_obj(case["case_id"], json.loads(expected_path.read_text()), result, diffs)
    return diffs


@pytest.mark.parametrize("profile", sorted(PROFILES))
def test_synthetic_vectors(profile):
    diffs: list[dict] = []
    for case in _load_cases():
        diffs.extend(_check_case(case, profile))
    assert not diffs, f"{len(diffs)} divergent fields under {profile}: {diffs[:5]}"


@pytest.mark.timeout(600)
@pytest.mark.parametrize("profile", sorted(PROFILES))
def test_real_history_stream(profile):
    genesis, manifest, blocks = runner._load_stream(runner.CASES_DIR)
    if genesis is None:
        pytest.skip("cases/genesis-state.json + stream/ not extracted yet")
    stream_dir = EXPECTED / profile / "stream"
    if not stream_dir.is_dir():
        pytest.fail(f"no recorded stream for {profile} — record first")
    outputs = runner.run_stream(genesis, blocks, profile)
    diffs: list[dict] = []
    for out in outputs:
        expected_path = stream_dir / f"{out['height']:08d}.json"
        label = f"stream/{out['height']}"
        if not expected_path.exists():
            diffs.append({"path": label, "expected": "<recorded>", "actual": "<no expected file>"})
            continue
        runner._diff_obj(label, json.loads(expected_path.read_text()), out, diffs)
    assert not diffs, f"{len(diffs)} divergent fields under {profile}: {diffs[:5]}"
