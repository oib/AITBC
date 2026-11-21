"""Tests for ``aitbc config check-keys`` credential-source probing (#2420).

The command used to read only ``os.environ``, so keys provisioned in
``/etc/aitbc/*.env`` service files, ``~/.aitbc/credentials.env``, or the
``set-secret`` store were reported missing on a working node. It now
reports every source that defines each key — values are never printed.
"""

import json

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.config as config_mod
from aitbc_cli.commands.config import config


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    """Redirect every probed source at tmp dirs; strip the process env."""
    etc = tmp_path / "etc-aitbc"
    etc.mkdir()
    monkeypatch.setattr(config_mod, "_ETC_AITBC_DIR", etc)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    for var in (
        "AITBC_API_KEY",
        "CLIENT_API_KEY",
        "MINER_API_KEY",
        "MINER_API_KEYS",
        "ADMIN_API_KEY",
        "COORDINATOR_API_KEY",
        "OPENAI_API_KEY",
        "GOOGLE_TRANSLATE_API_KEY",
        "DEEPL_API_KEY",
        "EXCHANGE_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    return {"etc": etc, "home": home}


def _keys(result):
    doc = json.loads(result.stdout)
    return {k["key"]: k for k in doc["keys"]}


def test_env_only_source(runner, isolated, monkeypatch):
    monkeypatch.setenv("CLIENT_API_KEY", "env-secret")
    result = runner.invoke(config, obj={"output_format": "json"}, args=["check-keys"])
    assert result.exit_code == 0, result.output
    entry = _keys(result)["CLIENT_API_KEY"]
    assert entry["present"] is True
    assert entry["sources"] == ["env"]
    assert entry["length"] == len("env-secret")
    # The secret value itself must never appear in the output.
    assert "env-secret" not in result.stdout


def test_etc_env_file_source_counts_present(runner, isolated):
    (isolated["etc"] / "aitbc-node.env").write_text("CLIENT_API_KEY=file-secret\n")
    result = runner.invoke(config, obj={"output_format": "json"}, args=["check-keys"])
    assert result.exit_code == 0, result.output
    entry = _keys(result)["CLIENT_API_KEY"]
    assert entry["present"] is True
    assert entry["sources"] == [f"env-file:{isolated['etc'] / 'aitbc-node.env'}"]
    assert "file-secret" not in result.stdout


def test_credentials_env_and_secrets_file_sources(runner, isolated):
    cred_dir = isolated["home"] / ".aitbc"
    cred_dir.mkdir()
    (cred_dir / "credentials.env").write_text("ADMIN_API_KEY=cred-secret\n")
    secrets_dir = isolated["home"] / ".config" / "aitbc"
    secrets_dir.mkdir(parents=True)
    (secrets_dir / "secrets.json").write_text(json.dumps({"openai_api_key": "ZW5jb2RlZA=="}))

    result = runner.invoke(config, obj={"output_format": "json"}, args=["check-keys"])
    assert result.exit_code == 0, result.output
    keys = _keys(result)
    assert any(s.startswith("env-file:") for s in keys["ADMIN_API_KEY"]["sources"])
    assert keys["OPENAI_API_KEY"]["present"] is True
    assert "secrets-file" in keys["OPENAI_API_KEY"]["sources"]


def test_miner_api_keys_plural_alias(runner, isolated):
    (isolated["etc"] / "miner.env").write_text('MINER_API_KEYS=["k1","k2"]\n')
    result = runner.invoke(config, obj={"output_format": "json"}, args=["check-keys"])
    assert result.exit_code == 0, result.output
    assert _keys(result)["MINER_API_KEY"]["present"] is True


def test_missing_required_still_reported(runner, isolated):
    result = runner.invoke(config, obj={"output_format": "json"}, args=["check-keys"])
    assert result.exit_code == 0, result.output
    doc = json.loads(result.stdout)
    assert doc["required_present"] == 0
    assert set(doc["missing_required"]) == {
        "AITBC_API_KEY",
        "CLIENT_API_KEY",
        "MINER_API_KEY",
        "ADMIN_API_KEY",
        "COORDINATOR_API_KEY",
    }


def test_partial_env_file_fills_required_count(runner, isolated):
    (isolated["etc"] / "a.env").write_text("CLIENT_API_KEY=x\nADMIN_API_KEY=y\n")
    result = runner.invoke(config, obj={"output_format": "json"}, args=["check-keys"])
    doc = json.loads(result.stdout)
    assert doc["required_present"] == 2
    assert set(doc["missing_required"]) == {"AITBC_API_KEY", "MINER_API_KEY", "COORDINATOR_API_KEY"}


def test_strict_exits_nonzero_when_required_missing(runner, isolated):
    result = runner.invoke(config, obj={"output_format": "json"}, args=["check-keys", "--strict"])
    assert result.exit_code == 1


def test_cwd_config_warning_names_absolute_path(monkeypatch, tmp_path):
    """The ambient-config warning must show the resolved path so it visibly
    matches `config show`/`config path` output (#2420)."""
    import re

    import aitbc_cli.config as cli_config

    (tmp_path / ".aitbc.yaml").write_text("timeout: 5\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AITBC_CONFIG_FILE", raising=False)
    with pytest.warns(UserWarning, match=re.escape(str(tmp_path / ".aitbc.yaml"))):
        cfg = cli_config.get_config()
    assert cfg.config_file == str(tmp_path / ".aitbc.yaml")
