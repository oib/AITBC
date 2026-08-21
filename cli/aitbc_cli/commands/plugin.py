"""Plugin scaffolding and discovery commands (v0.16.2 §B4)."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

import click

from aitbc_agent_core.plugins import PluginManager

from ..utils import output, success


@click.group()
def plugin():
    """Scaffold and manage AITBC plugins."""
    pass


@plugin.command("create")
@click.option("--type", "plugin_type", required=True, help="Plugin type")
@click.option("--name", required=True, help="Plugin name")
@click.option("--output", "output_dir", default=".", help="Output directory")
@click.pass_context
def create_plugin(ctx, plugin_type: str, name: str, output_dir: str):
    """Create a plugin manifest and skeleton."""
    target = Path(output_dir) / name
    target.mkdir(parents=True, exist_ok=True)

    manifest = {
        "name": name,
        "version": "0.1.0",
        "type": plugin_type,
        "entry_point": f"{name}.plugin:register",
        "hooks": ["onResourceDiscovery", "onNegotiationStart", "onProofGeneration", "onVerificationSuccess"],
        "config": {},
    }
    manifest_path = target / "plugin-manifest.json"

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    plugin_file = target / "plugin.py"
    plugin_file.write_text(
        f"""\"\"\"{name} plugin for AITBC.\"\"\"

from aitbc_core.plugins.manifest import PluginHookRegistry


def register(registry: PluginHookRegistry, config: dict) -> None:
    \"\"\"Register plugin hooks.\"\"\"
    registry.register("onResourceDiscovery", lambda ctx: ctx)
""",
        encoding="utf-8",
    )

    if ctx.obj["output"] == "table":
        success(f"Plugin '{name}' created at {target}")
    output({"plugin_path": str(target), "manifest": manifest}, ctx.obj["output"])


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
