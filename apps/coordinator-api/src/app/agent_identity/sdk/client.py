"""
AITBC Agent Identity SDK Client
Main client class for interacting with the Agent Identity API
"""

import asyncio
import json
import aiohttp
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from urllib.parse import urljoin

from .models import *
from .exceptions import *


class AgentIdentityClient:
    """Main client for the AITBC Agent Identity SDK"""
    
    def __init__(
        self,
        base_url: str = "http://localhost:8000/v1",
        api_key: Optional[str] = None,
        timeout: int = 30,
        max_retries: int = 3
    ):
        """
        Initialize the Agent Identity client
        
        Args:
            base_url: Base URL for the API
            api_key: Optional API key for authentication
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for failed requests
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_retries = max_retries
        self.session = None
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self._ensure_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
    
    async def _ensure_session(self):
        """Ensure HTTP session is created"""
        if self.session is None or self.session.closed:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            self.session = aiohttp.ClientSession(
                headers=headers,
                timeout=self.timeout
            )
    
    async def close(self):
        """Close the HTTP session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Make HTTP request with retry logic"""
        await self._ensure_session()
        
        url = urljoin(self.base_url, endpoint)
        
        for attempt in range(self.max_retries + 1):
            try:
                async with self.session.request(
                    method,
                    url,
                    json=data,
                    params=params,
                    **kwargs
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 201:
                        return await response.json()
                    elif response.status == 400:
                        error_data = await response.json()
                        raise ValidationError(error_data.get('detail', 'Bad request'))
                    elif response.status == 401:
                        raise AuthenticationError('Authentication failed')
                    elif response.status == 403:
                        raise AuthenticationError('Access forbidden')
                    elif response.status == 404:
                        raise AgentIdentityError('Resource not found')
                    elif response.status == 429:
                        raise RateLimitError('Rate limit exceeded')
                    elif response.status >= 500:
                        if attempt < self.max_retries:
                            await asyncio.sleep(2 ** attempt)  # Exponential backoff
                            continue
                        raise NetworkError(f'Server error: {response.status}')
                    else:
                        raise AgentIdentityError(f'HTTP {response.status}: {await response.text()}')
            
            except aiohttp.ClientError as e:
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise NetworkError(f'Network error: {str(e)}')
    
    # Identity Management Methods
    
    async def create_identity(
        self,
        owner_address: str,
        chains: List[int],
        display_name: str = "",
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None
    ) -> CreateIdentityResponse:
        """Create a new agent identity with cross-chain mappings"""
        
        request_data = {
            'owner_address': owner_address,
            'chains': chains,
            'display_name': display_name,
            'description': description,
            'metadata': metadata or {},
            'tags': tags or []
        }
        
        response = await self._request('POST', '/agent-identity/identities', request_data)
        
        return CreateIdentityResponse(
            identity_id=response['identity_id'],
            agent_id=response['agent_id'],
            owner_address=response['owner_address'],
            display_name=response['display_name'],
            supported_chains=response['supported_chains'],
            primary_chain=response['primary_chain'],
            registration_result=response['registration_result'],
            wallet_results=response['wallet_results'],
            created_at=response['created_at']
        )
    
    async def get_identity(self, agent_id: str) -> Dict[str, Any]:
        """Get comprehensive agent identity summary"""
        response = await self._request('GET', f'/agent-identity/identities/{agent_id}')
        return response
    
    async def update_identity(
        self,
        agent_id: str,
        updates: Dict[str, Any]
    ) -> UpdateIdentityResponse:
        """Update agent identity and related components"""
        response = await self._request('PUT', f'/agent-identity/identities/{agent_id}', updates)
        
        return UpdateIdentityResponse(
            agent_id=response['agent_id'],
            identity_id=response['identity_id'],
            updated_fields=response['updated_fields'],
            updated_at=response['updated_at']
        )
    
    async def deactivate_identity(self, agent_id: str, reason: str = "") -> bool:
        """Deactivate an agent identity across all chains"""
        request_data = {'reason': reason}
        await self._request('POST', f'/agent-identity/identities/{agent_id}/deactivate', request_data)
        return True
    
    # Cross-Chain Methods
    
    async def register_cross_chain_mappings(
        self,
        agent_id: str,
        chain_mappings: Dict[int, str],
        verifier_address: Optional[str] = None,
        verification_type: VerificationType = VerificationType.BASIC
    ) -> Dict[str, Any]:
        """Register cross-chain identity mappings"""
        request_data = {
            'chain_mappings': chain_mappings,
            'verifier_address': verifier_address,
            'verification_type': verification_type.value
        }
        
        response = await self._request(
            'POST',
            f'/agent-identity/identities/{agent_id}/cross-chain/register',
            request_data
        )
        
        return response
    
    async def get_cross_chain_mappings(self, agent_id: str) -> List[CrossChainMapping]:
        """Get all cross-chain mappings for an agent"""
        response = await self._request('GET', f'/agent-identity/identities/{agent_id}/cross-chain/mapping')
        
        return [
            CrossChainMapping(
                id=m['id'],
                agent_id=m['agent_id'],
                chain_id=m['chain_id'],
                chain_type=ChainType(m['chain_type']),
                chain_address=m['chain_address'],
                is_verified=m['is_verified'],
                verified_at=datetime.fromisoformat(m['verified_at']) if m['verified_at'] else None,
                wallet_address=m['wallet_address'],
                wallet_type=m['wallet_type'],
                chain_metadata=m['chain_metadata'],
                last_transaction=datetime.fromisoformat(m['last_transaction']) if m['last_transaction'] else None,
                transaction_count=m['transaction_count'],
                created_at=datetime.fromisoformat(m['created_at']),
                updated_at=datetime.fromisoformat(m['updated_at'])
            )
            for m in response
        ]
    
    async def verify_identity(
        self,
        agent_id: str,
        chain_id: int,
        verifier_address: str,
        proof_hash: str,
        proof_data: Dict[str, Any],
        verification_type: VerificationType = VerificationType.BASIC
    ) -> VerifyIdentityResponse:
        """Verify identity on a specific blockchain"""
        request_data = {
            'verifier_address': verifier_address,
            'proof_hash': proof_hash,
            'proof_data': proof_data,
            'verification_type': verification_type.value
        }
        
        response = await self._request(
            'POST',
            f'/agent-identity/identities/{agent_id}/cross-chain/{chain_id}/verify',
            request_data
        )
        
        return VerifyIdentityResponse(
            verification_id=response['verification_id'],
            agent_id=response['agent_id'],
            chain_id=response['chain_id'],
            verification_type=VerificationType(response['verification_type']),
            verified=response['verified'],
            timestamp=response['timestamp']
        )
    
    async def migrate_identity(
        self,
        agent_id: str,
        from_chain: int,
        to_chain: int,
        new_address: str,
        verifier_address: Optional[str] = None
    ) -> MigrationResponse:
        """Migrate agent identity from one chain to another"""
        request_data = {
            'from_chain': from_chain,
            'to_chain': to_chain,
            'new_address': new_address,
            'verifier_address': verifier_address
        }
        
        response = await self._request(
            'POST',
            f'/agent-identity/identities/{agent_id}/migrate',
            request_data
        )
        
        return MigrationResponse(
            agent_id=response['agent_id'],
            from_chain=response['from_chain'],
            to_chain=response['to_chain'],
            source_address=response['source_address'],
            target_address=response['target_address'],
            migration_successful=response['migration_successful'],
            action=response.get('action'),
            verification_copied=response.get('verification_copied'),
            wallet_created=response.get('wallet_created'),
            wallet_id=response.get('wallet_id'),
            wallet_address=response.get('wallet_address'),
            error=response.get('error')
        )
    
    # Wallet Methods
    
    async def create_wallet(
        self,
        agent_id: str,
        chain_id: int,
        owner_address: Optional[str] = None
    ) -> AgentWallet:
        """Create an agent wallet on a specific blockchain"""
        request_data = {
            'chain_id': chain_id,
            'owner_address': owner_address or ''
        }
        
        response = await self._request(
            'POST',
            f'/agent-identity/identities/{agent_id}/wallets',
            request_data
        )
        
        return AgentWallet(
            id=response['wallet_id'],
            agent_id=response['agent_id'],
            chain_id=response['chain_id'],
            chain_address=response['chain_address'],
            wallet_type=response['wallet_type'],
            contract_address=response['contract_address'],
            balance=0.0,  # Will be updated separately
            spending_limit=0.0,
            total_spent=0.0,
            is_active=True,
            permissions=[],
            requires_multisig=False,
            multisig_threshold=1,
            multisig_signers=[],
            last_transaction=None,
            transaction_count=0,
            created_at=datetime.fromisoformat(response['created_at']),
            updated_at=datetime.fromisoformat(response['created_at'])
        )
    
    async def get_wallet_balance(self, agent_id: str, chain_id: int) -> float:
        """Get wallet balance for an agent on a specific chain"""
        response = await self._request('GET', f'/agent-identity/identities/{agent_id}/wallets/{chain_id}/balance')
        return float(response['balance'])
    
    async def execute_transaction(
        self,
        agent_id: str,
        chain_id: int,
        to_address: str,
        amount: float,
        data: Optional[Dict[str, Any]] = None
    ) -> TransactionResponse:
        """Execute a transaction from agent wallet"""
        request_data = {
            'to_address': to_address,
            'amount': amount,
            'data': data
        }
        
        response = await self._request(
            'POST',
            f'/agent-identity/identities/{agent_id}/wallets/{chain_id}/transactions',
            request_data
        )
        
        return TransactionResponse(
            transaction_hash=response['transaction_hash'],
            from_address=response['from_address'],
            to_address=response['to_address'],
            amount=response['amount'],
            gas_used=response['gas_used'],
            gas_price=response['gas_price'],
            status=response['status'],
            block_number=response['block_number'],
            timestamp=response['timestamp']
        )
    
    async def get_transaction_history(
        self,
        agent_id: str,
        chain_id: int,
        limit: int = 50,
        offset: int = 0
    ) -> List[Transaction]:
        """Get transaction history for agent wallet"""
        params = {'limit': limit, 'offset': offset}
        response = await self._request(
            'GET',
            f'/agent-identity/identities/{agent_id}/wallets/{chain_id}/transactions',
            params=params
        )
        
        return [
            Transaction(
                hash=tx['hash'],
                from_address=tx['from_address'],
                to_address=tx['to_address'],
                amount=tx['amount'],
                gas_used=tx['gas_used'],
                gas_price=tx['gas_price'],
                status=tx['status'],
                block_number=tx['block_number'],
                timestamp=datetime.fromisoformat(tx['timestamp'])
            )
            for tx in response
        ]
    
    async def get_all_wallets(self, agent_id: str) -> Dict[str, Any]:
        """Get all wallets for an agent across all chains"""
        response = await self._request('GET', f'/agent-identity/identities/{agent_id}/wallets')
        return response
    
    # Search and Discovery Methods
    
    async def search_identities(
        self,
        query: str = "",
        chains: Optional[List[int]] = None,
        status: Optional[IdentityStatus] = None,
        verification_level: Optional[VerificationType] = None,
        min_reputation: Optional[float] = None,
        limit: int = 50,
        offset: int = 0
    ) -> SearchResponse:
        """Search agent identities with advanced filters"""
        params = {
            'query': query,
            'limit': limit,
            'offset': offset
        }
        
        if chains:
            params['chains'] = chains
        if status:
            params['status'] = status.value
        if verification_level:
            params['verification_level'] = verification_level.value
        if min_reputation is not None:
            params['min_reputation'] = min_reputation
        
        response = await self._request('GET', '/agent-identity/identities/search', params=params)
        
        return SearchResponse(
            results=response['results'],
            total_count=response['total_count'],
            query=response['query'],
            filters=response['filters'],
            pagination=response['pagination']
        )
    
    async def sync_reputation(self, agent_id: str) -> SyncReputationResponse:
        """Sync agent reputation across all chains"""
        response = await self._request('POST', f'/agent-identity/identities/{agent_id}/sync-reputation')
        
        return SyncReputationResponse(
            agent_id=response['agent_id'],
            aggregated_reputation=response['aggregated_reputation'],
            chain_reputations=response['chain_reputations'],
            verified_chains=response['verified_chains'],
            sync_timestamp=response['sync_timestamp']
        )
    
    # Utility Methods
    
    async def get_registry_health(self) -> RegistryHealth:
        """Get health status of the identity registry"""
        response = await self._request('GET', '/agent-identity/registry/health')
        
        return RegistryHealth(
            status=response['status'],
            registry_statistics=IdentityStatistics(**response['registry_statistics']),
            supported_chains=[ChainConfig(**chain) for chain in response['supported_chains']],
            cleaned_verifications=response['cleaned_verifications'],
            issues=response['issues'],
            timestamp=datetime.fromisoformat(response['timestamp'])
        )
    
    async def get_supported_chains(self) -> List[ChainConfig]:
        """Get list of supported blockchains"""
        response = await self._request('GET', '/agent-identity/chains/supported')
        
        return [ChainConfig(**chain) for chain in response]
    
    async def export_identity(self, agent_id: str, format: str = 'json') -> Dict[str, Any]:
        """Export agent identity data for backup or migration"""
        request_data = {'format': format}
        response = await self._request('POST', f'/agent-identity/identities/{agent_id}/export', request_data)
        return response
    
    async def import_identity(self, export_data: Dict[str, Any]) -> Dict[str, Any]:
        """Import agent identity data from backup or migration"""
        response = await self._request('POST', '/agent-identity/identities/import', export_data)
        return response
    
    async def resolve_identity(self, agent_id: str, chain_id: int) -> str:
        """Resolve agent identity to chain-specific address"""
        response = await self._request('GET', f'/agent-identity/identities/{agent_id}/resolve/{chain_id}')
        return response['address']
    
    async def resolve_address(self, chain_address: str, chain_id: int) -> str:
        """Resolve chain address back to agent ID"""
        response = await self._request('GET', f'/agent-identity/address/{chain_address}/resolve/{chain_id}')
        return response['agent_id']


# Convenience functions for common operations

async def create_identity_with_wallets(
    client: AgentIdentityClient,
    owner_address: str,
    chains: List[int],
    display_name: str = "",
    description: str = ""
) -> CreateIdentityResponse:
    """Create identity and ensure wallets are created on all chains"""
    
    # Create identity
    identity_response = await client.create_identity(
        owner_address=owner_address,
        chains=chains,
        display_name=display_name,
        description=description
    )
    
    # Verify wallets were created
    wallet_results = identity_response.wallet_results
    failed_wallets = [w for w in wallet_results if not w.get('success', False)]
    
    if failed_wallets:
        print(f"Warning: {len(failed_wallets)} wallets failed to create")
        for wallet in failed_wallets:
            print(f"  Chain {wallet['chain_id']}: {wallet.get('error', 'Unknown error')}")
    
    return identity_response


async def verify_identity_on_all_chains(
    client: AgentIdentityClient,
    agent_id: str,
    verifier_address: str,
    proof_data_template: Dict[str, Any]
) -> List[VerifyIdentityResponse]:
    """Verify identity on all supported chains"""
    
    # Get cross-chain mappings
    mappings = await client.get_cross_chain_mappings(agent_id)
    
    verification_results = []
    
    for mapping in mappings:
        try:
            # Generate proof hash for this mapping
            proof_data = {
                **proof_data_template,
                'chain_id': mapping.chain_id,
                'chain_address': mapping.chain_address,
                'chain_type': mapping.chain_type.value
            }
            
            # Create simple proof hash (in real implementation, this would be cryptographic)
            import hashlib
            proof_string = json.dumps(proof_data, sort_keys=True)
            proof_hash = hashlib.sha256(proof_string.encode()).hexdigest()
            
            # Verify identity
            result = await client.verify_identity(
                agent_id=agent_id,
                chain_id=mapping.chain_id,
                verifier_address=verifier_address,
                proof_hash=proof_hash,
                proof_data=proof_data
            )
            
            verification_results.append(result)
            
        except Exception as e:
            print(f"Failed to verify on chain {mapping.chain_id}: {e}")
    
    return verification_results


async def get_identity_summary(
    client: AgentIdentityClient,
    agent_id: str
) -> Dict[str, Any]:
    """Get comprehensive identity summary with additional calculations"""
    
    # Get basic identity info
    identity = await client.get_identity(agent_id)
    
    # Get wallet statistics
    wallets = await client.get_all_wallets(agent_id)
    
    # Calculate additional metrics
    total_balance = wallets['statistics']['total_balance']
    total_wallets = wallets['statistics']['total_wallets']
    active_wallets = wallets['statistics']['active_wallets']
    
    return {
        'identity': identity['identity'],
        'cross_chain': identity['cross_chain'],
        'wallets': wallets,
        'metrics': {
            'total_balance': total_balance,
            'total_wallets': total_wallets,
            'active_wallets': active_wallets,
            'wallet_activity_rate': active_wallets / max(total_wallets, 1),
            'verification_rate': identity['cross_chain']['verification_rate'],
            'chain_diversification': len(identity['cross_chain']['mappings'])
        }
    }
