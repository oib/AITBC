"""IPFS commands for AITBC CLI backed by a local Kubo daemon.

When a Kubo daemon is not reachable on `127.0.0.1:5001`, the CLI falls back to
a minimal filesystem shim so the surface still works on a node without a running
daemon. Cross-node retrieval requires the real daemon and the IPFS network.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import click
import requests

from ..config import get_config
from ..utils import OUTPUT_FORMAT_OPTION, error, output, success, warning
from ..utils.address import to_canonical
from ..utils.http_client import get_logger
from ..utils.output import resolve_output_format
from ..utils.wallet_loader import load_wallet_for_payment

IPFS_DIR = Path(os.environ.get("AITBC_IPFS_DIR", "/var/lib/aitbc/ipfs"))
IPFS_API = os.environ.get("IPFS_API_URL", "http://127.0.0.1:5001")
TIMEOUT = 120

logger = get_logger(__name__)


def _ensure_ipfs_dir() -> None:
    """Create the IPFS directory on demand; imports must not fail on fresh runners."""
    IPFS_DIR.mkdir(parents=True, exist_ok=True)


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
    _ensure_ipfs_dir()
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
    timeout = kwargs.pop("timeout", TIMEOUT)
    return requests.post(f"{IPFS_API}{path}", timeout=timeout, **kwargs)


# ---------------------------------------------------------------------------
# IPFS rental storage
# ---------------------------------------------------------------------------


def _rentals_path() -> Path:
    path = Path.home() / ".aitbc" / "ipfs_rentals.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_rentals() -> list[dict[str, Any]]:
    path = _rentals_path()
    if not path.exists():
        return []
    try:
        return cast(list, json.loads(path.read_text()))
    except (json.JSONDecodeError, OSError):
        return []


def _save_rentals(rentals: list[dict[str, Any]]) -> None:
    _rentals_path().write_text(json.dumps(rentals, indent=2))


def _save_rental(rental: dict[str, Any]) -> None:
    rentals = _load_rentals()
    rentals.append(rental)
    _save_rentals(rentals)


def _ipfs_add_file(ipfs_api: str, file_path: Path) -> str | None:
    """Add a file to an IPFS API and return the CID."""
    try:
        with open(file_path, "rb") as f:
            response = requests.post(
                f"{ipfs_api.rstrip('/')}/api/v0/add",
                files={"file": (file_path.name, f)},
                timeout=TIMEOUT,
            )
        response.raise_for_status()
        result = response.json()
        return result.get("Hash") or result.get("cid")
    except Exception as e:
        warning(f"IPFS add failed: {e}")
        return None


def _ipfs_pin_cid(ipfs_api: str, cid: str) -> bool:
    """Pin a CID on an IPFS API."""
    try:
        response = requests.post(
            f"{ipfs_api.rstrip('/')}/api/v0/pin/add",
            params={"arg": cid},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        return True
    except Exception as e:
        warning(f"IPFS pin failed: {e}")
        return False


def _ipfs_unpin_cid(ipfs_api: str, cid: str) -> bool:
    """Unpin a CID on an IPFS API."""
    try:
        response = requests.post(
            f"{ipfs_api.rstrip('/')}/api/v0/pin/rm",
            params={"arg": cid},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        return True
    except Exception as e:
        warning(f"IPFS unpin failed: {e}")
        return False


def _ipfs_swarm_connect(ipfs_api: str, multiaddr: str) -> bool:
    """Attempt to connect the local IPFS daemon to a provider multiaddr."""
    try:
        response = requests.post(
            f"{ipfs_api.rstrip('/')}/api/v0/swarm/connect",
            params={"arg": multiaddr},
            timeout=30,
        )
        response.raise_for_status()
        return True
    except Exception as e:
        warning(f"Could not swarm connect to {multiaddr}: {e}")
        return False


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
    _ensure_ipfs_dir()

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
            click.echo(
                json.dumps({"success": False, "warning": f"Kubo upload failed: {e}; falling back to filesystem"}), err=True
            )

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
            for _attempt in range(1, 60 if wait else 1):
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

    _ensure_ipfs_dir()
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
                        items.append(
                            {
                                "cid": obj.get("Cid") or obj.get("cid"),
                                "type": obj.get("Type") or obj.get("type"),
                            }
                        )
                    except json.JSONDecodeError:
                        continue
            click.echo(json.dumps({"success": True, "data": {"items": items}}))
            return
        except requests.RequestException as e:
            click.echo(
                json.dumps({"success": False, "warning": f"Kubo pin list failed: {e}; using filesystem index"}), err=True
            )

    items = _load_index()
    click.echo(json.dumps({"success": True, "data": {"items": items}}))


# ---------------------------------------------------------------------------
# Paid IPFS hosting rental commands
# ---------------------------------------------------------------------------


@ipfs.command(name="host")
@click.argument("offer_id_or_plugin_id")
@click.argument("cid_or_file")
@click.option("--days", type=int, default=1, help="Rental duration in days")
@click.option("--wallet", "wallet_name", help="Wallet to pay for the rental")
@click.option("--wallet-path", "wallet_path", help="Direct wallet file path")
@click.option("--password", help="Wallet password")
@click.option("--pin/--no-pin", default=True, help="Pin the CID after paying the rental")
@OUTPUT_FORMAT_OPTION
@click.pass_context
def host(
    ctx: click.Context,
    offer_id_or_plugin_id: str,
    cid_or_file: str,
    days: int,
    wallet_name: str | None,
    wallet_path: str | None,
    password: str | None,
    pin: bool,
    output_format: str,
):
    """Rent IPFS hosting for a CID or file through a marketplace IPFS offer."""
    from .market.escrow import _escrow_create
    from .market.jobs import _resolve_offer

    output_format = resolve_output_format(ctx, output_format)

    if days <= 0:
        error("--days must be a positive integer")
        raise click.Abort()

    offer = _resolve_offer(ctx, offer_id_or_plugin_id)
    if offer.get("service_type") != "ipfs":
        error(f"Offer '{offer_id_or_plugin_id}' is not an IPFS hosting offer (service_type={offer.get('service_type')})")
        raise click.Abort()
    if offer.get("price_unit") != "per_day":
        error(f"IPFS offer '{offer_id_or_plugin_id}' uses price_unit '{offer.get('price_unit')}'; expected 'per_day'")
        raise click.Abort()

    price = Decimal(str(offer.get("price", "0")))
    total_cost = price * Decimal(days)
    provider = to_canonical(offer.get("provider_address", ""))
    if not provider:
        error("Offer has no provider_address")
        raise click.Abort()

    # IPFS API: env wins, then the offer endpoint, then the island default.
    ipfs_api = os.environ.get("IPFS_API_URL") or offer.get("endpoint") or "http://127.0.0.1:5002"
    if not ipfs_api.startswith(("http://", "https://")):
        # The offer may advertise a p2p multiaddr as public_endpoint; the
        # actual pin/add call still goes to a local Kubo HTTP API.
        ipfs_api = "http://127.0.0.1:5002"

    public_endpoint = offer.get("public_endpoint") or ""

    # Load wallet and lock escrow.
    buyer, private_key, wallet_id = load_wallet_for_payment(
        ctx, wallet_name=wallet_name, wallet_path=wallet_path, password=password, require_private_key=True
    )

    # If a local file is supplied, add it to the IPFS daemon first.
    file_path = Path(cid_or_file)
    if file_path.exists() and file_path.is_file():
        cid = _ipfs_add_file(ipfs_api, file_path)
        if not cid:
            error(f"Failed to add file to IPFS at {ipfs_api}")
            raise click.Abort()
        success(f"Added file to IPFS: {cid}")
    else:
        cid = cid_or_file.strip()
        if not cid:
            error("CID cannot be empty")
            raise click.Abort()

    # Attempt to connect to the provider's public multiaddr so the island can replicate.
    if public_endpoint and not public_endpoint.startswith(("http://", "https://")):
        _ipfs_swarm_connect(ipfs_api, public_endpoint)

    job_id = f"ipfs_rental_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"

    contract_id = _escrow_create(ctx, job_id, buyer, provider, total_cost, get_config(), private_key)
    if not contract_id:
        error("Escrow creation failed; aborting rental")
        raise click.Abort()

    pinned = False
    if pin:
        pinned = _ipfs_pin_cid(ipfs_api, cid)
        if not pinned:
            error(
                f"Failed to pin CID {cid} on {ipfs_api}. Escrow contract {contract_id} was created; release or refund it manually if needed."
            )
            raise click.Abort()

    rental: dict[str, Any] = {
        "rental_id": job_id,
        "offer_id": offer.get("offer_id", offer_id_or_plugin_id),
        "plugin_id": offer.get("plugin_id", ""),
        "cid": cid,
        "duration_days": days,
        "total_cost_ait": str(round(total_cost, 6)),
        "escrow_contract_id": contract_id,
        "provider_address": provider,
        "buyer_address": buyer,
        "ipfs_api": ipfs_api,
        "public_endpoint": public_endpoint,
        "wallet_id": wallet_id,
        "created_at": datetime.now(UTC).isoformat(),
        "expires_at": (datetime.now(UTC) + timedelta(days=days)).isoformat(),
        "pinned": pinned,
        "status": "active",
    }
    _save_rental(rental)

    success(f"Hosted {cid} for {days} day(s); cost {total_cost:.4f} AIT; escrow contract {contract_id}")
    output(rental, output_format, title="IPFS Rental")


@ipfs.command(name="rentals")
@OUTPUT_FORMAT_OPTION
@click.pass_context
def rentals(ctx: click.Context, output_format: str):
    """List active IPFS rentals."""
    output_format = resolve_output_format(ctx, output_format)
    items = _load_rentals()
    output(items, output_format, title="IPFS Rentals")


@ipfs.command(name="unpin")
@click.argument("rental_id")
@click.option("--refund", is_flag=True, help="Refund the escrow for this rental")
@click.option("--reason", default="buyer_requested", help="Reason for refund")
@OUTPUT_FORMAT_OPTION
@click.pass_context
def unpin(ctx: click.Context, rental_id: str, refund: bool, reason: str, output_format: str):
    """Unpin a CID and end an IPFS rental."""
    from .market.escrow import refund_escrow

    output_format = resolve_output_format(ctx, output_format)
    rentals = _load_rentals()
    rental = next((r for r in rentals if r.get("rental_id") == rental_id), None)
    if not rental:
        error(f"Rental '{rental_id}' not found")
        raise click.Abort()

    cid = rental.get("cid", "")
    ipfs_api = rental.get("ipfs_api", "http://127.0.0.1:5002")
    unpinned = _ipfs_unpin_cid(ipfs_api, cid)
    if unpinned:
        success(f"Unpinned {cid}")
    else:
        warning(f"Could not unpin {cid} on {ipfs_api}")

    remaining = [r for r in rentals if r.get("rental_id") != rental_id]
    _save_rentals(remaining)

    if refund:
        refund_escrow(ctx, rental_id, reason)

    output({"rental_id": rental_id, "cid": cid, "unpinned": unpinned}, output_format)


if __name__ == "__main__":
    ipfs()
