"""Plugin scaffolding and discovery commands (v0.16.2 §B4)."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

import click

from aitbc_agent_core.plugins import PluginManager

from ..utils import output, success


def _default_roles() -> dict[str, str]:
    return {
        "Provider": "provider",
        "Consumer": "consumer",
        "Validator": "validator",
        "Arbiter": "arbiter",
    }


@click.group()
def plugin():
    """Scaffold and manage AITBC white-label brand plugins."""
    pass


@plugin.command("create")
@click.option("--type", "plugin_type", default="brand", help="Plugin type (metadata only)")
@click.option("--name", required=True, help="Plugin name")
@click.option("--output", "output_dir", default=".", help="Output directory")
@click.pass_context
def create_plugin(ctx, plugin_type: str, name: str, output_dir: str):
    """Create a brand plugin skeleton that PluginManager can load.

    Writes a single <name>.py file into <output_dir> with the brand, roles, and
    identity_method that the white-label loader expects. A plugin-manifest.json
    is also written for documentation but is not required by the loader.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    plugin_file = out_dir / f"{name}.py"
    plugin_file.write_text(
        f'''"""{name} white-label brand plugin for AITBC."""

from aitbc_agent_core.branding import BrandSettings

brand = BrandSettings(
    name="{name.title()}",
    token_symbol="{name.upper()[:4]}",
    token_name="{name.title()} Token",
    network_name="{name.title()} Network",
    dao_name="{name.title()} DAO",
    wallet_name="{name.title()} Wallet",
    explorer_name="{name.title()} Explorer",
)

roles = {{
    "Provider": "{name}-provider",
    "Consumer": "{name}-consumer",
    "Validator": "{name}-validator",
    "Arbiter": "{name}-arbiter",
}}

identity_method = "did:{name}"
''',
        encoding="utf-8",
    )

    manifest = {
        "name": name,
        "version": "0.1.0",
        "type": plugin_type,
        "entry_point": f"{name}.py",
        "hooks": ["onBrandDiscovery", "onNegotiationStart", "onProofGeneration", "onVerificationSuccess"],
        "config": {},
    }
    manifest_path = out_dir / f"{name}-manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    if ctx.obj.get("output") == "table":
        success(f"Plugin '{name}' created at {plugin_file}")
    output(
        {"plugin_path": str(plugin_file), "manifest_path": str(manifest_path), "manifest": manifest},
        ctx.obj.get("output", "table"),
    )


@plugin.command("list")
@click.option(
    "--plugins-dir",
    default=None,
    envvar="AITBC_PLUGINS_DIR",
    help="Directory containing .py brand plugins",
)
@click.pass_context
def list_plugins(ctx, plugins_dir: str | None):
    """List available brand plugins."""
    pm = PluginManager(plugins_dir or os.getenv("AITBC_PLUGINS_DIR", "/opt/aitbc/plugins"))
    names = pm.list_plugins()
    output({"plugins_dir": str(pm.plugins_dir), "plugins": names}, ctx.obj.get("output_format", "table"))


@plugin.command("load")
@click.argument("name")
@click.option(
    "--plugins-dir",
    default=None,
    envvar="AITBC_PLUGINS_DIR",
    help="Directory containing .py brand plugins",
)
@click.pass_context
def load_plugin(ctx, name: str, plugins_dir: str | None):
    """Load and display a brand plugin."""
    pm = PluginManager(plugins_dir or os.getenv("AITBC_PLUGINS_DIR", "/opt/aitbc/plugins"))
    loaded = pm.load(name)
    result = {
        "name": loaded.name,
        "identity_method": loaded.identity_method,
        "brand": asdict(loaded.brand),
        "roles": {role.value: address for role, address in loaded.roles.items()},
    }
    output(result, ctx.obj.get("output_format", "table"), title=f"Plugin {name}")
