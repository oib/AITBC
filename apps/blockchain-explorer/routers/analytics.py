"""Analytics routes — activity timeline, network stats, top addresses, provider reputation, overview."""

import hashlib
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

from aitbc.aitbc_logging import get_logger
from aitbc.utils.units import units_to_ait

from chain_client import (
    USE_DATA_LAYER,
    chain_db_connect,
    chain_db_path,
    chain_scope,
    default_chain_id,
    get_data_layer,
    rpc_url_for,
    scoped_where,
)
from validation import clamp_analytics_days, clamp_page_limit

logger = get_logger(__name__)

router = APIRouter()


def _activity_type_color(tx_type: str) -> str:
    """Stable distinct color for transaction types missing from the curated map."""
    hue = int(hashlib.sha256(tx_type.encode()).hexdigest()[:8], 16) % 360
    return f"hsl({hue}, 65%, 55%)"


@router.get("/api/analytics/activity")
async def api_activity_timeline(
    chain_id: str | None = None,
    days: int = 30,
) -> dict[str, Any]:
    """Get daily transaction counts for activity timeline chart"""
    days = clamp_analytics_days(days)
    try:
        cid = chain_id or default_chain_id()
        db_path = chain_db_path()
        if db_path is None:
            return {"labels": [], "datasets": []}

        async with chain_db_connect(db_path) as conn:
            cursor = await conn.cursor()

            # Get daily transaction counts for the last N days — scoped to
            # the requested chain (#1620).
            scope_sql, scope_params = await chain_scope(conn, "transaction", cid)
            where, params = scoped_where("created_at >= datetime('now', ?)", scope_sql, [f"-{int(days)} days"], scope_params)
            await cursor.execute(
                f"""
                SELECT DATE(created_at) as day, type, COUNT(*) as count
                FROM "transaction"
                WHERE {where}
                GROUP BY DATE(created_at), type
                ORDER BY day
                """,
                params,
            )

            # Organize by day and type
            data: dict[str, dict[str, int]] = {}
            tx_types: set[str] = set()
            rows = await cursor.fetchall()
            for row in rows:
                day, tx_type, count = row
                if day not in data:
                    data[day] = {}
                data[day][tx_type] = count
                tx_types.add(tx_type)

        labels = sorted(data.keys())
        type_colors = {
            "BRIDGE_LOCK": "#22d3ee",
            "BRIDGE_RELEASE": "#06b6d4",
            "BRIDGE_REFUND": "#0891b2",
            "ESCROW_FEE_SWEEP": "#a855f7",
            "ESCROW_LOCK": "#c4b5fd",
            "ESCROW_REFUND": "#7c3aed",
            "ESCROW_RELEASE": "#8b5cf6",
            "EXCHANGE": "#84cc16",
            "GOVERNANCE_EXECUTE": "#d97706",
            "GOVERNANCE_PROPOSE": "#fbbf24",
            "GOVERNANCE_VOTE": "#f59e0b",
            "GPU_ALLOCATE": "#6366f1",
            "GPU_DEREGISTER": "#f97316",
            "GPU_MARKET": "#3b82f6",
            "GPU_REGISTER": "#ef4444",
            "IPFS_SUBSCRIPTION": "#14b8a6",
            "STAKE_LOCK": "#fb7185",
            "STAKE_RELEASE": "#f43f5e",
            "TRANSFER": "#10b981",
        }

        datasets = []
        for tx_type in sorted(tx_types):
            datasets.append(
                {
                    "label": tx_type,
                    "data": [data.get(day, {}).get(tx_type, 0) for day in labels],
                    "backgroundColor": type_colors.get(tx_type) or _activity_type_color(tx_type),
                }
            )

        return {"labels": labels, "datasets": datasets}
    except Exception:
        logger.exception("Error getting activity timeline")
        return {"labels": [], "datasets": []}


@router.get("/api/analytics/network-stats")
async def api_network_stats(chain_id: str | None = None) -> dict[str, Any]:
    """Aggregate network stats: total AIT, transfer volume, distinct offers
    ever anchored on chain, unique nodes/providers, total transactions.

    A chain database that is missing or unreadable answers 503 — a failed
    read must never look like an empty chain.
    """
    try:
        cid = chain_id or default_chain_id()
        db_path = chain_db_path()
        if db_path is None:
            raise HTTPException(status_code=503, detail="chain database unavailable")
        async with chain_db_connect(db_path) as conn:
            cursor = await conn.cursor()

            # Every aggregate below is chain-scoped (#1620) and computed in
            # SQL (#1621) — no unbounded row fetches.
            acct_scope, acct_scope_params = await chain_scope(conn, "account", cid)
            acct_where, acct_params = scoped_where("", acct_scope, [], acct_scope_params)
            acct_clause = f"WHERE {acct_where}" if acct_where else ""

            # Circulating supply: sum of account balances (base units -> AIT)
            await cursor.execute(f"SELECT COALESCE(SUM(balance), 0) FROM account {acct_clause}", acct_params)
            row = await cursor.fetchone()
            total_ait = float(units_to_ait((row[0] if row else 0) or 0))

            tx_scope, tx_scope_params = await chain_scope(conn, "transaction", cid)

            # Cumulative transfer volume, labeled as such (base units -> AIT)
            where, params = scoped_where("type IN ('TRANSFER', 'GPU_MARKET')", tx_scope, [], tx_scope_params)
            await cursor.execute(
                f"""
                SELECT COALESCE(SUM(CAST(value AS REAL)), 0)
                FROM "transaction"
                WHERE {where}
            """,
                params,
            )
            row = await cursor.fetchone()
            # V23-46: fetchone() is Row | None. An aggregate always returns a row, but
            # only while the table exists -- otherwise this is a TypeError on None.
            transfer_volume = float(units_to_ait((row[0] if row else 0) or 0))

            # Anchored offers: distinct offer keys across all anchor tx types.
            # Software offers carry payload.offer_id; GPU registrations payload.gpu_id.
            where, params = scoped_where("type IN ('GPU_MARKET', 'GPU_REGISTER')", tx_scope, [], tx_scope_params)
            await cursor.execute(
                f"""
                SELECT COUNT(DISTINCT COALESCE(
                    json_extract(payload, '$.offer_id'),
                    json_extract(payload, '$.gpu_id')))
                FROM "transaction"
                WHERE {where}
            """,
                params,
            )
            row = await cursor.fetchone()
            anchored_offers = (row[0] if row else 0) or 0

            # Unique sender addresses
            where, params = scoped_where("", tx_scope, [], tx_scope_params)
            all_tx_clause = f"WHERE {where}" if where else ""
            all_tx_params = list(params)
            await cursor.execute(f'SELECT COUNT(DISTINCT sender) FROM "transaction" {all_tx_clause}', all_tx_params)
            row = await cursor.fetchone()
            unique_nodes = (row[0] if row else 0) or 0

            # Unique providers across all offer anchor types. Previously this
            # fetched every GPU_MARKET/GPU_REGISTER payload and extracted the
            # provider key in Python — unbounded (#1621). The same COALESCE
            # key order now runs in SQL: json_valid keeps malformed payloads
            # out (the Python path skipped them via try/except), and the
            # double NULLIF reproduces the `or`-chain's falsy skip for ''/0.
            where, params = scoped_where(
                "type IN ('GPU_MARKET', 'GPU_REGISTER') AND json_valid(payload)",
                tx_scope,
                [],
                tx_scope_params,
            )
            await cursor.execute(
                f"""
                SELECT COUNT(DISTINCT pid) FROM (
                    SELECT COALESCE(
                        NULLIF(NULLIF(json_extract(payload, '$.provider_node_id'), ''), 0),
                        NULLIF(NULLIF(json_extract(payload, '$.provider_address'), ''), 0),
                        NULLIF(NULLIF(json_extract(payload, '$.provider'), ''), 0),
                        NULLIF(NULLIF(json_extract(payload, '$.miner_id'), ''), 0),
                        NULLIF(NULLIF(json_extract(payload, '$.node_id'), ''), 0)
                    ) AS pid
                    FROM "transaction"
                    WHERE {where}
                )
                WHERE pid IS NOT NULL
            """,
                params,
            )
            row = await cursor.fetchone()
            unique_providers = (row[0] if row else 0) or 0

            # Total transactions
            await cursor.execute(f'SELECT COUNT(*) FROM "transaction" {all_tx_clause}', all_tx_params)
            row = await cursor.fetchone()
            total_transactions = (row[0] if row else 0) or 0

        return {
            "total_ait": round(total_ait, 2),
            "transfer_volume_ait": round(transfer_volume, 2),
            "anchored_offers": anchored_offers,
            # Deprecated alias of anchored_offers, kept so existing readers
            # do not break. Removal condition: the website reads
            # anchored_offers (WEB-ANCHORED-1 live) and the CLI/MCP docs
            # name the new field.
            "active_offers": anchored_offers,
            "unique_nodes": unique_nodes,
            "unique_providers": unique_providers,
            "total_transactions": total_transactions,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error getting network stats")
        raise HTTPException(status_code=503, detail="network stats unavailable") from e


@router.get("/api/analytics/top-addresses")
async def api_top_addresses(
    chain_id: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Get top addresses by transaction count and AIT volume"""
    limit = clamp_page_limit(limit)
    try:
        cid = chain_id or default_chain_id()
        db_path = chain_db_path()
        if db_path is None:
            return {"addresses": []}

        async with chain_db_connect(db_path) as conn:
            cursor = await conn.cursor()

            scope_sql, scope_params = await chain_scope(conn, "transaction", cid)
            where, params = scoped_where(
                "sender NOT IN ('bridge_release', 'bridge_refund') AND sender != '0x0000000000000000000000000000000000000000'",
                scope_sql,
                [],
                scope_params,
            )
            params = [*params, limit]
            await cursor.execute(
                f"""
                SELECT
                    CASE WHEN sender IN ('bridge_release', 'bridge_refund') OR sender = '0x0000000000000000000000000000000000000000' THEN recipient ELSE sender END as addr,
                    COUNT(*) as tx_count,
                    COALESCE(SUM(CAST(value AS REAL)), 0) as volume
                FROM "transaction"
                WHERE {where}
                GROUP BY addr
                ORDER BY tx_count DESC
                LIMIT ?
            """,
                params,
            )

            addresses = []
            rows = await cursor.fetchall()
            for row in rows:
                addr, tx_count, volume = row
                addresses.append(
                    {
                        "address": addr,
                        "transaction_count": tx_count,
                        # transaction.value is in base units; the column header
                        # says "Volume (AIT)", so convert here.
                        "volume": round(float(units_to_ait(volume or 0)), 2),
                    }
                )

        return {"addresses": addresses}
    except Exception:
        logger.exception("Error getting top addresses")
        return {"addresses": []}


@router.get("/api/analytics/provider-reputation/{provider_id}")
async def api_provider_reputation(provider_id: str, chain_id: str | None = None) -> dict[str, Any]:
    """Compute provider reputation score from blockchain history"""
    try:
        cid = chain_id or default_chain_id()
        db_path = chain_db_path()
        if db_path is None:
            return {"provider_id": provider_id, "score": 0, "level": "New", "transactions": 0, "days_active": 0}

        async with chain_db_connect(db_path) as conn:
            cursor = await conn.cursor()

            # All reputation inputs are aggregates — COUNT/SUM/MIN run in SQL
            # instead of fetching every transaction for the address
            # unbounded (#1621), and the read is chain-scoped (#1620). The
            # OR-group keeps sender/recipient matching unambiguous.
            scope_sql, scope_params = await chain_scope(conn, "transaction", cid)
            where, params = scoped_where("(sender = ? OR recipient = ?)", scope_sql, [provider_id, provider_id], scope_params)
            await cursor.execute(
                f"""
                SELECT COUNT(*),
                       COALESCE(SUM(CASE WHEN type = 'GPU_MARKET' THEN 1 ELSE 0 END), 0),
                       COALESCE(SUM(CAST(value AS REAL)), 0),
                       MIN(created_at)
                FROM "transaction"
                WHERE {where}
            """,
                params,
            )

            row = await cursor.fetchone()

        # fetchone() is Row | None; the aggregate always returns a row while
        # the table exists (same V23-46 caveat as network-stats).
        confirmed_count = int(row[0] or 0) if row else 0
        gpu_offers = int(row[1] or 0) if row else 0
        total_volume = float(row[2] or 0.0) if row else 0.0
        first_tx_date = row[3] if row else None

        days_active = 0
        if first_tx_date:
            try:
                # created_at is ISO-8601 ("YYYY-MM-DD[T ]HH:MM:SS[.ffffff]");
                # strptime("%Y-%m-%d %H:%M:%S") never matched the 'T' separator or
                # microseconds, so days_active silently stayed 0.
                first_dt = datetime.fromisoformat(str(first_tx_date).replace("Z", "+00:00"))
                if first_dt.tzinfo is not None:
                    first_dt = first_dt.astimezone(UTC).replace(tzinfo=None)
                days_active = max(0, (datetime.now(UTC).replace(tzinfo=None) - first_dt).days)
            except Exception:
                pass

        # Simple reputation formula
        score = min(100, 10 + (gpu_offers * 15) + (days_active * 2) + (confirmed_count * 5))
        level = "New"
        if score >= 80:
            level = "Elite"
        elif score >= 60:
            level = "Trusted"
        elif score >= 40:
            level = "Established"
        elif score >= 20:
            level = "Growing"

        return {
            "provider_id": provider_id,
            "score": score,
            "level": level,
            "transactions": confirmed_count,
            "gpu_offers": gpu_offers,
            "days_active": days_active,
            # tx values are base units; report the volume in AIT.
            "total_volume": round(float(units_to_ait(total_volume)), 2),
        }
    except Exception:
        logger.exception("Error getting provider reputation: %s", provider_id)
        return {"provider_id": provider_id, "score": 0, "level": "New", "transactions": 0, "days_active": 0}


@router.get("/api/analytics/overview")
async def analytics_overview(period: str = "24h") -> dict[str, Any]:
    """Get analytics overview from blockchain RPC"""
    try:
        if USE_DATA_LAYER:
            # Use data layer with toggle support
            data_layer = get_data_layer()
            rpc_url = rpc_url_for(default_chain_id())
            return await data_layer.get_analytics_overview(period, rpc_url)
        else:
            # Original implementation without data layer
            rpc_url = rpc_url_for(default_chain_id())
            params = {"period": period}

            async with httpx.AsyncClient() as client:
                response = await client.get(f"{rpc_url}/rpc/analytics/overview", params=params)
                if response.status_code == 200:
                    return response.json()  # type: ignore[no-any-return]
                elif response.status_code == 404:
                    raise HTTPException(status_code=501, detail="Analytics endpoint not available on blockchain RPC")
                else:
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Failed to fetch analytics from blockchain RPC: {response.text}",
                    )
    except httpx.RequestError as e:
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=503, detail="Internal server error") from e
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e
