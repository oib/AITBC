"""Tests for ``aitbc system file`` / ``aitbc system run-script`` path traversal.

The allowlists used to be raw ``startswith`` checks on the unresolved path,
so ``<prefix>/../outside`` passed and ``open``/``bash`` followed it — as root
over ssh that read any file on the node (CLI-SYSTEM-FILE-TRAVERSAL-1). Both
commands now resolve the path first (same shape as ``file-info``) and re-check
the prefix on the resolved path; the resolved path, not the raw one, is opened
or executed.

All files live under tmp_path; the allowlists are patched to point there so no
real /opt/aitbc, /etc/aitbc or /var/lib/aitbc content is touched.
"""

from unittest import mock

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.system as system_mod
from aitbc_cli.commands.system import system


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def allowed(tmp_path):
    """Patch the read allowlist to tmp_path/"allowed" for the test."""
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    with mock.patch.object(system_mod, "_ALLOWED_READ_PREFIXES", (str(allowed_dir) + "/",)):
        yield allowed_dir


@pytest.fixture
def allowed_scripts(tmp_path):
    """Patch the run-script allowlist to tmp_path/"scripts" for the test."""
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    with mock.patch.object(system_mod, "_ALLOWED_SCRIPT_PREFIXES", (str(scripts_dir) + "/",)):
        yield scripts_dir


# --------------------------------------------------------------- system file


def test_file_refuses_dotdot_escape(runner, allowed, tmp_path):
    secret = tmp_path / "outside" / "hostname"
    secret.parent.mkdir()
    secret.write_text("SECRET-CONTENT")
    traversal = str(allowed) + "/../outside/hostname"
    result = runner.invoke(system, obj={"output_format": "table"}, args=["file", "--path", traversal])
    assert result.exit_code != 0
    assert "not allowed" in result.output
    assert "SECRET-CONTENT" not in result.output


def test_file_refuses_dotdot_after_dot(runner, allowed, tmp_path):
    secret = tmp_path / "hostname"
    secret.write_text("SECRET-CONTENT")
    traversal = str(allowed) + "/./../hostname"
    result = runner.invoke(system, obj={"output_format": "table"}, args=["file", "--path", traversal])
    assert result.exit_code != 0
    assert "not allowed" in result.output
    assert "SECRET-CONTENT" not in result.output


def test_file_refuses_symlink_escape(runner, allowed, tmp_path):
    secret = tmp_path / "outside.txt"
    secret.write_text("SECRET-CONTENT")
    link = allowed / "link.txt"
    link.symlink_to(secret)
    result = runner.invoke(system, obj={"output_format": "table"}, args=["file", "--path", str(link)])
    assert result.exit_code != 0
    assert "not allowed" in result.output
    assert "SECRET-CONTENT" not in result.output


def test_file_reads_inside_allowlist(runner, allowed):
    f = allowed / "node.env"
    f.write_text("CHAIN_ID=ait-test\n")
    result = runner.invoke(system, obj={"output_format": "table"}, args=["file", "--path", str(f)])
    assert result.exit_code == 0, result.output
    assert "CHAIN_ID=ait-test" in result.output


def test_file_refuses_plain_outside(runner, allowed, tmp_path):
    result = runner.invoke(system, obj={"output_format": "table"}, args=["file", "--path", str(tmp_path / "x")])
    assert result.exit_code != 0
    assert "not allowed" in result.output


def test_file_info_unchanged(runner, allowed):
    f = allowed / "node.json"
    f.write_text('{"address": "0xabc"}')
    result = runner.invoke(system, obj={"output_format": "table"}, args=["file-info", "--path", str(f)])
    assert result.exit_code == 0, result.output
    assert "address" in result.output


# ---------------------------------------------------------- system run-script


def test_run_script_refuses_dotdot_escape(runner, allowed_scripts, tmp_path):
    outside = tmp_path / "evil.sh"
    outside.write_text("echo PWNED\n")
    traversal = str(allowed_scripts) + "/../evil.sh"
    with mock.patch.object(system_mod.subprocess, "run") as run_mock:
        result = runner.invoke(system, obj={"output_format": "table"}, args=["run-script", "--path", traversal])
    assert result.exit_code != 0
    assert "not allowed" in result.output
    run_mock.assert_not_called()


def test_run_script_refuses_symlink_escape(runner, allowed_scripts, tmp_path):
    outside = tmp_path / "evil.sh"
    outside.write_text("echo PWNED\n")
    link = allowed_scripts / "link.sh"
    link.symlink_to(outside)
    with mock.patch.object(system_mod.subprocess, "run") as run_mock:
        result = runner.invoke(system, obj={"output_format": "table"}, args=["run-script", "--path", str(link)])
    assert result.exit_code != 0
    assert "not allowed" in result.output
    run_mock.assert_not_called()


def test_run_script_runs_resolved_path(runner, allowed_scripts):
    script = allowed_scripts / "ok.sh"
    script.write_text("echo OK\n")
    fake = mock.Mock(returncode=0, stdout="OK\n", stderr="")
    with mock.patch.object(system_mod.subprocess, "run", return_value=fake) as run_mock:
        result = runner.invoke(system, obj={"output_format": "table"}, args=["run-script", "--path", str(script)])
    assert result.exit_code == 0, result.output
    run_mock.assert_called_once()
    # the resolved path, not the raw string, is handed to bash
    assert run_mock.call_args[0][0][2] == str(script.resolve())


def test_file_masks_env_and_keystore_secrets(runner, allowed):
    """#1097: a read of an env or keystore path returns no secret value."""
    env = allowed / "svc.env"
    env.write_text("AITBC_API_KEY=supersecret-api-key-value\nLISTEN_ADDR=0.0.0.0:8102\nCOMMENT=plain text stays\n")
    result = runner.invoke(system, obj={"output_format": "table"}, args=["file", "--path", str(env)])
    assert result.exit_code == 0, result.output
    assert "supersecret-api-key-value" not in result.output
    assert "***MASKED***" in result.output
    assert "0.0.0.0:8102" in result.output
    assert "plain text stays" in result.output

    keystore = allowed / "node.json"
    keystore.write_text('{"address": "0xabc", "private_key": "0x' + "a1" * 32 + '", "name": "miner"}')
    result = runner.invoke(system, obj={"output_format": "table"}, args=["file", "--path", str(keystore)])
    assert result.exit_code == 0, result.output
    assert "a1" * 32 not in result.output
    assert "miner" in result.output
