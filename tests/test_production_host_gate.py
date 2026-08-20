"""The production-write gate must skip ``tests/verification/`` and nothing else (V23-93).

``tests/verification/conftest.py`` skips any module whose source names a deployment host,
because every module in that directory POSTs to it. But ``pytest_collection_modifyitems`` is
handed the whole session's item list regardless of which ``conftest.py`` defines it, so for one
release that text match ran against the entire repository and skipped 159 ordinary unit tests
for mentioning the hostname in a URL constant or a docstring.

These tests exercise the gate logic with temporary files so the suite does not depend on the
real contents of ``tests/verification/``. The gate still protects against any future test file
in that directory that names a live deployment host.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE_CONFTEST = REPO_ROOT / "tests" / "verification" / "conftest.py"


def _load_gate():
    """Import the conftest as a plain module, by path -- pytest owns the real import."""
    spec = importlib.util.spec_from_file_location("_verification_gate", GATE_CONFTEST)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate():
    return _load_gate()


class TestTheDirectoryBoundary:
    def test_a_file_in_the_gated_directory_is_inside(self, gate):
        assert gate._is_in_this_directory(GATE_CONFTEST.parent / "test_minimal.py")

    def test_a_file_elsewhere_in_the_repo_is_outside(self, gate):
        assert not gate._is_in_this_directory(Path(__file__))
        assert not gate._is_in_this_directory(REPO_ROOT / "cli" / "tests" / "test_coin_request_notifications.py")

    def test_a_sibling_directory_with_a_similar_name_is_outside(self, gate):
        assert not gate._is_in_this_directory(REPO_ROOT / "tests" / "verification_helpers" / "test_x.py")

    def test_a_nested_file_in_the_gated_directory_is_inside(self, gate):
        assert gate._is_in_this_directory(GATE_CONFTEST.parent / "nested" / "test_y.py")


class TestTheSourceMatch:
    def test_a_module_naming_the_host_matches(self, gate, tmp_path):
        f = tmp_path / "test_a.py"
        f.write_text('BASE_URL = "https://hub.aitbc.bubuit.net/rpc"\n')

        assert gate._names_production_host(f)

    def test_a_module_naming_only_localhost_does_not(self, gate, tmp_path):
        f = tmp_path / "test_b.py"
        f.write_text('BASE_URL = "http://localhost:8202/rpc"\n')

        assert not gate._names_production_host(f)

    def test_an_unreadable_file_is_treated_as_production_touching(self, gate, tmp_path):
        assert gate._names_production_host(tmp_path / "does-not-exist.py")


class TestThisFileItself:
    def test_this_test_is_not_skipped(self):
        """Reaching this line is the assertion.

        This module's source contains ``bubuit.net`` (above and in the fixtures), which is what
        the repo-wide match keyed on. If the gate regresses, this test stops running -- and a
        test that stops running is exactly the failure mode V23-93 was about, so it is asserted
        from the outside too, by ``test_the_gate_only_skips_its_own_directory``.
        """
        assert True


class _FakeItem:
    """Enough of a pytest item for the hook: a path and somewhere to put a marker."""

    def __init__(self, path: Path):
        self.path = path
        self.markers: list[object] = []

    def add_marker(self, marker) -> None:  # noqa: ANN001 - takes whatever pytest.mark builds
        self.markers.append(marker)


def _run_hook(gate, paths: list[Path]) -> dict[Path, bool]:
    items = [_FakeItem(p) for p in paths]
    gate.pytest_collection_modifyitems(config=None, items=items)
    return {item.path: bool(item.markers) for item in items}


def test_the_hook_skips_inside_and_leaves_outside_alone(gate, monkeypatch, tmp_path):
    """A file inside the gated dir that names the host is skipped; a file outside is not."""
    monkeypatch.delenv(gate.ALLOW_ENV, raising=False)
    monkeypatch.setattr(gate, "GATED_DIR", tmp_path)

    inside = tmp_path / "test_hosted.py"
    inside.write_text('BASE_URL = "https://hub.aitbc.bubuit.net/rpc"\n')
    outside = Path(__file__)

    skipped = _run_hook(gate, [inside, outside])

    assert skipped[inside] is True, "a module in tests/verification/ that names the host must be gated"
    assert skipped[outside] is False, "this file names the host too, and must still run"


def test_the_opt_in_env_var_disarms_the_hook(gate, monkeypatch, tmp_path):
    """Setting the opt-in env var prevents the hook from gating files."""
    monkeypatch.setenv(gate.ALLOW_ENV, "1")
    monkeypatch.setattr(gate, "GATED_DIR", tmp_path)

    inside = tmp_path / "test_hosted.py"
    inside.write_text('BASE_URL = "https://hub.aitbc.bubuit.net/rpc"\n')

    assert _run_hook(gate, [inside])[inside] is False


def test_the_repo_wide_reach_is_measured_not_assumed(gate, monkeypatch, tmp_path):
    """The text match alone must not skip files outside the gated directory.

    Build a temporary tree containing a fake ``tests/verification`` directory and several
    ordinary test files outside it, all naming the host. Only the files inside the gated
    directory should be skipped.
    """
    monkeypatch.delenv(gate.ALLOW_ENV, raising=False)
    gated_dir = tmp_path / "tests" / "verification"
    other_dir = tmp_path / "tests" / "cli"
    gated_dir.mkdir(parents=True)
    other_dir.mkdir(parents=True)

    gated_file = gated_dir / "test_hosted.py"
    outside_file_a = other_dir / "test_a.py"
    outside_file_b = other_dir / "test_b.py"

    for f in (gated_file, outside_file_a, outside_file_b):
        f.write_text('BASE_URL = "https://hub.aitbc.bubuit.net/rpc"\n')

    monkeypatch.setattr(gate, "GATED_DIR", gated_dir)

    outside_matching = [
        p
        for p in [gated_file, outside_file_a, outside_file_b]
        if not gate._is_in_this_directory(p) and gate._names_production_host(p)
    ]
    assert len(outside_matching) == 2, "expected two outside files to match the host text"

    skipped = _run_hook(gate, [gated_file, outside_file_a, outside_file_b])

    assert skipped[gated_file] is True, "gated file must be skipped"
    assert not any(skipped[p] for p in outside_matching), "no file outside the gated dir may be skipped"


if __name__ == "__main__":
    pytest.main([__file__])
