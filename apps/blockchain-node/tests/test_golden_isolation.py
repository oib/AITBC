"""The golden runner must leave the shared ``settings`` singleton as it found it.

``runner.run_case``/``run_stream`` pin every gate attribute on the live
``settings`` via ``profiles.apply_profile``. Before the snapshot/restore wrap
was added, the last profile run in a process leaked its pins into every later
test — a full-suite run with the golden file ordered first failed 25 tests in
alphabetically-later files because every ``state_transition_vN_height`` stayed
at ``gates1``'s 1.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

# Same path shim as test_golden_vectors.py: the app's tests/ dir must precede
# the repo root's ``tests`` package on sys.path for the golden package import.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from golden import runner  # noqa: E402
from golden.profiles import GATE_ATTRS, GATES1_PINS  # noqa: E402


def _settings_state() -> dict:
    from aitbc_chain.config import settings

    return copy.deepcopy(vars(settings))


def _not_already_gates1() -> None:
    """If the pre-state is already gates1 the restore assertions are vacuous."""
    from aitbc_chain.config import settings

    gate_state = {attr: getattr(settings, attr) for attr in GATE_ATTRS}
    assert gate_state != GATES1_PINS, "settings already pinned at gates1 — test proves nothing"


def test_run_case_restores_settings_after_success():
    from aitbc_chain.config import settings

    _not_already_gates1()
    before = _settings_state()
    case = next(iter(runner._load_cases(runner.CASES_DIR)))
    runner.run_case(case, "gates1")
    assert vars(settings) == before


def test_run_stream_restores_settings_after_success():
    from aitbc_chain.config import settings

    genesis, _, blocks = runner._load_stream(runner.CASES_DIR)
    if genesis is None or not blocks:
        pytest.skip("cases/genesis-state.json + stream/ not extracted yet")
    _not_already_gates1()
    before = _settings_state()
    runner.run_stream(genesis, blocks[:1], "gates1")
    assert vars(settings) == before


def test_run_case_restores_settings_on_raise():
    from aitbc_chain.config import settings

    _not_already_gates1()
    before = _settings_state()
    with pytest.raises(KeyError):
        # Missing "block"/"tx" keys: apply blows up mid-run, after the profile
        # was already pinned — the restore must still happen.
        runner.run_case({"case_id": "raise-probe"}, "gates1")
    assert vars(settings) == before
