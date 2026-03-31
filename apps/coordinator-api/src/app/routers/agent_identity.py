"""
Agent Identity API Router
REST API endpoints for agent identity management and cross-chain operations
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from ..agent_identity.manager import AgentIdentityManager
from ..domain.agent_identity import (
    CrossChainMappingResponse,
    IdentityStatus,
    VerificationType,
)
from ..storage.db import get_session

router = APIRouter(prefix="/agent-identity", tags=["Agent Identity"])


def get_identity_manager(session=Depends(get_session)) -> AgentIdentityManager:
    """Dependency injection for AgentIdentityManager"""
    return AgentIdentityManager(session)


# Identity Management Endpoints


@router.post("/identities", response_model=dict[str, Any])
async def create_agent_identity(request: dict[str, Any], manager: AgentIdentityManager = Depends(get_identity_manager)):
    """Create a new agent identity with cross-chain mappings"""
    try:
        result = await manager.create_agent_identity(
            owner_address=request["owner_address"],
            chains=request["chains"],
            display_name=request.get("display_name", ""),
            description=request.get("description", ""),
            metadata=request.get("metadata"),
            tags=request.get("tags"),
        )
        return JSONResponse(content=result, status_code=201)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/identities/{agent_id}", response_model=dict[str, Any])
async def get_agent_identity(agent_id: str, manager: AgentIdentityManager = Depends(get_identity_manager)):
    """Get comprehensive agent identity summary"""
    try:
        result = await manager.get_agent_identity_summary(agent_id)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/identities/{agent_id}", response_model=dict[str, Any])
async def update_agent_identity(
    agent_id: str, request: dict[str, Any], manager: AgentIdentityManager = Depends(get_identity_manager)
):
    """Update agent identity and related components"""
    try:
        result = await manager.update_agent_identity(agent_id, request)
        if not result.get("update_successful", True):
            raise HTTPException(status_code=400, detail=result.get("error", "Update failed"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/identities/{agent_id}/deactivate", response_model=dict[str, Any])
async def deactivate_agent_identity(
    agent_id: str, request: dict[str, Any], manager: AgentIdentityManager = Depends(get_identity_manager)
):
    """Deactivate an agent identity across all chains"""
    try:
        reason = request.get("reason", "")
        success = await manager.deactivate_agent_identity(agent_id, reason)
        if not success:
            raise HTTPException(status_code=400, detail="Deactivation failed")
        return {"agent_id": agent_id, "deactivated": True, "reason": reason, "timestamp": datetime.utcnow().isoformat()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Cross-Chain Mapping Endpoints


@router.post("/identities/{agent_id}/cross-chain/register", response_model=dict[str, Any])
async def register_cross_chain_identity(
    agent_id: str, request: dict[str, Any], manager: AgentIdentityManager = Depends(get_identity_manager)
):
    """Register cross-chain identity mappings"""
    try:
        chain_mappings = request["chain_mappings"]
        verifier_address = request.get("verifier_address")
        verification_type = VerificationType(request.get("verification_type", "basic"))

        # Use registry directly for this operation
        result = await manager.registry.register_cross_chain_identity(
            agent_id, chain_mappings, verifier_address, verification_type
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/identities/{agent_id}/cross-chain/mapping", response_model=list[CrossChainMappingResponse])
async def get_cross_chain_mapping(agent_id: str, manager: AgentIdentityManager = Depends(get_identity_manager)):
    """Get all cross-chain mappings for an agent"""
    try:
        mappings = await manager.registry.get_all_cross_chain_mappings(agent_id)
        return [
            CrossChainMappingResponse(
                id=m.id,
                agent_id=m.agent_id,
                chain_id=m.chain_id,
                chain_type=m.chain_type,
                chain_address=m.chain_address,
                is_verified=m.is_verified,
                verified_at=m.verified_at,
                wallet_address=m.wallet_address,
                wallet_type=m.wallet_type,
                chain_metadata=m.chain_metadata,
                last_transaction=m.last_transaction,
                transaction_count=m.transaction_count,
                created_at=m.created_at,
                updated_at=m.updated_at,
            )
            for m in mappings
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/identities/{agent_id}/cross-chain/{chain_id}", response_model=dict[str, Any])
async def update_cross_chain_mapping(
    agent_id: str, chain_id: int, request: dict[str, Any], manager: AgentIdentityManager = Depends(get_identity_manager)
):
    """Update cross-chain mapping for a specific chain"""
    try:
        new_address = request.get("new_address")
        verifier_address = request.get("verifier_address")

        if not new_address:
            raise HTTPException(status_code=400, detail="new_address is required")

        success = await manager.registry.update_identity_mapping(agent_id, chain_id, new_address, verifier_address)

        if not success:
            raise HTTPException(status_code=400, detail="Update failed")

        return {
            "agent_id": agent_id,
            "chain_id": chain_id,
            "new_address": new_address,
            "updated": True,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/identities/{agent_id}/cross-chain/{chain_id}/verify", response_model=dict[str, Any])
async def verify_cross_chain_identity(
    agent_id: str, chain_id: int, request: dict[str, Any], manager: AgentIdentityManager = Depends(get_identity_manager)
):
    """Verify identity on a specific blockchain"""
    try:
        # Get identity ID
        identity = await manager.core.get_identity_by_agent_id(agent_id)
        if not identity:
            raise HTTPException(status_code=404, detail="Agent identity not found")

        verification = await manager.registry.verify_cross_chain_identity(
            identity.id,
            chain_id,
            request["verifier_address"],
            request["proof_hash"],
            request.get("proof_data", {}),
            VerificationType(request.get("verification_type", "basic")),
        )

        return {
            "verification_id": verification.id,
            "agent_id": agent_id,
            "chain_id": chain_id,
            "verification_type": verification.verification_type,
            "verified": True,
            "timestamp": verification.created_at.isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/identities/{agent_id}/migrate", response_model=dict[str, Any])
async def migrate_agent_identity(
    agent_id: str, request: dict[str, Any], manager: AgentIdentityManager = Depends(get_identity_manager)
):
    """Migrate agent identity from one chain to another"""
    try:
        result = await manager.migrate_agent_identity(
            agent_id, request["from_chain"], request["to_chain"], request["new_address"], request.get("verifier_address")
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# Wallet Management Endpoints


@router.post("/identities/{agent_id}/wallets", response_model=dict[str, Any])
async def create_agent_wallet(
    agent_id: str, request: dict[str, Any], manager: AgentIdentityManager = Depends(get_identity_manager)
):
    """Create an agent wallet on a specific blockchain"""
    try:
        wallet = await manager.wallet_adapter.create_agent_wallet(
            agent_id, request["chain_id"], request.get("owner_address", "")
        )

        return {
            "wallet_id": wallet.id,
            "agent_id": agent_id,
            "chain_id": wallet.chain_id,
            "chain_address": wallet.chain_address,
            "wallet_type": wallet.wallet_type,
            "contract_address": wallet.contract_address,
            "created_at": wallet.created_at.isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/identities/{agent_id}/wallets/{chain_id}/balance", response_model=dict[str, Any])
async def get_wallet_balance(agent_id: str, chain_id: int, manager: AgentIdentityManager = Depends(get_identity_manager)):
    """Get wallet balance for an agent on a specific chain"""
    try:
        balance = await manager.wallet_adapter.get_wallet_balance(agent_id, chain_id)
        return {
            "agent_id": agent_id,
            "chain_id": chain_id,
            "balance": str(balance),
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/identities/{agent_id}/wallets/{chain_id}/transactions", response_model=dict[str, Any])
async def execute_wallet_transaction(
    agent_id: str, chain_id: int, request: dict[str, Any], manager: AgentIdentityManager = Depends(get_identity_manager)
):
    """Execute a transaction from agent wallet"""
    try:
        from decimal import Decimal

        result = await manager.wallet_adapter.execute_wallet_transaction(
            agent_id, chain_id, request["to_address"], Decimal(str(request["amount"])), request.get("data")
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/identities/{agent_id}/wallets/{chain_id}/transactions", response_model=list[dict[str, Any]])
async def get_wallet_transaction_history(
    agent_id: str,
    chain_id: int,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    manager: AgentIdentityManager = Depends(get_identity_manager),
):
    """Get transaction history for agent wallet"""
    try:
        history = await manager.wallet_adapter.get_wallet_transaction_history(agent_id, chain_id, limit, offset)
        return history
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/identities/{agent_id}/wallets", response_model=dict[str, Any])
async def get_all_agent_wallets(agent_id: str, manager: AgentIdentityManager = Depends(get_identity_manager)):
    """Get all wallets for an agent across all chains"""
    try:
        wallets = await manager.wallet_adapter.get_all_agent_wallets(agent_id)
        stats = await manager.wallet_adapter.get_wallet_statistics(agent_id)

        return {
            "agent_id": agent_id,
            "wallets": [
                {
                    "id": w.id,
                    "chain_id": w.chain_id,
                    "chain_address": w.chain_address,
                    "wallet_type": w.wallet_type,
                    "contract_address": w.contract_address,
                    "balance": w.balance,
                    "spending_limit": w.spending_limit,
                    "total_spent": w.total_spent,
                    "is_active": w.is_active,
                    "transaction_count": w.transaction_count,
                    "last_transaction": w.last_transaction.isoformat() if w.last_transaction else None,
                    "created_at": w.created_at.isoformat(),
                    "updated_at": w.updated_at.isoformat(),
                }
                for w in wallets
            ],
            "statistics": stats,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Search and Discovery Endpoints


@router.get("/identities/search", response_model=dict[str, Any])
async def search_agent_identities(
    query: str = Query(default="", description="Search query"),
    chains: list[int] | None = Query(default=None, description="Filter by chain IDs"),
    status: IdentityStatus | None = Query(default=None, description="Filter by status"),
    verification_level: VerificationType | None = Query(default=None, description="Filter by verification level"),
    min_reputation: float | None = Query(default=None, ge=0, le=100, description="Minimum reputation score"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    manager: AgentIdentityManager = Depends(get_identity_manager),
):
    """Search agent identities with advanced filters"""
    try:
        result = await manager.search_agent_identities(
            query=query,
            chains=chains,
            status=status,
            verification_level=verification_level,
            min_reputation=min_reputation,
            limit=limit,
            offset=offset,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/identities/{agent_id}/sync-reputation", response_model=dict[str, Any])
async def sync_agent_reputation(agent_id: str, manager: AgentIdentityManager = Depends(get_identity_manager)):
    """Sync agent reputation across all chains"""
    try:
        result = await manager.sync_agent_reputation(agent_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Utility Endpoints


@router.get("/registry/health", response_model=dict[str, Any])
async def get_registry_health(manager: AgentIdentityManager = Depends(get_identity_manager)):
    """Get health status of the identity registry"""
    try:
        result = await manager.get_registry_health()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/registry/statistics", response_model=dict[str, Any])
async def get_registry_statistics(manager: AgentIdentityManager = Depends(get_identity_manager)):
    """Get comprehensive registry statistics"""
    try:
        result = await manager.registry.get_registry_statistics()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chains/supported", response_model=list[dict[str, Any]])
async def get_supported_chains(manager: AgentIdentityManager = Depends(get_identity_manager)):
    """Get list of supported blockchains"""
    try:
        chains = manager.wallet_adapter.get_supported_chains()
        return chains
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/identities/{agent_id}/export", response_model=dict[str, Any])
async def export_agent_identity(
    agent_id: str, request: dict[str, Any] = None, manager: AgentIdentityManager = Depends(get_identity_manager)
):
    """Export agent identity data for backup or migration"""
    try:
        format_type = (request or {}).get("format", "json")
        result = await manager.export_agent_identity(agent_id, format_type)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/identities/import", response_model=dict[str, Any])
async def import_agent_identity(export_data: dict[str, Any], manager: AgentIdentityManager = Depends(get_identity_manager)):
    """Import agent identity data from backup or migration"""
    try:
        result = await manager.import_agent_identity(export_data)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/registry/cleanup-expired", response_model=dict[str, Any])
async def cleanup_expired_verifications(manager: AgentIdentityManager = Depends(get_identity_manager)):
    """Clean up expired verification records"""
    try:
        cleaned_count = await manager.registry.cleanup_expired_verifications()
        return {"cleaned_verifications": cleaned_count, "timestamp": datetime.utcnow().isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/identities/batch-verify", response_model=list[dict[str, Any]])
async def batch_verify_identities(
    verifications: list[dict[str, Any]], manager: AgentIdentityManager = Depends(get_identity_manager)
):
    """Batch verify multiple identities"""
    try:
        results = await manager.registry.batch_verify_identities(verifications)
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/identities/{agent_id}/resolve/{chain_id}", response_model=dict[str, Any])
async def resolve_agent_identity(agent_id: str, chain_id: int, manager: AgentIdentityManager = Depends(get_identity_manager)):
    """Resolve agent identity to chain-specific address"""
    try:
        address = await manager.registry.resolve_agent_identity(agent_id, chain_id)
        if not address:
            raise HTTPException(status_code=404, detail="Identity mapping not found")

        return {"agent_id": agent_id, "chain_id": chain_id, "address": address, "resolved": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/address/{chain_address}/resolve/{chain_id}", response_model=dict[str, Any])
async def resolve_address_to_agent(
    chain_address: str, chain_id: int, manager: AgentIdentityManager = Depends(get_identity_manager)
):
    """Resolve chain address back to agent ID"""
    try:
        agent_id = await manager.registry.resolve_agent_identity_by_address(chain_address, chain_id)
        if not agent_id:
            raise HTTPException(status_code=404, detail="Address mapping not found")

        return {"chain_address": chain_address, "chain_id": chain_id, "agent_id": agent_id, "resolved": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
