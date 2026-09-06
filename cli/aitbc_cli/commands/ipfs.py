"""IPFS commands for AITBC CLI backed by a local Kubo daemon.

When a Kubo daemon is not reachable on `127.0.0.1:5001`, the CLI falls back to
a minimal filesystem shim so the surface still works on a node without a running
daemon. Cross-node retrieval requires the real daemon and the IPFS network.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sys
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import click
import requests
from eth_keys.datatypes import PrivateKey
from eth_utils import keccak

from aitbc.crypto.crypto import sign_transaction_hash

from ..config import _resolve_api_key, get_config
from ..utils import DECIMAL, OUTPUT_FORMAT_OPTION, error, info, output, success, warning
from ..utils.address import to_canonical
from ..utils.chain_id import get_chain_id
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger
from ..utils.output import resolve_output_format
from ..utils.wallet import decrypt_private_key
from ..utils.wallet_loader import load_wallet_for_payment
from ..utils.wallet_paths import wallet_dir
from .transactions import _send_transaction_impl

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


def _daemon_available(ipfs_api: str = IPFS_API) -> bool:
    try:
        requests.post(f"{ipfs_api}/api/v0/id", timeout=2)
        return True
    except requests.RequestException:
        return False


def _api_post(path: str, **kwargs: Any) -> requests.Response:
    ipfs_api = kwargs.pop("ipfs_api", IPFS_API)
    timeout = kwargs.pop("timeout", TIMEOUT)
    return requests.post(f"{ipfs_api}{path}", timeout=timeout, **kwargs)


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
        return cast(str | None, result.get("Hash") or result.get("cid"))
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


def _ipfs_object_size(ipfs_api: str, cid: str) -> int | None:
    """Return the dag cumulative size in bytes for a CID, or None if unreachable."""
    try:
        response = requests.post(
            f"{ipfs_api.rstrip('/')}/api/v0/object/stat",
            params={"arg": cid},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        cumulative = data.get("CumulativeSize")
        if cumulative is not None:
            return int(cumulative)
    except Exception:
        pass
    return None


def _active_customer_ipfs_usage(buyer_address: str, offer_id: str) -> int:
    """Sum the stored size of active rentals for the same buyer/offer."""
    total = 0
    for rental in _load_rentals():
        if (
            rental.get("buyer_address") == buyer_address
            and rental.get("offer_id") == offer_id
            and rental.get("status") == "active"
        ):
            size = rental.get("size")
            if size:
                total += int(size)
    return total


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


def _hub_marketplace_client(timeout: int = 15) -> AITBCHTTPClient:
    """Return an HTTP client for the hub marketplace service."""
    config = get_config()
    if config.marketplace_service_url and not config.marketplace_service_url.startswith("http://127.0.0.1"):
        return AITBCHTTPClient(base_url=config.marketplace_service_url, timeout=timeout)
    hub_host = config.hub_discovery_url or "hub.aitbc.bubuit.net"
    if hub_host.startswith(("http://", "https://")):
        hub_url = hub_host.rstrip("/")
    elif "localhost" in hub_host or "127.0.0.1" in hub_host:
        hub_url = f"http://{hub_host}"
    else:
        # Public hubs are exposed over HTTPS unless the env explicitly says http://
        hub_url = f"https://{hub_host}"
    return AITBCHTTPClient(base_url=hub_url, timeout=timeout)


def _lookup_ipfs_rental(access_key: str, access_secret: str) -> dict[str, Any] | None:
    """Validate an access token against the hub marketplace service."""
    try:
        client = _hub_marketplace_client()
        result = client.get(f"/v1/marketplace/ipfs/rental/{access_key}", params={"access_secret": access_secret})
        if result and not result.get("error"):
            return result
    except NetworkError as e:
        logger.warning("Could not validate IPFS rental token on hub: %s", e)
    return None


@click.group(
    epilog="""Examples:

  aitbc ipfs upload --file /tmp/data.txt

  aitbc ipfs download --cid Qm..."""
)
@click.pass_context
def ipfs(ctx):
    """Upload, download, pin, and rent IPFS content via the Kubo daemon or filesystem fallback."""
    ctx.ensure_object(dict)


@ipfs.command(
    epilog="""Examples:

  aitbc ipfs upload --file /tmp/data.txt

  aitbc ipfs upload --file /tmp/data.txt --name 'my file' --pin"""
)
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


@ipfs.command(
    epilog="""Examples:

  aitbc ipfs download --cid Qm...

  aitbc ipfs download --cid Qm... --output /tmp/data.txt --wait"""
)
@click.option("--cid", "cid", required=False, help="The Cid.")
@click.option("--output", type=click.Path(), help="Write retrieved content to this path")
@click.option("--wait", is_flag=True, default=False, help="Wait for the CID to become available on the network")
@click.option("--access-key", help="Rental access key (looks up CID from hub)")
@click.option("--access-secret", help="Rental access secret")
@click.option("--rental-id", help="Local rental ID (looks up CID and validates access)")
@click.pass_context
def download(
    ctx,
    cid: str | None,
    output: str | None,
    wait: bool,
    access_key: str | None,
    access_secret: str | None,
    rental_id: str | None,
):
    """Download content by CID, access key, or rental ID and optionally write it to a file."""
    rental: dict[str, Any] | None = None
    token: dict[str, Any] | None = None

    if rental_id:
        rental = next((r for r in _load_rentals() if r.get("rental_id") == rental_id), None)
        if not rental:
            error(f"Rental '{rental_id}' not found")
            raise click.Abort()
        if rental.get("status") != "active":
            error(f"Rental '{rental_id}' is not active")
            raise click.Abort()
        expires = rental.get("expires_at")
        if expires and datetime.fromisoformat(expires) < datetime.now(UTC):
            error(f"Rental '{rental_id}' has expired")
            raise click.Abort()
        cid = rental.get("cid")
        if not cid:
            error(f"Rental '{rental_id}' has no CID")
            raise click.Abort()

    if access_key and access_secret:
        token = _lookup_ipfs_rental(access_key, access_secret)
        if not token:
            error("Invalid, expired, or unknown IPFS rental token")
            raise click.Abort()
        cid = token.get("cid")
        if not cid:
            error("Token has no CID")
            raise click.Abort()

    if not cid:
        error("Provide a CID, --rental-id, or --access-key/--access-secret")
        raise click.Abort()

    # Prefer the daemon that was used for the rental.
    ipfs_api = IPFS_API
    if rental_id or access_key:
        ipfs_api = (rental or token or {}).get("ipfs_api") or os.environ.get("IPFS_API_URL") or "http://127.0.0.1:5001"

    if _daemon_available(ipfs_api):
        try:
            for _attempt in range(1, 60 if wait else 1):
                response = _api_post("/api/v0/cat", params={"arg": cid}, timeout=30, ipfs_api=ipfs_api)
                if response.status_code == 200:
                    break
                if not wait:
                    response.raise_for_status()
                    break
                import time

                time.sleep(2)
            else:
                response = _api_post("/api/v0/cat", params={"arg": cid}, timeout=30, ipfs_api=ipfs_api)
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


@ipfs.command(
    epilog="""Examples:

  aitbc ipfs pin --cid Qm...

  aitbc ipfs pin --cid Qm... --output json"""
)
@click.option("--cid", "cid", required=True, help="The Cid.")
@click.pass_context
def pin(ctx, cid: str):
    """Pin content by CID on the local Kubo daemon or filesystem index."""
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


@ipfs.command(
    name="list",
    epilog="""Examples:

  aitbc ipfs list

  aitbc ipfs list --output json""",
)
@click.pass_context
def list_items(ctx):
    """List uploaded and pinned IPFS items."""
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


@ipfs.command(
    name="host",
    epilog="""Examples:

  aitbc ipfs host --offer-id-or-plugin-id offer-1 --cid-or-file Qm... --days 7

  aitbc ipfs host --offer-id-or-plugin-id offer-1 --cid-or-file /tmp/data.txt --wallet wallet-1""",
)
@click.option("--offer-id-or-plugin-id", "offer_id_or_plugin_id", required=True, help="The Offer id or plugin id.")
@click.option("--cid-or-file", "cid_or_file", required=True, help="The Cid or file.")
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
    """Host IPFS content for a marketplace offer or plugin for a number of days."""
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

    # Determine the object size as early as possible so we can enforce the
    # per-customer disk quota before asking for the wallet password or
    # uploading the file to the IPFS daemon.
    file_path = Path(cid_or_file)
    content_size: int | None = None
    if file_path.exists() and file_path.is_file():
        content_size = file_path.stat().st_size
    else:
        cid = cid_or_file.strip()
        if not cid:
            error("CID cannot be empty")
            raise click.Abort()
        content_size = _ipfs_object_size(ipfs_api, cid)

    disk_quota_mb = offer.get("disk_quota_mb")
    if disk_quota_mb:
        quota_bytes = int(disk_quota_mb) * 1024 * 1024
        item_size = content_size if content_size is not None else 0
        if item_size > quota_bytes:
            if content_size is None:
                error(f"Could not determine size of {cid}; offer disk quota is {disk_quota_mb} MB per customer")
            else:
                error(
                    f"Object size {item_size / (1024 * 1024):.2f} MB exceeds "
                    f"the {disk_quota_mb} MB per-customer quota for this offer"
                )
            raise click.Abort()

    # Load wallet and lock escrow.
    buyer, private_key, wallet_id = load_wallet_for_payment(
        ctx, wallet_name=wallet_name, wallet_path=wallet_path, password=password, require_private_key=True
    )

    used_bytes = _active_customer_ipfs_usage(buyer, offer.get("offer_id", offer_id_or_plugin_id))
    if disk_quota_mb and used_bytes + item_size > quota_bytes:
        error(
            f"This upload would use {item_size / (1024 * 1024):.2f} MB and exceed "
            f"the {disk_quota_mb} MB per-customer quota for this offer (already using {used_bytes / (1024 * 1024):.2f} MB)"
        )
        raise click.Abort()

    # If a local file is supplied, add it to the IPFS daemon now.
    if file_path.exists() and file_path.is_file():
        cid = cast(str, _ipfs_add_file(ipfs_api, file_path))
        if not cid:
            error(f"Failed to add file to IPFS at {ipfs_api}")
            raise click.Abort()
        # Use the daemon's reported cumulative size when available.
        daemon_size = _ipfs_object_size(ipfs_api, cid)
        if daemon_size is not None:
            content_size = daemon_size
        success(f"Added file to IPFS: {cid}")

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

    # Re-check the daemon-reported size after pin for the rental record.
    if content_size is None:
        content_size = _ipfs_object_size(ipfs_api, cid)

    # Issue per-rental access credentials. These are the customer's login
    # credentials for retrieving this CID from the hub.
    access_key = secrets.token_urlsafe(16)
    access_secret = secrets.token_urlsafe(32)

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
        "size": content_size,
        "disk_quota_mb": disk_quota_mb,
        "access_key": access_key,
        "access_secret": access_secret,
    }

    # Register the token with the hub marketplace service so the customer can
    # retrieve the CID from another node with just access_key + access_secret.
    try:
        client = _hub_marketplace_client()
        client.post(
            "/v1/marketplace/ipfs/rental-token",
            json={
                "access_key": access_key,
                "access_secret": access_secret,
                "rental_id": job_id,
                "offer_id": offer.get("offer_id", offer_id_or_plugin_id),
                "cid": cid,
                "buyer_address": buyer,
                "provider_address": provider,
                "escrow_contract_id": contract_id,
                "ipfs_api": ipfs_api,
                "public_endpoint": public_endpoint,
                "disk_quota_mb": disk_quota_mb,
                "size": content_size,
                "status": "active",
                "expires_at": rental["expires_at"],
            },
        )
        info("Registered IPFS rental token with hub")
    except NetworkError as e:
        warning(f"Could not register IPFS rental token with hub: {e}")

    _save_rental(rental)

    success(f"Hosted {cid} for {days} day(s); cost {total_cost:.4f} AIT; escrow contract {contract_id}")
    output(rental, output_format, title="IPFS Rental")


@ipfs.command(
    name="token",
    epilog="""Examples:

  aitbc ipfs token --rental-id rental-123

  aitbc ipfs token --rental-id rental-123 --output json""",
)
@click.option("--rental-id", "rental_id", required=True, help="The Rental id.")
@OUTPUT_FORMAT_OPTION
@click.pass_context
def token(ctx: click.Context, rental_id: str, output_format: str):
    """Get an access token for an IPFS rental."""
    output_format = resolve_output_format(ctx, output_format)
    rental = next((r for r in _load_rentals() if r.get("rental_id") == rental_id), None)
    if not rental:
        error(f"Rental '{rental_id}' not found")
        raise click.Abort()
    if not rental.get("access_key"):
        error(f"Rental '{rental_id}' has no access credentials")
        raise click.Abort()
    output(
        {
            "rental_id": rental.get("rental_id"),
            "access_key": rental.get("access_key"),
            "access_secret": rental.get("access_secret"),
            "cid": rental.get("cid"),
            "expires_at": rental.get("expires_at"),
        },
        output_format,
        title="IPFS Rental Credentials",
    )


@ipfs.command(
    name="rentals",
    epilog="""Examples:

  aitbc ipfs rentals

  aitbc ipfs rentals --output json""",
)
@OUTPUT_FORMAT_OPTION
@click.pass_context
def rentals(ctx: click.Context, output_format: str):
    """List all active IPFS rentals and their details."""
    output_format = resolve_output_format(ctx, output_format)
    items = _load_rentals()
    output(items, output_format, title="IPFS Rentals")


@ipfs.command(
    name="unpin",
    epilog="""Examples:

  aitbc ipfs unpin --rental-id rental-123

  aitbc ipfs unpin --rental-id rental-123 --refund --reason 'buyer_requested'""",
)
@click.option("--rental-id", "rental_id", required=True, help="The Rental id.")
@click.option("--refund", is_flag=True, help="Refund the escrow for this rental")
@click.option("--reason", default="buyer_requested", help="Reason for refund")
@OUTPUT_FORMAT_OPTION
@click.pass_context
def unpin(ctx: click.Context, rental_id: str, refund: bool, reason: str, output_format: str):
    """Unpin a CID and end an IPFS rental with an optional refund."""
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
# ---------------------------------------------------------------------------
# Island IPFS subscription and swarm-key commands
# ---------------------------------------------------------------------------


def _resolve_wallet_password(password: str | None, password_file: str | None, wallet_name: str) -> str:
    """Resolve a wallet password from flags, env, unencrypted wallet, or TTY prompt."""
    if password is not None:
        return password
    if password_file:
        with open(password_file) as f:
            return f.read().strip()
    if "AITBC_WALLET_PASSWORD" in os.environ:
        return os.environ["AITBC_WALLET_PASSWORD"]

    keystore_dir = wallet_dir()
    keystore = keystore_dir / f"{wallet_name}.json"
    if keystore.exists():
        data = json.loads(keystore.read_text())
        if not data.get("encrypted") and not data.get("encrypted_private_key"):
            return ""

    if not sys.stdin.isatty():
        abort(None, "No TTY available for password prompt. Use --password, --password-file, or set AITBC_WALLET_PASSWORD.")
        return ""  # unreachable; abort always raises

    import getpass

    try:
        return getpass.getpass("Enter wallet password: ")
    except Exception as e:
        abort(None, f"Password prompt failed: {e}", from_exception=e)
        return ""  # unreachable; abort always raises


def _load_wallet_key(wallet_name: str, password: str) -> tuple[str, PrivateKey]:
    """Load a file wallet and return (address, private_key)."""
    keystore = wallet_dir() / f"{wallet_name}.json"
    if not keystore.exists():
        raise click.BadParameter(f"Wallet '{wallet_name}' not found at {keystore}")

    data = json.loads(keystore.read_text())
    address = data.get("address")
    if not address:
        raise click.BadParameter(f"Wallet '{wallet_name}' has no address")

    if data.get("encrypted") or data.get("encrypted_private_key"):
        if not password:
            raise click.BadParameter(f"Wallet '{wallet_name}' is encrypted; provide --password")
        private_key_hex = decrypt_private_key(keystore, password)
    else:
        private_key_hex = data.get("private_key", "")

    if not private_key_hex:
        raise click.BadParameter(f"Wallet '{wallet_name}' has no private key")
    if isinstance(private_key_hex, str) and private_key_hex.startswith("0x"):
        private_key_hex = private_key_hex[2:]

    try:
        private_key = PrivateKey(bytes.fromhex(private_key_hex))
    except ValueError as e:
        raise click.BadParameter(f"Invalid private key in wallet '{wallet_name}': {e}") from e

    return address, private_key


def _default_rpc_url(rpc_url: str | None) -> str:
    if rpc_url:
        return rpc_url
    config = get_config()
    return getattr(config, "blockchain_rpc_url", "http://127.0.0.1:8202") or "http://127.0.0.1:8202"


def _default_coordinator_url(coordinator_url: str | None) -> str:
    if coordinator_url:
        return coordinator_url
    config = get_config()
    return getattr(config, "coordinator_api_url", "http://127.0.0.1:8203") or "http://127.0.0.1:8203"


@click.group(name="island")
@click.pass_context
def island(ctx):
    """Private island IPFS subscription and swarm-key management."""
    ctx.ensure_object(dict)


@island.command()
@click.option("--wallet", "wallet_name", required=True, help="Wallet name to pay from")
@click.option("--to", "to_address", required=True, help="Island treasury / recipient address")
@click.option("--island-id", required=True, help="Island identifier (e.g. ait-hub.aitbc.bubuit.net-island)")
@click.option("--duration", type=int, default=1000, help="Subscription duration in blocks (default 1000)")
@click.option("--quota", type=int, default=1073741824, help="Quota in bytes (default 1 GiB)")
@click.option("--amount", type=DECIMAL, required=True, help="Payment amount in AIT")
@click.option("--fee", type=DECIMAL, default="0.001", help="Transaction fee in AIT")
@click.option("--password", help="Wallet password")
@click.option("--password-file", help="File containing wallet password")
@click.option("--rpc-url", help="Blockchain RPC URL")
@click.pass_context
def subscribe(
    ctx,
    wallet_name: str,
    to_address: str,
    island_id: str,
    duration: int,
    quota: int,
    amount: Decimal,
    fee: Decimal,
    password: str | None,
    password_file: str | None,
    rpc_url: str | None,
):
    """Subscribe to a private island IPFS network.

    Submits an IPFS_SUBSCRIPTION transaction that creates or extends an
    on-chain subscription record. The member can then request the swarm key
    with `aitbc-cli ipfs island swarm-key`.
    """
    resolved_password = _resolve_wallet_password(password, password_file, wallet_name)
    resolved_rpc_url = _default_rpc_url(rpc_url)
    payload = {
        "island_id": island_id,
        "duration_blocks": duration,
        "quota_bytes": quota,
    }

    tx_hash = _send_transaction_impl(
        from_wallet=wallet_name,
        to_address=to_address,
        amount=amount,
        fee=fee,
        password=resolved_password,
        rpc_url=resolved_rpc_url,
        tx_type="IPFS_SUBSCRIPTION",
        payload=payload,
    )
    if tx_hash:
        success(f"Island IPFS subscription transaction sent: {tx_hash}")
        click.echo(
            json.dumps(
                {
                    "success": True,
                    "data": {
                        "tx_hash": tx_hash,
                        "island_id": island_id,
                        "duration_blocks": duration,
                        "quota_bytes": quota,
                    },
                },
                indent=2,
            )
        )
    else:
        error("Failed to send island IPFS subscription transaction")


@island.command(name="swarm-key")
@click.option("--wallet", "wallet_name", required=True, help="Wallet name whose address is subscribed")
@click.option("--island-id", required=True, help="Island identifier")
@click.option("--coordinator-url", help="Coordinator API base URL")
@click.option("--chain-id", help="Blockchain chain ID (auto-detected from RPC if omitted)")
@click.option("--rpc-url", help="Blockchain RPC URL for chain ID auto-detection")
@click.option("--api-key", help="Coordinator API key (default from config / AITBC_API_KEY / MINER_API_KEYS)")
@click.option("--password", help="Wallet password")
@click.option("--password-file", help="File containing wallet password")
@click.option("--output", type=click.Path(), help="Optional path to write the swarm.key")
@click.option("--bootstrap", is_flag=True, help="Also print a bootstrap multiaddr for the hub island daemon")
@click.pass_context
def swarm_key(
    ctx,
    wallet_name: str,
    island_id: str,
    coordinator_url: str | None,
    chain_id: str | None,
    rpc_url: str | None,
    api_key: str | None,
    password: str | None,
    password_file: str | None,
    output: str | None,
    bootstrap: bool,
):
    """Request the swarm key for a subscribed island IPFS network.

    Signs an authorization challenge with the wallet key and calls the
    coordinator swarm-key endpoint. The coordinator checks the on-chain
    subscription before returning the key.
    """
    resolved_password = _resolve_wallet_password(password, password_file, wallet_name)
    member_address, private_key = _load_wallet_key(wallet_name, resolved_password)

    resolved_rpc_url = _default_rpc_url(rpc_url)
    if not chain_id:
        chain_id = get_chain_id(resolved_rpc_url, override=None, timeout=5)
        if not chain_id:
            error("Could not auto-detect chain_id; pass --chain-id explicitly")
            return

    resolved_coordinator_url = _default_coordinator_url(coordinator_url)
    resolved_api_key = api_key
    if not resolved_api_key:
        resolved_api_key = getattr(get_config(), "api_key", None)
    if not resolved_api_key:
        resolved_api_key = _resolve_api_key({})
    if not resolved_api_key:
        error("No API key available; set AITBC_API_KEY, add api_key to config, or pass --api-key")
        return

    nonce = f"{datetime.now(UTC).isoformat()}:{secrets.token_hex(8)}"
    challenge = f"{island_id}:{member_address}:{nonce}".encode()
    msg_hash = "0x" + keccak(challenge).hex()
    private_key_hex = private_key.to_hex()
    signature = sign_transaction_hash(msg_hash, private_key_hex)

    request = {
        "chain_id": chain_id,
        "island_id": island_id,
        "member_address": member_address,
        "nonce": nonce,
        "signature": signature,
    }

    base = resolved_coordinator_url.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    url = f"{base}/v1/ipfs/island/swarm-key"
    try:
        response = requests.post(
            url,
            json=request,
            headers={"X-Api-Key": resolved_api_key},
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        error(f"Failed to request swarm key: {e}")
        if isinstance(e, requests.HTTPError) and e.response is not None:
            click.echo(e.response.text, err=True)
        return

    data = response.json()
    key = data.get("swarm_key", "")
    if output:
        out_path = Path(output)
        out_path.write_text(key)
        out_path.chmod(0o600)
        success(f"Swarm key written to {output}")

    result_data: dict[str, Any] = {
        "island_id": data.get("island_id"),
        "chain_id": data.get("chain_id"),
        "member_address": data.get("member_address"),
        "swarm_key": key,
    }
    if bootstrap and data.get("hub_multiaddr_template"):
        template = data.get("hub_multiaddr_template", "")
        # The template contains <hub_peer_id>; keep it as a hint if peer id not known.
        if "<hub_peer_id>" in template:
            result_data["bootstrap_hint"] = template
        else:
            result_data["bootstrap"] = template

    click.echo(json.dumps({"success": True, "data": result_data}, indent=2))


ipfs.add_command(island, name="island")
