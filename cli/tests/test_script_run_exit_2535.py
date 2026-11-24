"""AUDIT-SCRIPT-RUN-EXIT-1 (#2535): ``aitbc script run`` exited 0 whatever
the script returned, had no timeout, and split ``--args`` on whitespace.
Now: non-zero script rc propagates, ``--timeout`` kills and reports,
``--args`` goes through ``shlex.split``.

AUDIT-CLI-SCRIPT-RUN-1 (#2886): ``script run`` also accepted any
``--script-path`` and inherited the full process env. It now shares the
``system run-script`` prefix allowlist and scrubs credential-looking env
vars from the child.
"""

import subprocess

import pytest
from click.testing import CliRunner

from aitbc_cli.commands.script import script


@pytest.fixture
def allowed_script(tmp_path, monkeypatch):
    """A real script file inside a (test-patched) allowed prefix.

    The path is fully resolved up front: ``_resolve_allowed_script_path``
    ``resolve(strict=True)``s it and requires the *resolved* path to stay
    under the prefix, so both the argument and the prefix must be canonical.
    """
    import aitbc_cli.commands.system as system_mod

    script_file = (tmp_path / "x.sh").resolve()
    script_file.write_text("#!/bin/sh\nexit 0\n")
    script_file.chmod(0o755)
    monkeypatch.setattr(
        system_mod,
        "_ALLOWED_SCRIPT_PREFIXES",
        (str(script_file.parent) + "/",),
    )
    return str(script_file)


def _patch_run(monkeypatch, result=None, exc=None, calls=None):
    def fake_run(cmd, **kwargs):
        if calls is not None:
            calls.append((cmd, kwargs))
        if exc is not None:
            raise exc
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)


def test_failing_script_exit_code_propagates(monkeypatch, allowed_script):
    _patch_run(monkeypatch, subprocess.CompletedProcess([], 3, "out", "err"))
    result = CliRunner().invoke(script, ["run", "--script-path", allowed_script], obj={"output_format": "table"})
    assert result.exit_code == 3


def test_successful_script_exit_zero(monkeypatch, allowed_script):
    _patch_run(monkeypatch, subprocess.CompletedProcess([], 0, "ok", ""))
    result = CliRunner().invoke(script, ["run", "--script-path", allowed_script], obj={"output_format": "table"})
    assert result.exit_code == 0


def test_signal_returncode_maps_to_nonzero(monkeypatch, allowed_script):
    _patch_run(monkeypatch, subprocess.CompletedProcess([], -9, "", ""))
    result = CliRunner().invoke(script, ["run", "--script-path", allowed_script], obj={"output_format": "table"})
    assert result.exit_code == 1


def test_args_use_shlex_split(monkeypatch, allowed_script):
    calls: list = []
    _patch_run(monkeypatch, subprocess.CompletedProcess([], 0, "", ""), calls=calls)
    result = CliRunner().invoke(
        script,
        ["run", "--script-path", allowed_script, "--args", '--msg "a b" --flag'],
        obj={"output_format": "table"},
    )
    assert result.exit_code == 0, result.output
    cmd, _ = calls[0]
    assert cmd == [allowed_script, "--msg", "a b", "--flag"]


def test_timeout_kills_and_reports(monkeypatch, allowed_script):
    calls: list = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout") or 0.0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = CliRunner().invoke(
        script,
        ["run", "--script-path", allowed_script, "--timeout", "5"],
        obj={"output_format": "table"},
    )
    assert result.exit_code != 0
    assert "timed out" in result.output
    assert calls[0][1].get("timeout") == 5.0


def test_default_timeout_is_300(monkeypatch, allowed_script):
    calls: list = []
    _patch_run(monkeypatch, subprocess.CompletedProcess([], 0, "", ""), calls=calls)
    result = CliRunner().invoke(script, ["run", "--script-path", allowed_script], obj={"output_format": "table"})
    assert result.exit_code == 0
    assert calls[0][1].get("timeout") == 300


def test_script_path_outside_allowlist_refused(monkeypatch, tmp_path):
    """#2886: an arbitrary path is refused before any subprocess spawns."""
    import aitbc_cli.commands.system as system_mod

    monkeypatch.setattr(system_mod, "_ALLOWED_SCRIPT_PREFIXES", (str(tmp_path / "allowed") + "/",))
    outside = tmp_path / "evil.sh"
    outside.write_text("#!/bin/sh\nexit 0\n")
    outside.chmod(0o755)
    calls: list = []
    _patch_run(monkeypatch, subprocess.CompletedProcess([], 0, "", ""), calls=calls)
    result = CliRunner().invoke(script, ["run", "--script-path", str(outside)], obj={"output_format": "table"})
    assert result.exit_code != 0
    assert "not allowed" in result.output
    assert calls == []


def test_symlink_escape_outside_allowlist_refused(monkeypatch, tmp_path):
    """#2886: a symlink inside the prefix that resolves outside is refused."""
    import aitbc_cli.commands.system as system_mod

    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    monkeypatch.setattr(system_mod, "_ALLOWED_SCRIPT_PREFIXES", (str(allowed_dir) + "/",))
    outside = tmp_path / "outside.sh"
    outside.write_text("#!/bin/sh\nexit 0\n")
    link = allowed_dir / "link.sh"
    link.symlink_to(outside)
    calls: list = []
    _patch_run(monkeypatch, subprocess.CompletedProcess([], 0, "", ""), calls=calls)
    result = CliRunner().invoke(script, ["run", "--script-path", str(link)], obj={"output_format": "table"})
    assert result.exit_code != 0
    assert calls == []


def test_child_env_strips_credential_vars(monkeypatch, allowed_script):
    """#2886: secrets in the service env must not reach the script child."""
    calls: list = []
    _patch_run(monkeypatch, subprocess.CompletedProcess([], 0, "", ""), calls=calls)
    monkeypatch.setenv("AITBC_API_KEY", "sekrit")
    monkeypatch.setenv("WALLET_MNEMONIC", "words")
    monkeypatch.setenv("HTTP_PROXY", "http://proxy:8080")
    result = CliRunner().invoke(script, ["run", "--script-path", allowed_script], obj={"output_format": "table"})
    assert result.exit_code == 0, result.output
    child_env = calls[0][1].get("env")
    assert child_env is not None
    assert "AITBC_API_KEY" not in child_env
    assert "WALLET_MNEMONIC" not in child_env
    assert child_env.get("HTTP_PROXY") == "http://proxy:8080"
