#!/usr/bin/env python3
"""User-facing version output must report the aitbc_cli package version.

`aitbc version` and `aitbc --version` used to print a hardcoded string in
aitbc_cli.core.main that drifted from aitbc_cli.__version__.
"""

import ast
import re
from pathlib import Path

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


class TestVersionOutput:
    """The version users see is the canonical package version."""

    def test_main_module_does_not_shadow_package_version(self):
        import aitbc_cli
        from aitbc_cli.core import main

        assert main.__version__ == aitbc_cli.__version__

    def test_version_flag_matches_package(self, runner):
        # --version is an eager option: output and exit before the group
        # callback runs, so this never touches config or chain-id detection.
        import aitbc_cli
        from aitbc_cli.core.main import cli

        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert result.output.strip() == f"aitbc, version {aitbc_cli.__version__}"

    def test_version_command_matches_package(self, runner):
        # Invoked standalone so the group callback (config load, chain-id
        # probe) never runs — the command itself needs no context.
        import aitbc_cli
        from aitbc_cli.core.main import version

        result = runner.invoke(version)
        assert result.exit_code == 0
        assert f"aitbc, version {aitbc_cli.__version__}" in result.output


class TestCanonicalVersionSource:
    """cli/aitbc_cli/__init__.py is the only literal __version__ in the package.

    core/__init__.py carried a stale 0.1.0 and core/main.py a stale 0.10.18
    while the package was at 0.25.x — one canonical literal, everything else
    imports it.
    """

    def test_all_version_attributes_agree(self):
        import importlib

        import aitbc_cli
        from aitbc_cli.core import main

        # aitbc_cli.core.__version__ is a submodule: once imported, the
        # attribute on the core package IS the module, not the string.
        # Resolve every surface to its final string before comparing.
        compat = importlib.import_module("aitbc_cli.core.__version__")
        core_pkg = importlib.import_module("aitbc_cli.core")

        def _resolve(surface):
            return surface.__version__ if not isinstance(surface, str) else surface

        versions = {
            "aitbc_cli.__version__": aitbc_cli.__version__,
            "aitbc_cli.core.__version__": _resolve(core_pkg.__version__),
            "aitbc_cli.core.__version__.__version__": compat.__version__,
            "aitbc_cli.core.main.__version__": main.__version__,
        }
        assert set(versions.values()) == {aitbc_cli.__version__}, f"version definitions disagree: {versions}"

    def test_no_literal_version_outside_canonical(self):
        pkg_dir = Path(__file__).resolve().parents[1] / "aitbc_cli"
        canonical = pkg_dir / "__init__.py"
        offenders = []
        for path in sorted(pkg_dir.rglob("*.py")):
            if path == canonical:
                continue
            for node in ast.walk(ast.parse(path.read_text())):
                if (
                    isinstance(node, ast.Assign)
                    and isinstance(node.value, ast.Constant)
                    and any(isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets)
                ):
                    offenders.append(str(path.relative_to(pkg_dir)))
        assert not offenders, f"literal __version__ assigned outside {canonical.name}: {offenders}"

    def test_setup_py_version_matches_package(self):
        import aitbc_cli

        text = (Path(__file__).resolve().parents[1] / "setup.py").read_text()
        uses_canonical = re.search(r"from aitbc_cli import __version__", text) and re.search(
            r"version\s*=\s*__version__", text
        )
        literal = re.search(r'version\s*=\s*"([^"]+)"', text)
        assert uses_canonical or (literal and literal.group(1) == aitbc_cli.__version__), (
            "cli/setup.py must take its version from aitbc_cli.__version__ — "
            "either `version=__version__` after `from aitbc_cli import __version__`, "
            "or a literal equal to it (scripts/ci/check-version-consistency.py)"
        )
