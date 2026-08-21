"""IPFS commands for AITBC CLI backed by a local Kubo daemon.

When a Kubo daemon is not reachable on `127.0.0.1:5001`, the CLI falls back to
a minimal filesystem shim so the surface still works on a node without a running
daemon. Cross-node retrieval requires the real daemon and the IPFS network.
"""

from __future__ import annotations

import hashlib
import os
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import click
import requests

IPFS_DIR = Path("/var/lib/aitbc/ipfs")
IPFS_DIR.mkdir(parents=True, exist_ok=True)
IPFS_API = os.environ.get("IPFS_API_URL", "http://127.0.0.1:5001")
TIMEOUT = 120


def _cid_for(data: bytes) -> str:
    """Deterministic fallback CID for the filesystem shim."""
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


def _daemon_available() -> bool:
    try:
        requests.post(f"{IPFS_API}/api/v0/id", timeout=2)
        return True
    except requests.RequestException:
        return False


def _api_post(path: str, **kwargs: Any) -> requests.Response:
    return requests.post(f"{IPFS_API}{path}", timeout=kwargs.pop("timeout", TIMEOUT), **kwargs)


@click.group()
@click.pass_context
def ipfs(ctx):
    """Content-addressed storage via IPFS (Kubo daemon with filesystem fallback)."""
    ctx.ensure_object(dict)


@ipfs.command()
@click.option("--file", required=True, type=click.Path(exists=True, readable=True), help="File to upload")
@click.option("--pin", is_flag=True, default=True, help="Pin uploaded content")
@click.option("--name", default=None, help="Human-readable name for the upload")
@click.pass_context
def upload(ctx, file: str, pin: bool, name: str | None):
    """Upload a file to IPFS and return its CID."""
    file_path = Path(file)
    data = file_path.read_bytes()

    if _daemon_available():
        try:
            response = _api_post(
                "/api/v0/add",
                params={"pin": "true" if pin else "false", "wrap-with-directory": "false"},
                files={"file": (file_path.name, data)},
                timeout=120,
            )
            response.raise_for_status()
            result = response.json()
            cid = result.get("Hash") or result.get("cid")
            size = int(result.get("Size", len(data)))
            click.echo(
                json.dumps(
                    {
                        "success": True,
                        "data": {
                            "cid": cid,
                            "size": size,
                            "name": name or file_path.name,
                            "pinned": pin,
                        },
                    }
                )
            )
            return
        except requests.RequestException as e:
            click.echo(json.dumps({"success": False, "warning": f"Kubo upload failed: {e}; falling back to filesystem"}), err=True)

    # Filesystem fallback
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

    click.echo(json.dumps({"success": True, "data": {"cid": cid, "size": len(data), "name": name or file_path.name}}))


@ipfs.command()
@click.argument("cid")
@click.option("--output", type=click.Path(), help="Write retrieved content to this path")
@click.option("--wait", is_flag=True, default=False, help="Wait for the CID to become available on the network")
@click.pass_context
def download(ctx, cid: str, output: str | None, wait: bool):
    """Download content by CID from the local Kubo daemon or filesystem fallback."""
    if _daemon_available():
        try:
            for attempt in range(1, 60 if wait else 1):
                response = _api_post("/api/v0/cat", params={"arg": cid}, timeout=30)
                if response.status_code == 200:
                    break
                if not wait:
                    response.raise_for_status()
                    break
                import time
                time.sleep(2)
            else:
                response = _api_post("/api/v0/cat", params={"arg": cid}, timeout=30)
            response.raise_for_status()
            data = response.content
        except requests.RequestException:
            data = None
    else:
        data = None

    if data is None:
        cid_path = _make_cid_path(cid)
        if not cid_path.exists():
            click.echo(json.dumps({"success": False, "error": f"CID not found: {cid}"}))
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

    click.echo(json.dumps({"success": True, "data": {"cid": cid, "file_path": file_path, "size": len(data)}}))


@ipfs.command()
@click.argument("cid")
@click.pass_context
def pin(ctx, cid: str):
    """Pin content by CID on the local Kubo daemon or the filesystem index."""
    if _daemon_available():
        try:
            response = _api_post("/api/v0/pin/add", params={"arg": cid})
            response.raise_for_status()
            click.echo(json.dumps({"success": True, "data": {"pinned": True, "cid": cid}}))
            return
        except requests.RequestException as e:
            click.echo(json.dumps({"success": False, "warning": f"Kubo pin failed: {e}; using filesystem index"}), err=True)

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

    click.echo(json.dumps({"success": True, "data": {"pinned": True, "cid": cid}}))


@ipfs.command(name="list")
@click.pass_context
def list_items(ctx):
    """List pinned IPFS content from the local Kubo daemon or filesystem index."""
    if _daemon_available():
        try:
            response = _api_post("/api/v0/pin/ls", params={"stream": "true"}, stream=True)
            response.raise_for_status()
            items = []
            for line in response.iter_lines():
                if line:
                    try:
                        obj = json.loads(line.decode())
                        items.append({
                            "cid": obj.get("Cid") or obj.get("cid"),
                            "type": obj.get("Type") or obj.get("type"),
                        })
                    except json.JSONDecodeError:
                        continue
            click.echo(json.dumps({"success": True, "data": {"items": items}}))
            return
        except requests.RequestException as e:
            click.echo(json.dumps({"success": False, "warning": f"Kubo pin list failed: {e}; using filesystem index"}), err=True)

    items = _load_index()
    click.echo(json.dumps({"success": True, "data": {"items": items}}))
