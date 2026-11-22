"""White-label deployment commands (v0.16.2 §B4)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import cast

import click

from ..utils import output, success
from ..utils.error_handling import abort

_DEPLOY_SLUG_RE = re.compile(r"[A-Za-z0-9_-]+")


def _deploy_slug(ctx, value: object, field: str) -> str:
    """Validate a path component used under --storage (#2533).

    ``--network`` and the manifest ``brand_id`` are joined into the output
    path unvalidated — ``../`` and absolute paths escaped --storage. Only
    slug characters are accepted; the resolved-target check below is the
    second wall.
    """
    if not isinstance(value, str) or not _DEPLOY_SLUG_RE.fullmatch(value):
        abort(ctx, f"Invalid {field} {value!r}: use only letters, digits, '-' and '_'")
    return cast(str, value)


@click.group(
    epilog="""Examples:

  aitbc deploy deploy-brand --config-path /tmp/brand.yaml

  aitbc deploy deploy-brand --config-path /tmp/brand.yaml --network ait-mainnet --storage /var/deployments"""
)
def deploy():
    """Deploy and manage white-label platform configurations to target networks."""
    pass


@deploy.command(
    "deploy-brand",
    epilog="""Examples:

  aitbc deploy deploy-brand --config-path /tmp/brand.yaml

  aitbc deploy deploy-brand --config-path /tmp/brand.yaml --network ait-mainnet --storage /var/deployments""",
)
@click.option("--config", "config_path", required=True, type=click.Path(exists=True), help="Brand manifest JSON")
@click.option("--network", default="local", help="Target network")
@click.option("--storage", default="./deployments", help="Deployment output directory")
@click.pass_context
def deploy_brand(ctx, config_path: str, network: str, storage: str):
    """Deploy a white-label brand configuration to a target network and storage directory."""
    manifest_path = Path(config_path)
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    network = _deploy_slug(ctx, network, "--network")
    brand_id = _deploy_slug(ctx, manifest.get("brand_id", "brand"), "manifest brand_id")
    storage_root = Path(storage).resolve()
    target = storage_root / network / brand_id
    if not target.resolve().is_relative_to(storage_root):
        abort(ctx, f"Deployment target escapes --storage: {target}")
    target.mkdir(parents=True, exist_ok=True)
    deployed_path = target / "brand-manifest.json"
    with open(deployed_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    if ctx.obj["output"] == "table":
        success(f"Brand deployed to {deployed_path}")
    output({"deployed_path": str(deployed_path), "network": network, "manifest": manifest}, ctx.obj["output"])
