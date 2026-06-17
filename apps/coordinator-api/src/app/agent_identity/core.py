"""
Agent Identity Core Implementation
Provides unified agent identification and cross-chain compatibility
"""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlmodel import Session, select

from aitbc.aitbc_logging import get_logger

from ..contexts.agent_identity.domain.agent_identity import (
    AgentIdentity,
    AgentIdentityCreate,
    AgentIdentityUpdate,
    AgentWallet,
    ChainType,
    CrossChainMapping,
    CrossChainMappingUpdate,
    IdentityStatus,
    IdentityVerification,
    VerificationType,
)

logger = get_logger(__name__)


class AgentIdentityCore:
    """Core agent identity management across multiple blockchains"""

    def __init__(self, session: Session):
        self.session = session

    async def create_identity(self, request: AgentIdentityCreate) -> AgentIdentity:
        """Create a new unified agent identity"""
        existing = await self.get_identity_by_agent_id(request.agent_id)
        if existing:
            raise ValueError(f"Agent identity already exists for agent_id: {request.agent_id}")
        identity = AgentIdentity(
            agent_id=request.agent_id,
            owner_address=request.owner_address.lower(),
            display_name=request.display_name,
            description=request.description,
            avatar_url=request.avatar_url,
            supported_chains=request.supported_chains,
            primary_chain=request.primary_chain,
            identity_data=request.meta_data,
            tags=request.tags,
        )
        self.session.add(identity)
        self.session.commit()
        self.session.refresh(identity)
        logger.info("Created agent identity: %s for agent: %s", identity.id, request.agent_id)
        return identity

    async def get_identity(self, identity_id: str) -> AgentIdentity | None:
        """Get identity by ID"""
        return self.session.get(AgentIdentity, identity_id)

    async def get_identity_by_agent_id(self, agent_id: str) -> AgentIdentity | None:
        """Get identity by agent ID"""
        stmt = select(AgentIdentity).where(AgentIdentity.agent_id == agent_id)
        result = self.session.execute(stmt)
        return result.scalars().first()

    async def get_identity_by_owner(self, owner_address: str) -> list[AgentIdentity]:
        """Get all identities for an owner"""
        stmt = select(AgentIdentity).where(AgentIdentity.owner_address == owner_address.lower())
        result = self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_identity(self, identity_id: str, request: AgentIdentityUpdate) -> AgentIdentity:
        """Update an existing agent identity"""
        identity = await self.get_identity(identity_id)
        if not identity:
            raise ValueError(f"Identity not found: {identity_id}")
        update_data = request.dict(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(identity, field):
                setattr(identity, field, value)
        identity.updated_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(identity)
        logger.info("Updated agent identity: %s", identity_id)
        return identity

    async def register_cross_chain_identity(
        self,
        identity_id: str,
        chain_id: int,
        chain_address: str,
        chain_type: ChainType = ChainType.ETHEREUM,
        wallet_address: str | None = None,
    ) -> CrossChainMapping:
        """Register identity on a new blockchain"""
        identity = await self.get_identity(identity_id)
        if not identity:
            raise ValueError(f"Identity not found: {identity_id}")
        existing = await self.get_cross_chain_mapping(identity_id, chain_id)
        if existing:
            raise ValueError(f"Cross-chain mapping already exists for chain {chain_id}")
        mapping = CrossChainMapping(
            agent_id=identity.agent_id,
            chain_id=chain_id,
            chain_type=chain_type,
            chain_address=chain_address.lower(),
            wallet_address=wallet_address.lower() if wallet_address else None,
        )
        self.session.add(mapping)
        self.session.commit()
        self.session.refresh(mapping)
        if str(chain_id) not in identity.supported_chains:
            identity.supported_chains.append(str(chain_id))
            identity.updated_at = datetime.now(UTC)
            self.session.commit()
        logger.info("Registered cross-chain identity: %s -> %s:%s", identity_id, chain_id, chain_address)
        return mapping

    async def get_cross_chain_mapping(self, identity_id: str, chain_id: int) -> CrossChainMapping | None:
        """Get cross-chain mapping for a specific chain"""
        identity = await self.get_identity(identity_id)
        if not identity:
            return None
        stmt = select(CrossChainMapping).where(
            CrossChainMapping.agent_id == identity.agent_id, CrossChainMapping.chain_id == chain_id
        )
        result = self.session.execute(stmt)
        return result.scalars().first()

    async def get_all_cross_chain_mappings(self, identity_id: str) -> list[CrossChainMapping]:
        """Get all cross-chain mappings for an identity"""
        identity = await self.get_identity(identity_id)
        if not identity:
            return []
        stmt = select(CrossChainMapping).where(CrossChainMapping.agent_id == identity.agent_id)
        result = self.session.execute(stmt)
        return list(result.scalars().all())

    async def verify_cross_chain_identity(
        self,
        identity_id: str,
        chain_id: int,
        verifier_address: str,
        proof_hash: str,
        proof_data: dict[str, Any],
        verification_type: VerificationType = VerificationType.BASIC,
    ) -> IdentityVerification:
        """Verify identity on a specific blockchain"""
        mapping = await self.get_cross_chain_mapping(identity_id, chain_id)
        if not mapping:
            raise ValueError(f"Cross-chain mapping not found for chain {chain_id}")
        verification = IdentityVerification(
            agent_id=mapping.agent_id,
            chain_id=chain_id,
            verification_type=verification_type,
            verifier_address=verifier_address.lower(),
            proof_hash=proof_hash,
            proof_data=proof_data,
        )
        self.session.add(verification)
        self.session.commit()
        self.session.refresh(verification)
        mapping.is_verified = True
        mapping.verified_at = datetime.now(UTC)
        mapping.verification_proof = proof_data
        self.session.commit()
        identity = await self.get_identity(identity_id)
        if identity and chain_id == identity.primary_chain:
            identity.is_verified = True
            identity.verified_at = datetime.now(UTC)
            identity.verification_level = verification_type
            self.session.commit()
        logger.info("Verified cross-chain identity: %s on chain %s", identity_id, chain_id)
        return verification

    async def resolve_agent_identity(self, agent_id: str, chain_id: int) -> str | None:
        """Resolve agent identity to chain-specific address"""
        identity = await self.get_identity_by_agent_id(agent_id)
        if not identity:
            return None
        mapping = await self.get_cross_chain_mapping(identity.id, chain_id)
        if not mapping:
            return None
        return mapping.chain_address

    async def get_cross_chain_mapping_by_address(self, chain_address: str, chain_id: int) -> CrossChainMapping | None:
        """Get cross-chain mapping by chain address"""
        stmt = select(CrossChainMapping).where(
            CrossChainMapping.chain_address == chain_address.lower(), CrossChainMapping.chain_id == chain_id
        )
        result = self.session.execute(stmt)
        return result.scalars().first()

    async def update_cross_chain_mapping(
        self, identity_id: str, chain_id: int, request: CrossChainMappingUpdate
    ) -> CrossChainMapping:
        """Update cross-chain mapping"""
        mapping = await self.get_cross_chain_mapping(identity_id, chain_id)
        if not mapping:
            raise ValueError(f"Cross-chain mapping not found for chain {chain_id}")
        update_data = request.dict(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(mapping, field):
                if field in ["chain_address", "wallet_address"] and value:
                    setattr(mapping, field, value.lower())
                else:
                    setattr(mapping, field, value)
        mapping.updated_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(mapping)
        logger.info("Updated cross-chain mapping: %s -> %s", identity_id, chain_id)
        return mapping

    async def revoke_identity(self, identity_id: str, reason: str = "") -> bool:
        """Revoke an agent identity"""
        identity = await self.get_identity(identity_id)
        if not identity:
            raise ValueError(f"Identity not found: {identity_id}")
        identity.status = IdentityStatus.REVOKED
        identity.is_verified = False
        identity.updated_at = datetime.now(UTC)
        identity.identity_data["revocation_reason"] = reason
        identity.identity_data["revoked_at"] = datetime.now(UTC).isoformat()
        self.session.commit()
        logger.warning("Revoked agent identity: %s, reason: %s", identity_id, reason)
        return True

    async def suspend_identity(self, identity_id: str, reason: str = "") -> bool:
        """Suspend an agent identity"""
        identity = await self.get_identity(identity_id)
        if not identity:
            raise ValueError(f"Identity not found: {identity_id}")
        identity.status = IdentityStatus.SUSPENDED
        identity.updated_at = datetime.now(UTC)
        identity.identity_data["suspension_reason"] = reason
        identity.identity_data["suspended_at"] = datetime.now(UTC).isoformat()
        self.session.commit()
        logger.warning("Suspended agent identity: %s, reason: %s", identity_id, reason)
        return True

    async def activate_identity(self, identity_id: str) -> bool:
        """Activate a suspended or inactive identity"""
        identity = await self.get_identity(identity_id)
        if not identity:
            raise ValueError(f"Identity not found: {identity_id}")
        if identity.status == IdentityStatus.REVOKED:
            raise ValueError(f"Cannot activate revoked identity: {identity_id}")
        identity.status = IdentityStatus.ACTIVE
        identity.updated_at = datetime.now(UTC)
        if "suspension_reason" in identity.identity_data:
            del identity.identity_data["suspension_reason"]
        if "suspended_at" in identity.identity_data:
            del identity.identity_data["suspended_at"]
        self.session.commit()
        logger.info("Activated agent identity: %s", identity_id)
        return True

    async def update_reputation(self, identity_id: str, transaction_success: bool, amount: float = 0.0) -> AgentIdentity:
        """Update agent reputation based on transaction outcome"""
        identity = await self.get_identity(identity_id)
        if not identity:
            raise ValueError(f"Identity not found: {identity_id}")
        identity.total_transactions += 1
        if transaction_success:
            identity.successful_transactions += 1
        success_rate = identity.successful_transactions / identity.total_transactions
        base_score = success_rate * 100
        volume_factor = min(amount / 1000.0, 1.0)
        identity.reputation_score = base_score * (0.7 + 0.3 * volume_factor)
        identity.last_activity = datetime.now(UTC)
        identity.updated_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(identity)
        logger.info("Updated reputation for identity %s: %s", identity_id, identity.reputation_score)
        return identity

    async def get_identity_statistics(self, identity_id: str) -> dict[str, Any]:
        """Get comprehensive statistics for an identity"""
        identity = await self.get_identity(identity_id)
        if not identity:
            return {}
        mappings = await self.get_all_cross_chain_mappings(identity_id)
        stmt = select(IdentityVerification).where(IdentityVerification.agent_id == identity.agent_id)
        result = self.session.execute(stmt)
        verifications = list(result.scalars().all())
        stmt_wallets = select(AgentWallet).where(AgentWallet.agent_id == identity.agent_id)
        result_wallets = self.session.execute(stmt_wallets)
        wallets = list(result_wallets.scalars().all())
        return {
            "identity": {
                "id": identity.id,
                "agent_id": identity.agent_id,
                "status": identity.status,
                "verification_level": identity.verification_level,
                "reputation_score": identity.reputation_score,
                "total_transactions": identity.total_transactions,
                "successful_transactions": identity.successful_transactions,
                "success_rate": identity.successful_transactions / max(identity.total_transactions, 1),
                "created_at": identity.created_at,
                "last_activity": identity.last_activity,
            },
            "cross_chain": {
                "total_mappings": len(mappings),
                "verified_mappings": len([m for m in mappings if m.is_verified]),
                "supported_chains": [m.chain_id for m in mappings],
                "primary_chain": identity.primary_chain,
            },
            "verifications": {
                "total_verifications": len(verifications),
                "pending_verifications": len([v for v in verifications if v.verification_result == "pending"]),
                "approved_verifications": len([v for v in verifications if v.verification_result == "approved"]),
                "rejected_verifications": len([v for v in verifications if v.verification_result == "rejected"]),
            },
            "wallets": {
                "total_wallets": len(wallets),
                "active_wallets": len([w for w in wallets if w.is_active]),
                "total_balance": sum(w.balance for w in wallets),
                "total_spent": sum(w.total_spent for w in wallets),
            },
        }

    async def search_identities(
        self,
        query: str = "",
        status: IdentityStatus | None = None,
        verification_level: VerificationType | None = None,
        chain_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AgentIdentity]:
        """Search identities with various filters"""
        stmt = select(AgentIdentity)
        if query:
            stmt = stmt.where(
                AgentIdentity.display_name.ilike(f"%{query}%")
                | AgentIdentity.description.ilike(f"%{query}%")
                | AgentIdentity.agent_id.ilike(f"%{query}%")
            )  # type: ignore[attr-defined]
        if status:
            stmt = stmt.where(AgentIdentity.status == status)
        if verification_level:
            stmt = stmt.where(AgentIdentity.verification_level == verification_level)
        if chain_id:
            stmt = stmt.join(CrossChainMapping, AgentIdentity.agent_id == CrossChainMapping.agent_id).where(
                CrossChainMapping.chain_id == chain_id
            )  # type: ignore[arg-type]
        stmt = stmt.offset(offset).limit(limit)
        result = self.session.execute(stmt)
        return list(result.scalars().all())

    async def generate_identity_proof(self, identity_id: str, chain_id: int) -> dict[str, Any]:
        """Generate a cryptographic proof for identity verification"""
        identity = await self.get_identity(identity_id)
        if not identity:
            raise ValueError(f"Identity not found: {identity_id}")
        mapping = await self.get_cross_chain_mapping(identity_id, chain_id)
        if not mapping:
            raise ValueError(f"Cross-chain mapping not found for chain {chain_id}")
        proof_data = {
            "identity_id": identity.id,
            "agent_id": identity.agent_id,
            "owner_address": identity.owner_address,
            "chain_id": chain_id,
            "chain_address": mapping.chain_address,
            "timestamp": datetime.now(UTC).isoformat(),
            "nonce": str(uuid4()),
        }
        proof_string = json.dumps(proof_data, sort_keys=True)
        proof_hash = hashlib.sha256(proof_string.encode()).hexdigest()
        return {
            "proof_data": proof_data,
            "proof_hash": proof_hash,
            "expires_at": (datetime.now(UTC) + timedelta(hours=24)).isoformat(),
        }
