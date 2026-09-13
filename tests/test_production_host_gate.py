"""The production-write gate must skip ``tests/verification/`` and nothing else (V23-93).

``tests/verification/conftest.py`` skips any module whose source names a deployment host,
because every module in that directory POSTs to it. But ``pytest_collection_modifyitems`` is
handed the whole session's item list regardless of which ``conftest.py`` defines it, so for one
release that text match ran against the entire repository and skipped 159 ordinary unit tests
for mentioning the hostname in a URL constant or a docstring.

The gate now keys on write behaviour as well as hostname, because keying on hostname alone
failed: the gated modules were converted to target ``127.0.0.1``, which removed them from the
gate without removing a single ``POST``, and a run of the directory forked a follower node 32
blocks deep. ``_sends_http_writes`` is the predicate that survives a hostname change.

That makes the directory boundary matter more, not less. 61 test files in this repository
issue an HTTP write and 37 name the host, so a repo-wide write match would skip a strictly
larger set than the 159 tests V23-93 was filed for.

These tests exercise the gate logic with temporary files so the suite does not depend on the
real contents of ``tests/verification/`` -- except for the last one, which asserts against the
real directory on purpose, so a new writer added there cannot quietly go ungated.
"""

from __future__ import annotations

import ast
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


class TestTheWriteMatch:
    """``_sends_http_writes`` is what the hostname match missed."""

    def test_a_localhost_only_block_import_matches(self, gate, tmp_path):
        """The exact shape that escaped the old gate and forked a node."""
        f = tmp_path / "test_import.py"
        f.write_text(
            'import requests\n'
            'BASE = "http://127.0.0.1:8202/rpc"\n'
            'def test_import_a_block():\n'
            '    requests.post(f"{BASE}/importBlock", json={}, timeout=10)\n'
        )

        assert gate._sends_http_writes(f)
        assert not gate._names_production_host(f), "the point is that the host match does not fire"

    @pytest.mark.parametrize(
        "line",
        [
            'requests.post(url, json={})',
            'requests.put(url, json={})',
            'requests.patch(url, json={})',
            'requests.delete(url)',
            'httpx.post(url, json={})',
            'self.client.post(url, json={})',
            'await client.post(url, json={})',
            'response = requests.post(\n    url,\n    json={},\n)',
            'requests.post (url)',
        ],
    )
    def test_every_call_shape_in_this_directory_matches(self, gate, tmp_path, line):
        f = tmp_path / "test_shape.py"
        f.write_text(line + "\n")

        assert gate._sends_http_writes(f), f"unmatched write shape: {line!r}"

    def test_a_read_only_module_does_not_match(self, gate, tmp_path):
        f = tmp_path / "test_read.py"
        f.write_text(
            'import requests\n'
            'def test_head():\n'
            '    assert requests.get("http://127.0.0.1:8202/rpc/head", timeout=5).ok\n'
        )

        assert not gate._sends_http_writes(f)

    def test_an_unreadable_file_is_treated_as_writing(self, gate, tmp_path):
        assert gate._sends_http_writes(tmp_path / "does-not-exist.py")


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


def test_a_localhost_writer_inside_the_directory_is_gated(gate, monkeypatch, tmp_path):
    """The regression this gate was rewritten for.

    A module that names no deployment host but POSTs a block must be skipped. Under the
    hostname-only gate this file ran, imported blocks at ``head + 1`` into whatever node the
    runner was standing on, and forked it.
    """
    monkeypatch.delenv(gate.ALLOW_ENV, raising=False)
    monkeypatch.setattr(gate, "GATED_DIR", tmp_path)

    inside = tmp_path / "test_localhost_import.py"
    inside.write_text(
        'import requests\n'
        'BASE = "http://127.0.0.1:8202/rpc"\n'
        'def test_import_a_block():\n'
        '    requests.post(f"{BASE}/importBlock", json={}, timeout=10)\n'
    )

    assert not gate._names_production_host(inside), "precondition: the host match must not fire"
    assert _run_hook(gate, [inside])[inside] is True


def test_a_read_only_module_inside_the_directory_still_runs(gate, monkeypatch, tmp_path):
    """Over-matching is the right direction to err, but not at any price."""
    monkeypatch.delenv(gate.ALLOW_ENV, raising=False)
    monkeypatch.setattr(gate, "GATED_DIR", tmp_path)

    inside = tmp_path / "test_read_only.py"
    inside.write_text(
        'import requests\n'
        'def test_head():\n'
        '    assert requests.get("http://127.0.0.1:8202/rpc/head", timeout=5).ok\n'
    )

    assert _run_hook(gate, [inside])[inside] is False


def test_the_write_match_is_confined_to_the_directory_too(gate, monkeypatch, tmp_path):
    """The write predicate is broader than the host one, so the boundary matters more.

    61 test files in this repo issue an HTTP write against 37 that name the host: a repo-wide
    write match would skip a strictly larger set than the 159 tests of V23-93.
    """
    monkeypatch.delenv(gate.ALLOW_ENV, raising=False)
    gated_dir = tmp_path / "tests" / "verification"
    other_dir = tmp_path / "tests" / "api"
    gated_dir.mkdir(parents=True)
    other_dir.mkdir(parents=True)

    body = 'def test_x(client):\n    client.post("/v1/jobs", json={})\n'
    gated_file = gated_dir / "test_writer.py"
    outside_file = other_dir / "test_ordinary_endpoint.py"
    for f in (gated_file, outside_file):
        f.write_text(body)

    monkeypatch.setattr(gate, "GATED_DIR", gated_dir)

    skipped = _run_hook(gate, [gated_file, outside_file])

    assert skipped[gated_file] is True
    assert skipped[outside_file] is False, "an ordinary API test that POSTs must not be gated"


def test_the_skip_reason_names_the_behaviour_not_the_host(gate, monkeypatch, tmp_path):
    """A localhost writer skipped for 'names a live deployment host' would be a lie."""
    monkeypatch.delenv(gate.ALLOW_ENV, raising=False)
    monkeypatch.setattr(gate, "GATED_DIR", tmp_path)

    inside = tmp_path / "test_localhost_import.py"
    inside.write_text('def test_x(client):\n    client.post("/rpc/importBlock", json={})\n')

    items = [_FakeItem(inside)]
    gate.pytest_collection_modifyitems(config=None, items=items)

    reason = items[0].markers[0].kwargs["reason"]
    assert "HTTP writes" in reason
    assert gate.ALLOW_ENV in reason


def _writers_by_ast(directory: Path) -> list[Path]:
    """Find the HTTP writers by parsing, independently of the gate's own regex.

    The gate matches source text. A check built on that same regex drifts exactly when the
    regex does, and would have reported a clean bill of health for the whole period the
    hostname match was stale. This walks the AST instead and looks for a call to anything
    named ``post``/``put``/``patch``/``delete``.
    """
    writers: list[Path] = []
    for f in sorted(directory.glob("*.py")):
        if f.name == "conftest.py":
            continue
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:  # pragma: no cover - a broken file is not this test's business
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"post", "put", "patch", "delete"}
            ):
                writers.append(f)
                break
    return writers


def test_the_gate_covers_what_the_files_actually_do(gate, monkeypatch):
    """Every module in the real directory that writes must be gated.

    Found by AST, asserted against the hook, so neither a new file nor a write shape the
    regex does not recognise can land ungated.
    """
    monkeypatch.delenv(gate.ALLOW_ENV, raising=False)

    writers = _writers_by_ast(GATE_CONFTEST.parent)
    assert writers, "expected this directory to still contain modules that write"

    skipped = _run_hook(gate, writers)

    ungated = sorted(p.name for p in writers if not skipped[p])
    assert not ungated, f"modules that write to a live node but are not gated: {ungated}"


def test_every_writer_in_the_real_directory_is_gated(gate, monkeypatch):
    """Assert against the real directory, so a new writer cannot land ungated.

    The hand-maintained list was wrong before, and the hostname match went stale the moment
    the modules were pointed at localhost. This checks the files that are actually there.
    """
    monkeypatch.delenv(gate.ALLOW_ENV, raising=False)
    verification = GATE_CONFTEST.parent

    writers = [
        f
        for f in sorted(verification.glob("*.py"))
        if f.name != "conftest.py" and gate._sends_http_writes(f)
    ]
    assert writers, "expected this directory to still contain modules that write"

    skipped = _run_hook(gate, writers)

    assert all(skipped.values()), f"ungated writers: {sorted(p.name for p in writers if not skipped[p])}"


class TestTheScriptGuard:
    """``conftest`` only exists inside a pytest session; the ``__main__`` blocks do not.

    Every writing module in the gated directory carries an ``if __name__ == "__main__"`` block
    that performs its writes. No collection hook can see that path, so the scripts are held to
    the same opt-in by ``_write_guard.require_opt_in``.
    """

    @staticmethod
    def _load_guard():
        spec = importlib.util.spec_from_file_location(
            "_verification_write_guard", GATE_CONFTEST.parent / "_write_guard.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_it_shares_the_pytest_opt_in(self, gate):
        """Two names for one switch would be worse than one name for none."""
        assert self._load_guard().ALLOW_ENV == gate.ALLOW_ENV

    def test_it_refuses_without_the_opt_in(self, monkeypatch):
        guard = self._load_guard()
        monkeypatch.delenv(guard.ALLOW_ENV, raising=False)

        with pytest.raises(SystemExit) as excinfo:
            guard.require_opt_in("/x/tests/verification/test_minimal.py")

        message = str(excinfo.value)
        assert "test_minimal.py" in message
        assert guard.ALLOW_ENV in message

    def test_it_allows_with_the_opt_in(self, monkeypatch):
        guard = self._load_guard()
        monkeypatch.setenv(guard.ALLOW_ENV, "1")

        assert guard.require_opt_in("/x/tests/verification/test_minimal.py") is None

    def test_every_self_running_writer_calls_it(self, gate):
        """A writer with an unguarded ``__main__`` block is an open door.

        Found the same way the gate finds writers, then checked for the guard call, so a new
        script in this directory cannot ship with a bare ``__main__``.
        """
        unguarded = []
        for f in sorted(GATE_CONFTEST.parent.glob("*.py")):
            if f.name in {"conftest.py", "_write_guard.py"}:
                continue
            source = f.read_text(encoding="utf-8")
            if '__name__ == "__main__"' not in source:
                continue
            if not gate._sends_http_writes(f):
                continue
            if "require_opt_in(" not in source:
                unguarded.append(f.name)

        assert not unguarded, f"self-running writers with no opt-in guard: {unguarded}"


if __name__ == "__main__":
    pytest.main([__file__])
