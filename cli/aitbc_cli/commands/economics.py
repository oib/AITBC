"""Economics commands for AITBC CLI."""

from __future__ import annotations

import os
import statistics
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import click
import httpx

from aitbc.config.hub import normalize_hub_base
from aitbc.exceptions import AITBCError
from aitbc.utils.units import DEFAULT_TX_FEE_AIT
from ..config import get_config
from ..utils import output
from ..utils.error_handling import CLIError, abort
from ..utils.http_client import AITBCHTTPClient, NetworkError, auth_client_kwargs, service_root_url

# Expected failure surface for the command handlers below: filesystem/JSON,
# data-shape, runtime, optional-dependency imports, HTTP-client errors and
# both error hierarchies (CLIError, aitbc_errors.AITBCError). RuntimeError
# covers generic runtime failures; abort() raises CLIError (already listed),
# preserving the previous re-abort behaviour. BaseExceptions still propagate
# (#1864).
_OPS_ERRORS = (
    OSError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
    ImportError,
    CLIError,
    AITBCError,
    httpx.HTTPError,
)


def _api_client(explicit_key: str | None = None) -> AITBCHTTPClient | None:
    """Return a client for the coordinator API if a URL is configured.

    Endpoints below carry absolute ``/v1/...`` paths, so normalize the
    configured URL to the service root — a configured ``.../v1`` value
    (e.g. the public ``/c/v1`` mount) must not double the version prefix.

    #2246: credentials resolve explicit ``--api-key`` > stored ``auth
    login`` credential > ``config.api_key`` via ``auth_client_kwargs``.
    """
    config = get_config()
    url = config.coordinator_api_url or os.getenv("COORDINATOR_API_URL", "")
    if not url:
        return None
    return AITBCHTTPClient(
        base_url=service_root_url(url), timeout=config.timeout, **auth_client_kwargs(explicit_key, config.api_key)
    )


# ---------------------------------------------------------------------------
# Live-data probes for market / model / distributed (#2344)
#
# Every probe records its outcome in a ``sources`` map — ``"ok"`` or the
# error string — so an unreachable service degrades to partial data instead
# of a fabricated result. Nothing here emits ``status: "simulated"``.
# ---------------------------------------------------------------------------

_ACTIVE_OFFER_STATUSES = {"active", "available", "open"}
_SUPPORTED_MODEL_TYPES = ("cost-optimization",)
_PROBE_TIMEOUT_CAP = 15


def _probe_timeout(config) -> int:
    """Short probe timeout: the configured value, capped so dead hosts fail fast."""
    try:
        timeout = int(getattr(config, "timeout", 10) or 10)
    except (TypeError, ValueError):
        timeout = 10
    return max(1, min(timeout, _PROBE_TIMEOUT_CAP))


def _try_get(client: AITBCHTTPClient, path: str, params: dict[str, Any] | None = None) -> tuple[Any, str | None]:
    """GET ``path``; return ``(data, None)`` or ``(None, error)``."""
    try:
        return client.get(path, params=params), None
    except _OPS_ERRORS as e:
        return None, f"{type(e).__name__}: {e}"


def _market_offer_bases(config) -> list[str]:
    """Candidate market-service bases: the hub origin first, then the local market URL.

    Mirrors ``commands/market/offers.py`` — on customer nodes the market API
    is reached through the hub's public mount, with the local
    ``market_service_url`` as fallback.
    """
    bases: list[str] = []
    hub_raw = getattr(config, "hub_discovery_url", None)
    if hub_raw:
        hub = normalize_hub_base(hub_raw)
        if hub:
            bases.append(hub.rstrip("/"))
    local = str(getattr(config, "market_service_url", "") or "").rstrip("/")
    if local:
        bases.append(local)
    return list(dict.fromkeys(bases))


def _fetch_market_offers(config, sources: dict[str, str]) -> tuple[list[dict[str, Any]], str | None]:
    """Fetch ``GET /v1/market/offer`` from the first reachable base.

    Returns ``(offers, base_url)``; ``sources["market_offers"]`` records
    ``"ok"`` or the collected per-base errors.
    """
    errors: list[str] = []
    for base in _market_offer_bases(config):
        try:
            client = AITBCHTTPClient(base_url=base, timeout=_probe_timeout(config))
            try:
                data, err = _try_get(client, "/v1/market/offer")
            finally:
                client.close()
        except _OPS_ERRORS as e:
            errors.append(f"{base}: {type(e).__name__}: {e}")
            continue
        if err is None and isinstance(data, dict) and isinstance(data.get("offers"), list):
            sources["market_offers"] = "ok"
            return data["offers"], base
        errors.append(f"{base}: {err or 'unexpected response shape'}")
    sources["market_offers"] = "; ".join(errors) if errors else "no market service URL configured"
    return [], None


def _exchange_orderbook(config, sources: dict[str, str]) -> dict[str, Any] | None:
    """Fetch the hub exchange order book (``GET /api/orders/orderbook``)."""
    base = str(getattr(config, "exchange_service_url", "") or "").rstrip("/")
    if not base or base.endswith("/rpc"):
        # ``exchange_service_url`` falls back to the blockchain RPC when no
        # hub exchange is configured — that host has no /api/orders routes.
        sources["exchange_orderbook"] = "not configured (exchange_service_url unset or resolves to blockchain RPC)"
        return None
    try:
        client = AITBCHTTPClient(base_url=base, timeout=_probe_timeout(config))
        try:
            data, err = _try_get(client, "/api/orders/orderbook")
        finally:
            client.close()
    except _OPS_ERRORS as e:
        sources["exchange_orderbook"] = f"{type(e).__name__}: {e}"
        return None
    if err is not None or not isinstance(data, dict):
        sources["exchange_orderbook"] = err or "unexpected response shape"
        return None
    buys = data.get("buys") or []
    sells = data.get("sells") or []
    sources["exchange_orderbook"] = "ok"
    return {
        "bids": len(buys),
        "asks": len(sells),
        "best_bid": buys[0].get("price") if buys else None,
        "best_ask": sells[0].get("price") if sells else None,
        "source": base,
    }


def _chain_rpc_bases(config) -> list[str]:
    """Blockchain RPC bases: local ``blockchain_rpc_url`` then ``hub_blockchain_rpc_url``."""
    bases: list[str] = []
    for attr in ("blockchain_rpc_url", "hub_blockchain_rpc_url"):
        url = str(getattr(config, attr, "") or "").rstrip("/")
        if url.endswith("/rpc"):
            url = url[:-4].rstrip("/")
        if url:
            bases.append(url)
    return list(dict.fromkeys(bases))


def _fetch_chain_info(config, sources: dict[str, str]) -> dict[str, Any] | None:
    """Fetch chain height/tx stats via ``GET /rpc/info`` (+ consensus status)."""
    errors: list[str] = []
    for base in _chain_rpc_bases(config):
        try:
            client = AITBCHTTPClient(base_url=base, timeout=_probe_timeout(config))
            try:
                info, err = _try_get(client, "/rpc/info")
                consensus, _consensus_err = (
                    _try_get(client, "/rpc/consensus/status") if err is None and isinstance(info, dict) else (None, None)
                )
            finally:
                client.close()
        except _OPS_ERRORS as e:
            errors.append(f"{base}: {type(e).__name__}: {e}")
            continue
        if err is not None or not isinstance(info, dict):
            errors.append(f"{base}: {err or 'unexpected response shape'}")
            continue
        height = info.get("height")
        total_txs = info.get("total_transactions")
        block_time = (info.get("genesis_params") or {}).get("block_time_seconds")
        avg_tps = None
        try:
            if height and total_txs is not None:
                avg_tps = round(float(total_txs) / float(height), 4)
        except (TypeError, ValueError, ZeroDivisionError):
            avg_tps = None
        result: dict[str, Any] = {
            "chain_id": info.get("chain_id"),
            "height": height,
            "total_transactions": total_txs,
            "block_time_seconds": block_time,
            "avg_tps": avg_tps,
            "source": base,
        }
        if isinstance(consensus, dict):
            result["consensus"] = {
                "mode": consensus.get("mode"),
                "active_validators": consensus.get("active_validators"),
                "configured_validators": consensus.get("configured_validators"),
            }
        sources["blockchain_rpc"] = "ok"
        return result
    sources["blockchain_rpc"] = "; ".join(errors) if errors else "no blockchain RPC URL configured"
    return None


def _probe_coordinator(config, api_key: str | None, sources: dict[str, str]) -> dict[str, Any] | None:
    """Coordinator-api liveness via ``GET /health`` on the configured client."""
    try:
        client = _api_client(api_key)
    except _OPS_ERRORS as e:
        sources["coordinator_api"] = f"{type(e).__name__}: {e}"
        return None
    if client is None:
        sources["coordinator_api"] = "not configured (coordinator_api_url unset)"
        return None
    try:
        data, err = _try_get(client, "/health")
    finally:
        client.close()
    if err is not None or not isinstance(data, dict):
        sources["coordinator_api"] = err or "unexpected response shape"
        return None
    sources["coordinator_api"] = "ok"
    return {"status": data.get("status"), "env": data.get("env")}


def _fetch_oracle_prices(config, api_key: str | None, sources: dict[str, str]) -> dict[str, Any] | None:
    """AIT price feeds via ``GET /v1/oracle/prices`` on the coordinator API."""
    try:
        client = _api_client(api_key)
    except _OPS_ERRORS as e:
        sources["oracle_prices"] = f"{type(e).__name__}: {e}"
        return None
    if client is None:
        sources["oracle_prices"] = "not configured (coordinator_api_url unset)"
        return None
    try:
        data, err = _try_get(client, "/v1/oracle/prices")
    finally:
        client.close()
    if err is not None or not isinstance(data, dict):
        sources["oracle_prices"] = err or "unexpected response shape"
        return None
    sources["oracle_prices"] = "ok"
    return data.get("prices") if isinstance(data.get("prices"), dict) else data


def _ait_usd_price(prices: dict[str, Any] | None) -> Decimal | None:
    """Best-effort AIT/USD price out of the oracle ``prices`` payload."""
    if not isinstance(prices, dict):
        return None
    for key, value in prices.items():
        if "AIT" not in str(key).upper():
            continue
        try:
            price = Decimal(str(value.get("price") if isinstance(value, dict) else value))
        except (InvalidOperation, TypeError, ValueError):
            continue
        if price > 0:
            return price
    return None


def _offer_price(offer: dict[str, Any]) -> Decimal | None:
    try:
        price = Decimal(str(offer.get("price")))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return price if price >= 0 else None


def _is_active_offer(offer: dict[str, Any]) -> bool:
    return str(offer.get("status", "")).lower() in _ACTIVE_OFFER_STATUSES


def _offer_provider(offer: dict[str, Any]) -> str:
    return str(offer.get("provider_address") or offer.get("node_id") or "unknown")


def _price_stats(prices: list[Decimal]) -> dict[str, Any]:
    """min/median/max over Decimal prices (empty list -> None fields)."""
    if not prices:
        return {"count": 0, "min": None, "median": None, "max": None}
    ordered = sorted(prices)
    return {
        "count": len(ordered),
        "min": str(ordered[0]),
        "median": str(Decimal(str(statistics.median(ordered)))),
        "max": str(ordered[-1]),
    }


def _aggregate_offers(offers: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate live market offers: counts by service_type, price stats, top providers."""
    total = len(offers)
    active = [o for o in offers if _is_active_offer(o)]
    priced_active = [o for o in active if _offer_price(o) is not None]
    # Scope note: when nothing is marked active, price stats fall back to all
    # priced offers so the aggregates stay honest about their input set.
    scope = "active"
    if not priced_active:
        priced_active = [o for o in offers if _offer_price(o) is not None]
        scope = "all_offers_no_active"

    by_service_type: dict[str, dict[str, Any]] = {}
    provider_counts: dict[str, int] = {}
    for offer in offers:
        st = str(offer.get("service_type") or "unknown")
        entry = by_service_type.setdefault(st, {"offers": 0, "active": 0, "providers": set(), "price_units": set()})
        entry["offers"] += 1
        entry["active"] += 1 if _is_active_offer(offer) else 0
        provider = _offer_provider(offer)
        entry["providers"].add(provider)
        provider_counts[provider] = provider_counts.get(provider, 0) + 1
        unit = str(offer.get("price_unit") or "unspecified")
        entry["price_units"].add(unit)

    # Price stats are per (service_type, price_unit) — mixing units in one
    # min/median/max would be meaningless.
    price_stats: dict[str, dict[str, Any]] = {}
    for offer in priced_active:
        st = str(offer.get("service_type") or "unknown")
        unit = str(offer.get("price_unit") or "unspecified")
        key = f"{st}/{unit}"
        bucket = price_stats.setdefault(key, {"service_type": st, "price_unit": unit, "prices": []})
        price = _offer_price(offer)
        if price is not None:
            bucket["prices"].append(price)

    stats_out = {
        k: _price_stats(v["prices"]) | {"service_type": v["service_type"], "price_unit": v["price_unit"]}
        for k, v in price_stats.items()
    }

    by_type_out = {
        st: {
            "offers": e["offers"],
            "active": e["active"],
            "providers": len(e["providers"]),
            "price_units": sorted(e["price_units"]),
        }
        for st, e in sorted(by_service_type.items())
    }

    top_providers = [
        {"provider": p, "offers": c} for p, c in sorted(provider_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    ]

    return {
        "total_offers": total,
        "active_offers": len(active),
        "priced_offers": len(priced_active),
        "price_scope": scope,
        "by_service_type": by_type_out,
        "price_stats": stats_out,
        "top_providers": top_providers,
    }


def _cost_optimization(offers: list[dict[str, Any]], ait_usd: Decimal | None) -> dict[str, Any]:
    """Cost-optimization model over live offer prices.

    For each (service_type, price_unit) bucket reports the cheapest and
    median price plus the cheapest provider. ``tx_fee_ait`` is the standard
    per-transaction fee constant; it is reported separately — it is not
    per-token, so it is never folded into the unit price.
    """
    aggregate = _aggregate_offers(offers)
    recommendations = []
    for _key, stats in aggregate["price_stats"].items():
        if not stats.get("count"):
            continue
        # Re-scan to find the cheapest offer's provider for this bucket.
        st, unit = stats["service_type"], stats["price_unit"]
        candidates = [
            o
            for o in offers
            if str(o.get("service_type") or "unknown") == st
            and str(o.get("price_unit") or "unspecified") == unit
            and _offer_price(o) is not None
            and (_is_active_offer(o) or aggregate["price_scope"] == "all_offers_no_active")
        ]
        cheapest = min(candidates, key=lambda o: _offer_price(o) or Decimal("0"))
        min_price = _offer_price(cheapest)
        rec: dict[str, Any] = {
            "service_type": st,
            "price_unit": unit,
            "offers": stats["count"],
            "cheapest_price": stats["min"],
            "median_price": stats["median"],
            "max_price": stats["max"],
            "cheapest_provider": _offer_provider(cheapest),
        }
        if min_price is not None and ait_usd is not None:
            rec["cheapest_price_usd"] = str(min_price * ait_usd)
        recommendations.append(rec)
    recommendations.sort(key=lambda r: (r["service_type"], r["price_unit"]))

    per_1k = [r for r in recommendations if r["price_unit"] == "per_1k_tokens"]
    return {
        "model": "cost-optimization",
        "inputs": {
            "total_offers": aggregate["total_offers"],
            "priced_offers": aggregate["priced_offers"],
            "price_scope": aggregate["price_scope"],
            "tx_fee_ait": str(DEFAULT_TX_FEE_AIT),
            "tx_fee_source": "aitbc.utils.units.DEFAULT_TX_FEE_AIT (per-transaction, not per-token)",
            "ait_usd_price": str(ait_usd) if ait_usd is not None else None,
        },
        "cost_per_1k_tokens": per_1k,
        "recommendations": recommendations,
    }


def _warnings_from_sources(sources: dict[str, str]) -> list[str]:
    return [f"{name}: {err}" for name, err in sources.items() if err != "ok"]


def _require_live_source(ctx, sources: dict[str, str], what: str) -> None:
    """Abort when every probed source failed — partial data is fine, none is not."""
    if not any(v == "ok" for v in sources.values()):
        abort(ctx, f"No live {what} data available: " + "; ".join(_warnings_from_sources(sources)))


@click.group(
    epilog="""Examples:

  aitbc economics market

  aitbc economics propose --parameter tx_fee --current 0.001 --proposed 0.0005"""
)
def economics():
    """Economic intelligence, modeling, market analysis, and OpenClaw DAO proposals."""
    pass


@economics.command(
    epilog="""Examples:

  aitbc economics distributed

  aitbc economics distributed --cost-optimize"""
)
@click.option("--cost-optimize", is_flag=True, help="Enable cost optimization")
@click.pass_context
def distributed(ctx, cost_optimize):
    """Probe the live fleet's economic services and aggregate their status.

    Queries the configured coordinator API, market service, exchange
    order book, and blockchain RPC; unreachable sources are reported in
    ``sources`` rather than simulated.
    """
    try:
        config = get_config()
        api_key = ctx.obj.get("api_key") if ctx.obj else None
        sources: dict[str, str] = {}

        coordinator = _probe_coordinator(config, api_key, sources)
        offers, _offers_base = _fetch_market_offers(config, sources)
        orderbook = _exchange_orderbook(config, sources)
        chain = _fetch_chain_info(config, sources)

        _require_live_source(ctx, sources, "economics")

        totals: dict[str, Any] = {
            "market_offers": len(offers),
            "market_active_offers": sum(1 for o in offers if _is_active_offer(o)),
        }
        if orderbook:
            totals["orderbook_bids"] = orderbook["bids"]
            totals["orderbook_asks"] = orderbook["asks"]
        if chain:
            totals["chain_height"] = chain.get("height")
            consensus = chain.get("consensus") or {}
            totals["active_validators"] = consensus.get("active_validators")

        result: dict[str, Any] = {
            "action": "distributed_optimization",
            "cost_optimize": cost_optimize,
            "status": "live",
            "generated_at": datetime.now(UTC).isoformat(),
            "services": {
                "coordinator_api": coordinator,
                "market": {"offers": len(offers), "base": _offers_base},
                "exchange_orderbook": orderbook,
                "blockchain": chain,
            },
            "totals": totals,
            "sources": sources,
        }
        if cost_optimize:
            prices = _fetch_oracle_prices(config, api_key, sources)
            result["cost_optimization"] = _cost_optimization(offers, _ait_usd_price(prices))
        result["warnings"] = _warnings_from_sources(sources)
        output(result, ctx.obj.get("output_format", "table"), title="Distributed Economics")
    except _OPS_ERRORS as e:
        abort(ctx, f"Error in distributed economics: {e}", from_exception=e)


@economics.command(
    epilog="""Examples:

  aitbc economics model

  aitbc economics model --type cost-optimization"""
)
@click.option("--type", default="cost-optimization", help="Model type")
@click.pass_context
def model(ctx, type):
    """Run an economic model over live fleet data.

    Supported types: ``cost-optimization`` — cheapest/median offer prices per
    service type from the live market, plus the standard tx fee and the
    oracle AIT price when reachable.
    """
    if type not in _SUPPORTED_MODEL_TYPES:
        abort(
            ctx,
            f"Unknown model type '{type}'. Supported types: {', '.join(_SUPPORTED_MODEL_TYPES)}",
        )
    try:
        config = get_config()
        api_key = ctx.obj.get("api_key") if ctx.obj else None
        sources: dict[str, str] = {}

        offers, offers_base = _fetch_market_offers(config, sources)
        prices = _fetch_oracle_prices(config, api_key, sources)

        # The model is meaningless with zero live inputs; partial data is OK.
        _require_live_source(ctx, sources, "economic model")

        result: dict[str, Any] = {
            "action": "economic_modeling",
            "model_type": type,
            "status": "live",
            "generated_at": datetime.now(UTC).isoformat(),
            "market_base": offers_base,
            "sources": sources,
            "warnings": _warnings_from_sources(sources),
        }
        if type == "cost-optimization":
            result["model"] = _cost_optimization(offers, _ait_usd_price(prices))
        output(result, ctx.obj.get("output_format", "table"), title="Economic Model")
    except _OPS_ERRORS as e:
        abort(ctx, f"Error in economic modeling: {e}", from_exception=e)


@economics.command(
    epilog="""Examples:

  aitbc economics market

  aitbc economics market --output json"""
)
@click.pass_context
def market(ctx):
    """Aggregate live market data: offers, exchange order book, chain state.

    Queries the market service (``GET /v1/market/offer``), the exchange
    service (``GET /api/orders/orderbook``), and the blockchain RPC
    (``GET /rpc/info``). Unreachable sources are listed in ``sources``.
    """
    try:
        config = get_config()
        sources: dict[str, str] = {}

        offers, offers_base = _fetch_market_offers(config, sources)
        orderbook = _exchange_orderbook(config, sources)
        chain = _fetch_chain_info(config, sources)

        _require_live_source(ctx, sources, "market")

        result: dict[str, Any] = {
            "action": "market_analysis",
            "status": "live",
            "generated_at": datetime.now(UTC).isoformat(),
            "market_base": offers_base,
            "offers": _aggregate_offers(offers),
            "orderbook": orderbook,
            "chain": chain,
            "sources": sources,
            "warnings": _warnings_from_sources(sources),
        }
        output(result, ctx.obj.get("output_format", "table"), title="Market Economics")
    except _OPS_ERRORS as e:
        abort(ctx, f"Error in market analysis: {e}", from_exception=e)


@economics.command(
    epilog="""Examples:

  aitbc economics propose --parameter tx_fee --current 0.001 --proposed 0.0005

  aitbc economics propose --parameter block_reward --current 10 --proposed 12 --unit AIT"""
)
@click.option("--parameter", required=True, help="Economic parameter name")
@click.option("--current", required=True, help="Current parameter value")
@click.option("--proposed", required=True, help="Proposed parameter value")
@click.option("--unit", default="", help="Parameter unit")
@click.option("--proposer-id", default="cli-user", help="Proposer identifier")
@click.pass_context
def propose(ctx, parameter, current, proposed, unit, proposer_id):
    """Submit an OpenClaw DAO economic parameter proposal."""
    client = _api_client(ctx.obj.get("api_key") if ctx.obj else None)
    try:
        if client is None:
            result = {
                "action": "economic_proposal",
                "parameter": parameter,
                "current_value": current,
                "proposed_value": proposed,
                "unit": unit,
                "status": "simulated",
            }
        else:
            result = client.post(
                "/v1/economic-proposals",
                json={
                    "proposer_id": proposer_id,
                    "parameter_name": parameter,
                    "current_value": current,
                    "proposed_value": proposed,
                    "unit": unit,
                },
            )
        output(result, ctx.obj.get("output_format", "table"), title="Economic Proposal")
    except NetworkError as e:
        abort(ctx, f"Coordinator API error: {e}", from_exception=e)
    except _OPS_ERRORS as e:
        abort(ctx, f"Error submitting economic proposal: {e}", from_exception=e)


@economics.command(
    epilog="""Examples:

  aitbc economics vote --proposal-id prop-123 --vote for

  aitbc economics vote --proposal-id prop-123 --vote against --voting-power 10"""
)
@click.option("--proposal-id", "proposal_id", required=True, help="The Proposal-id.")
@click.option("--vote", type=click.Choice(["for", "against", "abstain"]), required=True, help="Vote choice")
@click.option("--voting-power", default=1.0, help="Voting power to apply")
@click.pass_context
def vote(ctx, proposal_id, vote, voting_power):
    """Vote for, against, or abstain on an OpenClaw DAO economic parameter proposal."""
    client = _api_client(ctx.obj.get("api_key") if ctx.obj else None)
    try:
        if client is None:
            result = {"action": "economic_vote", "proposal_id": proposal_id, "vote": vote, "status": "simulated"}
        else:
            result = client.post(
                f"/v1/economic-proposals/{proposal_id}/votes",
                json={"vote": vote, "voting_power": voting_power},
            )
        output(result, ctx.obj.get("output_format", "table"), title="Economic Vote")
    except NetworkError as e:
        abort(ctx, f"Coordinator API error: {e}", from_exception=e)
    except _OPS_ERRORS as e:
        abort(ctx, f"Error voting on proposal {proposal_id}: {e}", from_exception=e)


@economics.command(
    epilog="""Examples:

  aitbc economics status --proposal-id prop-123

  aitbc economics status --proposal-id prop-123 --output json"""
)
@click.option("--proposal-id", "proposal_id", required=True, help="The Proposal-id.")
@click.pass_context
def status(ctx, proposal_id):
    """Show the status of an OpenClaw DAO economic parameter proposal by proposal ID."""
    client = _api_client(ctx.obj.get("api_key") if ctx.obj else None)
    try:
        if client is None:
            result = {
                "action": "economic_status",
                "proposal_id": proposal_id,
                "status": "draft",
                "votes_for": 0,
                "votes_against": 0,
                "votes_abstain": 0,
            }
        else:
            result = client.get(f"/v1/economic-proposals/{proposal_id}")
        output(result, ctx.obj.get("output_format", "table"), title="Economic Proposal Status")
    except NetworkError as e:
        abort(ctx, f"Coordinator API error: {e}", from_exception=e)
    except _OPS_ERRORS as e:
        abort(ctx, f"Error fetching proposal {proposal_id}: {e}", from_exception=e)
