"""#2591: ``exchange register`` must store credentials owner-only, accept them
from file/stdin/prompt instead of argv, and ``exchange status`` must never
echo the stored secrets."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest
from click.testing import CliRunner

from aitbc_cli.commands.exchange.main import exchange

API_KEY = "test-api-key-0001"
SECRET_KEY = "test-secret-key-0002"


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AITBC_EXCHANGE_API_KEY", "")
    monkeypatch.setenv("AITBC_EXCHANGE_SECRET_KEY", "")
    return tmp_path


def _exchanges_path(home: Path) -> Path:
    return home / ".aitbc" / "exchanges.json"


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _invoke(runner, args, **kwargs):
    return runner.invoke(exchange, args, obj={"output_format": "json"}, **kwargs)


def test_register_writes_0600_in_0700_dir(runner, home):
    old = os.umask(0o022)
    try:
        result = _invoke(runner, ["register", "--name", "binance", "--api-key", API_KEY])
    finally:
        os.umask(old)
    assert result.exit_code == 0, result.output
    path = _exchanges_path(home)
    assert _mode(path) == 0o600
    assert _mode(path.parent) == 0o700
    # argv form still works but warns
    assert "process list" in result.output


def test_status_never_prints_secrets(runner, home):
    _invoke(runner, ["register", "--name", "binance", "--api-key", API_KEY, "--secret-key", SECRET_KEY])
    result = _invoke(runner, ["status", "--exchange-name", "binance"])
    assert result.exit_code == 0, result.output
    assert API_KEY not in result.output
    assert SECRET_KEY not in result.output
    assert "***0001" in result.output  # last-four mask only
    assert "***0002" in result.output


def test_secret_key_file_and_stdin(runner, home, tmp_path):
    key_file = tmp_path / "binance.key"
    key_file.write_text(SECRET_KEY + "\n")
    os.chmod(key_file, 0o600)
    result = _invoke(
        runner,
        ["register", "--name", "binance", "--api-key-file", str(_write_api(home)), "--secret-key-file", str(key_file)],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(_exchanges_path(home).read_text())
    assert data["binance"]["secret_key"] == SECRET_KEY
    assert "process list" not in result.output

    result = _invoke(
        runner,
        ["register", "--name", "kraken", "--api-key-stdin", "--secret-key-stdin"],
        input=f"{API_KEY}\n{SECRET_KEY}\n",
    )
    assert result.exit_code == 0, result.output
    data = json.loads(_exchanges_path(home).read_text())
    assert data["kraken"]["api_key"] == API_KEY
    assert data["kraken"]["secret_key"] == SECRET_KEY


def _write_api(home: Path) -> Path:
    p = home / "api.key"
    p.write_text(API_KEY + "\n")
    os.chmod(p, 0o600)
    return p


def test_api_key_prompt_when_no_source(runner, home):
    result = _invoke(runner, ["register", "--name", "binance"], input=f"{API_KEY}\n")
    assert result.exit_code == 0, result.output
    data = json.loads(_exchanges_path(home).read_text())
    assert data["binance"]["api_key"] == API_KEY
    assert data["binance"]["secret_key"] == "NOT_SET"


def test_env_vars_supply_credentials(runner, home, monkeypatch):
    monkeypatch.setenv("AITBC_EXCHANGE_API_KEY", API_KEY)
    monkeypatch.setenv("AITBC_EXCHANGE_SECRET_KEY", SECRET_KEY)
    result = _invoke(runner, ["register", "--name", "binance"])
    assert result.exit_code == 0, result.output
    data = json.loads(_exchanges_path(home).read_text())
    assert data["binance"]["api_key"] == API_KEY
    assert data["binance"]["secret_key"] == SECRET_KEY


def test_other_writers_keep_0600(runner, home):
    _invoke(runner, ["register", "--name", "binance", "--api-key", API_KEY])
    _invoke(
        runner,
        ["create-pair", "--base-asset", "AITBC", "--quote-asset", "ETH", "--exchange", "binance"],
    )
    path = _exchanges_path(home)
    assert _mode(path) == 0o600
    assert _mode(path.parent) == 0o700
