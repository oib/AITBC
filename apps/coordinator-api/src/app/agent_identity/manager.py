"""
Agent Identity Manager Implementation
High-level manager for agent identity operations and cross-chain management
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from uuid import uuid4
import json
import logging
logger = logging.getLogger(__name__)

from sqlmodel import Session, select, update, delete
from sqlalchemy.exc import SQLAlchemyError

from ..domain.agent_identity import (
    AgentIdentity, CrossChainMapping, IdentityVerification, AgentWallet,
    IdentityStatus, VerificationType, ChainType,
    AgentIdentityCreate, AgentIdentityUpdate, CrossChainMappingCreate,
    CrossChainMappingUpdate, IdentityVerificationCreate, AgentWalletCreate,
    AgentWalletUpdate
)

from .core import AgentIdentityCore
from .registry import CrossChainRegistry
from .wallet_adapter import MultiChainWalletAdapter




class AgentIdentityManager:
    """High-level manager for agent identity operations"""
    
    def __init__(self, session: Session):
        self.session = session
        self.core = AgentIdentityCore(session)
        self.registry = CrossChainRegistry(session)
        self.wallet_adapter = MultiChainWalletAdapter(session)
    
    async def create_agent_identity(
        self,
        owner_address: str,
        chains: List[int],
        display_name: str = "",
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Create a complete agent identity with cross-chain mappings"""
        
        # Generate agent ID
        agent_id = f"agent_{uuid4().hex[:12]}"
        
        # Create identity request
        identity_request = AgentIdentityCreate(
            agent_id=agent_id,
            owner_address=owner_address,
            display_name=display_name,
            description=description,
            supported_chains=chains,
            primary_chain=chains[0] if chains else 1,
            metadata=metadata or {},
            tags=tags or []
        )
        
        # Create identity
        identity = await self.core.create_identity(identity_request)
        
        # Create cross-chain mappings
        chain_mappings = {}
        for chain_id in chains:
            # Generate a mock address for now
            chain_address = f"0x{uuid4().hex[:40]}"
            chain_mappings[chain_id] = chain_address
        
        # Register cross-chain identities
        registration_result = await self.registry.register_cross_chain_identity(
            agent_id,
            chain_mappings,
            owner_address,  # Self-verify
            VerificationType.BASIC
        )
        
        # Create wallets for each chain
        wallet_results = []
        for chain_id in chains:
            try:
                wallet = await self.wallet_adapter.create_agent_wallet(agent_id, chain_id, owner_address)
                wallet_results.append({
                    'chain_id': chain_id,
                    'wallet_id': wallet.id,
                    'wallet_address': wallet.chain_address,
                    'success': True
                })
            except Exception as e:
                logger.error(f"Failed to create wallet for chain {chain_id}: {e}")
                wallet_results.append({
                    'chain_id': chain_id,
                    'error': str(e),
                    'success': False
                })
        
        return {
            'identity_id': identity.id,
            'agent_id': agent_id,
            'owner_address': owner_address,
            'display_name': display_name,
            'supported_chains': chains,
            'primary_chain': identity.primary_chain,
            'registration_result': registration_result,
            'wallet_results': wallet_results,
            'created_at': identity.created_at.isoformat()
        }
    
    async def migrate_agent_identity(
        self,
        agent_id: str,
        from_chain: int,
        to_chain: int,
        new_address: str,
        verifier_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """Migrate agent identity from one chain to another"""
        
        try:
            # Perform migration
            migration_result = await self.registry.migrate_agent_identity(
                agent_id,
                from_chain,
                to_chain,
                new_address,
                verifier_address
            )
            
            # Create wallet on new chain if migration successful
            if migration_result['migration_successful']:
                try:
                    identity = await self.core.get_identity_by_agent_id(agent_id)
                    if identity:
                        wallet = await self.wallet_adapter.create_agent_wallet(
                            agent_id,
                            to_chain,
                            identity.owner_address
                        )
                        migration_result['wallet_created'] = True
                        migration_result['wallet_id'] = wallet.id
                        migration_result['wallet_address'] = wallet.chain_address
                    else:
                        migration_result['wallet_created'] = False
                        migration_result['error'] = 'Identity not found'
                except Exception as e:
                    migration_result['wallet_created'] = False
                    migration_result['wallet_error'] = str(e)
            else:
                migration_result['wallet_created'] = False
            
            return migration_result
            
        except Exception as e:
            logger.error(f"Failed to migrate agent {agent_id} from chain {from_chain} to {to_chain}: {e}")
            return {
                'agent_id': agent_id,
                'from_chain': from_chain,
                'to_chain': to_chain,
                'migration_successful': False,
                'error': str(e)
            }
    
    async def sync_agent_reputation(self, agent_id: str) -> Dict[str, Any]:
        """Sync agent reputation across all chains"""
        
        try:
            # Get identity
            identity = await self.core.get_identity_by_agent_id(agent_id)
            if not identity:
                raise ValueError(f"Agent identity not found: {agent_id}")
            
            # Get cross-chain reputation scores
            reputation_scores = await self.registry.sync_agent_reputation(agent_id)
            
            # Calculate aggregated reputation
            if reputation_scores:
                # Weighted average based on verification status
                verified_mappings = await self.registry.get_verified_mappings(agent_id)
                verified_chains = {m.chain_id for m in verified_mappings}
                
                total_weight = 0
                weighted_sum = 0
                
                for chain_id, score in reputation_scores.items():
                    weight = 2.0 if chain_id in verified_chains else 1.0
                    total_weight += weight
                    weighted_sum += score * weight
                
                aggregated_score = weighted_sum / total_weight if total_weight > 0 else 0
                
                # Update identity reputation
                await self.core.update_reputation(agent_id, True, 0)  # This will recalculate based on new data
                identity.reputation_score = aggregated_score
                identity.updated_at = datetime.utcnow()
                self.session.commit()
            else:
                aggregated_score = identity.reputation_score
            
            return {
                'agent_id': agent_id,
                'aggregated_reputation': aggregated_score,
                'chain_reputations': reputation_scores,
                'verified_chains': list(verified_chains) if 'verified_chains' in locals() else [],
                'sync_timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to sync reputation for agent {agent_id}: {e}")
            return {
                'agent_id': agent_id,
                'sync_successful': False,
                'error': str(e)
            }
    
    async def get_agent_identity_summary(self, agent_id: str) -> Dict[str, Any]:
        """Get comprehensive summary of agent identity"""
        
        try:
            # Get identity
            identity = await self.core.get_identity_by_agent_id(agent_id)
            if not identity:
                return {'agent_id': agent_id, 'error': 'Identity not found'}
            
            # Get cross-chain mappings
            mappings = await self.registry.get_all_cross_chain_mappings(agent_id)
            
            # Get wallet statistics
            wallet_stats = await self.wallet_adapter.get_wallet_statistics(agent_id)
            
            # Get identity statistics
            identity_stats = await self.core.get_identity_statistics(identity.id)
            
            # Get verification status
            verified_mappings = await self.registry.get_verified_mappings(agent_id)
            
            return {
                'identity': {
                    'id': identity.id,
                    'agent_id': identity.agent_id,
                    'owner_address': identity.owner_address,
                    'display_name': identity.display_name,
                    'description': identity.description,
                    'status': identity.status,
                    'verification_level': identity.verification_level,
                    'is_verified': identity.is_verified,
                    'verified_at': identity.verified_at.isoformat() if identity.verified_at else None,
                    'reputation_score': identity.reputation_score,
                    'supported_chains': identity.supported_chains,
                    'primary_chain': identity.primary_chain,
                    'total_transactions': identity.total_transactions,
                    'successful_transactions': identity.successful_transactions,
                    'success_rate': identity.successful_transactions / max(identity.total_transactions, 1),
                    'created_at': identity.created_at.isoformat(),
                    'updated_at': identity.updated_at.isoformat(),
                    'last_activity': identity.last_activity.isoformat() if identity.last_activity else None,
                    'identity_data': identity.identity_data,
                    'tags': identity.tags
                },
                'cross_chain': {
                    'total_mappings': len(mappings),
                    'verified_mappings': len(verified_mappings),
                    'verification_rate': len(verified_mappings) / max(len(mappings), 1),
                    'mappings': [
                        {
                            'chain_id': m.chain_id,
                            'chain_type': m.chain_type,
                            'chain_address': m.chain_address,
                            'is_verified': m.is_verified,
                            'verified_at': m.verified_at.isoformat() if m.verified_at else None,
                            'wallet_address': m.wallet_address,
                            'transaction_count': m.transaction_count,
                            'last_transaction': m.last_transaction.isoformat() if m.last_transaction else None
                        }
                        for m in mappings
                    ]
                },
                'wallets': wallet_stats,
                'statistics': identity_stats
            }
            
        except Exception as e:
            logger.error(f"Failed to get identity summary for agent {agent_id}: {e}")
            return {
                'agent_id': agent_id,
                'error': str(e)
            }
    
    async def update_agent_identity(
        self,
        agent_id: str,
        updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update agent identity and related components"""
        
        try:
            # Get identity
            identity = await self.core.get_identity_by_agent_id(agent_id)
            if not identity:
                raise ValueError(f"Agent identity not found: {agent_id}")
            
            # Update identity
            update_request = AgentIdentityUpdate(**updates)
            updated_identity = await self.core.update_identity(identity.id, update_request)
            
            # Handle cross-chain updates if provided
            cross_chain_updates = updates.get('cross_chain_updates', {})
            if cross_chain_updates:
                for chain_id, chain_update in cross_chain_updates.items():
                    try:
                        await self.registry.update_identity_mapping(
                            agent_id,
                            int(chain_id),
                            chain_update.get('new_address'),
                            chain_update.get('verifier_address')
                        )
                    except Exception as e:
                        logger.error(f"Failed to update cross-chain mapping for chain {chain_id}: {e}")
            
            # Handle wallet updates if provided
            wallet_updates = updates.get('wallet_updates', {})
            if wallet_updates:
                for chain_id, wallet_update in wallet_updates.items():
                    try:
                        wallet_request = AgentWalletUpdate(**wallet_update)
                        await self.wallet_adapter.update_agent_wallet(agent_id, int(chain_id), wallet_request)
                    except Exception as e:
                        logger.error(f"Failed to update wallet for chain {chain_id}: {e}")
            
            return {
                'agent_id': agent_id,
                'identity_id': updated_identity.id,
                'updated_fields': list(updates.keys()),
                'updated_at': updated_identity.updated_at.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to update agent identity {agent_id}: {e}")
            return {
                'agent_id': agent_id,
                'update_successful': False,
                'error': str(e)
            }
    
    async def deactivate_agent_identity(self, agent_id: str, reason: str = "") -> bool:
        """Deactivate an agent identity across all chains"""
        
        try:
            # Get identity
            identity = await self.core.get_identity_by_agent_id(agent_id)
            if not identity:
                raise ValueError(f"Agent identity not found: {agent_id}")
            
            # Deactivate identity
            await self.core.suspend_identity(identity.id, reason)
            
            # Deactivate all wallets
            wallets = await self.wallet_adapter.get_all_agent_wallets(agent_id)
            for wallet in wallets:
                await self.wallet_adapter.deactivate_wallet(agent_id, wallet.chain_id)
            
            # Revoke all verifications
            mappings = await self.registry.get_all_cross_chain_mappings(agent_id)
            for mapping in mappings:
                await self.registry.revoke_verification(identity.id, mapping.chain_id, reason)
            
            logger.info(f"Deactivated agent identity: {agent_id}, reason: {reason}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to deactivate agent identity {agent_id}: {e}")
            return False
    
    async def search_agent_identities(
        self,
        query: str = "",
        chains: Optional[List[int]] = None,
        status: Optional[IdentityStatus] = None,
        verification_level: Optional[VerificationType] = None,
        min_reputation: Optional[float] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """Search agent identities with advanced filters"""
        
        try:
            # Base search
            identities = await self.core.search_identities(
                query=query,
                status=status,
                verification_level=verification_level,
                limit=limit,
                offset=offset
            )
            
            # Apply additional filters
            filtered_identities = []
            
            for identity in identities:
                # Chain filter
                if chains:
                    identity_chains = [int(chain_id) for chain_id in identity.supported_chains]
                    if not any(chain in identity_chains for chain in chains):
                        continue
                
                # Reputation filter
                if min_reputation is not None and identity.reputation_score < min_reputation:
                    continue
                
                filtered_identities.append(identity)
            
            # Get additional details for each identity
            results = []
            for identity in filtered_identities:
                try:
                    # Get cross-chain mappings
                    mappings = await self.registry.get_all_cross_chain_mappings(identity.agent_id)
                    verified_count = len([m for m in mappings if m.is_verified])
                    
                    # Get wallet stats
                    wallet_stats = await self.wallet_adapter.get_wallet_statistics(identity.agent_id)
                    
                    results.append({
                        'identity_id': identity.id,
                        'agent_id': identity.agent_id,
                        'owner_address': identity.owner_address,
                        'display_name': identity.display_name,
                        'description': identity.description,
                        'status': identity.status,
                        'verification_level': identity.verification_level,
                        'is_verified': identity.is_verified,
                        'reputation_score': identity.reputation_score,
                        'supported_chains': identity.supported_chains,
                        'primary_chain': identity.primary_chain,
                        'total_transactions': identity.total_transactions,
                        'success_rate': identity.successful_transactions / max(identity.total_transactions, 1),
                        'cross_chain_mappings': len(mappings),
                        'verified_mappings': verified_count,
                        'total_wallets': wallet_stats['total_wallets'],
                        'total_balance': wallet_stats['total_balance'],
                        'created_at': identity.created_at.isoformat(),
                        'last_activity': identity.last_activity.isoformat() if identity.last_activity else None
                    })
                except Exception as e:
                    logger.error(f"Error getting details for identity {identity.id}: {e}")
                    continue
            
            return {
                'results': results,
                'total_count': len(results),
                'query': query,
                'filters': {
                    'chains': chains,
                    'status': status,
                    'verification_level': verification_level,
                    'min_reputation': min_reputation
                },
                'pagination': {
                    'limit': limit,
                    'offset': offset
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to search agent identities: {e}")
            return {
                'results': [],
                'total_count': 0,
                'error': str(e)
            }
    
    async def get_registry_health(self) -> Dict[str, Any]:
        """Get health status of the identity registry"""
        
        try:
            # Get registry statistics
            registry_stats = await self.registry.get_registry_statistics()
            
            # Clean up expired verifications
            cleaned_count = await self.registry.cleanup_expired_verifications()
            
            # Get supported chains
            supported_chains = self.wallet_adapter.get_supported_chains()
            
            # Check for any issues
            issues = []
            
            if registry_stats['verification_rate'] < 0.5:
                issues.append('Low verification rate')
            
            if registry_stats['total_mappings'] == 0:
                issues.append('No cross-chain mappings found')
            
            return {
                'status': 'healthy' if not issues else 'degraded',
                'registry_statistics': registry_stats,
                'supported_chains': supported_chains,
                'cleaned_verifications': cleaned_count,
                'issues': issues,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get registry health: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
    
    async def export_agent_identity(self, agent_id: str, format: str = 'json') -> Dict[str, Any]:
        """Export agent identity data for backup or migration"""
        
        try:
            # Get complete identity summary
            summary = await self.get_agent_identity_summary(agent_id)
            
            if 'error' in summary:
                return summary
            
            # Prepare export data
            export_data = {
                'export_version': '1.0',
                'export_timestamp': datetime.utcnow().isoformat(),
                'agent_id': agent_id,
                'identity': summary['identity'],
                'cross_chain_mappings': summary['cross_chain']['mappings'],
                'wallet_statistics': summary['wallets'],
                'identity_statistics': summary['statistics']
            }
            
            if format.lower() == 'json':
                return export_data
            else:
                # For other formats, would need additional implementation
                return {'error': f'Format {format} not supported'}
            
        except Exception as e:
            logger.error(f"Failed to export agent identity {agent_id}: {e}")
            return {
                'agent_id': agent_id,
                'export_successful': False,
                'error': str(e)
            }
    
    async def import_agent_identity(self, export_data: Dict[str, Any]) -> Dict[str, Any]:
        """Import agent identity data from backup or migration"""
        
        try:
            # Validate export data
            if 'export_version' not in export_data or 'agent_id' not in export_data:
                raise ValueError('Invalid export data format')
            
            agent_id = export_data['agent_id']
            identity_data = export_data['identity']
            
            # Check if identity already exists
            existing = await self.core.get_identity_by_agent_id(agent_id)
            if existing:
                return {
                    'agent_id': agent_id,
                    'import_successful': False,
                    'error': 'Identity already exists'
                }
            
            # Create identity
            identity_request = AgentIdentityCreate(
                agent_id=agent_id,
                owner_address=identity_data['owner_address'],
                display_name=identity_data['display_name'],
                description=identity_data['description'],
                supported_chains=[int(chain_id) for chain_id in identity_data['supported_chains']],
                primary_chain=identity_data['primary_chain'],
                metadata=identity_data['metadata'],
                tags=identity_data['tags']
            )
            
            identity = await self.core.create_identity(identity_request)
            
            # Restore cross-chain mappings
            mappings = export_data.get('cross_chain_mappings', [])
            chain_mappings = {}
            
            for mapping in mappings:
                chain_mappings[mapping['chain_id']] = mapping['chain_address']
            
            if chain_mappings:
                await self.registry.register_cross_chain_identity(
                    agent_id,
                    chain_mappings,
                    identity_data['owner_address'],
                    VerificationType.BASIC
                )
            
            # Restore wallets
            for chain_id in chain_mappings.keys():
                try:
                    await self.wallet_adapter.create_agent_wallet(
                        agent_id,
                        chain_id,
                        identity_data['owner_address']
                    )
                except Exception as e:
                    logger.error(f"Failed to restore wallet for chain {chain_id}: {e}")
            
            return {
                'agent_id': agent_id,
                'identity_id': identity.id,
                'import_successful': True,
                'restored_mappings': len(chain_mappings),
                'import_timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to import agent identity: {e}")
            return {
                'import_successful': False,
                'error': str(e)
            }
