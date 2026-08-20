"""White-label deployment commands (v0.16.2 §B4)."""

from __future__ import annotations

import json
from pathlib import Path

import click

from ..utils import output, success


@click.group()
def deploy():
    """Deploy and manage white-label platform configurations."""
    pass


@deploy.command("deploy-brand")
@click.option("--config", "config_path", required=True, type=click.Path(exists=True), help="Brand manifest JSON")
@click.option("--network", default="local", help="Target network")
@click.option("--storage", default="./deployments", help="Deployment output directory")
@click.pass_context
def deploy_brand(ctx, config_path: str, network: str, storage: str):
    """Deploy a white-label brand configuration to a target network."""
    manifest_path = Path(config_path)
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    target = Path(storage) / network / manifest.get("brand_id", "brand")
    target.mkdir(parents=True, exist_ok=True)
    deployed_path = target / "brand-manifest.json"
    with open(deployed_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    if ctx.obj["output"] == "table":
        success(f"Brand deployed to {deployed_path}")
    output({"deployed_path": str(deployed_path), "network": network, "manifest": manifest}, ctx.obj["output"])
