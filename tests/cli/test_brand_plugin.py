"""Tests for brand and plugin CLI commands."""

import json
import re
from pathlib import Path

import pytest
from click.testing import CliRunner

from aitbc_cli.commands.brand import brand
from aitbc_cli.commands.plugin import plugin


def _parse_json_output(output: str) -> dict:
    """Extract the JSON object from CLI table+JSON output."""
    match = re.search(r"\{.*\}", output, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object in output: {output!r}")
    return json.loads(match.group(0))


@pytest.fixture
def runner():
    return CliRunner()


def test_brand_show_defaults(runner):
    result = runner.invoke(brand, ["show"])
    assert result.exit_code == 0
    data = _parse_json_output(result.output)
    assert data["name"] == "AITBC"


def test_brand_show_from_env(runner, monkeypatch):
    monkeypatch.setenv("AITBC_BRAND_NAME", "EnvCo")
    result = runner.invoke(brand, ["show"])
    assert result.exit_code == 0
    data = _parse_json_output(result.output)
    assert data["name"] == "EnvCo"


def test_plugin_list_finds_demo(tmp_path, runner, monkeypatch):
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    (plugins_dir / "demo.py").write_text(
        "from aitbc_agent_core.branding import BrandSettings\n"
        "brand = BrandSettings.default()\n"
        "roles = {}\n"
        "identity_method = 'did:demo'\n"
    )
    monkeypatch.setenv("AITBC_PLUGINS_DIR", str(plugins_dir))
    result = runner.invoke(plugin, ["list"])
    assert result.exit_code == 0
    data = _parse_json_output(result.output)
    assert "demo" in data["plugins"]


def test_plugin_load_demo(tmp_path, runner, monkeypatch):
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    (plugins_dir / "demo.py").write_text(
        "from aitbc_agent_core.branding import BrandSettings\n"
        "brand = BrandSettings(name='Demo', token_symbol='D', token_name='Demo Token', "
        "network_name='Demo Net', dao_name='Demo DAO', wallet_name='Demo Wallet', "
        "explorer_name='Demo Explorer')\n"
        "roles = {}\n"
        "identity_method = 'did:demo'\n"
    )
    monkeypatch.setenv("AITBC_PLUGINS_DIR", str(plugins_dir))
    result = runner.invoke(plugin, ["load", "demo"])
    assert result.exit_code == 0
    data = _parse_json_output(result.output)
    assert data["name"] == "demo"
    assert data["brand"]["name"] == "Demo"

def test_plugin_create_writes_loadable_plugin(tmp_path, runner, monkeypatch):
    """``aitbc plugin create`` writes a .py plugin that PluginManager can load."""
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    result = runner.invoke(plugin, ["create", "--name", "newbrand", "--output", str(plugins_dir)])
    assert result.exit_code == 0, result.output
    data = _parse_json_output(result.output)
    assert (plugins_dir / "newbrand.py").exists()

    monkeypatch.setenv("AITBC_PLUGINS_DIR", str(plugins_dir))
    result = runner.invoke(plugin, ["load", "newbrand"])
    assert result.exit_code == 0, result.output
    data = _parse_json_output(result.output)
    assert data["name"] == "newbrand"
    assert data["brand"]["token_symbol"] == "NEWB"


def test_brand_show_uses_active_plugin(tmp_path, runner, monkeypatch):
    """AITBC_ACTIVE_PLUGIN makes ``aitbc brand show`` load that plugin's brand."""
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    (plugins_dir / "custom.py").write_text(
        "from aitbc_agent_core.branding import BrandSettings\n"
        "brand = BrandSettings(name='CustomBrand', token_symbol='CUST', token_name='Custom Token', "
        "network_name='Custom Net', dao_name='Custom DAO', wallet_name='Custom Wallet', "
        "explorer_name='Custom Explorer')\n"
        "roles = {}\n"
        "identity_method = 'did:custom'\n"
    )
    monkeypatch.setenv("AITBC_PLUGINS_DIR", str(plugins_dir))
    monkeypatch.setenv("AITBC_ACTIVE_PLUGIN", "custom")
    result = runner.invoke(brand, ["show"])
    assert result.exit_code == 0, result.output
    data = _parse_json_output(result.output)
    assert data["name"] == "CustomBrand"
    assert data["source"] == "custom"

