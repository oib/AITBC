"""
Cross-Chain Registry Implementation
Registry for cross-chain agent identity mapping and synchronization
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
from uuid import uuid4
import json
import hashlib
from aitbc.logging import get_logger

from sqlmodel import Session, select, update, delete
from sqlalchemy.exc import SQLAlchemyError

from ..domain.agent_identity import (
    AgentIdentity, CrossChainMapping, IdentityVerification, AgentWallet,
    IdentityStatus, VerificationType, ChainType
)

logger = get_logger(__name__)


class CrossChainRegistry:
    """Registry for cross-chain agent identity mapping and synchronization"""
    
    def __init__(self, session: Session):
        self.session = session
    
    async def register_cross_chain_identity(
        self,
        agent_id: str,
        chain_mappings: Dict[int, str],
        verifier_address: Optional[str] = None,
        verification_type: VerificationType = VerificationType.BASIC
    ) -> Dict[str, Any]:
        """Register cross-chain identity mappings for an agent"""
        
        # Get or create agent identity
        stmt = select(AgentIdentity).where(AgentIdentity.agent_id == agent_id)
        identity = self.session.exec(stmt).first()
        
        if not identity:
            raise ValueError(f"Agent identity not found for agent_id: {agent_id}")
        
        registration_results = []
        
        for chain_id, chain_address in chain_mappings.items():
            try:
                # Check if mapping already exists
                existing = await self.get_cross_chain_mapping_by_agent_chain(agent_id, chain_id)
                if existing:
                    logger.warning(f"Mapping already exists for agent {agent_id} on chain {chain_id}")
                    continue
                
                # Create cross-chain mapping
                mapping = CrossChainMapping(
                    agent_id=agent_id,
                    chain_id=chain_id,
                    chain_type=self._get_chain_type(chain_id),
                    chain_address=chain_address.lower()
                )
                
                self.session.add(mapping)
                self.session.commit()
                self.session.refresh(mapping)
                
                # Auto-verify if verifier provided
                if verifier_address:
                    await self.verify_cross_chain_identity(
                        identity.id,
                        chain_id,
                        verifier_address,
                        self._generate_proof_hash(mapping),
                        {'auto_verification': True},
                        verification_type
                    )
                
                registration_results.append({
                    'chain_id': chain_id,
                    'chain_address': chain_address,
                    'mapping_id': mapping.id,
                    'verified': verifier_address is not None
                })
                
                # Update identity's supported chains
                if str(chain_id) not in identity.supported_chains:
                    identity.supported_chains.append(str(chain_id))
                
            except Exception as e:
                logger.error(f"Failed to register mapping for chain {chain_id}: {e}")
                registration_results.append({
                    'chain_id': chain_id,
                    'chain_address': chain_address,
                    'error': str(e)
                })
        
        # Update identity
        identity.updated_at = datetime.utcnow()
        self.session.commit()
        
        return {
            'agent_id': agent_id,
            'identity_id': identity.id,
            'registration_results': registration_results,
            'total_mappings': len([r for r in registration_results if 'error' not in r]),
            'failed_mappings': len([r for r in registration_results if 'error' in r])
        }
    
    async def resolve_agent_identity(self, agent_id: str, chain_id: int) -> Optional[str]:
        """Resolve agent identity to chain-specific address"""
        
        stmt = (
            select(CrossChainMapping)
            .where(
                CrossChainMapping.agent_id == agent_id,
                CrossChainMapping.chain_id == chain_id
            )
        )
        mapping = self.session.exec(stmt).first()
        
        if not mapping:
            return None
        
        return mapping.chain_address
    
    async def resolve_agent_identity_by_address(self, chain_address: str, chain_id: int) -> Optional[str]:
        """Resolve chain address back to agent ID"""
        
        stmt = (
            select(CrossChainMapping)
            .where(
                CrossChainMapping.chain_address == chain_address.lower(),
                CrossChainMapping.chain_id == chain_id
            )
        )
        mapping = self.session.exec(stmt).first()
        
        if not mapping:
            return None
        
        return mapping.agent_id
    
    async def update_identity_mapping(
        self,
        agent_id: str,
        chain_id: int,
        new_address: str,
        verifier_address: Optional[str] = None
    ) -> bool:
        """Update identity mapping for a specific chain"""
        
        mapping = await self.get_cross_chain_mapping_by_agent_chain(agent_id, chain_id)
        if not mapping:
            raise ValueError(f"Mapping not found for agent {agent_id} on chain {chain_id}")
        
        old_address = mapping.chain_address
        mapping.chain_address = new_address.lower()
        mapping.updated_at = datetime.utcnow()
        
        # Reset verification status since address changed
        mapping.is_verified = False
        mapping.verified_at = None
        mapping.verification_proof = None
        
        self.session.commit()
        
        # Re-verify if verifier provided
        if verifier_address:
            await self.verify_cross_chain_identity(
                await self._get_identity_id(agent_id),
                chain_id,
                verifier_address,
                self._generate_proof_hash(mapping),
                {'address_update': True, 'old_address': old_address}
            )
        
        logger.info(f"Updated identity mapping: {agent_id} on chain {chain_id}: {old_address} -> {new_address}")
        return True
    
    async def verify_cross_chain_identity(
        self,
        identity_id: str,
        chain_id: int,
        verifier_address: str,
        proof_hash: str,
        proof_data: Dict[str, Any],
        verification_type: VerificationType = VerificationType.BASIC
    ) -> IdentityVerification:
        """Verify identity on a specific blockchain"""
        
        # Get identity
        identity = self.session.get(AgentIdentity, identity_id)
        if not identity:
            raise ValueError(f"Identity not found: {identity_id}")
        
        # Get mapping
        mapping = await self.get_cross_chain_mapping_by_agent_chain(identity.agent_id, chain_id)
        if not mapping:
            raise ValueError(f"Mapping not found for agent {identity.agent_id} on chain {chain_id}")
        
        # Create verification record
        verification = IdentityVerification(
            agent_id=identity.agent_id,
            chain_id=chain_id,
            verification_type=verification_type,
            verifier_address=verifier_address.lower(),
            proof_hash=proof_hash,
            proof_data=proof_data,
            verification_result='approved',
            expires_at=datetime.utcnow() + timedelta(days=30)
        )
        
        self.session.add(verification)
        self.session.commit()
        self.session.refresh(verification)
        
        # Update mapping verification status
        mapping.is_verified = True
        mapping.verified_at = datetime.utcnow()
        mapping.verification_proof = proof_data
        self.session.commit()
        
        # Update identity verification status if this improves verification level
        if self._is_higher_verification_level(verification_type, identity.verification_level):
            identity.verification_level = verification_type
            identity.is_verified = True
            identity.verified_at = datetime.utcnow()
            self.session.commit()
        
        logger.info(f"Verified cross-chain identity: {identity_id} on chain {chain_id}")
        return verification
    
    async def revoke_verification(self, identity_id: str, chain_id: int, reason: str = "") -> bool:
        """Revoke verification for a specific chain"""
        
        mapping = await self.get_cross_chain_mapping_by_identity_chain(identity_id, chain_id)
        if not mapping:
            raise ValueError(f"Mapping not found for identity {identity_id} on chain {chain_id}")
        
        # Update mapping
        mapping.is_verified = False
        mapping.verified_at = None
        mapping.verification_proof = None
        mapping.updated_at = datetime.utcnow()
        
        # Add revocation to metadata
        if not mapping.chain_metadata:
            mapping.chain_metadata = {}
        mapping.chain_metadata['verification_revoked'] = True
        mapping.chain_metadata['revocation_reason'] = reason
        mapping.chain_metadata['revoked_at'] = datetime.utcnow().isoformat()
        
        self.session.commit()
        
        logger.warning(f"Revoked verification for identity {identity_id} on chain {chain_id}: {reason}")
        return True
    
    async def sync_agent_reputation(self, agent_id: str) -> Dict[int, float]:
        """Sync agent reputation across all chains"""
        
        # Get identity
        stmt = select(AgentIdentity).where(AgentIdentity.agent_id == agent_id)
        identity = self.session.exec(stmt).first()
        
        if not identity:
            raise ValueError(f"Agent identity not found: {agent_id}")
        
        # Get all cross-chain mappings
        stmt = select(CrossChainMapping).where(CrossChainMapping.agent_id == agent_id)
        mappings = self.session.exec(stmt).all()
        
        reputation_scores = {}
        
        for mapping in mappings:
            # For now, use the identity's base reputation
            # In a real implementation, this would fetch chain-specific reputation data
            reputation_scores[mapping.chain_id] = identity.reputation_score
        
        return reputation_scores
    
    async def get_cross_chain_mapping_by_agent_chain(self, agent_id: str, chain_id: int) -> Optional[CrossChainMapping]:
        """Get cross-chain mapping by agent ID and chain ID"""
        
        stmt = (
            select(CrossChainMapping)
            .where(
                CrossChainMapping.agent_id == agent_id,
                CrossChainMapping.chain_id == chain_id
            )
        )
        return self.session.exec(stmt).first()
    
    async def get_cross_chain_mapping_by_identity_chain(self, identity_id: str, chain_id: int) -> Optional[CrossChainMapping]:
        """Get cross-chain mapping by identity ID and chain ID"""
        
        identity = self.session.get(AgentIdentity, identity_id)
        if not identity:
            return None
        
        return await self.get_cross_chain_mapping_by_agent_chain(identity.agent_id, chain_id)
    
    async def get_cross_chain_mapping_by_address(self, chain_address: str, chain_id: int) -> Optional[CrossChainMapping]:
        """Get cross-chain mapping by chain address"""
        
        stmt = (
            select(CrossChainMapping)
            .where(
                CrossChainMapping.chain_address == chain_address.lower(),
                CrossChainMapping.chain_id == chain_id
            )
        )
        return self.session.exec(stmt).first()
    
    async def get_all_cross_chain_mappings(self, agent_id: str) -> List[CrossChainMapping]:
        """Get all cross-chain mappings for an agent"""
        
        stmt = select(CrossChainMapping).where(CrossChainMapping.agent_id == agent_id)
        return self.session.exec(stmt).all()
    
    async def get_verified_mappings(self, agent_id: str) -> List[CrossChainMapping]:
        """Get all verified cross-chain mappings for an agent"""
        
        stmt = (
            select(CrossChainMapping)
            .where(
                CrossChainMapping.agent_id == agent_id,
                CrossChainMapping.is_verified == True
            )
        )
        return self.session.exec(stmt).all()
    
    async def get_identity_verifications(self, agent_id: str, chain_id: Optional[int] = None) -> List[IdentityVerification]:
        """Get verification records for an agent"""
        
        stmt = select(IdentityVerification).where(IdentityVerification.agent_id == agent_id)
        
        if chain_id:
            stmt = stmt.where(IdentityVerification.chain_id == chain_id)
        
        return self.session.exec(stmt).all()
    
    async def migrate_agent_identity(
        self,
        agent_id: str,
        from_chain: int,
        to_chain: int,
        new_address: str,
        verifier_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """Migrate agent identity from one chain to another"""
        
        # Get source mapping
        source_mapping = await self.get_cross_chain_mapping_by_agent_chain(agent_id, from_chain)
        if not source_mapping:
            raise ValueError(f"Source mapping not found for agent {agent_id} on chain {from_chain}")
        
        # Check if target mapping already exists
        target_mapping = await self.get_cross_chain_mapping_by_agent_chain(agent_id, to_chain)
        
        migration_result = {
            'agent_id': agent_id,
            'from_chain': from_chain,
            'to_chain': to_chain,
            'source_address': source_mapping.chain_address,
            'target_address': new_address,
            'migration_successful': False
        }
        
        try:
            if target_mapping:
                # Update existing mapping
                await self.update_identity_mapping(agent_id, to_chain, new_address, verifier_address)
                migration_result['action'] = 'updated_existing'
            else:
                # Create new mapping
                await self.register_cross_chain_identity(
                    agent_id,
                    {to_chain: new_address},
                    verifier_address
                )
                migration_result['action'] = 'created_new'
            
            # Copy verification status if source was verified
            if source_mapping.is_verified and verifier_address:
                await self.verify_cross_chain_identity(
                    await self._get_identity_id(agent_id),
                    to_chain,
                    verifier_address,
                    self._generate_proof_hash(target_mapping or await self.get_cross_chain_mapping_by_agent_chain(agent_id, to_chain)),
                    {'migration': True, 'source_chain': from_chain}
                )
                migration_result['verification_copied'] = True
            else:
                migration_result['verification_copied'] = False
            
            migration_result['migration_successful'] = True
            
            logger.info(f"Successfully migrated agent {agent_id} from chain {from_chain} to {to_chain}")
            
        except Exception as e:
            migration_result['error'] = str(e)
            logger.error(f"Failed to migrate agent {agent_id} from chain {from_chain} to {to_chain}: {e}")
        
        return migration_result
    
    async def batch_verify_identities(
        self,
        verifications: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Batch verify multiple identities"""
        
        results = []
        
        for verification_data in verifications:
            try:
                result = await self.verify_cross_chain_identity(
                    verification_data['identity_id'],
                    verification_data['chain_id'],
                    verification_data['verifier_address'],
                    verification_data['proof_hash'],
                    verification_data.get('proof_data', {}),
                    verification_data.get('verification_type', VerificationType.BASIC)
                )
                
                results.append({
                    'identity_id': verification_data['identity_id'],
                    'chain_id': verification_data['chain_id'],
                    'success': True,
                    'verification_id': result.id
                })
                
            except Exception as e:
                results.append({
                    'identity_id': verification_data['identity_id'],
                    'chain_id': verification_data['chain_id'],
                    'success': False,
                    'error': str(e)
                })
        
        return results
    
    async def get_registry_statistics(self) -> Dict[str, Any]:
        """Get comprehensive registry statistics"""
        
        # Total identities
        identity_count = self.session.exec(select(AgentIdentity)).count()
        
        # Total mappings
        mapping_count = self.session.exec(select(CrossChainMapping)).count()
        
        # Verified mappings
        verified_mapping_count = self.session.exec(
            select(CrossChainMapping).where(CrossChainMapping.is_verified == True)
        ).count()
        
        # Total verifications
        verification_count = self.session.exec(select(IdentityVerification)).count()
        
        # Chain breakdown
        chain_breakdown = {}
        mappings = self.session.exec(select(CrossChainMapping)).all()
        
        for mapping in mappings:
            chain_name = self._get_chain_name(mapping.chain_id)
            if chain_name not in chain_breakdown:
                chain_breakdown[chain_name] = {
                    'total_mappings': 0,
                    'verified_mappings': 0,
                    'unique_agents': set()
                }
            
            chain_breakdown[chain_name]['total_mappings'] += 1
            if mapping.is_verified:
                chain_breakdown[chain_name]['verified_mappings'] += 1
            chain_breakdown[chain_name]['unique_agents'].add(mapping.agent_id)
        
        # Convert sets to counts
        for chain_data in chain_breakdown.values():
            chain_data['unique_agents'] = len(chain_data['unique_agents'])
        
        return {
            'total_identities': identity_count,
            'total_mappings': mapping_count,
            'verified_mappings': verified_mapping_count,
            'verification_rate': verified_mapping_count / max(mapping_count, 1),
            'total_verifications': verification_count,
            'supported_chains': len(chain_breakdown),
            'chain_breakdown': chain_breakdown
        }
    
    async def cleanup_expired_verifications(self) -> int:
        """Clean up expired verification records"""
        
        current_time = datetime.utcnow()
        
        # Find expired verifications
        stmt = select(IdentityVerification).where(
            IdentityVerification.expires_at < current_time
        )
        expired_verifications = self.session.exec(stmt).all()
        
        cleaned_count = 0
        
        for verification in expired_verifications:
            try:
                # Update corresponding mapping
                mapping = await self.get_cross_chain_mapping_by_agent_chain(
                    verification.agent_id,
                    verification.chain_id
                )
                
                if mapping and mapping.verified_at and mapping.verified_at == verification.expires_at:
                    mapping.is_verified = False
                    mapping.verified_at = None
                    mapping.verification_proof = None
                
                # Delete verification record
                self.session.delete(verification)
                cleaned_count += 1
                
            except Exception as e:
                logger.error(f"Error cleaning up verification {verification.id}: {e}")
        
        self.session.commit()
        
        logger.info(f"Cleaned up {cleaned_count} expired verification records")
        return cleaned_count
    
    def _get_chain_type(self, chain_id: int) -> ChainType:
        """Get chain type by chain ID"""
        chain_type_map = {
            1: ChainType.ETHEREUM,
            3: ChainType.ETHEREUM,  # Ropsten
            4: ChainType.ETHEREUM,  # Rinkeby
            5: ChainType.ETHEREUM,  # Goerli
            137: ChainType.POLYGON,
            80001: ChainType.POLYGON,  # Mumbai
            56: ChainType.BSC,
            97: ChainType.BSC,  # BSC Testnet
            42161: ChainType.ARBITRUM,
            421611: ChainType.ARBITRUM,  # Arbitrum Testnet
            10: ChainType.OPTIMISM,
            69: ChainType.OPTIMISM,  # Optimism Testnet
            43114: ChainType.AVALANCHE,
            43113: ChainType.AVALANCHE,  # Avalanche Testnet
        }
        
        return chain_type_map.get(chain_id, ChainType.CUSTOM)
    
    def _get_chain_name(self, chain_id: int) -> str:
        """Get chain name by chain ID"""
        chain_name_map = {
            1: 'Ethereum Mainnet',
            3: 'Ethereum Ropsten',
            4: 'Ethereum Rinkeby',
            5: 'Ethereum Goerli',
            137: 'Polygon Mainnet',
            80001: 'Polygon Mumbai',
            56: 'BSC Mainnet',
            97: 'BSC Testnet',
            42161: 'Arbitrum One',
            421611: 'Arbitrum Testnet',
            10: 'Optimism',
            69: 'Optimism Testnet',
            43114: 'Avalanche C-Chain',
            43113: 'Avalanche Testnet'
        }
        
        return chain_name_map.get(chain_id, f'Chain {chain_id}')
    
    def _generate_proof_hash(self, mapping: CrossChainMapping) -> str:
        """Generate proof hash for a mapping"""
        
        proof_data = {
            'agent_id': mapping.agent_id,
            'chain_id': mapping.chain_id,
            'chain_address': mapping.chain_address,
            'created_at': mapping.created_at.isoformat(),
            'nonce': str(uuid4())
        }
        
        proof_string = json.dumps(proof_data, sort_keys=True)
        return hashlib.sha256(proof_string.encode()).hexdigest()
    
    def _is_higher_verification_level(
        self,
        new_level: VerificationType,
        current_level: VerificationType
    ) -> bool:
        """Check if new verification level is higher than current"""
        
        level_hierarchy = {
            VerificationType.BASIC: 1,
            VerificationType.ADVANCED: 2,
            VerificationType.ZERO_KNOWLEDGE: 3,
            VerificationType.MULTI_SIGNATURE: 4
        }
        
        return level_hierarchy.get(new_level, 0) > level_hierarchy.get(current_level, 0)
    
    async def _get_identity_id(self, agent_id: str) -> str:
        """Get identity ID by agent ID"""
        
        stmt = select(AgentIdentity).where(AgentIdentity.agent_id == agent_id)
        identity = self.session.exec(stmt).first()
        
        if not identity:
            raise ValueError(f"Identity not found for agent: {agent_id}")
        
        return identity.id
