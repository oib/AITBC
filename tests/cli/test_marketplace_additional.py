"""Tests for additional marketplace commands"""

import pytest
import json
from click.testing import CliRunner
from unittest.mock import Mock, patch
from aitbc_cli.main import cli


@pytest.fixture
def runner():
    """Create CLI runner"""
    return CliRunner()


@pytest.fixture
def mock_config():
    """Mock configuration for testing"""
    return {
        'coordinator_url': 'http://localhost:8000',
        'api_key': 'test-key',
        'wallet_name': 'test-wallet'
    }


class TestMarketplaceBidCommands:
    """Test suite for marketplace bid operations"""
    
    def test_bid_submit_success(self, runner, mock_config):
        """Test successful bid submission"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            with patch('httpx.Client.post') as mock_post:
                mock_response = Mock()
                mock_response.status_code = 202
                mock_response.json.return_value = {
                    'id': 'bid_123',
                    'provider': 'miner123',
                    'capacity': 10,
                    'price': 0.5
                }
                mock_post.return_value = mock_response
                
                result = runner.invoke(cli, [
                    'marketplace', 'bid', 'submit',
                    '--provider', 'miner123',
                    '--capacity', '10',
                    '--price', '0.5',
                    '--notes', 'High performance GPU'
                ])
                
                assert result.exit_code == 0
                assert 'bid submitted successfully' in result.output.lower()
                assert 'bid_123' in result.output
                
    def test_bid_submit_invalid_capacity(self, runner, mock_config):
        """Test bid submission with invalid capacity"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            
            result = runner.invoke(cli, [
                'marketplace', 'bid', 'submit',
                '--provider', 'miner123',
                '--capacity', '0',
                '--price', '0.5'
            ])
            
            assert 'capacity must be greater than 0' in result.output.lower()
            
    def test_bid_submit_invalid_price(self, runner, mock_config):
        """Test bid submission with invalid price"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            
            result = runner.invoke(cli, [
                'marketplace', 'bid', 'submit',
                '--provider', 'miner123',
                '--capacity', '10',
                '--price', '-1'
            ])
            
            assert 'price must be greater than 0' in result.output.lower()
            
    def test_bid_list_success(self, runner, mock_config):
        """Test successful bid listing"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            with patch('httpx.Client.get') as mock_get:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    'bids': [
                        {
                            'id': 'bid_123',
                            'provider': 'miner123',
                            'capacity': 10,
                            'price': 0.5,
                            'status': 'pending'
                        },
                        {
                            'id': 'bid_456',
                            'provider': 'miner456',
                            'capacity': 5,
                            'price': 0.3,
                            'status': 'accepted'
                        }
                    ]
                }
                mock_get.return_value = mock_response
                
                result = runner.invoke(cli, [
                    'marketplace', 'bid', 'list',
                    '--status', 'pending',
                    '--limit', '10'
                ])
                
                assert result.exit_code == 0
                assert 'bid_123' in result.output
                
    def test_bid_details_success(self, runner, mock_config):
        """Test successful bid details retrieval"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            with patch('httpx.Client.get') as mock_get:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    'id': 'bid_123',
                    'provider': 'miner123',
                    'capacity': 10,
                    'price': 0.5,
                    'status': 'pending',
                    'created_at': '2023-01-01T00:00:00Z',
                    'notes': 'High performance GPU'
                }
                mock_get.return_value = mock_response
                
                result = runner.invoke(cli, [
                    'marketplace', 'bid', 'details',
                    'bid_123'
                ])
                
                assert result.exit_code == 0
                assert 'bid_123' in result.output
                assert 'miner123' in result.output
                
    def test_bid_details_not_found(self, runner, mock_config):
        """Test bid details for non-existent bid"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            with patch('httpx.Client.get') as mock_get:
                mock_response = Mock()
                mock_response.status_code = 404
                mock_get.return_value = mock_response
                
                result = runner.invoke(cli, [
                    'marketplace', 'bid', 'details',
                    'non_existent'
                ])
                
                assert result.exit_code == 0
                # Should handle 404 gracefully


class TestMarketplaceGovernanceCommands:
    """Test suite for marketplace governance operations"""
    
    def test_governance_create_proposal_success(self, runner, mock_config):
        """Test successful governance proposal creation"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            with patch('httpx.Client.post') as mock_post:
                mock_response = Mock()
                mock_response.status_code = 201
                mock_response.json.return_value = {
                    'proposal_id': 'prop_123',
                    'title': 'Update GPU Pricing',
                    'status': 'active'
                }
                mock_post.return_value = mock_response
                
                result = runner.invoke(cli, [
                    'marketplace', 'governance', 'create-proposal',
                    '--title', 'Update GPU Pricing',
                    '--description', 'Adjust pricing based on market demand',
                    '--proposal-type', 'pricing_update',
                    '--params', '{"min_price": 0.1, "max_price": 2.0}',
                    '--voting-period', '48'
                ])
                
                assert result.exit_code == 0
                assert 'proposal created successfully' in result.output.lower()
                assert 'prop_123' in result.output
                
    def test_governance_create_proposal_invalid_json(self, runner, mock_config):
        """Test governance proposal creation with invalid JSON parameters"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            
            result = runner.invoke(cli, [
                'marketplace', 'governance', 'create-proposal',
                '--title', 'Update GPU Pricing',
                '--description', 'Adjust pricing based on market demand',
                '--proposal-type', 'pricing_update',
                '--params', 'invalid json',
                '--voting-period', '48'
            ])
            
            assert 'invalid json parameters' in result.output.lower()
            
    def test_governance_list_proposals_success(self, runner, mock_config):
        """Test successful governance proposals listing"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            with patch('httpx.Client.get') as mock_get:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    'proposals': [
                        {
                            'proposal_id': 'prop_123',
                            'title': 'Update GPU Pricing',
                            'status': 'active',
                            'votes_for': 15,
                            'votes_against': 3
                        },
                        {
                            'proposal_id': 'prop_456',
                            'title:': 'Add New GPU Category',
                            'status': 'completed',
                            'votes_for': 25,
                            'votes_against': 2
                        }
                    ]
                }
                mock_get.return_value = mock_response
                
                result = runner.invoke(cli, [
                    'marketplace', 'governance', 'list-proposals',
                    '--status', 'active',
                    '--limit', '10'
                ])
                
                assert result.exit_code == 0
                assert 'prop_123' in result.output
                
    def test_governance_vote_success(self, runner, mock_config):
        """Test successful governance voting"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            with patch('httpx.Client.post') as mock_post:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    'proposal_id': 'prop_123',
                    'vote': 'for',
                    'voter': 'user123',
                    'timestamp': '2023-01-01T12:00:00Z'
                }
                mock_post.return_value = mock_response
                
                result = runner.invoke(cli, [
                    'marketplace', 'governance', 'vote',
                    '--proposal-id', 'prop_123',
                    '--vote', 'for',
                    '--reason', 'Supports market stability'
                ])
                
                assert result.exit_code == 0
                assert 'vote recorded' in result.output.lower()
                
    def test_governance_vote_invalid_choice(self, runner, mock_config):
        """Test governance voting with invalid vote choice"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            
            result = runner.invoke(cli, [
                'marketplace', 'governance', 'vote',
                '--proposal-id', 'prop_123',
                '--vote', 'invalid',
                '--reason', 'Test vote'
            ])
            
            assert 'invalid vote choice' in result.output.lower()


class TestMarketplaceReviewCommands:
    """Test suite for marketplace review operations"""
    
    def test_marketplace_reviews_success(self, runner, mock_config):
        """Test successful GPU reviews listing"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            with patch('httpx.Client.get') as mock_get:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    'reviews': [
                        {
                            'review_id': 'rev_123',
                            'gpu_id': 'gpu_123',
                            'rating': 5,
                            'comment': 'Excellent performance!',
                            'reviewer': 'user123',
                            'created_at': '2023-01-01T10:00:00Z'
                        },
                        {
                            'review_id': 'rev_456',
                            'gpu_id': 'gpu_123',
                            'rating': 4,
                            'comment': 'Good value for money',
                            'reviewer': 'user456',
                            'created_at': '2023-01-02T15:30:00Z'
                        }
                    ],
                    'average_rating': 4.5,
                    'total_reviews': 2
                }
                mock_get.return_value = mock_response
                
                result = runner.invoke(cli, [
                    'marketplace', 'reviews',
                    'gpu_123',
                    '--limit', '10'
                ])
                
                assert result.exit_code == 0
                assert 'rev_123' in result.output
                assert '4.5' in result.output  # Average rating
                
    def test_marketplace_reviews_not_found(self, runner, mock_config):
        """Test reviews for non-existent GPU"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            with patch('httpx.Client.get') as mock_get:
                mock_response = Mock()
                mock_response.status_code = 404
                mock_get.return_value = mock_response
                
                result = runner.invoke(cli, [
                    'marketplace', 'reviews',
                    'non_existent_gpu'
                ])
                
                assert result.exit_code == 0
                # Should handle 404 gracefully
                
    def test_marketplace_review_add_success(self, runner, mock_config):
        """Test successful review addition"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            with patch('httpx.Client.post') as mock_post:
                mock_response = Mock()
                mock_response.status_code = 201
                mock_response.json.return_value = {
                    'review_id': 'rev_789',
                    'gpu_id': 'gpu_123',
                    'rating': 5,
                    'comment': 'Amazing GPU!',
                    'reviewer': 'user789'
                }
                mock_post.return_value = mock_response
                
                result = runner.invoke(cli, [
                    'marketplace', 'review',
                    'gpu_123',
                    '--rating', '5',
                    '--comment', 'Amazing GPU!'
                ])
                
                assert result.exit_code == 0
                assert 'review added successfully' in result.output.lower()
                assert 'rev_789' in result.output
                
    def test_marketplace_review_invalid_rating(self, runner, mock_config):
        """Test review addition with invalid rating"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            
            result = runner.invoke(cli, [
                'marketplace', 'review',
                'gpu_123',
                '--rating', '6',  # Invalid rating > 5
                '--comment', 'Test review'
            ])
            
            assert 'rating must be between 1 and 5' in result.output.lower()
            
    def test_marketplace_review_missing_comment(self, runner, mock_config):
        """Test review addition without required comment"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            
            result = runner.invoke(cli, [
                'marketplace', 'review',
                'gpu_123',
                '--rating', '5'
                # Missing --comment
            ])
            
            assert 'comment is required' in result.output.lower()


class TestMarketplaceTestCommands:
    """Test suite for marketplace testing operations"""
    
    def test_marketplace_test_load_success(self, runner, mock_config):
        """Test successful marketplace load test"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            with patch('httpx.Client.post') as mock_post:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    'test_id': 'test_123',
                    'status': 'completed',
                    'duration': 30,
                    'total_requests': 1500,
                    'successful_requests': 1495,
                    'failed_requests': 5,
                    'average_response_time': 0.25
                }
                mock_post.return_value = mock_response
                
                result = runner.invoke(cli, [
                    'marketplace', 'test', 'load',
                    '--concurrent-users', '20',
                    '--rps', '100',
                    '--duration', '60'
                ])
                
                assert result.exit_code == 0
                assert 'load test completed successfully' in result.output.lower()
                assert 'test_123' in result.output
                
    def test_marketplace_test_health_success(self, runner, mock_config):
        """Test successful marketplace health check"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            with patch('httpx.Client.get') as mock_get:
                def mock_response(url, **kwargs):
                    response = Mock()
                    if '/health' in url:
                        response.status_code = 200
                        response.json.return_value = {'status': 'healthy'}
                    elif '/marketplace/status' in url:
                        response.status_code = 200
                        response.json.return_value = {'active_gpus': 25, 'active_bids': 10}
                    elif '/agents/health' in url:
                        response.status_code = 200
                        response.json.return_value = {'active_agents': 5}
                    elif '/blockchain/health' in url:
                        response.status_code = 200
                        response.json.return_value = {'block_height': 12345, 'synced': True}
                    else:
                        response.status_code = 404
                    return response
                
                mock_get.side_effect = mock_response
                
                result = runner.invoke(cli, [
                    'marketplace', 'test', 'health'
                ])
                
                assert result.exit_code == 0
                assert 'healthy' in result.output.lower()
                
    def test_marketplace_test_health_partial_failure(self, runner, mock_config):
        """Test marketplace health check with some endpoints failing"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            with patch('httpx.Client.get') as mock_get:
                def mock_response(url, **kwargs):
                    response = Mock()
                    if '/health' in url:
                        response.status_code = 200
                        response.json.return_value = {'status': 'healthy'}
                    elif '/marketplace/status' in url:
                        response.status_code = 500  # Failed endpoint
                    elif '/agents/health' in url:
                        response.status_code = 200
                        response.json.return_value = {'active_agents': 5}
                    elif '/blockchain/health' in url:
                        response.status_code = 200
                        response.json.return_value = {'block_height': 12345, 'synced': True}
                    else:
                        response.status_code = 404
                    return response
                
                mock_get.side_effect = mock_response
                
                result = runner.invoke(cli, [
                    'marketplace', 'test', 'health'
                ])
                
                assert result.exit_code == 0
                # Should show mixed health status
