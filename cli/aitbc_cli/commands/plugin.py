"""Plugin scaffolding commands (v0.16.2 §B4)."""

from __future__ import annotations

from pathlib import Path

import click

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
    import json

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
