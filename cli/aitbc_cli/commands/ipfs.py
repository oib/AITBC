"""IPFS storage commands for AITBC CLI.

Uses a local Kubo daemon when IPFS_API_URL is set or the HTTP API is
reachable on 127.0.0.1:5001, otherwise falls back to a filesystem stub.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import click
import requests

IPFS_DIR = Path("/var/lib/aitbc/ipfs")
IPFS_DIR.mkdir(parents=True, exist_ok=True)


def _ipfs_api_url() -> str:
    return os.environ.get("IPFS_API_URL") or "http://127.0.0.1:5001"


def _daemon_available() -> bool:
    try:
        r = requests.post(f"{_ipfs_api_url()}/api/v0/version", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


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


def _add_to_index(cid: str, name: str, size: int, pinned: bool = True) -> None:
    items = _load_index()
    items = [i for i in items if i.get("cid") != cid]
    items.append(
        {
            "cid": cid,
            "name": name,
            "size": size,
            "pinned": pinned,
            "uploaded_at": datetime.now(UTC).isoformat(),
        }
    )
    _save_index(items)


def _upload_to_daemon(file_path: Path, pin: bool, name: str | None) -> dict[str, Any]:
    api = _ipfs_api_url()
    params = {"pin": "true" if pin else "false"}
    with open(file_path, "rb") as f:
        r = requests.post(f"{api}/api/v0/add", params=params, files={"file": f}, timeout=120)
    r.raise_for_status()
    result = r.json()
    cid = result.get("Hash")
    size = int(result.get("Size", 0))
    _add_to_index(cid, name or file_path.name, size, pinned=pin)
    return {"cid": cid, "size": size, "name": name or file_path.name}


def _download_from_daemon(cid: str, output: str | None) -> dict[str, Any]:
    api = _ipfs_api_url()
    r = requests.post(f"{api}/api/v0/cat?arg={cid}", timeout=60)
    r.raise_for_status()
    data = r.content
    if output:
        out_path = Path(output)
        out_path.write_bytes(data)
        file_path = str(out_path)
    else:
        with tempfile.NamedTemporaryFile(delete=False, mode="wb") as tmp:
            tmp.write(data)
            file_path = tmp.name
    return {"cid": cid, "file_path": file_path, "size": len(data)}


def _pin_to_daemon(cid: str) -> None:
    api = _ipfs_api_url()
    requests.post(f"{api}/api/v0/pin/add?arg={cid}&recursive=true", timeout=30).raise_for_status()


def _list_daemon_pins() -> list[dict[str, Any]]:
    api = _ipfs_api_url()
    r = requests.post(f"{api}/api/v0/pin/ls?type=recursive", timeout=30)
    r.raise_for_status()
    data = r.json()
    pins = data.get("Keys") or {}
    return [{"cid": cid, "pinned": True, "name": cid, "size": 0} for cid in pins]


@click.group()
@click.pass_context
def ipfs(ctx):
    """Content-addressed storage (IPFS-compatible surface)."""
    ctx.ensure_object(dict)


@ipfs.command()
@click.option("--file", required=True, type=click.Path(exists=True, readable=True), help="File to upload")
@click.option("--pin", is_flag=True, default=True, help="Pin uploaded content")
@click.option("--name", default=None, help="Human-readable name for the upload")
@click.pass_context
def upload(ctx, file: str, pin: bool, name: str | None):
    """Upload a file and return its CID."""
    file_path = Path(file)
    if _daemon_available():
        try:
            result = _upload_to_daemon(file_path, pin, name)
            click.echo(json.dumps({"success": True, "data": result}))
            return
        except Exception as e:
            click.echo(json.dumps({"success": False, "error": f"daemon upload failed: {e}"}))
            raise click.Abort()

    data = file_path.read_bytes()
    cid = _cid_for(data)
    cid_path = _make_cid_path(cid)
    cid_path.write_bytes(data)
    _add_to_index(cid, name or file_path.name, len(data), pinned=pin)
    result = {"success": True, "data": {"cid": cid, "size": len(data), "name": name or file_path.name}}
    click.echo(json.dumps(result))


@ipfs.command()
@click.argument("cid")
@click.option("--output", type=click.Path(), help="Write retrieved content to this path")
@click.pass_context
def download(ctx, cid: str, output: str | None):
    """Download content by CID."""
    if _daemon_available():
        try:
            result = _download_from_daemon(cid, output)
            click.echo(json.dumps({"success": True, "data": result}))
            return
        except Exception as e:
            click.echo(json.dumps({"success": False, "error": f"daemon download failed: {e}"}))
            raise click.Abort()

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
    if _daemon_available():
        try:
            _pin_to_daemon(cid)
            click.echo(json.dumps({"success": True, "data": {"pinned": True, "cid": cid}}))
        except Exception as e:
            click.echo(json.dumps({"success": False, "error": f"daemon pin failed: {e}"}))
            raise click.Abort()
        return

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
    """List pinned IPFS content."""
    if _daemon_available():
        daemon_items = _list_daemon_pins()
    else:
        daemon_items = []
    local_items = _load_index()
    by_cid = {i["cid"]: i for i in local_items}
    for i in daemon_items:
        by_cid.setdefault(i["cid"], i).update({"pinned": True})
    result = {"success": True, "data": {"items": list(by_cid.values())}}
    click.echo(json.dumps(result))
