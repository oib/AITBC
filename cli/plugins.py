"""Plugin system for AITBC CLI custom commands"""

import importlib
import importlib.util
import json
import click
from pathlib import Path
from typing import Optional


PLUGIN_DIR = Path.home() / ".aitbc" / "plugins"


def get_plugin_dir() -> Path:
    """Get and ensure plugin directory exists"""
    PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
    return PLUGIN_DIR


def load_plugins(cli_group):
    """Load all plugins and register them with the CLI group"""
    plugin_dir = get_plugin_dir()
    manifest_file = plugin_dir / "plugins.json"

    if not manifest_file.exists():
        return

    with open(manifest_file) as f:
        manifest = json.load(f)

    for plugin_info in manifest.get("plugins", []):
        if not plugin_info.get("enabled", True):
            continue

        plugin_path = plugin_dir / plugin_info["file"]
        if not plugin_path.exists():
            continue

        try:
            spec = importlib.util.spec_from_file_location(
                plugin_info["name"], str(plugin_path)
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Look for a click group or command named 'plugin_command'
            if hasattr(module, "plugin_command"):
                cli_group.add_command(module.plugin_command)
        except Exception:
            pass  # Skip broken plugins silently


@click.group()
def plugin():
    """Manage CLI plugins"""
    pass


@plugin.command(name="list")
@click.pass_context
def list_plugins(ctx):
    """List installed plugins"""
    from .utils import output

    plugin_dir = get_plugin_dir()
    manifest_file = plugin_dir / "plugins.json"

    if not manifest_file.exists():
        output({"message": "No plugins installed"}, ctx.obj.get('output_format', 'table'))
        return

    with open(manifest_file) as f:
        manifest = json.load(f)

    plugins = manifest.get("plugins", [])
    if not plugins:
        output({"message": "No plugins installed"}, ctx.obj.get('output_format', 'table'))
    else:
        output(plugins, ctx.obj.get('output_format', 'table'))


@plugin.command()
@click.argument("name")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--description", default="", help="Plugin description")
@click.pass_context
def install(ctx, name: str, file_path: str, description: str):
    """Install a plugin from a Python file"""
    import shutil
    from .utils import output, error, success

    plugin_dir = get_plugin_dir()
    manifest_file = plugin_dir / "plugins.json"

    # Copy plugin file
    dest = plugin_dir / f"{name}.py"
    shutil.copy2(file_path, dest)

    # Update manifest
    manifest = {"plugins": []}
    if manifest_file.exists():
        with open(manifest_file) as f:
            manifest = json.load(f)

    # Remove existing entry with same name
    manifest["plugins"] = [p for p in manifest["plugins"] if p["name"] != name]
    manifest["plugins"].append({
        "name": name,
        "file": f"{name}.py",
        "description": description,
        "enabled": True
    })

    with open(manifest_file, "w") as f:
        json.dump(manifest, f, indent=2)

    success(f"Plugin '{name}' installed")
    output({"name": name, "file": str(dest), "status": "installed"}, ctx.obj.get('output_format', 'table'))


@plugin.command()
@click.argument("name")
@click.pass_context
def uninstall(ctx, name: str):
    """Uninstall a plugin"""
    from .utils import output, error, success

    plugin_dir = get_plugin_dir()
    manifest_file = plugin_dir / "plugins.json"

    if not manifest_file.exists():
        error(f"Plugin '{name}' not found")
        return

    with open(manifest_file) as f:
        manifest = json.load(f)

    plugin_entry = next((p for p in manifest["plugins"] if p["name"] == name), None)
    if not plugin_entry:
        error(f"Plugin '{name}' not found")
        return

    # Remove file
    plugin_file = plugin_dir / plugin_entry["file"]
    if plugin_file.exists():
        plugin_file.unlink()

    # Update manifest
    manifest["plugins"] = [p for p in manifest["plugins"] if p["name"] != name]
    with open(manifest_file, "w") as f:
        json.dump(manifest, f, indent=2)

    success(f"Plugin '{name}' uninstalled")
    output({"name": name, "status": "uninstalled"}, ctx.obj.get('output_format', 'table'))


@plugin.command()
@click.argument("name")
@click.argument("state", type=click.Choice(["enable", "disable"]))
@click.pass_context
def toggle(ctx, name: str, state: str):
    """Enable or disable a plugin"""
    from .utils import output, error, success

    plugin_dir = get_plugin_dir()
    manifest_file = plugin_dir / "plugins.json"

    if not manifest_file.exists():
        error(f"Plugin '{name}' not found")
        return

    with open(manifest_file) as f:
        manifest = json.load(f)

    plugin_entry = next((p for p in manifest["plugins"] if p["name"] == name), None)
    if not plugin_entry:
        error(f"Plugin '{name}' not found")
        return

    plugin_entry["enabled"] = (state == "enable")

    with open(manifest_file, "w") as f:
        json.dump(manifest, f, indent=2)

    success(f"Plugin '{name}' {'enabled' if state == 'enable' else 'disabled'}")
    output({"name": name, "enabled": plugin_entry["enabled"]}, ctx.obj.get('output_format', 'table'))
