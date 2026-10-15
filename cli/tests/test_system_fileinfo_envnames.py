"""Tests for ``aitbc system file-info`` and ``aitbc system env-names`` (CLI-2).

file-info is the safe metadata view for sensitive files: it never dumps
content, and ``--field`` hard-refuses denied names (private_key, *_key,
secrets) — a denied value must never reach stdout or the log. env-names
lists variable NAMES only across a unit's EnvironmentFiles (drop-ins
included), never values.

All files are created under tmp_path; _ALLOWED_READ_PREFIXES is patched to
point there so no real /var/lib/aitbc or /etc/aitbc content is touched.
"""

import json
import os
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
    """Patch the read allowlist to tmp_path for the duration of a test."""
    with mock.patch.object(system_mod, "_ALLOWED_READ_PREFIXES", (str(tmp_path) + "/",)):
        yield tmp_path


def _write_json(path, obj):
    path.write_text(json.dumps(obj))
    return path


# ---------------------------------------------------------------- file-info


def test_file_info_reports_metadata_and_json_keys(runner, allowed):
    f = _write_json(allowed / "node.json", {"address": "0xabc", "private_key": "0xdeadbeef", "label": "n1"})
    result = runner.invoke(system, obj={"output_format": "table"}, args=["file-info", "--path", str(f)])
    assert result.exit_code == 0, result.output
    assert "size" in result.output
    assert "mtime" in result.output
    assert "mode" in result.output
    assert "owner" in result.output
    # top-level key names are listed, but not a hash of the file
    for key in ("address", "label", "private_key"):
        assert key in result.output
    assert "sha256" not in result.output
    assert "0xdeadbeef" not in result.output


def test_file_info_field_prints_scalar(runner, allowed):
    f = _write_json(allowed / "node.json", {"Address": "0xAbC123", "label": "n1"})
    result = runner.invoke(system, obj={"output_format": "table"}, args=["file-info", "--path", str(f), "--field", "address"])
    assert result.exit_code == 0, result.output
    assert "0xAbC123" in result.output


@pytest.mark.parametrize("denied", ["private_key", "PRIVATE_KEY", "password", "api_key", "node_key", "seed"])
def test_file_info_field_denied_names_refused(runner, allowed, capsys, caplog, denied):
    secret = "0xSECRETNEVERPRINTED123"
    f = _write_json(allowed / "node.json", {denied: secret, "address": "0xabc"})
    result = runner.invoke(system, obj={"output_format": "table"}, args=["file-info", "--path", str(f), "--field", denied])
    assert result.exit_code != 0
    assert "refused" in result.output.lower() or "denied" in result.output.lower()
    # the denied value must never reach stdout or the log
    assert secret not in capsys.readouterr().out
    assert secret not in caplog.text


def test_file_info_field_denied_inside_nested_value(runner, allowed, capsys):
    secret = "0xSECRETNEVERPRINTED123"
    f = _write_json(allowed / "node.json", {"credentials": {"inner": {"private_key": secret}}})
    result = runner.invoke(
        system, obj={"output_format": "table"}, args=["file-info", "--path", str(f), "--field", "credentials"]
    )
    assert result.exit_code != 0
    assert secret not in capsys.readouterr().out


def test_file_info_field_non_scalar_refused(runner, allowed):
    f = _write_json(allowed / "node.json", {"peers": ["a", "b"]})
    result = runner.invoke(system, obj={"output_format": "table"}, args=["file-info", "--path", str(f), "--field", "peers"])
    assert result.exit_code != 0
    assert "scalar" in result.output


def test_file_info_field_over_200_chars_refused(runner, allowed, capsys):
    big = "x" * 201
    f = _write_json(allowed / "node.json", {"note": big})
    result = runner.invoke(system, obj={"output_format": "table"}, args=["file-info", "--path", str(f), "--field", "note"])
    assert result.exit_code != 0
    assert big not in capsys.readouterr().out


def test_file_info_field_missing_name(runner, allowed):
    f = _write_json(allowed / "node.json", {"address": "0xabc"})
    result = runner.invoke(system, obj={"output_format": "table"}, args=["file-info", "--path", str(f), "--field", "nosuch"])
    assert result.exit_code != 0
    assert "no such top-level field" in result.output


def test_file_info_field_on_non_json_refused(runner, allowed):
    f = allowed / "plain.log"
    f.write_text("just a log line\n")
    result = runner.invoke(system, obj={"output_format": "table"}, args=["file-info", "--path", str(f), "--field", "address"])
    assert result.exit_code != 0
    assert "JSON" in result.output


def test_file_info_rejects_path_outside_allowlist(runner, allowed):
    result = runner.invoke(system, obj={"output_format": "table"}, args=["file-info", "--path", "/etc/passwd"])
    assert result.exit_code != 0
    assert "not allowed" in result.output


def test_file_info_rejects_symlink_escaping_allowlist(runner, allowed, tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir(exist_ok=True)
    secret_file = _write_json(outside / "w.json", {"address": "0xabc"})
    link = allowed / "link.json"
    os.symlink(secret_file, link)
    result = runner.invoke(system, obj={"output_format": "table"}, args=["file-info", "--path", str(link)])
    assert result.exit_code != 0
    assert "not allowed" in result.output


def test_system_file_unchanged_still_dumps_content(runner, allowed):
    """Regression: the existing `system file` behaviour is untouched."""
    f = allowed / "node.json"
    f.write_text('{"address": "0xabc", "private_key": "0xdeadbeef"}')
    result = runner.invoke(system, obj={"output_format": "table"}, args=["file", "--path", str(f)])
    assert result.exit_code == 0
    assert "0xdeadbeef" in result.output


# ---------------------------------------------------------------- env-names


def _systemctl_result(stdout: str, returncode: int = 0):
    return mock.Mock(returncode=returncode, stdout=stdout, stderr="")


def test_env_names_lists_all_declared_files(runner, tmp_path):
    main_env = tmp_path / "svc.env"
    drop_env = tmp_path / "svc-dropin.env"
    main_env.write_text("FOO=1\nBAR=2\n# comment\n")
    drop_env.write_text("BAZ=3\n")
    show = f"{main_env} (ignore_errors=no) {drop_env} (ignore_errors=yes)\n"
    with mock.patch("aitbc_cli.commands.system.subprocess.run", return_value=_systemctl_result(show)):
        result = runner.invoke(system, obj={"output_format": "table"}, args=["env-names", "--service", "aitbc-svc"])
    assert result.exit_code == 0, result.output
    for name in ("FOO", "BAR", "BAZ"):
        assert name in result.output
    # values never print
    assert "=1" not in result.output and "=2" not in result.output and "=3" not in result.output
    assert "optional" in result.output  # the '-' / ignore_errors=yes file is marked


def test_env_names_missing_file_noted(runner, tmp_path):
    gone = tmp_path / "gone.env"
    show = f"{gone} (ignore_errors=yes)\n"
    with mock.patch("aitbc_cli.commands.system.subprocess.run", return_value=_systemctl_result(show)):
        result = runner.invoke(system, obj={"output_format": "table"}, args=["env-names", "--service", "aitbc-svc"])
    assert result.exit_code == 0, result.output
    assert "missing" in result.output


def test_env_names_filter_reports_set_unset(runner, tmp_path):
    env = tmp_path / "svc.env"
    env.write_text("FOO=1\n")
    show = f"{env} (ignore_errors=no)\n"
    with mock.patch("aitbc_cli.commands.system.subprocess.run", return_value=_systemctl_result(show)):
        result = runner.invoke(
            system,
            obj={"output_format": "table"},
            args=["env-names", "--service", "aitbc-svc", "--names", "FOO", "--names", "ABSENT"],
        )
    assert result.exit_code == 0, result.output
    assert "FOO" in result.output and "ABSENT" in result.output
    out = result.output
    foo_line = next(line for line in out.splitlines() if "FOO" in line)
    absent_line = next(line for line in out.splitlines() if "ABSENT" in line)
    assert foo_line != absent_line  # one true, one false — values themselves never appear
    assert "=1" not in out


def test_env_names_unparsed_line_reports_line_number_only(runner, tmp_path):
    env = tmp_path / "svc.env"
    env.write_text("FOO=1\nthis line has no key and might carry a value\nBAR=2\n")
    show = f"{env} (ignore_errors=no)\n"
    with mock.patch("aitbc_cli.commands.system.subprocess.run", return_value=_systemctl_result(show)):
        result = runner.invoke(system, obj={"output_format": "table"}, args=["env-names", "--service", "aitbc-svc"])
    assert result.exit_code == 0, result.output
    assert "2" in result.output  # the unparsed line number is reported…
    assert "this line has no key" not in result.output  # …but never its text


def test_env_names_no_declared_no_fallback_fails(runner, tmp_path):
    with (
        mock.patch("aitbc_cli.commands.system.subprocess.run", return_value=_systemctl_result("")),
        mock.patch("aitbc_cli.commands.system.Path.exists", return_value=False),
    ):
        result = runner.invoke(system, obj={"output_format": "table"}, args=["env-names", "--service", "aitbc-nosuch"])
    assert result.exit_code != 0
    assert "no EnvironmentFile" in result.output


def test_env_names_conventional_fallback(runner, tmp_path):
    """No declared EnvironmentFiles -> the conventional /etc/aitbc/<unit>.env is used."""
    env = tmp_path / "aitbc-svc.env"
    env.write_text("FALLBACK_KEY=1\n")
    real_path = system_mod.Path

    def fake_path(arg):
        return tmp_path if arg == "/etc/aitbc" else real_path(arg)

    with (
        mock.patch.object(system_mod, "_unit_env_files", return_value=[]),
        mock.patch.object(system_mod, "Path", side_effect=fake_path),
    ):
        result = runner.invoke(system, obj={"output_format": "table"}, args=["env-names", "--service", "aitbc-svc"])
    assert result.exit_code == 0, result.output
    assert "FALLBACK_KEY" in result.output
