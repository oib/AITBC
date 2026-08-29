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
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import click
import requests

from ..config import get_config
from ..utils import OUTPUT_FORMAT_OPTION, error, info, output, success, warning
from ..utils.address import to_canonical
from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger
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
        cid = _ipfs_add_file(ipfs_api, file_path)
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
    """List active IPFS rentals."""
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
