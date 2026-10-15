"""Tests for ``aitbc config get <key>`` (CLI-3).

Prints the stored value of one key from the config file; bare ``config get``
stays an alias for ``config show``. Absent keys exit nonzero; sensitive key
names (the file-info denylist plus passphrase/credential) are refused
outright — a denied value must never reach stdout.
"""

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.config as config_mod
from aitbc_cli.commands.config import config


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    """A temp local config file wired in via AITBC_CONFIG_FILE."""
    f = tmp_path / "aitbc.yaml"
    f.write_text(
        "coordinator_api_url: http://hub.example:8201\n"
        "exchange_service_url: https://hub.example\n"
        "timeout: 60\n"
        "api_key: sk-secret-value\n"
    )
    monkeypatch.setenv("AITBC_CONFIG_FILE", str(f))
    return f


def test_get_prints_stored_value(runner, cfg):
    result = runner.invoke(config, obj={"output_format": "table"}, args=["get", "exchange_service_url"])
    assert result.exit_code == 0, result.output
    assert "https://hub.example" in result.output


def test_get_absent_key_exits_nonzero(runner, cfg):
    result = runner.invoke(config, obj={"output_format": "table"}, args=["get", "no_such_key_xyz"])
    assert result.exit_code != 0
    assert "no_such_key_xyz" in result.output


def test_get_denied_key_refused_and_never_prints(runner, cfg):
    for denied in ("api_key", "private_key", "smtp_key", "passphrase", "credential", "key"):
        result = runner.invoke(config, obj={"output_format": "table"}, args=["get", denied])
        assert result.exit_code != 0, denied
        assert "sk-secret-value" not in result.output


def test_get_missing_file_exits_nonzero(runner, tmp_path, monkeypatch):
    monkeypatch.setenv("AITBC_CONFIG_FILE", str(tmp_path / "absent.yaml"))
    result = runner.invoke(config, obj={"output_format": "table"}, args=["get", "timeout"])
    assert result.exit_code != 0


def test_bare_get_still_shows_config(runner, cfg):
    result = runner.invoke(config, obj={"output_format": "table"}, args=["get"])
    assert result.exit_code == 0, result.output
    # the show alias redacts api_key — the stored secret must not print either
    assert "sk-secret-value" not in result.output


def test_get_global_reads_global_file(runner, tmp_path, monkeypatch):
    monkeypatch.setenv("AITBC_CONFIG_FILE", str(tmp_path / "local.yaml"))
    gfile = tmp_path / "config.yaml"
    gfile.write_text("timeout: 99\n")
    monkeypatch.setattr(config_mod, "_global_config_path", lambda create=False: gfile)
    result = runner.invoke(config, obj={"output_format": "table"}, args=["get", "timeout", "--global"])
    assert result.exit_code == 0, result.output
    assert "99" in result.output
