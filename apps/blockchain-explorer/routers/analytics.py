"""Analytics routes — activity timeline, network stats, top addresses, provider reputation, overview."""

import hashlib
import json
from datetime import UTC, datetime
import os
from pathlib import Path
from typing import Any

import aiosqlite
import httpx
from fastapi import APIRouter, HTTPException

from aitbc.aitbc_logging import get_logger
from aitbc.utils.units import units_to_ait

from chain_client import BLOCKCHAIN_RPC_URLS, DEFAULT_CHAIN, USE_DATA_LAYER, get_data_layer

logger = get_logger(__name__)

router = APIRouter()


def _chain_db_path() -> Path | None:
    """Return the configured on-disk chain database, or None if it does not exist."""
    chain_db_path = Path(f"/var/lib/aitbc/data/{os.environ.get('CHAIN_ID', 'ait-localnet')}/chain.db")
    if not chain_db_path.exists():
        chain_db_path = Path("/var/lib/aitbc/data/chain.db")
    return chain_db_path if chain_db_path.exists() else None


def _activity_type_color(tx_type: str) -> str:
    """Stable distinct color for transaction types missing from the curated map."""
    hue = int(hashlib.sha256(tx_type.encode()).hexdigest()[:8], 16) % 360
    return f"hsl({hue}, 65%, 55%)"


@router.get("/api/analytics/activity")
async def api_activity_timeline(
    chain_id: str | None = DEFAULT_CHAIN,
    days: int = 30,
) -> dict[str, Any]:
    """Get daily transaction counts for activity timeline chart"""
    try:
        chain_db_path = _chain_db_path()
        if chain_db_path is None:
            return {"labels": [], "datasets": []}

        async with aiosqlite.connect(str(chain_db_path)) as conn:
            cursor = await conn.cursor()

            # Get daily transaction counts for the last N days
            await cursor.execute(
                """
                SELECT DATE(created_at) as day, type, COUNT(*) as count
                FROM "transaction"
                WHERE created_at >= datetime('now', ?)
                GROUP BY DATE(created_at), type
                ORDER BY day
                """,
                (f"-{int(days)} days",),
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
            "ESCROW_LOCK": "#c4b5fd",
            "ESCROW_REFUND": "#7c3aed",
            "ESCROW_RELEASE": "#8b5cf6",
            "EXCHANGE": "#84cc16",
            "GOVERNANCE_EXECUTE": "#d97706",
            "GOVERNANCE_PROPOSE": "#fbbf24",
            "GOVERNANCE_VOTE": "#f59e0b",
            "GPU_ALLOCATE": "#6366f1",
            "GPU_MARKET": "#3b82f6",
            "GPU_MARKETPLACE": "#60a5fa",
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
async def api_network_stats(chain_id: str | None = DEFAULT_CHAIN) -> dict[str, Any]:
    """Get aggregate network stats: total AIT, active offers, unique nodes/providers"""
    try:
        chain_db_path = _chain_db_path()
        if chain_db_path is None:
            return {"total_ait": 0, "active_offers": 0, "unique_nodes": 0, "unique_providers": 0, "total_transactions": 0}

        async with aiosqlite.connect(str(chain_db_path)) as conn:
            cursor = await conn.cursor()

            # Circulating supply: sum of account balances (base units -> AIT)
            await cursor.execute('SELECT COALESCE(SUM(balance), 0) FROM account')
            row = await cursor.fetchone()
            total_ait = float(units_to_ait((row[0] if row else 0) or 0))

            # Cumulative transfer volume, labeled as such (base units -> AIT)
            await cursor.execute("""
                SELECT COALESCE(SUM(CAST(value AS REAL)), 0)
                FROM "transaction"
                WHERE type IN ('TRANSFER', 'GPU_MARKET')
            """)
            row = await cursor.fetchone()
            # V23-46: fetchone() is Row | None. An aggregate always returns a row, but
            # only while the table exists -- otherwise this is a TypeError on None.
            transfer_volume = float(units_to_ait((row[0] if row else 0) or 0))

            # Anchored offers: distinct offer keys across all anchor tx types.
            # Software offers carry payload.offer_id; GPU registrations payload.gpu_id.
            await cursor.execute("""
                SELECT COUNT(DISTINCT COALESCE(
                    json_extract(payload, '$.offer_id'),
                    json_extract(payload, '$.gpu_id')))
                FROM "transaction"
                WHERE type IN ('GPU_MARKET', 'GPU_MARKETPLACE', 'GPU_REGISTER')
            """)
            row = await cursor.fetchone()
            active_offers = (row[0] if row else 0) or 0

            # Unique sender addresses
            await cursor.execute("""
                SELECT COUNT(DISTINCT sender) FROM "transaction"
            """)
            row = await cursor.fetchone()
            unique_nodes = (row[0] if row else 0) or 0

            # Unique providers across all offer anchor types
            await cursor.execute("""
                SELECT payload FROM "transaction"
                WHERE type IN ('GPU_MARKET', 'GPU_MARKETPLACE', 'GPU_REGISTER')
            """)
            providers = set()
            rows = await cursor.fetchall()
            for row in rows:
                try:
                    payload = json.loads(row[0]) if row[0] else {}
                    pid = (
                        payload.get("provider_node_id")
                        or payload.get("provider_address")
                        or payload.get("provider")
                        or payload.get("miner_id")
                        or payload.get("node_id")
                    )
                    if pid:
                        providers.add(pid)
                except Exception:
                    pass
            unique_providers = len(providers)

            # Total transactions
            await cursor.execute('SELECT COUNT(*) FROM "transaction"')
            row = await cursor.fetchone()
            total_transactions = (row[0] if row else 0) or 0

        return {
            "total_ait": round(total_ait, 2),
            "transfer_volume_ait": round(transfer_volume, 2),
            "active_offers": active_offers,
            "unique_nodes": unique_nodes,
            "unique_providers": unique_providers,
            "total_transactions": total_transactions,
        }
    except Exception:
        logger.exception("Error getting network stats")
        return {"total_ait": 0, "active_offers": 0, "unique_nodes": 0, "unique_providers": 0, "total_transactions": 0}


@router.get("/api/analytics/top-addresses")
async def api_top_addresses(
    chain_id: str | None = DEFAULT_CHAIN,
    limit: int = 20,
) -> dict[str, Any]:
    """Get top addresses by transaction count and AIT volume"""
    try:
        chain_db_path = _chain_db_path()
        if chain_db_path is None:
            return {"addresses": []}

        async with aiosqlite.connect(str(chain_db_path)) as conn:
            cursor = await conn.cursor()

            await cursor.execute(
                """
                SELECT
                    CASE WHEN sender IN ('bridge_release', 'bridge_refund') OR sender = '0x0000000000000000000000000000000000000000' THEN recipient ELSE sender END as addr,
                    COUNT(*) as tx_count,
                    COALESCE(SUM(CAST(value AS REAL)), 0) as volume
                FROM "transaction"
                WHERE sender NOT IN ('bridge_release', 'bridge_refund') AND sender != '0x0000000000000000000000000000000000000000'
                GROUP BY addr
                ORDER BY tx_count DESC
                LIMIT ?
            """,
                (limit,),
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
async def api_provider_reputation(provider_id: str, chain_id: str | None = DEFAULT_CHAIN) -> dict[str, Any]:
    """Compute provider reputation score from blockchain history"""
    try:
        chain_db_path = _chain_db_path()
        if chain_db_path is None:
            return {"provider_id": provider_id, "score": 0, "level": "New", "transactions": 0, "days_active": 0}

        async with aiosqlite.connect(str(chain_db_path)) as conn:
            cursor = await conn.cursor()

            # Find all transactions related to this provider
            await cursor.execute(
                """
                SELECT type, value, created_at, payload
                FROM "transaction"
                WHERE sender = ? OR recipient = ?
                ORDER BY created_at ASC
            """,
                (provider_id, provider_id),
            )

            txs = await cursor.fetchall()

        gpu_offers = 0
        total_volume = 0.0
        first_tx_date = None
        confirmed_count = 0

        for tx in txs:
            tx_type, tx_value, created_at, payload = tx
            if first_tx_date is None:
                first_tx_date = created_at
            if tx_type == "GPU_MARKET":
                gpu_offers += 1
            try:
                total_volume += float(tx_value or 0)
            except Exception:
                pass
            confirmed_count += 1

        days_active = 0
        if first_tx_date:
            try:
                first_dt = datetime.strptime(first_tx_date, "%Y-%m-%d %H:%M:%S")
                days_active = (datetime.now(UTC).replace(tzinfo=None) - first_dt).days
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
            rpc_url = BLOCKCHAIN_RPC_URLS.get(DEFAULT_CHAIN)
            return await data_layer.get_analytics_overview(period, rpc_url)
        else:
            # Original implementation without data layer
            rpc_url = BLOCKCHAIN_RPC_URLS.get(DEFAULT_CHAIN)
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
    except Exception as e:
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e
