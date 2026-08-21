"""Customer and shop operational dashboards for the AITBC CLI."""

from __future__ import annotations

import os
from collections import Counter
from typing import Any

import click

from ..auth import AuthManager
from ..config import get_config
from ..utils import error, info, output, success, warning
from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger

logger = get_logger(__name__)


def _auth_headers(ctx: click.Context) -> dict[str, str] | None:
    """Return Authorization header from --api-key or the stored credential."""
    token = ctx.obj.get("api_key")
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
        coord_client = _client(ctx, timeout=15)

        jobs_data = _safe_get(coord_client, "/v1/jobs", {"limit": limit}) or {}
        if isinstance(jobs_data, list):
            jobs = jobs_data
        elif isinstance(jobs_data, dict):
            jobs = jobs_data.get("items", [])
        else:
            jobs = []

        state_counts: Counter = Counter()
        payment_counts: Counter = Counter()
        recent_jobs: list[dict[str, Any]] = []
        for job in jobs:
            if not isinstance(job, dict):
                continue
            state_counts[job.get("state", "UNKNOWN")] += 1
            payment_counts[job.get("payment_status", "unknown")] += 1
            payload = job.get("payload") or {}
            result = job.get("result") or {}
            model = (
                result.get("model")
                or payload.get("model")
                or (result.get("result") or {}).get("model")
                or (result.get("receipt") or {}).get("model")
                or "N/A"
            )
            requested_at = job.get("requested_at") or job.get("created_at")
            created = str(requested_at)[:19] if requested_at else "N/A"
            recent_jobs.append(
                {
                    "Job ID": job.get("job_id", job.get("id", "N/A")),
                    "State": job.get("state", "N/A"),
                    "Payment": job.get("payment_status", "N/A"),
                    "Model": model,
                    "Created": created,
                }
            )

        wallets_data: dict[str, Any] = {}
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
                try:
                    balance_data = wallet_client.get(f"/v1/chains/{chain_id}/wallets/{wallet_id}/balance") or {}
                    balance = balance_data.get("balance", "N/A")
                except Exception:
                    balance = "N/A"
                wallet_balances.append(
                    {
                        "Wallet": wallet_id,
                        "Address": wallet.get("address") or wallet.get("metadata", {}).get("address", "N/A"),
                        "Balance": balance,
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
        import socket

        config = ctx.obj["config"]
        if not miner_id:
            miner_id = os.environ.get("NODE_ID") or socket.gethostname() or getattr(config, "node_id", "") or "unknown"

        coord_client = _client(ctx, timeout=15)

        # Aggregate job/miner metrics (public monitoring endpoint)
        metrics = _safe_get(coord_client, "/v1/monitoring/metrics") or {}
        jobs_metrics = metrics.get("jobs", {}) if isinstance(metrics, dict) else {}
        miners_metrics = metrics.get("miners", {}) if isinstance(metrics, dict) else {}

        # Try to get local miner details if an ID is available
        miner_jobs: list[dict[str, Any]] = []
        miner_earnings: dict[str, Any] = {}
        if miner_id:
            jobs_resp = _safe_post(coord_client, f"/v1/miners/{miner_id}/jobs", {"limit": limit})
            if jobs_resp:
                miner_jobs = jobs_resp.get("items", []) if isinstance(jobs_resp, dict) else jobs_resp
            earnings_resp = _safe_post(coord_client, f"/v1/miners/{miner_id}/earnings")
            if earnings_resp:
                miner_earnings = earnings_resp if isinstance(earnings_resp, dict) else {}

        # GPUs on this node
        gpu_data: dict[str, Any] = {}
        try:
            gpu_client = AITBCHTTPClient(base_url=config.gpu_service_url or "http://localhost:8101", timeout=10)
            gpu_data = gpu_client.get("/v1/gpu/discover") or {}
        except NetworkError as e:
            logger.warning("GPU service unavailable: %s", e)

        # Marketplace offers published by this shop
        offers_data: dict[str, Any] = {}
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
                try:
                    balance_data = wallet_client.get(f"/v1/chains/{chain_id}/wallets/{wallet_id}/balance") or {}
                    balance = balance_data.get("balance", "N/A")
                except Exception:
                    balance = "N/A"
                wallet_balances.append(
                    {
                        "Wallet": wallet_id,
                        "Address": wallet.get("address") or wallet.get("metadata", {}).get("address", "N/A"),
                        "Balance": balance,
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
                    "Created": str(job.get("created_at", "N/A"))[:19],
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
