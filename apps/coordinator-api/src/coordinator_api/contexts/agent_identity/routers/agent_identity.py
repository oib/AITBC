"""
Agent Identity API Router
REST API endpoints for agent identity management and cross-chain operations
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any

from aitbc.aitbc_logging import get_logger

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlmodel import Session, select

from ....auth import AuthDep
from ..services.manager import AgentIdentityManager
from ....storage.db import get_session
from ...infrastructure.domain.user import Wallet
from ..domain.agent_identity import (
    AgentIdentity,
    AgentWallet,
    AgentSpendSessionCreate,
    CrossChainMappingResponse,
    IdentityStatus,
    VerificationType,
)
from ..services.spend_session_service import SpendSessionService
from starlette.concurrency import run_in_threadpool

router = APIRouter(prefix="/agent-identity", tags=["Agent Identity"])
logger = get_logger(__name__)


def get_identity_manager(session: Annotated[Session, Depends(get_session)]) -> AgentIdentityManager:
    """Dependency injection for AgentIdentityManager"""
    return AgentIdentityManager(session)


def _caller_wallets(session: Session, user: dict[str, Any]) -> set[str]:
    """Wallet addresses the authenticated caller controls (users.id -> wallets)."""
    sub = str(user.get("sub") or "")
    if not sub:
        return set()
    return {str(w.address).lower() for w in session.exec(select(Wallet).where(Wallet.user_id == sub)).all() if w.address}


def _require_owned_identity(session: Session, agent_id: str, user: dict[str, Any]) -> AgentIdentity:
    """Load the identity and require the caller to own it (or be admin) (#1070)."""
    identity = session.exec(select(AgentIdentity).where(AgentIdentity.agent_id == agent_id)).first()
    if identity is None:
        raise HTTPException(status_code=404, detail="Agent identity not found")
    if user.get("role") == "admin":
        return identity
    if str(identity.owner_address).lower() in _caller_wallets(session, user):
        return identity
    raise HTTPException(status_code=403, detail="not the identity owner")


def _require_address_or_admin(session: Session, user: dict[str, Any], address: Any) -> None:
    """The caller must control `address` through its wallets, or be admin (#1070)."""
    if user.get("role") == "admin":
        return
    if str(address or "").lower() not in _caller_wallets(session, user):
        raise HTTPException(status_code=403, detail="address is not one of the caller's wallets")


# Identity Management Endpoints


@router.post("/identities", response_model=dict[str, Any])
async def create_agent_identity(
    request: dict[str, Any],
    manager: Annotated[AgentIdentityManager, Depends(get_identity_manager)],
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
) -> JSONResponse:
    """Create a new agent identity with cross-chain mappings"""
    _require_address_or_admin(session, user, request.get("owner_address"))
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
        import traceback

        logger.error("Failed to create agent identity: %s\n%s", str(e), traceback.format_exc())
        raise HTTPException(status_code=400, detail="Failed to create agent identity") from e


# Declared above the parameterized routes below on purpose. Starlette matches in
# declaration order, so moving this back down makes it unreachable -- the request
# binds the literal segment as the path parameter instead, and the caller gets a
# plausible-looking answer from the wrong handler rather than a routing error.
# Pinned by tests/security/test_no_unreachable_routes.py.
@router.get("/identities/search", response_model=dict[str, Any])
async def search_agent_identities(
    manager: Annotated[AgentIdentityManager, Depends(get_identity_manager)],
    query: str = "",
    status: IdentityStatus | None = None,
    verification_level: VerificationType | None = None,
    min_reputation: float | None = None,
    limit: int = 50,
    offset: int = 0,
    chains: Annotated[list[int] | None, Query()] = None,
) -> dict[str, Any]:
    """Search agent identities with advanced filters"""
    try:
        result = await manager.search_agent_identities(
            query=query or "",
            chains=chains,
            status=status,
            verification_level=verification_level,
            min_reputation=min_reputation,
            limit=limit or 50,
            offset=offset or 0,
        )
        return result
    except Exception:
        raise HTTPException(status_code=500, detail="Operation failed") from None


@router.get("/identities/{agent_id}", response_model=dict[str, Any])
async def get_agent_identity(
    agent_id: str, manager: Annotated[AgentIdentityManager, Depends(get_identity_manager)]
) -> dict[str, Any]:
    """Get comprehensive agent identity summary"""
    try:
        result = await manager.get_agent_identity_summary(agent_id)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Operation failed") from None


@router.put("/identities/{agent_id}", response_model=dict[str, Any])
async def update_agent_identity(
    agent_id: str,
    request: dict[str, Any],
    manager: Annotated[AgentIdentityManager, Depends(get_identity_manager)],
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
) -> dict[str, Any]:
    """Update agent identity and related components"""
    _require_owned_identity(session, agent_id, user)
    try:
        result = await manager.update_agent_identity(agent_id, request)
        if not result.get("update_successful", True):
            raise HTTPException(status_code=400, detail=result.get("error", "Update failed"))
        return result
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Operation failed") from None


@router.post("/identities/{agent_id}/deactivate", response_model=dict[str, Any])
async def deactivate_agent_identity(
    agent_id: str,
    request: dict[str, Any],
    manager: Annotated[AgentIdentityManager, Depends(get_identity_manager)],
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
) -> dict[str, Any]:
    """Deactivate an agent identity across all chains"""
    _require_owned_identity(session, agent_id, user)
    try:
        reason = request.get("reason", "")
        success = await manager.deactivate_agent_identity(agent_id, reason)
        if not success:
            raise HTTPException(status_code=400, detail="Deactivation failed")
        return {"agent_id": agent_id, "deactivated": True, "reason": reason, "timestamp": datetime.now(UTC).isoformat()}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Operation failed") from None


# Cross-Chain Mapping Endpoints


@router.post("/identities/{agent_id}/cross-chain/register", response_model=dict[str, Any])
async def register_cross_chain_identity(
    agent_id: str,
    request: dict[str, Any],
    manager: Annotated[AgentIdentityManager, Depends(get_identity_manager)],
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
) -> dict[str, Any]:
    """Register cross-chain identity mappings"""
    _require_owned_identity(session, agent_id, user)
    try:
        chain_mappings = request["chain_mappings"]
        verifier_address = request.get("verifier_address")
        verification_type = VerificationType(request.get("verification_type", "basic"))

        # Use registry directly for this operation
        result = await manager.registry.register_cross_chain_identity(
            agent_id, chain_mappings, verifier_address, verification_type
        )
        return result
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to create agent identity") from None


@router.get("/identities/{agent_id}/cross-chain/mapping", response_model=list[CrossChainMappingResponse])
async def get_cross_chain_mapping(
    agent_id: str, manager: Annotated[AgentIdentityManager, Depends(get_identity_manager)]
) -> list[CrossChainMappingResponse]:
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
                chain_meta_data=m.chain_meta_data,
                last_transaction=m.last_transaction,
                transaction_count=m.transaction_count,
                created_at=m.created_at,
                updated_at=m.updated_at,
            )
            for m in mappings
        ]
    except Exception:
        raise HTTPException(status_code=500, detail="Operation failed") from None


@router.put("/identities/{agent_id}/cross-chain/{chain_id}", response_model=dict[str, Any])
async def update_cross_chain_mapping(
    agent_id: str,
    chain_id: int,
    request: dict[str, Any],
    manager: Annotated[AgentIdentityManager, Depends(get_identity_manager)],
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
) -> dict[str, Any]:
    """Update cross-chain mapping for a specific chain"""
    _require_owned_identity(session, agent_id, user)
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
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Operation failed") from None


@router.post("/identities/{agent_id}/cross-chain/{chain_id}/verify", response_model=dict[str, Any])
async def verify_cross_chain_identity(
    agent_id: str,
    chain_id: int,
    request: dict[str, Any],
    manager: Annotated[AgentIdentityManager, Depends(get_identity_manager)],
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
) -> dict[str, Any]:
    """Verify identity on a specific blockchain"""
    _require_address_or_admin(session, user, request.get("verifier_address"))
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
    except Exception:
        raise HTTPException(status_code=500, detail="Operation failed") from None


@router.post("/identities/{agent_id}/migrate", response_model=dict[str, Any])
async def migrate_agent_identity(
    agent_id: str,
    request: dict[str, Any],
    manager: Annotated[AgentIdentityManager, Depends(get_identity_manager)],
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
) -> dict[str, Any]:
    """Migrate agent identity from one chain to another"""
    _require_owned_identity(session, agent_id, user)
    try:
        result = await manager.migrate_agent_identity(
            agent_id, request["from_chain"], request["to_chain"], request["new_address"], request.get("verifier_address")
        )
        return result
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to create agent identity") from None


# Wallet Management Endpoints


@router.post("/identities/{agent_id}/wallets", response_model=dict[str, Any])
async def create_agent_wallet(
    agent_id: str,
    request: dict[str, Any],
    manager: Annotated[AgentIdentityManager, Depends(get_identity_manager)],
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
) -> dict[str, Any]:
    """Create an agent wallet on a specific blockchain"""
    _require_owned_identity(session, agent_id, user)
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
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to create agent identity") from None


@router.get("/identities/{agent_id}/wallets/{chain_id}/balance", response_model=dict[str, Any])
async def get_wallet_balance(
    agent_id: str, chain_id: int, manager: Annotated[AgentIdentityManager, Depends(get_identity_manager)]
) -> dict[str, Any]:
    """Get wallet balance for an agent on a specific chain"""
    try:
        balance = await manager.wallet_adapter.get_wallet_balance(agent_id, chain_id)
        return {
            "agent_id": agent_id,
            "chain_id": chain_id,
            "balance": str(balance),
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to create agent identity") from None


@router.post("/identities/{agent_id}/wallets/{chain_id}/transactions", response_model=dict[str, Any])
async def execute_wallet_transaction(
    agent_id: str,
    chain_id: int,
    request: dict[str, Any],
    manager: Annotated[AgentIdentityManager, Depends(get_identity_manager)],
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
) -> dict[str, Any]:
    """Execute a transaction from agent wallet"""
    _require_owned_identity(session, agent_id, user)
    try:
        from decimal import Decimal

        from ..domain.spend_policy import SpendPermissionError, SpendSessionCapError, SpendSessionRequiredError

        result = await manager.wallet_adapter.execute_wallet_transaction(
            agent_id, chain_id, request["to_address"], Decimal(str(request["amount"])), request.get("data")
        )
        return result
    except SpendPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (SpendSessionRequiredError, SpendSessionCapError) as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Wallet transaction failed") from exc


@router.get("/identities/{agent_id}/wallets/{chain_id}/transactions", response_model=list[dict[str, Any]])
async def get_wallet_transaction_history(
    agent_id: str,
    chain_id: int,
    manager: Annotated[AgentIdentityManager, Depends(get_identity_manager)],
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Get transaction history for agent wallet"""
    try:
        history = await manager.wallet_adapter.get_wallet_transaction_history(agent_id, chain_id, limit or 50, offset or 0)
        return history
    except Exception:
        raise HTTPException(status_code=500, detail="Operation failed") from None


@router.get("/identities/{agent_id}/wallets", response_model=dict[str, Any])
async def get_all_agent_wallets(
    agent_id: str, manager: Annotated[AgentIdentityManager, Depends(get_identity_manager)]
) -> dict[str, Any]:
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
    except Exception:
        raise HTTPException(status_code=500, detail="Operation failed") from None


@router.post("/identities/{agent_id}/wallets/{chain_id}/export", response_model=dict[str, Any])
def export_agent_wallet(
    agent_id: str,
    chain_id: int,
    manager: Annotated[AgentIdentityManager, Depends(get_identity_manager)],
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
) -> dict[str, Any]:
    """Export agent wallet data for backup or migration"""
    _require_owned_identity(session, agent_id, user)
    try:
        from sqlalchemy import select

        # Get wallet from database
        stmt = select(AgentWallet).where(
            AgentWallet.agent_id == agent_id,  # type: ignore[arg-type]
            AgentWallet.chain_id == chain_id,  # type: ignore[arg-type]
            AgentWallet.is_active == True,  # type: ignore[arg-type]  # noqa: E712
        )
        wallet = manager.session.execute(stmt).scalars().first()

        if not wallet:
            raise HTTPException(status_code=404, detail="Wallet not found")

        # Export wallet data (excluding sensitive private key)
        return {
            "wallet_id": wallet.id,
            "agent_id": agent_id,
            "chain_id": chain_id,
            "chain_address": wallet.chain_address,
            "wallet_type": wallet.wallet_type,
            "contract_address": wallet.contract_address,
            "balance": wallet.balance,
            "is_active": wallet.is_active,
            "transaction_count": wallet.transaction_count,
            "created_at": wallet.created_at.isoformat(),
            "updated_at": wallet.updated_at.isoformat(),
            "exported_at": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Operation failed") from None


@router.delete("/identities/{agent_id}/wallets/{chain_id}", response_model=dict[str, Any])
def delete_agent_wallet(
    agent_id: str,
    chain_id: int,
    manager: Annotated[AgentIdentityManager, Depends(get_identity_manager)],
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
) -> dict[str, Any]:
    """Delete an agent wallet"""
    _require_owned_identity(session, agent_id, user)
    try:
        from sqlalchemy import select

        # Get wallet from database
        stmt = select(AgentWallet).where(
            AgentWallet.agent_id == agent_id,  # type: ignore[arg-type]
            AgentWallet.chain_id == chain_id,  # type: ignore[arg-type]
            AgentWallet.is_active == True,  # type: ignore[arg-type]  # noqa: E712
        )
        wallet = manager.session.execute(stmt).scalars().first()

        if not wallet:
            raise HTTPException(status_code=404, detail="Wallet not found")

        # Deactivate wallet instead of deleting
        wallet.is_active = False
        wallet.updated_at = datetime.now(UTC)
        manager.session.commit()

        return {
            "wallet_id": wallet.id,
            "agent_id": agent_id,
            "chain_id": chain_id,
            "deleted": True,
            "deleted_at": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Operation failed") from None


@router.post("/identities/{agent_id}/wallets/{chain_id}/sign", response_model=dict[str, Any])
def sign_message(
    agent_id: str,
    chain_id: int,
    request: dict[str, Any],
    manager: Annotated[AgentIdentityManager, Depends(get_identity_manager)],
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
) -> dict[str, Any]:
    """Sign a message with agent wallet.

    ponytail: Disabled until secure encrypted-key signing is implemented.
    The previous implementation returned a SHA-256 hash, not a valid signature.
    """
    _require_owned_identity(session, agent_id, user)
    raise HTTPException(
        status_code=501,
        detail="Agent wallet signing is disabled until secure key custody is implemented",
    )


# Search and Discovery Endpoints


@router.post("/identities/{agent_id}/sync-reputation", response_model=dict[str, Any])
async def sync_agent_reputation(
    agent_id: str,
    manager: Annotated[AgentIdentityManager, Depends(get_identity_manager)],
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
) -> dict[str, Any]:
    """Sync agent reputation across all chains"""
    _require_owned_identity(session, agent_id, user)
    try:
        result = await manager.sync_agent_reputation(agent_id)
        return result
    except Exception:
        raise HTTPException(status_code=500, detail="Operation failed") from None


# Utility Endpoints


@router.get("/registry/health", response_model=dict[str, Any])
async def get_registry_health(manager: Annotated[AgentIdentityManager, Depends(get_identity_manager)]) -> dict[str, Any]:
    """Get health status of the identity registry"""
    try:
        result = await manager.get_registry_health()
        return result
    except Exception:
        raise HTTPException(status_code=500, detail="Operation failed") from None


@router.get("/registry/statistics", response_model=dict[str, Any])
async def get_registry_statistics(manager: Annotated[AgentIdentityManager, Depends(get_identity_manager)]) -> dict[str, Any]:
    """Get comprehensive registry statistics"""
    try:
        result = await manager.registry.get_registry_statistics()
        return result
    except Exception:
        raise HTTPException(status_code=500, detail="Operation failed") from None


@router.get("/chains/supported", response_model=list[dict[str, Any]])
def get_supported_chains(
    manager: Annotated[AgentIdentityManager, Depends(get_identity_manager)],
) -> list[dict[str, Any]]:
    """Get list of supported blockchains"""
    try:
        chains = manager.wallet_adapter.get_supported_chains()
        return chains
    except Exception:
        raise HTTPException(status_code=500, detail="Operation failed") from None


@router.post("/identities/{agent_id}/export", response_model=dict[str, Any])
async def export_agent_identity(
    agent_id: str,
    request: dict[str, Any] | None,
    manager: Annotated[AgentIdentityManager, Depends(get_identity_manager)],
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
) -> dict[str, Any]:
    """Export agent identity data for backup or migration"""
    _require_owned_identity(session, agent_id, user)
    try:
        format_type = (request or {}).get("format", "json")
        result = await manager.export_agent_identity(agent_id, format_type)
        return result
    except Exception:
        raise HTTPException(status_code=500, detail="Operation failed") from None


@router.post("/identities/import", response_model=dict[str, Any])
async def import_agent_identity(
    export_data: dict[str, Any],
    manager: Annotated[AgentIdentityManager, Depends(get_identity_manager)],
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
) -> dict[str, Any]:
    """Import agent identity data from backup or migration"""
    _require_address_or_admin(session, user, (export_data.get("identity") or {}).get("owner_address"))
    try:
        result = await manager.import_agent_identity(export_data)
        return result
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to create agent identity") from None


@router.post("/registry/cleanup-expired", response_model=dict[str, Any])
async def cleanup_expired_verifications(
    manager: Annotated[AgentIdentityManager, Depends(get_identity_manager)],
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
) -> dict[str, Any]:
    """Clean up expired verification records"""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="admin only")
    try:
        cleaned_count = await manager.registry.cleanup_expired_verifications()
        return {"cleaned_verifications": cleaned_count, "timestamp": datetime.now(UTC).isoformat()}
    except Exception:
        raise HTTPException(status_code=500, detail="Operation failed") from None


@router.post("/identities/batch-verify", response_model=list[dict[str, Any]])
async def batch_verify_identities(
    verifications: list[dict[str, Any]],
    manager: Annotated[AgentIdentityManager, Depends(get_identity_manager)],
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
) -> list[dict[str, Any]]:
    """Batch verify multiple identities"""
    wallets = _caller_wallets(session, user)
    if user.get("role") != "admin":
        for v in verifications:
            if str(v.get("verifier_address") or "").lower() not in wallets:
                raise HTTPException(status_code=403, detail="verifier_address is not one of the caller's wallets")
    try:
        results = await manager.registry.batch_verify_identities(verifications)
        return results
    except Exception:
        raise HTTPException(status_code=500, detail="Operation failed") from None


@router.get("/identities/{agent_id}/resolve/{chain_id}", response_model=dict[str, Any])
async def resolve_agent_identity(
    agent_id: str, chain_id: int, manager: Annotated[AgentIdentityManager, Depends(get_identity_manager)]
) -> dict[str, Any]:
    """Resolve agent identity to chain-specific address"""
    try:
        address = await manager.registry.resolve_agent_identity(agent_id, chain_id)
        if not address:
            raise HTTPException(status_code=404, detail="Identity mapping not found")

        return {"agent_id": agent_id, "chain_id": chain_id, "address": address, "resolved": True}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Operation failed") from None


@router.get("/address/{chain_address}/resolve/{chain_id}", response_model=dict[str, Any])
async def resolve_address_to_agent(
    chain_address: str, chain_id: int, manager: Annotated[AgentIdentityManager, Depends(get_identity_manager)]
) -> dict[str, Any]:
    """Resolve chain address back to agent ID"""
    try:
        agent_id = await manager.registry.resolve_agent_identity_by_address(chain_address, chain_id)
        if not agent_id:
            raise HTTPException(status_code=404, detail="Address mapping not found")

        return {"chain_address": chain_address, "chain_id": chain_id, "agent_id": agent_id, "resolved": True}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Operation failed") from None


# Spend policy (AGENT-SPEND-A-1 Phase A)


@router.post("/identities/{agent_id}/spend-sessions", response_model=dict[str, Any])
async def create_spend_session(
    agent_id: str,
    request: dict[str, Any],
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
) -> dict[str, Any]:
    """Owner issues a scoped spend session for an agent."""
    identity = _require_owned_identity(session, agent_id, user)
    body = AgentSpendSessionCreate(
        chain_id=int(request.get("chain_id", 1000)),
        cap_ait=Decimal(str(request["cap_ait"])),
        allowed_ops=list(request.get("allowed_ops") or ["wallet.execute"]),
        expires_at=request.get("expires_at"),
    )
    svc = SpendSessionService(session)
    try:
        row = await run_in_threadpool(
            svc.create_session,
            agent_id,
            identity.owner_address,
            body.chain_id,
            body.cap_ait,
            body.allowed_ops,
            body.expires_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "session_id": row.id,
        "agent_id": row.agent_id,
        "chain_id": row.chain_id,
        "cap_ait": str(row.cap_ait),
        "used_ait": str(row.used_ait),
        "allowed_ops": row.allowed_ops,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "revoked_at": None,
    }


@router.get("/identities/{agent_id}/spend-sessions", response_model=list[dict[str, Any]])
async def list_spend_sessions(
    agent_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
    include_revoked: bool = False,
) -> list[dict[str, Any]]:
    _require_owned_identity(session, agent_id, user)
    svc = SpendSessionService(session)
    rows = await run_in_threadpool(svc.list_sessions, agent_id, include_revoked)
    return [
        {
            "session_id": r.id,
            "chain_id": r.chain_id,
            "cap_ait": str(r.cap_ait),
            "used_ait": str(r.used_ait),
            "allowed_ops": r.allowed_ops,
            "expires_at": r.expires_at.isoformat() if r.expires_at else None,
            "revoked_at": r.revoked_at.isoformat() if r.revoked_at else None,
        }
        for r in rows
    ]


@router.post("/identities/{agent_id}/spend-sessions/{session_id}/revoke", response_model=dict[str, Any])
async def revoke_spend_session(
    agent_id: str,
    session_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
) -> dict[str, Any]:
    _require_owned_identity(session, agent_id, user)
    svc = SpendSessionService(session)
    try:
        row = await run_in_threadpool(svc.revoke_session, agent_id, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"session_id": row.id, "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None}
