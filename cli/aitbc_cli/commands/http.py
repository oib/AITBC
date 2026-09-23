"""Generic HTTP pivot for AITBC CLI.

Calls pre-mapped local AITBC services by name so users and scripts do not
have to remember ports. Any path can be reached with ``aitbc http``; it is
intended for ad-hoc inspection and for automation that talks to several
internal services.
"""

from __future__ import annotations

import json
from typing import Any

import click

from ..config import get_config
from ..utils import OUTPUT_FORMAT_OPTION, output
from ..utils.http_client import AITBCHTTPClient, NetworkError, auth_client_kwargs
from ..utils.output import resolve_output_format


# Logical service name -> local base URL. These are the documented local
# service ports; they can be overridden with --url.
_SERVICE_BASES: dict[str, str] = {
    "api-gateway": "http://127.0.0.1:8201",
    "blockchain-event-bridge": "http://127.0.0.1:8205",
    "blockchain-explorer": "http://127.0.0.1:8100",
    "blockchain-rpc": "http://127.0.0.1:8202/rpc",
    "coordinator-api": "http://127.0.0.1:8203",
    "agent-coordinator": "http://127.0.0.1:8107",
    "exchange": "http://127.0.0.1:8106",
    "ffmpeg": "http://127.0.0.1:8230",
    "governance": "http://127.0.0.1:8105",
    "gpu": "http://127.0.0.1:8101",
    "edge": "http://127.0.0.1:8111",
    "ipfs": "http://127.0.0.1:5002",
    "marketplace": "http://127.0.0.1:8102",
    "monitoring": "http://127.0.0.1:8002",
    "pool-hub": "http://127.0.0.1:8210",
    "trading": "http://127.0.0.1:8104",
    "wallet": "http://127.0.0.1:8108",
    "whisper": "http://127.0.0.1:8110",
    "ollama": "http://127.0.0.1:11434",
}


def _normalize_service_name(service: str) -> str:
    """Accept systemd-style (aitbc-*) and underscored names."""
    service = service.lower().strip().replace("_", "-")
    if service.startswith("aitbc-"):
        service = service[6:]
    return service


def _resolve_miner_api_key(env_path: str = "/etc/aitbc/aitbc-coordinator-api.env") -> str | None:
    """Resolve the first miner API key from the on-node env file."""
    try:
        from pathlib import Path

        p = Path(env_path)
        if not p.exists():
            return None
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith(("#", ";")) or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == "MINER_API_KEYS":
                value = value.strip().strip('"').strip("'")
                if value.startswith("["):
                    try:
                        keys = json.loads(value)
                        if isinstance(keys, (list, tuple)) and keys:
                            return str(keys[0])
                    except json.JSONDecodeError:
                        pass
                if value:
                    return value.split(",")[0].strip()
                return None
    except Exception:
        pass
    return None


@click.group(
    epilog="""Examples:

  aitbc http call blockchain-rpc height

  aitbc http call wallet v1/wallets --output json

  aitbc http call coordinator-api v1/jobs --method POST --body '{"limit": 10}'"""
)
def http():
    """Generic HTTP client for local AITBC services."""
    pass


@http.command(
    name="call",
    epilog="""Examples:

  aitbc http call blockchain-rpc height

  aitbc http call marketplace v1/offers --params '{"limit": "5"}'

  aitbc http call wallet v1/wallets --method POST --body '{"wallet_id": "genesis"}'""",
)
@click.argument("service")
@click.argument("path")
@click.option("--method", "-X", default="GET", help="HTTP method (GET, POST, PUT, PATCH, DELETE)")
@click.option("--params", default=None, help="JSON object of query parameters")
@click.option("--body", default=None, help="JSON object request body")
@click.option("--url", default=None, help="Override the service base URL")
@click.option("--api-key", default=None, help="API key header (X-API-Key; X-Trading-Api-Key with --auth trading)")
@click.option(
    "--auth",
    "auth_kind",
    type=click.Choice(["none", "miner", "rpc", "trading"]),
    default="none",
    help="Use configured API key for auth ('miner' = coordinator/miner key, 'rpc' = blockchain RPC key, 'trading' = trading service key)",
)
@click.option("--timeout", type=int, default=30, help="Request timeout in seconds")
@click.option(
    "--idempotency-key",
    default=None,
    help="Idempotency-Key header for write requests; enables safe retry of ambiguous outcomes",
)
@OUTPUT_FORMAT_OPTION
@click.pass_context
def call_http(
    ctx,
    service: str,
    path: str,
    method: str,
    params: str | None,
    body: str | None,
    url: str | None,
    api_key: str | None,
    auth_kind: str,
    timeout: int,
    idempotency_key: str | None,
    output_format: str,
):
    """Call an AITBC HTTP endpoint by service name and path."""
    service = _normalize_service_name(service)

    base_url: str | None
    if url:
        base_url = url
    else:
        base_url = _SERVICE_BASES.get(service)
        if not base_url:
            raise click.ClickException(f"Unknown service: {service}. Use --url or one of: {', '.join(sorted(_SERVICE_BASES))}")

    query_params: dict[str, Any] | None = None
    if params:
        try:
            query_params = json.loads(params)
        except json.JSONDecodeError as e:
            raise click.ClickException(f"Invalid --params JSON: {e}") from e

    request_body: dict[str, Any] | None = None
    if body:
        try:
            request_body = json.loads(body)
        except json.JSONDecodeError as e:
            raise click.ClickException(f"Invalid --body JSON: {e}") from e

    resolved_key: str | None = None
    if not api_key:
        if auth_kind == "miner":
            try:
                resolved_key = get_config().api_key
            except Exception:
                resolved_key = None
            if not resolved_key:
                resolved_key = _resolve_miner_api_key()
        elif auth_kind == "rpc":
            try:
                resolved_key = get_config().blockchain_rpc_api_key
            except Exception:
                resolved_key = None
        elif auth_kind == "trading":
            try:
                trading_key = get_config().trading_api_key
                resolved_key = trading_key.get_secret_value() if trading_key else None
            except Exception:
                resolved_key = None

    output_format = resolve_output_format(ctx, output_format)
    method = method.upper()
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        raise click.ClickException(f"Unsupported HTTP method: {method}")

    # --api-key wins; otherwise a stored `aitbc auth login` JWT goes out as
    # Bearer before falling back to the resolved/configured API key. The trading
    # service authenticates on X-Trading-Api-Key, so --auth trading bypasses
    # auth_client_kwargs (which only emits X-API-Key) and fails loudly when no
    # trading key resolves — silently sending an unrelated credential would
    # surface as a misleading "Missing API key" 401.
    if auth_kind == "trading":
        trading_token = api_key or resolved_key
        if not trading_token:
            raise click.ClickException(
                "No trading API key configured: set TRADING_API_KEY or a readable /etc/aitbc/aitbc-trading.env"
            )
        client = AITBCHTTPClient(
            base_url=base_url,
            timeout=timeout,
            headers={"X-Trading-Api-Key": trading_token},
        )
    else:
        client = AITBCHTTPClient(
            base_url=base_url,
            timeout=timeout,
            **auth_client_kwargs(api_key, resolved_key),
        )
    try:
        if method == "GET":
            result = client.get(path, params=query_params)
        elif method == "POST":
            result = client.post(path, json=request_body, idempotency_key=idempotency_key)
        elif method == "PUT":
            result = client.put(path, json=request_body, idempotency_key=idempotency_key)
        elif method == "PATCH":
            result = client.patch(path, json=request_body, idempotency_key=idempotency_key)
        else:  # DELETE
            result = client.delete(path, params=query_params, idempotency_key=idempotency_key)
        output(result, output_format, title=f"{method} {service}/{path}")
    except NetworkError as e:
        raise click.ClickException(f"Network error calling {service}/{path}: {e}") from e
    finally:
        client.close()
