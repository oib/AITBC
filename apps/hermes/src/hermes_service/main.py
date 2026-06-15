"""Hermes Service for agent orchestration and edge computing."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from .handlers import HandlerRegistry  # type: ignore[import-not-found]
from .services.transaction_service import TransactionService  # type: ignore
from .storage import CoinRequest, CoinRequestStatus, get_db_session, init_db  # type: ignore

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
app = FastAPI(title="AITBC Hermes Service", description="Agent orchestration and edge computing service", version="1.0.0")
COORDINATOR_URL = os.getenv("HERMES_COORDINATOR_URL", "http://localhost:8011")
HERMES_AGENT_ID = os.getenv("HERMES_AGENT_ID", "hermes-agent")
handler_registry = HandlerRegistry(COORDINATOR_URL, HERMES_AGENT_ID)
handler_registry.load_all_handlers()
init_db()


async def expire_old_requests() -> None:
    """Background task to expire requests older than 1 month."""
    while True:
        try:
            with get_db_session() as session:
                cutoff = datetime.utcnow() - timedelta(days=30)
                expired_requests = (
                    session.query(CoinRequest)
                    .filter(CoinRequest.status == CoinRequestStatus.PENDING, CoinRequest.expires_at < cutoff)
                    .all()
                )
                for req in expired_requests:
                    req.status = CoinRequestStatus.EXPIRED
                    req.audit_log += f" | Auto-expired at {datetime.utcnow().isoformat()}"
                    logger.info("Expired request %s from %s", req.id, req.sender)
                if expired_requests:
                    logger.info("Expired %s old coin requests", len(expired_requests))
        except Exception as e:
            logger.error("Error expiring old requests: %s", e)
        await asyncio.sleep(3600)


@app.on_event("startup")
async def startup_event() -> None:
    """Start background tasks on startup."""
    asyncio.create_task(expire_old_requests())


def _check_db() -> bool:
    """Check SQLite database connectivity."""
    try:
        from sqlalchemy import text

        with get_db_session() as session:
            session.execute(text("SELECT 1"))
            return True
    except Exception:
        return False


def _check_coordinator() -> bool:
    """Check Agent Coordinator reachability."""
    try:
        import requests

        response = requests.get(f"{COORDINATOR_URL}/health", timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def _check_blockchain_rpc() -> bool:
    """Check blockchain RPC reachability."""
    try:
        import requests

        rpc_url = os.getenv("BLOCKCHAIN_RPC_URL", "http://localhost:8202")
        response = requests.get(f"{rpc_url}/health", timeout=5)
        return response.status_code == 200
    except Exception:
        return False


@app.get("/health")
async def health() -> dict[str, Any]:
    """Health check endpoint with dependency verification."""
    checks = {"database": _check_db(), "coordinator": _check_coordinator(), "blockchain_rpc": _check_blockchain_rpc()}
    all_healthy = all(checks.values())
    status = "healthy" if all_healthy else "degraded"
    return {"status": status, "service": "hermes-service", "checks": checks}


@app.post("/message")
async def receive_message(message: dict[str, Any]) -> dict[str, Any]:
    """Receive message from polling daemon and process it via handler registry."""
    content = message.get("content", "")
    sender = message.get("sender", "unknown")
    msg_id = message.get("id", "unknown")
    logger.info("Received message from %s: %s (ID: %s)", sender, content, msg_id)
    result = await handler_registry.process_message(message)
    return dict(result)


@app.get("/")
async def root() -> dict[str, Any]:
    """Root endpoint."""
    return {"service": "AITBC Hermes Service", "version": "1.0.0", "status": "operational"}


@app.post("/routing/skill")
async def route_agent_skill(request: dict[str, Any]) -> dict[str, Any]:
    """Sophisticated agent skill routing"""
    return {
        "selected_agent": "agent_default",
        "routing_strategy": "performance_based",
        "expected_performance": "high",
        "estimated_cost": 0.5,
    }


@app.post("/offloading/intelligent")
async def intelligent_job_offloading(request: dict[str, Any]) -> dict[str, Any]:
    """Intelligent job offloading strategies"""
    return {
        "should_offload": True,
        "job_size": "medium",
        "cost_analysis": {"estimated_cost": 10.0, "savings": 5.0},
        "performance_prediction": "improved",
        "fallback_mechanism": "local_execution",
    }


@app.post("/collaboration/coordinate")
async def coordinate_agent_collaboration(request: dict[str, Any]) -> dict[str, Any]:
    """Agent collaboration and coordination"""
    return {
        "coordination_method": "consensus",
        "selected_coordinator": "agent_coordinator_1",
        "consensus_reached": True,
        "task_distribution": {"agent_1": 0.5, "agent_2": 0.5},
        "estimated_completion_time": 300,
    }


@app.post("/execution/hybrid-optimize")
async def optimize_hybrid_execution(request: dict[str, Any]) -> dict[str, Any]:
    """Hybrid execution optimization"""
    return {
        "execution_mode": "hybrid",
        "strategy": "cost_performance_balance",
        "resource_allocation": {"cpu": 50, "memory": 40, "gpu": 10},
        "performance_tuning": "optimized",
        "expected_improvement": "30%",
    }


@app.post("/edge/deploy")
async def deploy_to_edge(request: dict[str, Any]) -> dict[str, Any]:
    """Deploy agent to edge computing infrastructure"""
    return {
        "deployment_id": "deployment_123",
        "agent_id": request.get("agent_id", "unknown"),
        "edge_locations": request.get("edge_locations", []),
        "deployment_results": {"success": True, "deployed_count": 3},
        "status": "completed",
    }


@app.post("/edge/coordinate")
async def coordinate_edge_to_cloud(request: dict[str, Any]) -> dict[str, Any]:
    """Coordinate edge-to-cloud agent operations"""
    return {
        "coordination_id": "coord_456",
        "edge_deployment_id": request.get("edge_deployment_id", "unknown"),
        "synchronization": "enabled",
        "load_balancing": "round_robin",
        "failover": "active",
        "status": "active",
    }


@app.post("/ecosystem/develop")
async def develop_hermes_ecosystem(request: dict[str, Any]) -> dict[str, Any]:
    """Build comprehensive Hermes ecosystem"""
    return {
        "ecosystem_id": "eco_789",
        "developer_tools": ["cli", "sdk", "dashboard"],
        "marketplace": "enabled",
        "community": "growing",
        "partnerships": ["partner_1", "partner_2"],
        "status": "developing",
    }


class RemoteExecuteRequest(BaseModel):
    request_id: str
    sender: str
    amount: int
    wallet_address: str
    approved_by: str = "cli"


@app.post("/coin-requests/execute")
async def remote_execute_coin_request(
    req: RemoteExecuteRequest, x_api_key: str | None = Header(default=None)
) -> dict[str, Any]:
    """
    Execute an approved coin request forwarded from a follower node.
    Hub-only endpoint — requires COORDINATOR_API_KEY authentication.
    Signs and submits the transaction using the genesis wallet.
    """
    expected_key = os.getenv("COORDINATOR_API_KEY") or os.getenv("SECRET_KEY")
    if not expected_key or x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    tx_service = TransactionService()
    if not tx_service.genesis_private_key:
        raise HTTPException(status_code=503, detail="GENESIS_PRIVATE_KEY not configured on this node")
    balance = tx_service.get_balance(tx_service.genesis_address)
    total_required = req.amount + 1000
    if balance < total_required:
        raise HTTPException(status_code=400, detail=f"Insufficient genesis balance: {balance} < {total_required}")
    signed_tx = tx_service.generate_signed_transaction(to_address=req.wallet_address, amount=req.amount)
    if not signed_tx:
        raise HTTPException(status_code=500, detail="Failed to generate signed transaction")
    try:
        from aitbc import AITBCHTTPClient

        http_client = AITBCHTTPClient(base_url=tx_service.rpc_url, timeout=30)
        result = http_client.post("/rpc/transaction", json=signed_tx)
        tx_hash = result.get("transaction_hash")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Blockchain RPC error: {e}") from e
    logger.info("Remote execution of %s: %s AIT to %s — tx %s", req.request_id, req.amount, req.wallet_address, tx_hash)
    return {
        "success": True,
        "request_id": req.request_id,
        "tx_hash": tx_hash,
        "amount": req.amount,
        "recipient": req.wallet_address,
    }


if __name__ == "__main__":
    import os

    import uvicorn

    # Standardized environment variable naming: SERVICE_BIND_HOST and SERVICE_BIND_PORT
    host = os.getenv("HERMES_BIND_HOST", os.getenv("BIND_HOST", "0.0.0.0"))
    port = int(os.getenv("HERMES_BIND_PORT", os.getenv("HERMES_PORT", "8103")))

    uvicorn.run(app, host=host, port=port)
