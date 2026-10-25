"""Pin the format-then-compare behaviour of generate_mcp_cli_tools.py --check.

The write path formats emitted modules with ``ruff format`` before saving, so
the committed files are always formatted.  ``--check`` must compare the
committed file against the *formatted* generator output — comparing the raw
emitted text reports drift on every tree (MCP-DRIFT-1).
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR = REPO_ROOT / "scripts" / "dev" / "generate_mcp_cli_tools.py"


def _load_generator():
    spec = importlib.util.spec_from_file_location("generate_mcp_cli_tools", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ruff_available() -> bool:
    return (
        subprocess.run(
            [sys.executable, "-m", "ruff", "--version"],
            capture_output=True,
        ).returncode
        == 0
    )


pytestmark = pytest.mark.skipif(not _ruff_available(), reason="ruff not importable by the running interpreter")


@pytest.fixture(scope="module")
def gen():
    return _load_generator()


def test_format_emitted_normalizes_unformatted_source(gen):
    unformatted = "x=1\n"
    formatted = gen._format_emitted(unformatted)
    assert formatted == "x = 1\n"


def test_format_emitted_falls_back_to_raw_text_when_ruff_fails(gen, monkeypatch):
    def _boom(*args, **kwargs):
        raise OSError("no ruff")

    monkeypatch.setattr(gen.subprocess, "run", _boom)
    assert gen._format_emitted("x=1\n") == "x=1\n"


def test_emitted_matches_compares_formatted_output(gen, tmp_path):
    committed = tmp_path / "mod.py"
    committed.write_text("x = 1\n")
    # Raw generator output is not ruff-formatted; the check must still pass
    # because the write path would format it to the committed shape.
    assert gen._emitted_matches(committed, "x=1\n")
    assert not gen._emitted_matches(committed, "x = 2\n")


def test_check_exits_zero_on_committed_layout(gen, monkeypatch, capsys):
    """End-to-end: --check on the repo's committed split modules passes."""
    monkeypatch.setattr(sys, "argv", ["generate_mcp_cli_tools.py", "--check"])
    assert gen.main() == 0
    assert "up to date" in capsys.readouterr().out
