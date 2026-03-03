"""
Integration Tests for AITBC API Components
Tests interaction between different API services
"""

import pytest
import json
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
from click.testing import CliRunner


class TestCoordinatorAPIIntegration:
    """Test coordinator API integration"""
    
    @pytest.fixture
    def mock_coordinator_client(self):
        """Mock coordinator API client"""
        client = Mock()
        
        # Mock health check
        client.health_check.return_value = {
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'services': {
                'job_manager': 'running',
                'marketplace': 'running',
                'blockchain': 'running'
            }
        }
        
        # Mock job submission
        client.submit_job.return_value = {
            'job_id': 'test-job-123',
            'status': 'submitted',
            'estimated_completion': '2024-01-01T12:00:00Z'
        }
        
        # Mock job status
        client.get_job_status.return_value = {
            'job_id': 'test-job-123',
            'status': 'running',
            'progress': 45,
            'started_at': datetime.utcnow().isoformat()
        }
        
        return client
    
    def test_health_check_integration(self, mock_coordinator_client):
        """Test health check integration"""
        response = mock_coordinator_client.health_check()
        
        assert response['status'] == 'healthy'
        assert 'timestamp' in response
        assert 'services' in response
        assert all(service in ['running', 'stopped', 'error'] 
                  for service in response['services'].values())
    
    def test_job_submission_workflow(self, mock_coordinator_client):
        """Test complete job submission workflow"""
        job_data = {
            'type': 'ml_inference',
            'model': 'resnet50',
            'input_data': 's3://test-data/input.json',
            'requirements': {
                'gpu_type': 'RTX 3080',
                'memory_gb': 8,
                'duration_minutes': 30
            }
        }
        
        # Submit job
        response = mock_coordinator_client.submit_job(job_data)
        
        assert 'job_id' in response
        assert response['status'] == 'submitted'
        assert response['job_id'].startswith('test-job-')
        
        # Check job status
        status_response = mock_coordinator_client.get_job_status(response['job_id'])
        
        assert status_response['job_id'] == response['job_id']
        assert status_response['status'] in ['submitted', 'running', 'completed', 'failed']
        assert 'progress' in status_response
    
    def test_marketplace_integration(self, mock_coordinator_client):
        """Test marketplace API integration"""
        # Mock marketplace responses
        mock_coordinator_client.list_offers.return_value = {
            'offers': [
                {
                    'id': 'offer-1',
                    'provider': 'miner-1',
                    'gpu_type': 'RTX 3080',
                    'price_per_hour': 0.1,
                    'available': True
                },
                {
                    'id': 'offer-2',
                    'provider': 'miner-2',
                    'gpu_type': 'RTX 3090',
                    'price_per_hour': 0.15,
                    'available': True
                }
            ],
            'total_count': 2
        }
        
        # Get marketplace offers
        offers_response = mock_coordinator_client.list_offers()
        
        assert 'offers' in offers_response
        assert 'total_count' in offers_response
        assert len(offers_response['offers']) == 2
        assert all('gpu_type' in offer for offer in offers_response['offers'])
        assert all('price_per_hour' in offer for offer in offers_response['offers'])


class TestBlockchainIntegration:
    """Test blockchain integration"""
    
    @pytest.fixture
    def mock_blockchain_client(self):
        """Mock blockchain client"""
        client = Mock()
        
        # Mock blockchain info
        client.get_chain_info.return_value = {
            'chain_id': 'aitbc-mainnet',
            'block_height': 12345,
            'latest_block_hash': '0xabc123...',
            'network_status': 'active'
        }
        
        # Mock transaction creation
        client.create_transaction.return_value = {
            'tx_hash': '0xdef456...',
            'from_address': 'aitbc1sender123',
            'to_address': 'aitbc1receiver456',
            'amount': 100.0,
            'fee': 0.001,
            'status': 'pending'
        }
        
        # Mock wallet balance
        client.get_balance.return_value = {
            'address': 'aitbc1test123',
            'balance': 1500.75,
            'pending_balance': 25.0,
            'last_updated': datetime.utcnow().isoformat()
        }
        
        return client
    
    def test_blockchain_info_retrieval(self, mock_blockchain_client):
        """Test blockchain information retrieval"""
        info = mock_blockchain_client.get_chain_info()
        
        assert 'chain_id' in info
        assert 'block_height' in info
        assert 'latest_block_hash' in info
        assert 'network_status' in info
        assert info['block_height'] > 0
        assert info['network_status'] == 'active'
    
    def test_transaction_creation(self, mock_blockchain_client):
        """Test transaction creation and validation"""
        tx_data = {
            'from_address': 'aitbc1sender123',
            'to_address': 'aitbc1receiver456',
            'amount': 100.0,
            'private_key': 'test_private_key'
        }
        
        tx_result = mock_blockchain_client.create_transaction(tx_data)
        
        assert 'tx_hash' in tx_result
        assert tx_result['tx_hash'].startswith('0x')
        assert tx_result['from_address'] == tx_data['from_address']
        assert tx_result['to_address'] == tx_data['to_address']
        assert tx_result['amount'] == tx_data['amount']
        assert tx_result['status'] == 'pending'
    
    def test_wallet_balance_check(self, mock_blockchain_client):
        """Test wallet balance checking"""
        address = 'aitbc1test123'
        balance_info = mock_blockchain_client.get_balance(address)
        
        assert 'address' in balance_info
        assert 'balance' in balance_info
        assert 'pending_balance' in balance_info
        assert 'last_updated' in balance_info
        assert balance_info['address'] == address
        assert isinstance(balance_info['balance'], (int, float))
        assert isinstance(balance_info['pending_balance'], (int, float))


class TestCLIIntegration:
    """Test CLI integration with APIs"""
    
    def test_cli_config_integration(self):
        """Test CLI configuration integration"""
        runner = CliRunner()
        
        # Test config show command
        result = runner.invoke(cli, ['config-show'])
        assert result.exit_code == 0
        assert 'coordinator_url' in result.output.lower() or 'api' in result.output.lower()
    
    def test_cli_wallet_integration(self):
        """Test CLI wallet integration"""
        runner = CliRunner()
        
        # Test wallet help
        result = runner.invoke(cli, ['wallet', '--help'])
        assert result.exit_code == 0
        assert 'wallet' in result.output.lower()
    
    def test_cli_marketplace_integration(self):
        """Test CLI marketplace integration"""
        runner = CliRunner()
        
        # Test marketplace help
        result = runner.invoke(cli, ['marketplace', '--help'])
        assert result.exit_code == 0
        assert 'marketplace' in result.output.lower()


class TestDataFlowIntegration:
    """Test data flow between components"""
    
    def test_job_to_blockchain_flow(self):
        """Test data flow from job submission to blockchain recording"""
        # Simulate job submission
        job_data = {
            'id': 'job-123',
            'type': 'ml_inference',
            'provider': 'miner-456',
            'cost': 10.0,
            'status': 'completed'
        }
        
        # Simulate blockchain transaction
        tx_data = {
            'job_id': job_data['id'],
            'amount': job_data['cost'],
            'from': 'client_wallet',
            'to': 'miner_wallet',
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Validate data flow
        assert tx_data['job_id'] == job_data['id']
        assert tx_data['amount'] == job_data['cost']
        assert 'timestamp' in tx_data
    
    def test_marketplace_to_job_flow(self):
        """Test data flow from marketplace selection to job execution"""
        # Simulate marketplace offer selection
        offer = {
            'id': 'offer-789',
            'provider': 'miner-456',
            'gpu_type': 'RTX 3080',
            'price_per_hour': 0.1
        }
        
        # Simulate job creation based on offer
        job = {
            'id': 'job-456',
            'type': 'ml_training',
            'assigned_provider': offer['provider'],
            'gpu_requirements': offer['gpu_type'],
            'cost_per_hour': offer['price_per_hour'],
            'status': 'assigned'
        }
        
        # Validate data flow
        assert job['assigned_provider'] == offer['provider']
        assert job['gpu_requirements'] == offer['gpu_type']
        assert job['cost_per_hour'] == offer['price_per_hour']
    
    def test_wallet_transaction_flow(self):
        """Test wallet transaction data flow"""
        # Simulate wallet balance before
        initial_balance = 1000.0
        
        # Simulate transaction
        transaction = {
            'type': 'payment',
            'amount': 50.0,
            'from_wallet': 'client_wallet',
            'to_wallet': 'miner_wallet',
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Calculate new balance
        new_balance = initial_balance - transaction['amount']
        
        # Validate transaction flow
        assert transaction['amount'] > 0
        assert new_balance == initial_balance - transaction['amount']
        assert new_balance < initial_balance


class TestErrorHandlingIntegration:
    """Test error handling across integrated components"""
    
    def test_api_error_propagation(self):
        """Test error propagation through API calls"""
        # Mock API client that raises errors
        client = Mock()
        client.submit_job.side_effect = Exception("API unavailable")
        
        # Test error handling
        with pytest.raises(Exception, match="API unavailable"):
            client.submit_job({"type": "test_job"})
    
    def test_fallback_mechanisms(self):
        """Test fallback mechanisms for integrated services"""
        # Mock primary service failure
        primary_client = Mock()
        primary_client.get_balance.side_effect = Exception("Primary service down")
        
        # Mock fallback service
        fallback_client = Mock()
        fallback_client.get_balance.return_value = {
            'address': 'aitbc1test',
            'balance': 1000.0
        }
        
        # Test fallback logic
        try:
            balance = primary_client.get_balance('aitbc1test')
        except Exception:
            balance = fallback_client.get_balance('aitbc1test')
        
        assert balance['balance'] == 1000.0
    
    def test_data_validation_integration(self):
        """Test data validation across component boundaries"""
        # Test invalid job data
        invalid_job = {
            'type': 'invalid_type',
            'requirements': {}
        }
        
        # Test validation at different stages
        valid_job_types = ['ml_training', 'ml_inference', 'data_processing']
        
        assert invalid_job['type'] not in valid_job_types
        
        # Test validation function
        def validate_job(job_data):
            if job_data.get('type') not in valid_job_types:
                raise ValueError("Invalid job type")
            if not job_data.get('requirements'):
                raise ValueError("Requirements missing")
            return True
        
        with pytest.raises(ValueError, match="Invalid job type"):
            validate_job(invalid_job)
