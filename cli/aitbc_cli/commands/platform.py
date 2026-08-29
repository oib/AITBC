"""White-label platform scaffolding commands (v0.16.2 §B4)."""

from __future__ import annotations

import json
from pathlib import Path

import click

from ..utils import output, success


@click.group(
    epilog="""Examples:

  aitbc platform init-platform --name 'My Platform'

  aitbc platform init-platform --name 'My Platform' --template default --output /tmp/platform"""
)
def platform():
    """Scaffold white-label platform configurations and brand manifests."""
    pass


@platform.command(
    "init-platform",
    epilog="""Examples:

  aitbc platform init-platform --name 'My Platform'

  aitbc platform init-platform --name 'My Platform' --template default --output /tmp/platform""",
)
@click.option("--name", required=True, help="Platform name")
@click.option("--template", default="default", help="Template name")
@click.option("--output", "output_dir", default=".", help="Output directory")
@click.pass_context
def init_platform(ctx, name: str, template: str, output_dir: str):
    """Initialize a white-label platform brand manifest in the output directory."""
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    manifest = {
        "brand_id": name.lower().replace(" ", "-"),
        "name": name,
        "domain": f"{name.lower().replace(' ', '-')}.example.com",
        "template": template,
        "assets": {
            "logo_url": "",
            "favicon_url": "",
            "primary_color": "#000000",
            "secondary_color": "#ffffff",
        },
        "endpoints": {
            "coordinator": "http://localhost:8000",
            "wallet": "http://localhost:8001",
        },
        "settlement": {
            "default_asset": "",
            "min_bond_amount": "0",
            "platform_fee_basis_points": 0,
            "disbursement_delay_blocks": 0,
        },
        "features": {},
    }
    manifest_path = target / "brand-manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    if ctx.obj["output"] == "table":
        success(f"Platform '{name}' initialized at {manifest_path}")
    output({"manifest_path": str(manifest_path), "brand": manifest}, ctx.obj["output"])
