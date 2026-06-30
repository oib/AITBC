"""
Cross-Chain Registry Implementation
Registry for cross-chain agent identity mapping and synchronization
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
    ChainType,
    CrossChainMapping,
    IdentityVerification,
    VerificationType,
)

logger = get_logger(__name__)


class CrossChainRegistry:
    """Registry for cross-chain agent identity mapping and synchronization"""

    def __init__(self, session: Session):
        self.session = session

    async def register_cross_chain_identity(
        self,
        agent_id: str,
        chain_mappings: dict[int, str],
        verifier_address: str | None = None,
        verification_type: VerificationType = VerificationType.BASIC,
    ) -> dict[str, Any]:
        """Register cross-chain identity mappings for an agent"""
        stmt = select(AgentIdentity).where(AgentIdentity.agent_id == agent_id)
        result = self.session.execute(stmt)
        identity = result.scalars().first()
        if not identity:
            raise ValueError(f"Agent identity not found for agent_id: {agent_id}")
        registration_results = []
        for chain_id, chain_address in chain_mappings.items():
            try:
                existing = await self.get_cross_chain_mapping_by_agent_chain(agent_id, chain_id)
                if existing:
                    logger.warning("Mapping already exists for agent %s on chain %s", agent_id, chain_id)
                    continue
                mapping = CrossChainMapping(
                    agent_id=agent_id,
                    chain_id=chain_id,
                    chain_type=self._get_chain_type(chain_id),
                    chain_address=chain_address.lower(),
                )
                self.session.add(mapping)
                self.session.commit()
                self.session.refresh(mapping)
                if verifier_address:
                    await self.verify_cross_chain_identity(
                        identity.id,
                        chain_id,
                        verifier_address,
                        self._generate_proof_hash(mapping),
                        {"auto_verification": True},
                        verification_type,
                    )
                registration_results.append(
                    {
                        "chain_id": chain_id,
                        "chain_address": chain_address,
                        "mapping_id": mapping.id,
                        "verified": verifier_address is not None,
                    }
                )
                if str(chain_id) not in identity.supported_chains:
                    identity.supported_chains.append(str(chain_id))
            except Exception as e:
                logger.error("Failed to register mapping for chain %s: %s", chain_id, e)
                registration_results.append({"chain_id": chain_id, "chain_address": chain_address, "error": str(e)})
        identity.updated_at = datetime.now(UTC)
        self.session.commit()
        return {
            "agent_id": agent_id,
            "identity_id": identity.id,
            "registration_results": registration_results,
            "total_mappings": len([r for r in registration_results if "error" not in r]),
            "failed_mappings": len([r for r in registration_results if "error" in r]),
        }

    async def resolve_agent_identity(self, agent_id: str, chain_id: int) -> str | None:
        """Resolve agent identity to chain-specific address"""
        stmt = select(CrossChainMapping).where(CrossChainMapping.agent_id == agent_id, CrossChainMapping.chain_id == chain_id)
        result = self.session.execute(stmt)
        mapping = result.scalars().first()
        if not mapping:
            return None
        return mapping.chain_address  # type: ignore[no-any-return]

    async def resolve_agent_identity_by_address(self, chain_address: str, chain_id: int) -> str | None:
        """Resolve chain address back to agent ID"""
        stmt = select(CrossChainMapping).where(
            CrossChainMapping.chain_address == chain_address.lower(), CrossChainMapping.chain_id == chain_id
        )
        result = self.session.execute(stmt)
        mapping = result.scalars().first()
        if not mapping:
            return None
        return mapping.agent_id  # type: ignore[no-any-return]

    async def update_identity_mapping(
        self, agent_id: str, chain_id: int, new_address: str, verifier_address: str | None = None
    ) -> bool:
        """Update identity mapping for a specific chain"""
        mapping = await self.get_cross_chain_mapping_by_agent_chain(agent_id, chain_id)
        if not mapping:
            raise ValueError(f"Mapping not found for agent {agent_id} on chain {chain_id}")
        old_address = mapping.chain_address
        mapping.chain_address = new_address.lower()
        mapping.updated_at = datetime.now(UTC)
        mapping.is_verified = False
        mapping.verified_at = None
        mapping.verification_proof = None
        self.session.commit()
        if verifier_address:
            await self.verify_cross_chain_identity(
                await self._get_identity_id(agent_id),
                chain_id,
                verifier_address,
                self._generate_proof_hash(mapping),
                {"address_update": True, "old_address": old_address},
            )
        logger.info("Updated identity mapping: %s on chain %s: %s -> %s", agent_id, chain_id, old_address, new_address)
        return True

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
        identity = self.session.get(AgentIdentity, identity_id)
        if not identity:
            raise ValueError(f"Identity not found: {identity_id}")
        mapping = await self.get_cross_chain_mapping_by_agent_chain(identity.agent_id, chain_id)
        if not mapping:
            raise ValueError(f"Mapping not found for agent {identity.agent_id} on chain {chain_id}")
        verification = IdentityVerification(
            agent_id=identity.agent_id,
            chain_id=chain_id,
            verification_type=verification_type,
            verifier_address=verifier_address.lower(),
            proof_hash=proof_hash,
            proof_data=proof_data,
            verification_result="approved",
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
        self.session.add(verification)
        self.session.commit()
        self.session.refresh(verification)
        mapping.is_verified = True
        mapping.verified_at = datetime.now(UTC)
        mapping.verification_proof = proof_data
        self.session.commit()
        if self._is_higher_verification_level(verification_type, identity.verification_level):
            identity.verification_level = verification_type
            identity.is_verified = True
            identity.verified_at = datetime.now(UTC)
            self.session.commit()
        logger.info("Verified cross-chain identity: %s on chain %s", identity_id, chain_id)
        return verification

    async def revoke_verification(self, identity_id: str, chain_id: int, reason: str = "") -> bool:
        """Revoke verification for a specific chain"""
        mapping = await self.get_cross_chain_mapping_by_identity_chain(identity_id, chain_id)
        if not mapping:
            raise ValueError(f"Mapping not found for identity {identity_id} on chain {chain_id}")
        mapping.is_verified = False
        mapping.verified_at = None
        mapping.verification_proof = None
        mapping.updated_at = datetime.now(UTC)
        if not mapping.chain_meta_data:
            mapping.chain_meta_data = {}
        mapping.chain_meta_data["verification_revoked"] = True
        mapping.chain_meta_data["revocation_reason"] = reason
        mapping.chain_meta_data["revoked_at"] = datetime.now(UTC).isoformat()
        self.session.commit()
        logger.warning("Revoked verification for identity %s on chain %s: %s", identity_id, chain_id, reason)
        return True

    async def sync_agent_reputation(self, agent_id: str) -> dict[int, float]:
        """Sync agent reputation across all chains"""
        stmt = select(AgentIdentity).where(AgentIdentity.agent_id == agent_id)
        result = self.session.execute(stmt)
        identity = result.scalars().first()
        if not identity:
            raise ValueError(f"Agent identity not found: {agent_id}")
        stmt_mappings = select(CrossChainMapping).where(CrossChainMapping.agent_id == agent_id)
        result_mappings = self.session.execute(stmt_mappings)
        mappings = list(result_mappings.scalars().all())
        reputation_scores = {}
        for mapping in mappings:
            reputation_scores[mapping.chain_id] = identity.reputation_score
        return reputation_scores

    async def get_cross_chain_mapping_by_agent_chain(self, agent_id: str, chain_id: int) -> CrossChainMapping | None:
        """Get cross-chain mapping by agent ID and chain ID"""
        stmt = select(CrossChainMapping).where(CrossChainMapping.agent_id == agent_id, CrossChainMapping.chain_id == chain_id)
        result = self.session.execute(stmt)
        return result.scalars().first()

    async def get_cross_chain_mapping_by_identity_chain(self, identity_id: str, chain_id: int) -> CrossChainMapping | None:
        """Get cross-chain mapping by identity ID and chain ID"""
        identity = self.session.get(AgentIdentity, identity_id)
        if not identity:
            return None
        return await self.get_cross_chain_mapping_by_agent_chain(identity.agent_id, chain_id)

    async def get_cross_chain_mapping_by_address(self, chain_address: str, chain_id: int) -> CrossChainMapping | None:
        """Get cross-chain mapping by chain address"""
        stmt = select(CrossChainMapping).where(
            CrossChainMapping.chain_address == chain_address.lower(), CrossChainMapping.chain_id == chain_id
        )
        result = self.session.execute(stmt)
        return result.scalars().first()

    async def get_all_cross_chain_mappings(self, agent_id: str) -> list[CrossChainMapping]:
        """Get all cross-chain mappings for an agent"""
        stmt = select(CrossChainMapping).where(CrossChainMapping.agent_id == agent_id)
        result = self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_verified_mappings(self, agent_id: str) -> list[CrossChainMapping]:
        """Get all verified cross-chain mappings for an agent"""
        stmt = select(CrossChainMapping).where(CrossChainMapping.agent_id == agent_id, CrossChainMapping.is_verified)
        result = self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_identity_verifications(self, agent_id: str, chain_id: int | None = None) -> list[IdentityVerification]:
        """Get verification records for an agent"""
        stmt = select(IdentityVerification).where(IdentityVerification.agent_id == agent_id)
        if chain_id:
            stmt = stmt.where(IdentityVerification.chain_id == chain_id)
        result = self.session.execute(stmt)
        return list(result.scalars().all())

    async def migrate_agent_identity(
        self, agent_id: str, from_chain: int, to_chain: int, new_address: str, verifier_address: str | None = None
    ) -> dict[str, Any]:
        """Migrate agent identity from one chain to another"""
        source_mapping = await self.get_cross_chain_mapping_by_agent_chain(agent_id, from_chain)
        if not source_mapping:
            raise ValueError(f"Source mapping not found for agent {agent_id} on chain {from_chain}")
        target_mapping = await self.get_cross_chain_mapping_by_agent_chain(agent_id, to_chain)
        migration_result = {
            "agent_id": agent_id,
            "from_chain": from_chain,
            "to_chain": to_chain,
            "source_address": source_mapping.chain_address,
            "target_address": new_address,
            "migration_successful": False,
        }
        try:
            if target_mapping:
                await self.update_identity_mapping(agent_id, to_chain, new_address, verifier_address)
                migration_result["action"] = "updated_existing"
            else:
                await self.register_cross_chain_identity(agent_id, {to_chain: new_address}, verifier_address)
                migration_result["action"] = "created_new"
            if source_mapping.is_verified and verifier_address:
                await self.verify_cross_chain_identity(
                    await self._get_identity_id(agent_id),
                    to_chain,
                    verifier_address,
                    self._generate_proof_hash(
                        target_mapping or await self.get_cross_chain_mapping_by_agent_chain(agent_id, to_chain)  # type: ignore[arg-type]
                    ),
                    {"migration": True, "source_chain": from_chain},
                )
                migration_result["verification_copied"] = True
            else:
                migration_result["verification_copied"] = False
            migration_result["migration_successful"] = True
            logger.info("Successfully migrated agent %s from chain %s to %s", agent_id, from_chain, to_chain)
        except Exception as e:
            migration_result["error"] = str(e)
            logger.error("Failed to migrate agent %s from chain %s to %s: %s", agent_id, from_chain, to_chain, e)
        return migration_result

    async def batch_verify_identities(self, verifications: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Batch verify multiple identities"""
        results = []
        for verification_data in verifications:
            try:
                result = await self.verify_cross_chain_identity(
                    verification_data["identity_id"],
                    verification_data["chain_id"],
                    verification_data["verifier_address"],
                    verification_data["proof_hash"],
                    verification_data.get("proof_data", {}),
                    verification_data.get("verification_type", VerificationType.BASIC),
                )
                results.append(
                    {
                        "identity_id": verification_data["identity_id"],
                        "chain_id": verification_data["chain_id"],
                        "success": True,
                        "verification_id": result.id,
                    }
                )
            except Exception as e:
                results.append(
                    {
                        "identity_id": verification_data["identity_id"],
                        "chain_id": verification_data["chain_id"],
                        "success": False,
                        "error": str(e),
                    }
                )
        return results

    async def get_registry_statistics(self) -> dict[str, Any]:
        """Get comprehensive registry statistics"""
        identity_count = self.session.execute(select(AgentIdentity)).scalar()
        mapping_count = self.session.execute(select(CrossChainMapping)).scalar()
        verified_mapping_count = self.session.execute(select(CrossChainMapping).where(CrossChainMapping.is_verified)).scalar()
        verification_count = self.session.execute(select(IdentityVerification)).scalar()
        chain_breakdown: dict[str, dict[str, Any]] = {}
        result = self.session.execute(select(CrossChainMapping))
        mappings = list(result.scalars().all())
        for mapping in mappings:
            chain_name = self._get_chain_name(mapping.chain_id)
            if chain_name not in chain_breakdown:
                chain_breakdown[chain_name] = {"total_mappings": 0, "verified_mappings": 0, "unique_agents": set()}
            chain_breakdown[chain_name]["total_mappings"] += 1
            if mapping.is_verified:
                chain_breakdown[chain_name]["verified_mappings"] += 1
            chain_breakdown[chain_name]["unique_agents"].add(mapping.agent_id)
        for chain_data in chain_breakdown.values():
            chain_data["unique_agents"] = len(chain_data["unique_agents"])
        verification_rate = verified_mapping_count / max(mapping_count, 1) if mapping_count else 0
        return {
            "total_identities": identity_count,
            "total_mappings": mapping_count,
            "verified_mappings": verified_mapping_count,
            "verification_rate": verification_rate,
            "total_verifications": verification_count,
            "supported_chains": len(chain_breakdown),
            "chain_breakdown": chain_breakdown,
        }

    async def cleanup_expired_verifications(self) -> int:
        """Clean up expired verification records"""
        current_time = datetime.now(UTC)
        stmt = select(IdentityVerification).where(IdentityVerification.expires_at < current_time)  # type: ignore[operator]
        result = self.session.execute(stmt)
        expired_verifications = list(result.scalars().all())
        cleaned_count = 0
        for verification in expired_verifications:
            try:
                mapping = await self.get_cross_chain_mapping_by_agent_chain(verification.agent_id, verification.chain_id)
                if mapping and mapping.verified_at and (mapping.verified_at == verification.expires_at):
                    mapping.is_verified = False
                    mapping.verified_at = None
                    mapping.verification_proof = None
                self.session.delete(verification)
                cleaned_count += 1
            except Exception as e:
                logger.error("Error cleaning up verification %s: %s", verification.id, e)
        self.session.commit()
        logger.info("Cleaned up %s expired verification records", cleaned_count)
        return cleaned_count

    def _get_chain_type(self, chain_id: int) -> ChainType:
        """Get chain type by chain ID"""
        chain_type_map = {
            1: ChainType.ETHEREUM,
            3: ChainType.ETHEREUM,
            4: ChainType.ETHEREUM,
            5: ChainType.ETHEREUM,
            137: ChainType.POLYGON,
            80001: ChainType.POLYGON,
            56: ChainType.BSC,
            97: ChainType.BSC,
            42161: ChainType.ARBITRUM,
            421611: ChainType.ARBITRUM,
            10: ChainType.OPTIMISM,
            69: ChainType.OPTIMISM,
            43114: ChainType.AVALANCHE,
            43113: ChainType.AVALANCHE,
        }
        return chain_type_map.get(chain_id, ChainType.CUSTOM)

    def _get_chain_name(self, chain_id: int) -> str:
        """Get chain name by chain ID"""
        chain_name_map = {
            1: "Ethereum Mainnet",
            3: "Ethereum Ropsten",
            4: "Ethereum Rinkeby",
            5: "Ethereum Goerli",
            137: "Polygon Mainnet",
            80001: "Polygon Mumbai",
            56: "BSC Mainnet",
            97: "BSC Testnet",
            42161: "Arbitrum One",
            421611: "Arbitrum Testnet",
            10: "Optimism",
            69: "Optimism Testnet",
            43114: "Avalanche C-Chain",
            43113: "Avalanche Testnet",
        }
        return chain_name_map.get(chain_id, f"Chain {chain_id}")

    def _generate_proof_hash(self, mapping: CrossChainMapping) -> str:
        """Generate proof hash for a mapping"""
        proof_data = {
            "agent_id": mapping.agent_id,
            "chain_id": mapping.chain_id,
            "chain_address": mapping.chain_address,
            "created_at": mapping.created_at.isoformat(),
            "nonce": str(uuid4()),
        }
        proof_string = json.dumps(proof_data, sort_keys=True)
        return hashlib.sha256(proof_string.encode()).hexdigest()

    def _is_higher_verification_level(self, new_level: VerificationType, current_level: VerificationType) -> bool:
        """Check if new verification level is higher than current"""
        level_hierarchy = {
            VerificationType.BASIC: 1,
            VerificationType.ADVANCED: 2,
            VerificationType.ZERO_KNOWLEDGE: 3,
            VerificationType.MULTI_SIGNATURE: 4,
        }
        return level_hierarchy.get(new_level, 0) > level_hierarchy.get(current_level, 0)

    async def _get_identity_id(self, agent_id: str) -> str:
        """Get identity ID by agent ID"""
        stmt = select(AgentIdentity).where(AgentIdentity.agent_id == agent_id)
        result = self.session.execute(stmt)
        identity = result.scalars().first()
        if not identity:
            raise ValueError(f"Identity not found for agent: {agent_id}")
        return identity.id  # type: ignore[no-any-return]
