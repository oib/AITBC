"""Tests for advanced marketplace commands"""

import pytest
import json
import base64
from unittest.mock import Mock, patch
from click.testing import CliRunner
from aitbc_cli.main import cli


class TestMarketplaceAdvanced:
    """Test advanced marketplace commands"""
    
    def test_marketplace_help(self):
        """Test marketplace help command"""
        runner = CliRunner()
        result = runner.invoke(cli, ['marketplace', '--help'])
        assert result.exit_code == 0
        assert 'marketplace' in result.output.lower()
    
    def test_marketplace_agents_help(self):
        """Test marketplace agents help command"""
        runner = CliRunner()
        result = runner.invoke(cli, ['marketplace', 'agents', '--help'])
        assert result.exit_code == 0
        assert 'agents' in result.output.lower()
        self.runner = CliRunner()
        self.config = {
            'coordinator_url': 'http://test:8000',
            'api_key': 'test_key'
        }
    
    @patch('aitbc_cli.commands.marketplace_advanced.httpx.Client')
    def test_models_list_success(self, mock_client):
        """Test successful advanced models listing"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                'id': 'nft_1',
                'name': 'Advanced Model 1',
                'nft_version': '2.0',
                'rating': 4.5,
                'category': 'multimodal'
            },
            {
                'id': 'nft_2',
                'name': 'Advanced Model 2',
                'nft_version': '2.0',
                'rating': 4.2,
                'category': 'text'
            }
        ]
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(models, [
            'list',
            '--nft-version', '2.0',
            '--category', 'multimodal',
            '--rating-min', '4.0',
            '--limit', '10'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'nft_1' in result.output
        assert '4.5' in result.output
    
    @patch('aitbc_cli.commands.marketplace_advanced.httpx.Client')
    @patch('aitbc_cli.commands.marketplace_advanced.Path.exists')
    def test_models_mint_success(self, mock_exists, mock_client):
        """Test successful model NFT minting"""
        mock_exists.return_value = True
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            'id': 'nft_123',
            'name': 'Test Model',
            'nft_version': '2.0',
            'royalty_percentage': 5.0,
            'supply': 1
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        with self.runner.isolated_filesystem():
            # Create dummy model file
            with open('model.pkl', 'wb') as f:
                f.write(b'fake model data')
            
            # Create metadata file
            with open('metadata.json', 'w') as f:
                json.dump({
                    'name': 'Test Model',
                    'description': 'Test model description',
                    'category': 'multimodal'
                }, f)
            
            result = self.runner.invoke(models, [
                'mint',
                '--model-file', 'model.pkl',
                '--metadata', 'metadata.json',
                '--price', '100.0',
                '--royalty', '5.0',
                '--supply', '1'
            ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'nft_123' in result.output
    
    @patch('aitbc_cli.commands.marketplace_advanced.httpx.Client')
    @patch('aitbc_cli.commands.marketplace_advanced.Path.exists')
    def test_models_update_success(self, mock_exists, mock_client):
        """Test successful model NFT update"""
        mock_exists.return_value = True
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'id': 'nft_123',
            'version': '2.1',
            'compatibility': 'backward',
            'update_time': '2026-02-24T10:00:00Z'
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        with self.runner.isolated_filesystem():
            # Create dummy version file
            with open('model_v2.pkl', 'wb') as f:
                f.write(b'fake model v2 data')
            
            result = self.runner.invoke(models, [
                'update',
                'nft_123',
                '--new-version', 'model_v2.pkl',
                '--version-notes', 'Performance improvements',
                '--compatibility', 'backward'
            ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert '2.1' in result.output
    
    @patch('aitbc_cli.commands.marketplace_advanced.httpx.Client')
    def test_models_verify_success(self, mock_client):
        """Test successful model verification"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'nft_id': 'nft_123',
            'authentic': True,
            'integrity_check': 'passed',
            'performance_verified': True,
            'verification_score': 0.95
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = self.runner.invoke(models, [
            'verify',
            'nft_123',
            '--deep-scan',
            '--check-integrity',
            '--verify-performance'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'authentic' in result.output
        assert '0.95' in result.output


class TestAnalyticsCommands:
    """Test marketplace analytics and insights commands"""
    
    def setup_method(self):
        """Setup test environment"""
        self.runner = CliRunner()
        self.config = {
            'coordinator_url': 'http://test:8000',
            'api_key': 'test_key'
        }
    
    @patch('aitbc_cli.commands.marketplace_advanced.httpx.Client')
    def test_analytics_success(self, mock_client):
        """Test successful analytics retrieval"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'period': '30d',
            'metrics': {
                'volume': 1500000,
                'trends': {'growth': 15.5, 'direction': 'up'},
                'top_categories': ['multimodal', 'text', 'image'],
                'average_price': 250.0
            }
        }
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(analytics, [
            'analytics',
            '--period', '30d',
            '--metrics', 'volume,trends',
            '--category', 'multimodal',
            '--format', 'json'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert '1500000' in result.output
        assert '15.5' in result.output
    
    @patch('aitbc_cli.commands.marketplace_advanced.httpx.Client')
    def test_benchmark_success(self, mock_client):
        """Test successful model benchmarking"""
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.json.return_value = {
            'id': 'benchmark_123',
            'model_id': 'model_123',
            'status': 'running',
            'datasets': ['standard'],
            'iterations': 100
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = self.runner.invoke(analytics, [
            'benchmark',
            'model_123',
            '--competitors',
            '--datasets', 'standard',
            '--iterations', '100'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'benchmark_123' in result.output
    
    @patch('aitbc_cli.commands.marketplace_advanced.httpx.Client')
    def test_trends_success(self, mock_client):
        """Test successful market trends analysis"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'category': 'multimodal',
            'forecast_period': '7d',
            'trends': {
                'current': {'price': 300, 'volume': 1000},
                'forecast': {'price': 320, 'volume': 1100},
                'confidence': 0.85
            },
            'indicators': ['bullish', 'growth']
        }
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(analytics, [
            'trends',
            '--category', 'multimodal',
            '--forecast', '7d',
            '--confidence', '0.8'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert '320' in result.output
        assert '0.85' in result.output
    
    @patch('aitbc_cli.commands.marketplace_advanced.httpx.Client')
    def test_report_success(self, mock_client):
        """Test successful report generation"""
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.json.return_value = {
            'id': 'report_123',
            'format': 'pdf',
            'status': 'generating',
            'sections': ['overview', 'trends', 'analytics'],
            'estimated_completion': '2026-02-24T11:00:00Z'
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = self.runner.invoke(analytics, [
            'report',
            '--format', 'pdf',
            '--email', 'test@example.com',
            '--sections', 'overview,trends,analytics'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'report_123' in result.output


class TestTradingCommands:
    """Test advanced trading features commands"""
    
    def setup_method(self):
        """Setup test environment"""
        self.runner = CliRunner()
        self.config = {
            'coordinator_url': 'http://test:8000',
            'api_key': 'test_key'
        }
    
    @patch('aitbc_cli.commands.marketplace_advanced.httpx.Client')
    def test_bid_success(self, mock_client):
        """Test successful auction bid"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'auction_id': 'auction_123',
            'bid_id': 'bid_456',
            'amount': 1000.0,
            'status': 'active',
            'current_high_bid': 1000.0
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = self.runner.invoke(trading, [
            'bid',
            'auction_123',
            '--amount', '1000.0',
            '--max-auto-bid', '1500.0',
            '--proxy'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'bid_456' in result.output
        assert '1000.0' in result.output
    
    @patch('aitbc_cli.commands.marketplace_advanced.httpx.Client')
    def test_royalties_success(self, mock_client):
        """Test successful royalty agreement creation"""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            'id': 'royalty_123',
            'model_id': 'model_123',
            'recipients': [
                {'address': '0x123...', 'percentage': 10.0},
                {'address': '0x456...', 'percentage': 5.0}
            ],
            'smart_contract': True,
            'status': 'active'
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = self.runner.invoke(trading, [
            'royalties',
            'model_123',
            '--recipients', '0x123...:10,0x456...:5',
            '--smart-contract'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'royalty_123' in result.output
        assert '10.0' in result.output
    
    @patch('aitbc_cli.commands.marketplace_advanced.httpx.Client')
    def test_execute_success(self, mock_client):
        """Test successful trading strategy execution"""
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.json.return_value = {
            'id': 'execution_123',
            'strategy': 'arbitrage',
            'budget': 5000.0,
            'risk_level': 'medium',
            'status': 'executing'
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = self.runner.invoke(trading, [
            'execute',
            '--strategy', 'arbitrage',
            '--budget', '5000.0',
            '--risk-level', 'medium'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'execution_123' in result.output
        assert 'arbitrage' in result.output


class TestDisputeCommands:
    """Test dispute resolution operations commands"""
    
    def setup_method(self):
        """Setup test environment"""
        self.runner = CliRunner()
        self.config = {
            'coordinator_url': 'http://test:8000',
            'api_key': 'test_key'
        }
    
    @patch('aitbc_cli.commands.marketplace_advanced.httpx.Client')
    def test_dispute_file_success(self, mock_client):
        """Test successful dispute filing"""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            'id': 'dispute_123',
            'transaction_id': 'tx_456',
            'reason': 'Model quality issues',
            'category': 'quality',
            'status': 'pending'
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        with self.runner.isolated_filesystem():
            # Create dummy evidence file
            with open('evidence.pdf', 'wb') as f:
                f.write(b'fake evidence data')
            
            result = self.runner.invoke(dispute, [
                'file',
                'tx_456',
                '--reason', 'Model quality issues',
                '--category', 'quality',
                '--evidence', 'evidence.pdf'
            ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'dispute_123' in result.output
    
    @patch('aitbc_cli.commands.marketplace_advanced.httpx.Client')
    def test_dispute_status_success(self, mock_client):
        """Test successful dispute status retrieval"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'id': 'dispute_123',
            'status': 'under_review',
            'progress': 45,
            'evidence_submitted': 2,
            'reviewer_assigned': True,
            'estimated_resolution': '2026-02-26T00:00:00Z'
        }
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(dispute, [
            'status',
            'dispute_123'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'under_review' in result.output
        assert '45' in result.output
    
    @patch('aitbc_cli.commands.marketplace_advanced.httpx.Client')
    def test_dispute_resolve_success(self, mock_client):
        """Test successful dispute resolution proposal"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'dispute_id': 'dispute_123',
            'resolution_id': 'res_456',
            'resolution': 'Partial refund - 50%',
            'status': 'proposed',
            'proposed_by': 'seller',
            'proposal_time': '2026-02-24T10:30:00Z'
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = self.runner.invoke(dispute, [
            'resolve',
            'dispute_123',
            '--resolution', 'Partial refund - 50%'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'res_456' in result.output
        assert 'proposed' in result.output
