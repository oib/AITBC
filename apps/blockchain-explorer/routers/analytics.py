"""Analytics routes — activity timeline, network stats, top addresses, provider reputation, overview."""

import json
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

from aitbc.aitbc_logging import get_logger

from chain_client import BLOCKCHAIN_RPC_URLS, DEFAULT_CHAIN, USE_DATA_LAYER, get_data_layer

logger = get_logger(__name__)

router = APIRouter()


@router.get("/api/analytics/activity")
async def api_activity_timeline(
    chain_id: str | None = DEFAULT_CHAIN,
    days: int = 30,
) -> dict[str, Any]:
    """Get daily transaction counts for activity timeline chart"""
    try:
        import sqlite3
        from pathlib import Path

        chain_db_path = Path("/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db")
        if not chain_db_path.exists():
            chain_db_path = Path("/var/lib/aitbc/data/chain.db")

        if not chain_db_path.exists():
            return {"labels": [], "datasets": []}

        conn = sqlite3.connect(str(chain_db_path))
        cursor = conn.cursor()

        # Get daily transaction counts for the last N days
        cursor.execute(f"""
            SELECT DATE(created_at) as day, type, COUNT(*) as count
            FROM "transaction"
            WHERE created_at >= datetime('now', '-{days} days')
            GROUP BY DATE(created_at), type
            ORDER BY day
        """)

        # Organize by day and type
        data: dict[str, dict[str, int]] = {}
        tx_types: set[str] = set()
        for row in cursor.fetchall():
            day, tx_type, count = row
            if day not in data:
                data[day] = {}
            data[day][tx_type] = count
            tx_types.add(tx_type)

        conn.close()

        labels = sorted(data.keys())
        type_colors = {
            "TRANSFER": "#10b981",
            "GPU_MARKETPLACE": "#3b82f6",
            "ESCROW_RELEASE": "#8b5cf6",
            "FAUCET": "#f59e0b",
            "GPU_REGISTER": "#ef4444",
        }

        datasets = []
        for tx_type in sorted(tx_types):
            datasets.append(
                {
                    "label": tx_type,
                    "data": [data.get(day, {}).get(tx_type, 0) for day in labels],
                    "backgroundColor": type_colors.get(tx_type, "#6b7280"),
                }
            )

        return {"labels": labels, "datasets": datasets}
    except Exception as e:
        print(f"Error getting activity timeline: {e}")
        return {"labels": [], "datasets": []}


@router.get("/api/analytics/network-stats")
async def api_network_stats(chain_id: str | None = DEFAULT_CHAIN) -> dict[str, Any]:
    """Get aggregate network stats: total AIT, active offers, unique nodes/providers"""
    try:
        import sqlite3
        from pathlib import Path

        chain_db_path = Path("/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db")
        if not chain_db_path.exists():
            chain_db_path = Path("/var/lib/aitbc/data/chain.db")

        if not chain_db_path.exists():
            return {"total_ait": 0, "active_offers": 0, "unique_nodes": 0, "unique_providers": 0, "total_transactions": 0}

        conn = sqlite3.connect(str(chain_db_path))
        cursor = conn.cursor()

        # Total AIT from TRANSFER + GPU_MARKETPLACE transactions (sum of values)
        cursor.execute("""
            SELECT COALESCE(SUM(CAST(value AS REAL)), 0)
            FROM "transaction"
            WHERE type IN ('TRANSFER', 'GPU_MARKETPLACE')
        """)
        total_ait = cursor.fetchone()[0] or 0

        # Active offers (GPU_MARKETPLACE transactions)
        cursor.execute("""
            SELECT COUNT(DISTINCT tx_hash) FROM "transaction" WHERE type = 'GPU_MARKETPLACE'
        """)
        active_offers = cursor.fetchone()[0] or 0

        # Unique nodes (distinct senders)
        cursor.execute("""
            SELECT COUNT(DISTINCT sender) FROM "transaction"
        """)
        unique_nodes = cursor.fetchone()[0] or 0

        # Unique providers from GPU_MARKETPLACE payload
        cursor.execute("""
            SELECT payload FROM "transaction" WHERE type = 'GPU_MARKETPLACE'
        """)
        providers = set()
        for row in cursor.fetchall():
            try:
                payload = json.loads(row[0]) if row[0] else {}
                pid = payload.get("provider_node_id") or payload.get("node_id")
                if pid:
                    providers.add(pid)
            except Exception:
                pass
        unique_providers = len(providers)

        # Total transactions
        cursor.execute('SELECT COUNT(*) FROM "transaction"')
        total_transactions = cursor.fetchone()[0] or 0

        conn.close()
        return {
            "total_ait": round(total_ait, 2),
            "active_offers": active_offers,
            "unique_nodes": unique_nodes,
            "unique_providers": unique_providers,
            "total_transactions": total_transactions,
        }
    except Exception as e:
        print(f"Error getting network stats: {e}")
        return {"total_ait": 0, "active_offers": 0, "unique_nodes": 0, "unique_providers": 0, "total_transactions": 0}


@router.get("/api/analytics/top-addresses")
async def api_top_addresses(
    chain_id: str | None = DEFAULT_CHAIN,
    limit: int = 20,
) -> dict[str, Any]:
    """Get top addresses by transaction count and AIT volume"""
    try:
        import sqlite3
        from pathlib import Path

        chain_db_path = Path("/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db")
        if not chain_db_path.exists():
            chain_db_path = Path("/var/lib/aitbc/data/chain.db")

        if not chain_db_path.exists():
            return {"addresses": []}

        conn = sqlite3.connect(str(chain_db_path))
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                CASE WHEN sender = 'faucet' OR sender = '0x0000000000000000000000000000000000000000' THEN recipient ELSE sender END as addr,
                COUNT(*) as tx_count,
                COALESCE(SUM(CAST(value AS REAL)), 0) as volume
            FROM "transaction"
            WHERE sender != 'faucet' AND sender != '0x0000000000000000000000000000000000000000'
            GROUP BY addr
            ORDER BY tx_count DESC
            LIMIT ?
        """,
            (limit,),
        )

        addresses = []
        for row in cursor.fetchall():
            addr, tx_count, volume = row
            addresses.append(
                {
                    "address": addr,
                    "transaction_count": tx_count,
                    "volume": round(volume, 2),
                }
            )

        conn.close()
        return {"addresses": addresses}
    except Exception as e:
        print(f"Error getting top addresses: {e}")
        return {"addresses": []}


@router.get("/api/analytics/provider-reputation/{provider_id}")
async def api_provider_reputation(provider_id: str, chain_id: str | None = DEFAULT_CHAIN) -> dict[str, Any]:
    """Compute provider reputation score from blockchain history"""
    try:
        import sqlite3
        from pathlib import Path
        from datetime import datetime

        chain_db_path = Path("/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db")
        if not chain_db_path.exists():
            chain_db_path = Path("/var/lib/aitbc/data/chain.db")

        if not chain_db_path.exists():
            return {"provider_id": provider_id, "score": 0, "level": "New", "transactions": 0, "days_active": 0}

        conn = sqlite3.connect(str(chain_db_path))
        cursor = conn.cursor()

        # Find all transactions related to this provider
        cursor.execute(
            """
            SELECT type, value, created_at, payload
            FROM "transaction"
            WHERE sender = ? OR recipient = ?
            ORDER BY created_at ASC
        """,
            (provider_id, provider_id),
        )

        txs = cursor.fetchall()
        conn.close()

        gpu_offers = 0
        total_volume = 0.0
        first_tx_date = None
        confirmed_count = 0

        for tx in txs:
            tx_type, tx_value, created_at, payload = tx
            if first_tx_date is None:
                first_tx_date = created_at
            if tx_type == "GPU_MARKETPLACE":
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
                days_active = (datetime.utcnow() - first_dt).days
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
            "total_volume": round(total_volume, 2),
        }
    except Exception as e:
        print(f"Error getting provider reputation: {e}")
        return {"provider_id": provider_id, "score": 0, "level": "New", "transactions": 0, "days_active": 0}


@router.get("/api/analytics/overview")
async def analytics_overview(period: str = "24h") -> dict[str, Any]:
    """Get analytics overview from blockchain RPC"""
    try:
        if USE_DATA_LAYER:
            # Use data layer with toggle support
            data_layer = get_data_layer()
            rpc_url = BLOCKCHAIN_RPC_URLS.get(DEFAULT_CHAIN)
            return await data_layer.get_analytics_overview(period, rpc_url)  # type: ignore[no-any-return]
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
        raise HTTPException(status_code=503, detail=f"Blockchain RPC unavailable: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analytics failed: {str(e)}") from e
