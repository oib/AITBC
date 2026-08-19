"""Local IPFS storage commands for AITBC CLI.

This is a filesystem-backed implementation used when no external IPFS daemon
is available. It provides the ``ipfs upload|download|pin|list`` subcommands
that the ``aitbc_agent`` SDK expects to find on PATH.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import click

IPFS_DIR = Path("/var/lib/aitbc/ipfs")
IPFS_DIR.mkdir(parents=True, exist_ok=True)


def _cid_for(data: bytes) -> str:
    """Compute a deterministic content id from bytes."""
    digest = hashlib.sha256(data).hexdigest()
    return f"Qm{digest[:44]}"


def _index_path() -> Path:
    return IPFS_DIR / "index.json"


def _load_index() -> list[dict[str, Any]]:
    path = _index_path()
    if not path.exists():
        return []
    try:
        return cast(list, json.loads(path.read_text()))
    except (json.JSONDecodeError, OSError):
        return []


def _save_index(items: list[dict[str, Any]]) -> None:
    _index_path().write_text(json.dumps(items, indent=2))


def _make_cid_path(cid: str) -> Path:
    return IPFS_DIR / cid


@click.group()
@click.pass_context
def ipfs(ctx):
    """Local content-addressed storage (IPFS-compatible surface)."""
    ctx.ensure_object(dict)


@ipfs.command()
@click.option("--file", required=True, type=click.Path(exists=True, readable=True), help="File to upload")
@click.option("--pin", is_flag=True, default=True, help="Pin uploaded content")
@click.option("--name", default=None, help="Human-readable name for the upload")
@click.pass_context
def upload(ctx, file: str, pin: bool, name: str | None):
    """Upload a file and return its CID."""
    file_path = Path(file)
    data = file_path.read_bytes()
    cid = _cid_for(data)
    cid_path = _make_cid_path(cid)
    cid_path.write_bytes(data)

    items = _load_index()
    items = [i for i in items if i.get("cid") != cid]
    items.append(
        {
            "cid": cid,
            "name": name or file_path.name,
            "size": len(data),
            "pinned": pin,
            "uploaded_at": datetime.now(UTC).isoformat(),
        }
    )
    _save_index(items)

    result = {"success": True, "data": {"cid": cid, "size": len(data), "name": name or file_path.name}}
    click.echo(json.dumps(result))


@ipfs.command()
@click.argument("cid")
@click.option("--output", type=click.Path(), help="Write retrieved content to this path")
@click.pass_context
def download(ctx, cid: str, output: str | None):
    """Download content by CID."""
    cid_path = _make_cid_path(cid)
    if not cid_path.exists():
        result = {"success": False, "error": f"CID not found: {cid}"}
        click.echo(json.dumps(result))
        raise click.Abort()

    data = cid_path.read_bytes()
    if output:
        out_path = Path(output)
        out_path.write_bytes(data)
        file_path = str(out_path)
    else:
        with tempfile.NamedTemporaryFile(delete=False, mode="wb") as tmp:
            tmp.write(data)
            file_path = tmp.name

    result = {"success": True, "data": {"cid": cid, "file_path": file_path, "size": len(data)}}
    click.echo(json.dumps(result))


@ipfs.command()
@click.argument("cid")
@click.pass_context
def pin(ctx, cid: str):
    """Pin existing content by CID."""
    cid_path = _make_cid_path(cid)
    if not cid_path.exists():
        result = {"success": False, "error": f"CID not found: {cid}"}
        click.echo(json.dumps(result))
        raise click.Abort()

    items = _load_index()
    found = False
    for item in items:
        if item.get("cid") == cid:
            item["pinned"] = True
            found = True
    if not found:
        items.append(
            {
                "cid": cid,
                "name": cid,
                "size": cid_path.stat().st_size,
                "pinned": True,
                "uploaded_at": datetime.now(UTC).isoformat(),
            }
        )
    _save_index(items)

    result = {"success": True, "data": {"pinned": True, "cid": cid}}
    click.echo(json.dumps(result))


@ipfs.command(name="list")
@click.pass_context
def list_items(ctx):
    """List locally stored IPFS content."""
    items = _load_index()
    result = {"success": True, "data": {"items": items}}
    click.echo(json.dumps(result))
