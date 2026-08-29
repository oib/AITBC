"""Brand and white-label commands for AITBC CLI."""

from __future__ import annotations

import os
from dataclasses import asdict

import click

from aitbc_agent_core.branding import BrandSettings
from aitbc_agent_core.plugins import PluginManager

from ..utils import output


def _get_brand() -> BrandSettings:
    active = os.getenv("AITBC_ACTIVE_PLUGIN")
    if active:
        return PluginManager(os.getenv("AITBC_PLUGINS_DIR", "/opt/aitbc/plugins")).load(active).brand
    return BrandSettings.from_env()


@click.group(
    epilog="""Examples:

  aitbc brand show

  aitbc brand list"""
)
def brand():
    """Show and manage white-label brand settings and plugins."""
    pass


@brand.command(
    name="show",
    epilog="""Examples:

  aitbc brand show

  aitbc brand show --output json""",
)
@click.pass_context
def show_brand(ctx):
    """Display the active brand configuration from the environment or plugin."""
    b = _get_brand()
    result = {
        "source": os.getenv("AITBC_ACTIVE_PLUGIN", "environment/defaults"),
        **asdict(b),
    }
    output(result, ctx.obj.get("output_format", "table"), title="Brand")


@brand.command(
    name="list",
    epilog="""Examples:

  aitbc brand list

  aitbc brand list --output json""",
)
@click.pass_context
def list_plugins(ctx):
    """List available brand plugins in the configured plugin directory."""
    pm = PluginManager(os.getenv("AITBC_PLUGINS_DIR", "/opt/aitbc/plugins"))
    names = pm.list_plugins()
    result = {"plugins_dir": str(pm.plugins_dir), "plugins": names}
    output(result, ctx.obj.get("output_format", "table"), title="Brand Plugins")
