"""Exercise the real ``CLIConfig`` path for the energy rate window.

The Task-33 fix added ``CLIConfig.energy_max_rate_age_seconds`` (default
86400) and threaded it into every CLI quote-verification call site. Those
call sites are covered in ``test_cli_energy_quote.py`` with a mocked
``get_config``; this file covers the configuration machinery itself with
the real ``CLIConfig``:

- the default is 86400 (the operator policy the coordinator runs on hub);
- ``ENERGY_MAX_RATE_AGE_SECONDS`` binds — the same variable name the
  coordinator and the node RPC honour;
- the YAML key ``energy_max_rate_age_seconds`` loads through
  ``CONFIG_FILE_KEYS``;
- ``aitbc config set energy_max_rate_age_seconds 600`` writes an integer
  through ``_INT_CONFIG_KEYS`` and ``get_config()`` reads it back.
"""

from __future__ import annotations

import yaml
from click.testing import CliRunner

from aitbc_cli.commands.config import config as config_group
from aitbc_cli.config import CLIConfig, get_config


def test_default_is_86400(monkeypatch) -> None:
    """The field exists and defaults to the operator's 24 h window."""
    monkeypatch.delenv("ENERGY_MAX_RATE_AGE_SECONDS", raising=False)
    assert CLIConfig().energy_max_rate_age_seconds == 86400


def test_env_var_binds(monkeypatch) -> None:
    """The same name as the coordinator's setting binds with no prefix."""
    monkeypatch.setenv("ENERGY_MAX_RATE_AGE_SECONDS", "600")
    assert CLIConfig().energy_max_rate_age_seconds == 600


def test_yaml_key_loads(tmp_path, monkeypatch) -> None:
    """The YAML key is in CONFIG_FILE_KEYS and reaches the field."""
    monkeypatch.delenv("ENERGY_MAX_RATE_AGE_SECONDS", raising=False)
    cfg_file = tmp_path / ".aitbc.yaml"
    cfg_file.write_text("energy_max_rate_age_seconds: 7200\n")
    assert get_config(str(cfg_file)).energy_max_rate_age_seconds == 7200


def test_config_set_round_trips(tmp_path, monkeypatch) -> None:
    """`config set` writes an integer that get_config() reads back."""
    cfg_file = tmp_path / ".aitbc.yaml"
    monkeypatch.setenv("AITBC_CONFIG_FILE", str(cfg_file))
    monkeypatch.delenv("ENERGY_MAX_RATE_AGE_SECONDS", raising=False)
    result = CliRunner().invoke(
        config_group,
        ["set", "--key", "energy_max_rate_age_seconds", "--value", "600"],
        obj={},
    )
    assert result.exit_code == 0, result.output
    stored = yaml.safe_load(cfg_file.read_text())
    assert stored["energy_max_rate_age_seconds"] == 600
    assert isinstance(stored["energy_max_rate_age_seconds"], int)
    assert get_config().energy_max_rate_age_seconds == 600


def test_config_set_rejects_non_integer(tmp_path, monkeypatch) -> None:
    """_INT_CONFIG_KEYS coercion: a non-integer value exits non-zero."""
    cfg_file = tmp_path / ".aitbc.yaml"
    monkeypatch.setenv("AITBC_CONFIG_FILE", str(cfg_file))
    result = CliRunner().invoke(
        config_group,
        ["set", "--key", "energy_max_rate_age_seconds", "--value", "abc"],
        obj={},
    )
    assert result.exit_code != 0
