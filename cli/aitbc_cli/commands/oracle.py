"""Local data oracle commands for AITBC CLI.

Filesystem-backed data-oracle surface used by the ``aitbc_agent`` SDK. Stores
CID listings so that agents can announce data availability and buyers can list
available data sets.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import click

from aitbc.constants import DATA_DIR

ORACLE_DIR = Path(os.environ.get("AITBC_ORACLE_DIR") or str(DATA_DIR / "oracle"))
IPFS_DIR = Path(os.environ.get("AITBC_IPFS_DIR") or str(DATA_DIR / "ipfs"))
LISTINGS_FILE = ORACLE_DIR / "listings.json"


def _ensure_oracle_dir() -> None:
    """Create the oracle directory on demand; imports must not fail on fresh runners."""
    ORACLE_DIR.mkdir(parents=True, exist_ok=True)


def _load_listings() -> list[dict[str, Any]]:
    if not LISTINGS_FILE.exists():
        return []
    try:
        return cast(list, json.loads(LISTINGS_FILE.read_text()))
    except (json.JSONDecodeError, OSError):
        return []


def _save_listings(listings: list[dict[str, Any]]) -> None:
    _ensure_oracle_dir()
    LISTINGS_FILE.write_text(json.dumps(listings, indent=2))


@click.group(
    epilog="""Examples:

  aitbc oracle store --cid Qm... --price 10

  aitbc oracle listings"""
)
@click.pass_context
def oracle(ctx):
    """Local data oracle for agent data availability announcements."""
    ctx.ensure_object(dict)


def _cid_exists(cid: str) -> bool:
    """Check CID presence on the same backend ``aitbc ipfs`` resolved.

    ``ipfs upload`` prefers a live Kubo daemon and only falls back to the
    filesystem store — checking only ``IPFS_DIR`` refused every
    daemon-uploaded CID (ORACLE-IPFS-BACKEND-SPLIT-1, #2339).
    """
    from .ipfs import _ipfs_object_size, resolve_ipfs_api

    ipfs_api = resolve_ipfs_api()
    if ipfs_api is not None:
        return _ipfs_object_size(ipfs_api, cid) is not None
    return (IPFS_DIR / cid).exists()


@oracle.command(
    epilog="""Examples:

  aitbc oracle store --cid Qm... --price 10

  aitbc oracle store --cid Qm... --price 10 --description 'training data'"""
)
@click.option("--cid", required=True, help="Content identifier to announce")
@click.option("--price", required=True, help="Price for the data set (in AIT)")
@click.option("--description", default="", help="Description of the data")
@click.pass_context
def store(ctx, cid: str, price: str, description: str):
    """Announce a CID for sale on the local data oracle."""
    if not _cid_exists(cid):
        result = {"success": False, "error": f"CID not found in local IPFS store: {cid}"}
        click.echo(json.dumps(result))
        raise click.Abort()

    listings = _load_listings()
    listings = [entry for entry in listings if entry.get("cid") != cid]
    announcement_id = f"ann_{uuid.uuid4().hex[:12]}"
    listings.append(
        {
            "announcement_id": announcement_id,
            "cid": cid,
            "price": str(Decimal(price)),
            "description": description,
            "status": "active",
            "created_at": datetime.now(UTC).isoformat(),
        }
    )
    _save_listings(listings)

    result = {
        "success": True,
        "data": {
            "announcement_id": announcement_id,
            "cid": cid,
            "price": str(Decimal(price)),
            "description": description,
        },
    }
    click.echo(json.dumps(result))


@oracle.command(
    epilog="""Examples:

  aitbc oracle listings

  aitbc oracle listings --output json"""
)
@click.pass_context
def listings(ctx):
    """List all active data oracle announcements."""
    result = {"success": True, "data": {"listings": _load_listings()}}
    click.echo(json.dumps(result))
