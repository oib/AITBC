"""
Tests for Agent Identity SDK
Unit tests for the Agent Identity client and models
"""
import sys

import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from datetime import datetime, UTC

from app.agent_identity.sdk.client import AgentIdentityClient
from app.agent_identity.sdk.models import (
    AgentIdentity, CrossChainMapping, AgentWallet,
    IdentityStatus, VerificationType, ChainType,
    CreateIdentityRequest, TransactionRequest
)
from app.agent_identity.sdk.exceptions import (
    AgentIdentityError, ValidationError, NetworkError,
    AuthenticationError, RateLimitError
)


class TestAgentIdentityClient:
    """Test cases for AgentIdentityClient"""
    
    @pytest.fixture
    def client(self):
        """Create a test client"""
        return AgentIdentityClient(
            base_url="http://test:8000/v1",
            api_key="test_key",
            timeout=10
        )
    
    @pytest.fixture
    def mock_session(self):
        """Create a mock HTTP session"""
        session = AsyncMock()
        session.closed = False
        return session
    
    @pytest.mark.asyncio
    async def test_client_initialization(self, client):
        """Test client initialization"""
        assert client.base_url == "http://test:8000/v1"
        assert client.api_key == "test_key"
        assert client.timeout.total == 10
        assert client.max_retries == 3
        assert client.session is None
    
    @pytest.mark.asyncio
    async def test_context_manager(self, client):
        """Test async context manager"""
        async with client as c:
            assert c is client
            assert c.session is not None
            assert not c.session.closed
        
        # Session should be closed after context
        assert client.session.closed
    
    @pytest.mark.asyncio
    async def test_create_identity_success(self, client, mock_session):
        """Test successful identity creation"""
        # Mock the session
        with patch.object(client, 'session', mock_session):
            # Mock response
            mock_response = AsyncMock()
            mock_response.status = 201
            mock_response.json = AsyncMock(return_value={
                'identity_id': 'identity_123',
                'agent_id': 'agent_456',
                'owner_address': '0x123...',
                'display_name': 'Test Agent',
                'supported_chains': [1, 137],
                'primary_chain': 1,
                'registration_result': {'total_mappings': 2},
                'wallet_results': [{'chain_id': 1, 'success': True}],
                'created_at': '2024-01-01T00:00:00'
            })
            
            mock_session.request.return_value.__aenter__.return_value = mock_response
            
            # Create identity
            result = await client.create_identity(
                owner_address='0x123...',
                chains=[1, 137],
                display_name='Test Agent',
                description='Test description'
            )
            
            # Verify result
            assert result.identity_id == 'identity_123'
            assert result.agent_id == 'agent_456'
            assert result.display_name == 'Test Agent'
            assert result.supported_chains == [1, 137]
            assert result.created_at == '2024-01-01T00:00:00'
            
            # Verify request was made correctly
            mock_session.request.assert_called_once()
            call_args = mock_session.request.call_args
            assert call_args[0][0] == 'POST'
            assert '/agent-identity/identities' in call_args[0][1]
    
    @pytest.mark.asyncio
    async def test_create_identity_validation_error(self, client, mock_session):
        """Test identity creation with validation error"""
        with patch.object(client, 'session', mock_session):
            # Mock 400 response
            mock_response = AsyncMock()
            mock_response.status = 400
            mock_response.json = AsyncMock(return_value={'detail': 'Invalid owner address'})
            
            mock_session.request.return_value.__aenter__.return_value = mock_response
            
            # Should raise ValidationError
            with pytest.raises(ValidationError) as exc_info:
                await client.create_identity(
                    owner_address='invalid',
                    chains=[1]
                )
            
            assert 'Invalid owner address' in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_get_identity_success(self, client, mock_session):
        """Test successful identity retrieval"""
        with patch.object(client, 'session', mock_session):
            # Mock response
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={
                'identity': {
                    'id': 'identity_123',
                    'agent_id': 'agent_456',
                    'owner_address': '0x123...',
                    'display_name': 'Test Agent',
                    'status': 'active',
                    'reputation_score': 85.5
                },
                'cross_chain': {
                    'total_mappings': 2,
                    'verified_mappings': 2
                },
                'wallets': {
                    'total_wallets': 2,
                    'total_balance': 1.5
                }
            })
            
            mock_session.request.return_value.__aenter__.return_value = mock_response
            
            # Get identity
            result = await client.get_identity('agent_456')
            
            # Verify result
            assert result['identity']['agent_id'] == 'agent_456'
            assert result['identity']['display_name'] == 'Test Agent'
            assert result['cross_chain']['total_mappings'] == 2
            assert result['wallets']['total_balance'] == 1.5
    
    @pytest.mark.asyncio
    async def test_verify_identity_success(self, client, mock_session):
        """Test successful identity verification"""
        with patch.object(client, 'session', mock_session):
            # Mock response
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={
                'verification_id': 'verify_123',
                'agent_id': 'agent_456',
                'chain_id': 1,
                'verification_type': 'basic',
                'verified': True,
                'timestamp': '2024-01-01T00:00:00'
            })
            
            mock_session.request.return_value.__aenter__.return_value = mock_response
            
            # Verify identity
            result = await client.verify_identity(
                agent_id='agent_456',
                chain_id=1,
                verifier_address='0x789...',
                proof_hash='abc123',
                proof_data={'test': 'data'}
            )
            
            # Verify result
            assert result.verification_id == 'verify_123'
            assert result.agent_id == 'agent_456'
            assert result.verified == True
            assert result.verification_type == VerificationType.BASIC
    
    @pytest.mark.asyncio
    async def test_execute_transaction_success(self, client, mock_session):
        """Test successful transaction execution"""
        with patch.object(client, 'session', mock_session):
            # Mock response
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={
                'transaction_hash': '0xabc...',
                'from_address': '0x123...',
                'to_address': '0x456...',
                'amount': '0.1',
                'gas_used': '21000',
                'gas_price': '20000000000',
                'status': 'success',
                'block_number': 12345,
                'timestamp': '2024-01-01T00:00:00'
            })
            
            mock_session.request.return_value.__aenter__.return_value = mock_response
            
            # Execute transaction
            result = await client.execute_transaction(
                agent_id='agent_456',
                chain_id=1,
                to_address='0x456...',
                amount=0.1
            )
            
            # Verify result
            assert result.transaction_hash == '0xabc...'
            assert result.from_address == '0x123...'
            assert result.to_address == '0x456...'
            assert result.amount == '0.1'
            assert result.status == 'success'
    
    @pytest.mark.asyncio
    async def test_search_identities_success(self, client, mock_session):
        """Test successful identity search"""
        with patch.object(client, 'session', mock_session):
            # Mock response
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={
                'results': [
                    {
                        'identity_id': 'identity_123',
                        'agent_id': 'agent_456',
                        'display_name': 'Test Agent',
                        'reputation_score': 85.5
                    }
                ],
                'total_count': 1,
                'query': 'test',
                'filters': {},
                'pagination': {'limit': 50, 'offset': 0}
            })
            
            mock_session.request.return_value.__aenter__.return_value = mock_response
            
            # Search identities
            result = await client.search_identities(
                query='test',
                limit=50,
                offset=0
            )
            
            # Verify result
            assert result.total_count == 1
            assert len(result.results) == 1
            assert result.results[0]['display_name'] == 'Test Agent'
            assert result.query == 'test'
    
    @pytest.mark.asyncio
    async def test_network_error_retry(self, client, mock_session):
        """Test retry logic for network errors"""
        with patch.object(client, 'session', mock_session):
            # Mock network error first two times, then success
            mock_session.request.side_effect = [
                aiohttp.ClientError("Network error"),
                aiohttp.ClientError("Network error"),
                AsyncMock(status=200, json=AsyncMock(return_value={'test': 'success'}).__aenter__.return_value)
            ]
            
            # Should succeed after retries
            result = await client._request('GET', '/test')
            assert result['test'] == 'success'
            
            # Should have retried 3 times total
            assert mock_session.request.call_count == 3
    
    @pytest.mark.asyncio
    async def test_authentication_error(self, client, mock_session):
        """Test authentication error handling"""
        with patch.object(client, 'session', mock_session):
            # Mock 401 response
            mock_response = AsyncMock()
            mock_response.status = 401
            
            mock_session.request.return_value.__aenter__.return_value = mock_response
            
            # Should raise AuthenticationError
            with pytest.raises(AuthenticationError):
                await client._request('GET', '/test')
    
    @pytest.mark.asyncio
    async def test_rate_limit_error(self, client, mock_session):
        """Test rate limit error handling"""
        with patch.object(client, 'session', mock_session):
            # Mock 429 response
            mock_response = AsyncMock()
            mock_response.status = 429
            
            mock_session.request.return_value.__aenter__.return_value = mock_response
            
            # Should raise RateLimitError
            with pytest.raises(RateLimitError):
                await client._request('GET', '/test')


class TestModels:
    """Test cases for SDK models"""
    
    def test_agent_identity_model(self):
        """Test AgentIdentity model"""
        identity = AgentIdentity(
            id='identity_123',
            agent_id='agent_456',
            owner_address='0x123...',
            display_name='Test Agent',
            description='Test description',
            avatar_url='https://example.com/avatar.png',
            status=IdentityStatus.ACTIVE,
            verification_level=VerificationType.BASIC,
            is_verified=True,
            verified_at=datetime.now(datetime.UTC),
            supported_chains=['1', '137'],
            primary_chain=1,
            reputation_score=85.5,
            total_transactions=100,
            successful_transactions=95,
            success_rate=0.95,
            created_at=datetime.now(datetime.UTC),
            updated_at=datetime.now(datetime.UTC),
            last_activity=datetime.now(datetime.UTC),
            metadata={'key': 'value'},
            tags=['test', 'agent']
        )
        
        assert identity.id == 'identity_123'
        assert identity.agent_id == 'agent_456'
        assert identity.status == IdentityStatus.ACTIVE
        assert identity.verification_level == VerificationType.BASIC
        assert identity.success_rate == 0.95
        assert 'test' in identity.tags
    
    def test_cross_chain_mapping_model(self):
        """Test CrossChainMapping model"""
        mapping = CrossChainMapping(
            id='mapping_123',
            agent_id='agent_456',
            chain_id=1,
            chain_type=ChainType.ETHEREUM,
            chain_address='0x123...',
            is_verified=True,
            verified_at=datetime.now(datetime.UTC),
            wallet_address='0x456...',
            wallet_type='agent-wallet',
            chain_metadata={'test': 'data'},
            last_transaction=datetime.now(datetime.UTC),
            transaction_count=10,
            created_at=datetime.now(datetime.UTC),
            updated_at=datetime.now(datetime.UTC)
        )
        
        assert mapping.id == 'mapping_123'
        assert mapping.chain_id == 1
        assert mapping.chain_type == ChainType.ETHEREUM
        assert mapping.is_verified is True
        assert mapping.transaction_count == 10
    
    def test_agent_wallet_model(self):
        """Test AgentWallet model"""
        wallet = AgentWallet(
            id='wallet_123',
            agent_id='agent_456',
            chain_id=1,
            chain_address='0x123...',
            wallet_type='agent-wallet',
            contract_address='0x789...',
            balance=1.5,
            spending_limit=10.0,
            total_spent=0.5,
            is_active=True,
            permissions=['send', 'receive'],
            requires_multisig=False,
            multisig_threshold=1,
            multisig_signers=['0x123...'],
            last_transaction=datetime.now(datetime.UTC),
            transaction_count=5,
            created_at=datetime.now(datetime.UTC),
            updated_at=datetime.now(datetime.UTC)
        )
        
        assert wallet.id == 'wallet_123'
        assert wallet.balance == 1.5
        assert wallet.spending_limit == 10.0
        assert wallet.is_active is True
        assert 'send' in wallet.permissions
        assert wallet.requires_multisig is False


class TestConvenienceFunctions:
    """Test cases for convenience functions"""
    
    @pytest.mark.asyncio
    async def test_create_identity_with_wallets_success(self):
        """Test create_identity_with_wallets convenience function"""
        from app.agent_identity.sdk.client import create_identity_with_wallets
        
        # Mock client
        client = AsyncMock(spec=AgentIdentityClient)
        
        # Mock successful response
        client.create_identity.return_value = AsyncMock(
            identity_id='identity_123',
            agent_id='agent_456',
            wallet_results=[
                {'chain_id': 1, 'success': True},
                {'chain_id': 137, 'success': True}
            ]
        )
        
        # Call function
        result = await create_identity_with_wallets(
            client=client,
            owner_address='0x123...',
            chains=[1, 137],
            display_name='Test Agent'
        )
        
        # Verify result
        assert result.identity_id == 'identity_123'
        assert len(result.wallet_results) == 2
        assert all(w['success'] for w in result.wallet_results)
    
    @pytest.mark.asyncio
    async def test_verify_identity_on_all_chains_success(self):
        """Test verify_identity_on_all_chains convenience function"""
        from app.agent_identity.sdk.client import verify_identity_on_all_chains
        
        # Mock client
        client = AsyncMock(spec=AgentIdentityClient)
        
        # Mock mappings
        mappings = [
            AsyncMock(chain_id=1, chain_type=ChainType.ETHEREUM, chain_address='0x123...'),
            AsyncMock(chain_id=137, chain_type=ChainType.POLYGON, chain_address='0x456...')
        ]
        
        client.get_cross_chain_mappings.return_value = mappings
        client.verify_identity.return_value = AsyncMock(
            verification_id='verify_123',
            verified=True
        )
        
        # Call function
        results = await verify_identity_on_all_chains(
            client=client,
            agent_id='agent_456',
            verifier_address='0x789...',
            proof_data_template={'test': 'data'}
        )
        
        # Verify results
        assert len(results) == 2
        assert all(r.verified for r in results)
        assert client.verify_identity.call_count == 2


# Integration tests would go here in a real implementation
# These would test the actual API endpoints

class TestIntegration:
    """Integration tests for the SDK"""
    
    @pytest.mark.asyncio
    async def test_full_identity_workflow(self):
        """Test complete identity creation and management workflow"""
        # This would be an integration test that:
        # 1. Creates an identity
        # 2. Registers cross-chain mappings
        # 3. Creates wallets
        # 4. Verifies identities
        # 5. Executes transactions
        # 6. Searches for identities
        # 7. Exports/imports identity data
        
        # Skip for now as it requires a running API
        pytest.skip("Integration test requires running API")


if __name__ == '__main__':
    pytest.main([__file__])
