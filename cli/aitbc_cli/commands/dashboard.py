"""Customer and shop operational dashboards for the AITBC CLI."""

from __future__ import annotations

import os
import socket
from collections import Counter
from typing import Any

import click

from ..auth import AuthManager
from ..utils import error, info, output, success
from ..utils.address import to_canonical
from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger
from aitbc.utils import format_ait

logger = get_logger(__name__)

_MINER_ENV_FILE = "/etc/aitbc/aitbc-miner.env"
_MINER_UNIT_FILE = "/opt/aitbc/apps/miner/aitbc-miner.service"


def _parse_env_assignment(line: str) -> tuple[str, str] | None:
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        return None
    if line.startswith("Environment="):
        line = line.split("=", 1)[1].strip().strip("'\"")
    key, value = line.split("=", 1)
    key, value = key.strip().strip("'\""), value.strip().strip("'\"")
    if key in ("MINER_ID", "MINER_API_KEY", "AITBC_API_KEY") and value:
        return key, value
    return None


def _miner_env() -> dict[str, str]:
    """Return miner id/key from the process environment, miner env file, or unit file."""
    values: dict[str, str] = {}
    for key in ("MINER_ID", "MINER_API_KEY", "AITBC_API_KEY"):
        value = os.environ.get(key)
        if value:
            values[key] = value
    for path in (_MINER_ENV_FILE, _MINER_UNIT_FILE):
        if "MINER_ID" in values and "MINER_API_KEY" in values:
            break
        try:
            with open(path) as handle:
                for raw in handle:
                    parsed = _parse_env_assignment(raw)
                    if parsed and parsed[0] not in values:
                        values[parsed[0]] = parsed[1]
        except OSError:
            logger.debug("Could not read %s", path, exc_info=True)
    return values


def _ctx_obj(ctx: click.Context | dict[str, Any]) -> dict[str, Any]:
    """Return the CLI object dict from a Click context or a plain dict."""
    obj = getattr(ctx, "obj", ctx)
    return obj if isinstance(obj, dict) else {}


def _auth_headers(ctx: click.Context | dict[str, Any], role: str = "client") -> dict[str, str] | None:
    """Return auth headers for a dashboard role.

    Customer views use a client JWT. Shop views use miner API-key auth
    (``X-Api-Key`` / ``X-Miner-ID``), matching production miners. A client JWT
    must not be sent to miner-only endpoints: AuthMiddleware rejects
    role=client on ``/v1/miners/*`` with 401.
    """
    obj = _ctx_obj(ctx)
    if role == "miner":
        miner_env = _miner_env()
        api_key = obj.get("api_key") or miner_env.get("MINER_API_KEY") or miner_env.get("AITBC_API_KEY")
        if not api_key:
            return None
        headers = {"X-Api-Key": api_key}
        miner_id = miner_env.get("MINER_ID")
        if miner_id:
            headers["X-Miner-ID"] = miner_id
        return headers

    token = obj.get("api_key")
    if not token:
        token = AuthManager().get_credential("client")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return None


def _coordinator_base_url(ctx: click.Context) -> str:
    """Return the coordinator base URL without a trailing /v1 path.

    The coordinator routers are mounted under /v1, and callers below use
    absolute /v1/... endpoints. If the configured URL already ends in /v1,
    strip it to avoid doubling the path.
    """
    config = ctx.obj["config"]
    url = ctx.obj.get("url") or config.coordinator_api_url or "http://localhost:8203"
    url = url.rstrip("/")
    if url.endswith("/v1"):
        url = url[:-3]
    return url


def _client(ctx: click.Context, base_url: str | None = None, timeout: int = 10) -> AITBCHTTPClient:
    url = base_url or _coordinator_base_url(ctx)
    headers = _auth_headers(ctx)
    return AITBCHTTPClient(base_url=url, timeout=timeout, headers=headers)


def _safe_get(client: AITBCHTTPClient, path: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    try:
        return client.get(path, params=params)  # type: ignore[no-any-return]
    except NetworkError as e:
        logger.warning("Dashboard GET %s failed: %s", path, e)
        return None
    except Exception as e:
        logger.warning("Dashboard GET %s failed: %s", path, e)
        return None


def _safe_post(client: AITBCHTTPClient, path: str, json: dict[str, Any] | None = None) -> dict[str, Any] | None:
    try:
        return client.post(path, json=json)  # type: ignore[no-any-return]
    except NetworkError as e:
        logger.warning("Dashboard POST %s failed: %s", path, e)
        return None
    except Exception as e:
        logger.warning("Dashboard POST %s failed: %s", path, e)
        return None


def _blockchain_balance(rpc_url: str, address: str, chain_id: str) -> tuple[int, int, str]:
    """Return on-chain balance, nonce and chain_id for an address (any accepted spelling)."""
    try:
        canon = to_canonical(address)
        client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        data = client.get(f"/rpc/account/{canon}") or {}
        return int(data.get("balance", 0)), int(data.get("nonce", 0)), data.get("chain_id", chain_id)
    except Exception:
        logger.debug("Blockchain balance query failed for %s", address, exc_info=True)
        return 0, 0, chain_id


def _live_wallet_balance(
    wallet_client: AITBCHTTPClient,
    wallet_id: str,
    address: str,
    chain_id: str,
    blockchain_rpc_url: str,
) -> dict[str, Any]:
    """Return wallet balance, preferring the daemon and falling back to the blockchain RPC."""
    balance: Any = "N/A"
    fallback = False
    try:
        balance_data = wallet_client.get(f"/v1/chains/{chain_id}/wallets/{wallet_id}/balance") or {}
        balance = balance_data.get("balance", "N/A")
    except Exception:
        fallback = True
    if balance in (None, "N/A", ""):
        fallback = True
    if fallback:
        balance, _, _ = _blockchain_balance(blockchain_rpc_url, address, chain_id)
    balance_ait = format_ait(balance) if not isinstance(balance, str) or balance not in ("N/A", "") else "N/A"
    return {"balance": balance, "balance_ait": balance_ait}


def _escrow_payment_status(blockchain_rpc_url: str, job_id: str) -> str | None:
    """Query on-chain escrow state and map it to a payment_status string."""
    try:
        client = AITBCHTTPClient(base_url=blockchain_rpc_url, timeout=10)
        data = client.get(f"/rpc/escrow/{job_id}") or {}
        state = (data.get("state") or data.get("status") or "").lower()
        mapping = {
            "created": "escrowed",
            "funded": "escrowed",
            "locked": "escrowed",
            "job_started": "escrowed",
            "job_completed": "escrowed",
            "released": "released",
            "refunded": "refunded",
        }
        return mapping.get(state)
    except Exception:
        logger.debug("Escrow payment status query failed for %s", job_id, exc_info=True)
        return None


def _enrich_jobs_with_escrow(jobs: list[Any], blockchain_rpc_url: str) -> None:
    """Override coordinator payment_status with on-chain escrow state when available."""
    for job in jobs:
        if not isinstance(job, dict):
            continue
        job_id = job.get("job_id") or job.get("id")
        if not job_id:
            continue
        ps = _escrow_payment_status(blockchain_rpc_url, job_id)
        if ps:
            job["payment_status"] = ps


def _model_for_job(job: dict[str, Any]) -> str:
    """Extract the model name from a job record."""
    payload = job.get("payload") or {}
    result = job.get("result") or {}
    return (
        result.get("model")
        or payload.get("model")
        or (result.get("result") or {}).get("model")
        or (result.get("receipt") or {}).get("model")
        or "N/A"
    )


@click.group()
def dashboard():
    """Operational dashboards for customers and shops."""
    pass


@dashboard.command()
@click.option("--limit", type=int, default=20, help="Number of recent jobs to show")
@click.option("--wallet-limit", type=int, default=10, help="Number of wallet balances to show")
@click.pass_context
def customer(ctx: click.Context, limit: int, wallet_limit: int) -> None:
    """Customer dashboard: jobs, payments, and wallets."""
    try:
        config = ctx.obj["config"]
        blockchain_rpc_url = config.blockchain_rpc_url or "http://localhost:8202"
        coord_client = _client(ctx, timeout=15)

        jobs_data = _safe_get(coord_client, "/v1/jobs", {"limit": limit}) or {}
        if isinstance(jobs_data, list):
            jobs = jobs_data
        elif isinstance(jobs_data, dict):
            jobs = jobs_data.get("items", [])
        else:
            jobs = []

        _enrich_jobs_with_escrow(jobs, blockchain_rpc_url)

        state_counts: Counter = Counter()
        payment_counts: Counter = Counter()
        recent_jobs: list[dict[str, Any]] = []
        for job in jobs:
            if not isinstance(job, dict):
                continue
            state_counts[job.get("state", "UNKNOWN")] += 1
            payment_counts[job.get("payment_status", "unknown")] += 1
            requested_at = job.get("requested_at") or job.get("created_at")
            created = str(requested_at)[:19] if requested_at else "N/A"
            recent_jobs.append(
                {
                    "Job ID": job.get("job_id", job.get("id", "N/A")),
                    "State": job.get("state", "N/A"),
                    "Payment": job.get("payment_status", "N/A"),
                    "Model": _model_for_job(job),
                    "Created": created,
                }
            )

        wallet_balances: list[dict[str, Any]] = []
        try:
            wallet_client = AITBCHTTPClient(base_url=config.wallet_daemon_url, timeout=10)
            wallets_data = wallet_client.get("/v1/wallets") or {}
            wallets = wallets_data.get("items", []) if isinstance(wallets_data, dict) else []
            chain_id = ctx.obj.get("chain_id") or "ait-devnet"
            for wallet in wallets[:wallet_limit]:
                if not isinstance(wallet, dict):
                    continue
                wallet_id = wallet.get("wallet_id", "N/A")
                address = wallet.get("address") or wallet.get("metadata", {}).get("address", "N/A")
                canonical = to_canonical(address)
                bal_info = _live_wallet_balance(wallet_client, wallet_id, address, chain_id, blockchain_rpc_url)
                wallet_balances.append(
                    {
                        "Wallet": wallet_id,
                        "Address": address,
                        "Canonical": canonical,
                        "Balance AIT": bal_info["balance_ait"],
                    }
                )
        except NetworkError as e:
            logger.warning("Wallet daemon unavailable: %s", e)

        dashboard_data: dict[str, Any] = {
            "summary": {
                "total_jobs": len(jobs),
                "job_states": dict(state_counts),
                "payment_statuses": dict(payment_counts),
                "wallets": len(wallet_balances),
            },
            "recent_jobs": recent_jobs,
            "wallets": wallet_balances,
        }

        output(dashboard_data, ctx.obj.get("output_format", "table"), title="Customer Dashboard")
        if not jobs and not wallet_balances:
            info("No jobs or wallets found. Submit a job or create a wallet to populate the dashboard.")
        else:
            success("Customer dashboard loaded")
    except click.Abort:
        raise
    except Exception as e:
        error(f"Error loading customer dashboard: {e}")
        raise click.Abort() from e


@dashboard.command()
@click.option("--miner-id", help="Miner ID for this shop (optional; defaults to island id)")
@click.option("--limit", type=int, default=20, help="Number of marketplace offers to show")
@click.pass_context
def shop(ctx: click.Context, miner_id: str | None, limit: int) -> None:
    """Shop dashboard: miners, GPUs, offers, jobs, and earnings."""
    try:
        config = ctx.obj["config"]
        blockchain_rpc_url = config.blockchain_rpc_url or "http://localhost:8202"
        if not miner_id:
            miner_id = (
                _miner_env().get("MINER_ID")
                or os.environ.get("NODE_ID")
                or socket.gethostname()
                or getattr(config, "node_id", "")
                or "unknown"
            )

        # Miner-role headers for /v1/miners/* and /v1/monitoring* (ANY authenticated role).
        miner_headers = _auth_headers(ctx, role="miner")
        coord_url = _coordinator_base_url(ctx)
        coord_client = AITBCHTTPClient(base_url=coord_url, timeout=15, headers=miner_headers)

        metrics = _safe_get(coord_client, "/v1/monitoring/metrics") or {}
        jobs_metrics = metrics.get("jobs", {}) if isinstance(metrics, dict) else {}
        miners_metrics = metrics.get("miners", {}) if isinstance(metrics, dict) else {}

        # Try to get local miner details if an ID is available
        miner_jobs: list[dict[str, Any]] = []
        miner_earnings: dict[str, Any] = {}
        if miner_id:
            jobs_resp = _safe_post(coord_client, f"/v1/miners/{miner_id}/jobs", {"limit": limit})
            if jobs_resp:
                miner_jobs = jobs_resp.get("jobs", jobs_resp.get("items", [])) if isinstance(jobs_resp, dict) else jobs_resp
            earnings_resp = _safe_post(coord_client, f"/v1/miners/{miner_id}/earnings")
            if earnings_resp:
                miner_earnings = earnings_resp if isinstance(earnings_resp, dict) else {}

        _enrich_jobs_with_escrow(miner_jobs, blockchain_rpc_url)

        # GPUs on this node
        gpu_data: dict[str, Any] = {}
        try:
            gpu_client = AITBCHTTPClient(base_url=config.gpu_service_url or "http://localhost:8101", timeout=10)
            gpu_data = gpu_client.get("/v1/gpu/discover") or {}
        except NetworkError as e:
            logger.warning("GPU service unavailable: %s", e)

        # Marketplace offers published by this shop
        offer_rows: list[dict[str, Any]] = []
        try:
            market_client = AITBCHTTPClient(
                base_url=f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}",
                timeout=10,
                headers=_auth_headers(ctx),
            )
            offers_data = _safe_get(market_client, "/v1/marketplace/offer", {"limit": limit}) or {}
            offers = offers_data.get("offers", []) if isinstance(offers_data, dict) else []
            shop_id = miner_id or config.node_id or ""
            if shop_id:
                offers = [o for o in offers if o.get("node_id") == shop_id or shop_id in str(o.get("provider_address", ""))]
            for offer in offers:
                offer_rows.append(
                    {
                        "Plugin ID": offer.get("plugin_id", "N/A"),
                        "Model": offer.get("model", "N/A"),
                        "Price": f"{offer.get('price', 0)} {offer.get('price_unit', 'units')}",
                        "Status": offer.get("status", "unknown"),
                        "Rating": f"{offer.get('avg_rating', 0):.1f} ({offer.get('rating_count', 0)})",
                    }
                )
        except NetworkError as e:
            logger.warning("Marketplace service unavailable: %s", e)

        # Shop wallet balances
        wallet_balances: list[dict[str, Any]] = []
        try:
            wallet_client = AITBCHTTPClient(base_url=config.wallet_daemon_url, timeout=10)
            wallets_data = wallet_client.get("/v1/wallets") or {}
            wallets = wallets_data.get("items", []) if isinstance(wallets_data, dict) else []
            chain_id = ctx.obj.get("chain_id") or "ait-devnet"
            for wallet in wallets[:5]:
                if not isinstance(wallet, dict):
                    continue
                wallet_id = wallet.get("wallet_id", "N/A")
                address = wallet.get("address") or wallet.get("metadata", {}).get("address", "N/A")
                canonical = to_canonical(address)
                bal_info = _live_wallet_balance(wallet_client, wallet_id, address, chain_id, blockchain_rpc_url)
                wallet_balances.append(
                    {
                        "Wallet": wallet_id,
                        "Address": address,
                        "Canonical": canonical,
                        "Balance AIT": bal_info["balance_ait"],
                    }
                )
        except NetworkError as e:
            logger.warning("Wallet daemon unavailable: %s", e)

        dashboard_data: dict[str, Any] = {
            "summary": {
                "miner_id": miner_id,
                "network_jobs_total": jobs_metrics.get("total", 0),
                "network_jobs_completed": jobs_metrics.get("completed", 0),
                "network_jobs_pending": jobs_metrics.get("pending", 0),
                "network_jobs_failed": jobs_metrics.get("failed", 0),
                "miners_total": miners_metrics.get("total", 0),
                "miners_online": miners_metrics.get("online", 0),
                "gpus_found": len(gpu_data.get("gpus", []) if isinstance(gpu_data, dict) else gpu_data),
                "offers_published": len(offer_rows),
                "shop_assigned_jobs": len(miner_jobs),
                "wallets": len(wallet_balances),
            },
            "assigned_jobs": [
                {
                    "Job ID": job.get("job_id", job.get("id", "N/A")),
                    "State": job.get("state", "N/A"),
                    "Payment": job.get("payment_status", "N/A"),
                    "Model": (
                        (job.get("result") or {}).get("model")
                        or (job.get("payload") or {}).get("model")
                        or ((job.get("result") or {}).get("result") or {}).get("model")
                        or "N/A"
                    ),
                    "Created": str(job.get("requested_at") or job.get("created_at"))[:19],
                }
                for job in (miner_jobs if isinstance(miner_jobs, list) else [])
            ],
            "marketplace_offers": offer_rows,
            "wallets": wallet_balances,
            "earnings": {
                "total": miner_earnings.get("total_earnings", "N/A"),
                "paid": miner_earnings.get("paid_earnings", "N/A"),
                "pending": miner_earnings.get("pending_earnings", "N/A"),
            },
        }

        output(dashboard_data, ctx.obj.get("output_format", "table"), title="Shop Dashboard")
        success("Shop dashboard loaded")
    except click.Abort:
        raise
    except Exception as e:
        error(f"Error loading shop dashboard: {e}")
        raise click.Abort() from e
