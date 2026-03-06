"""Tests for exchange CLI commands"""

import pytest
import json
import time
from click.testing import CliRunner
from unittest.mock import Mock, patch
from aitbc_cli.commands.exchange import exchange


@pytest.fixture
def runner():
    """Create CLI runner"""
    return CliRunner()


@pytest.fixture
def mock_config():
    """Mock configuration"""
    config = Mock()
    config.coordinator_url = "http://test:8000"
    config.api_key = "test_api_key"
    return config


class TestExchangeRatesCommand:
    """Test exchange rates command"""
    
    @patch('aitbc_cli.commands.exchange.httpx.Client')
    def test_rates_success(self, mock_client_class, runner, mock_config):
        """Test successful exchange rates retrieval"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "btc_to_aitbc": 100000,
            "aitbc_to_btc": 0.00001,
            "fee_percent": 0.5
        }
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(exchange, ['rates'], 
                             obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        # Extract JSON from output
        import re
        clean_output = re.sub(r'\x1b\[[0-9;]*m', '', result.output)
        lines = clean_output.strip().split('\n')
        
        # Find JSON part
        json_lines = []
        in_json = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('{'):
                in_json = True
                json_lines.append(stripped)
            elif in_json:
                json_lines.append(stripped)
                if stripped.endswith('}'):
                    break
        
        json_str = '\n'.join(json_lines)
        assert json_str, "No JSON found in output"
        data = json.loads(json_str)
        assert data['btc_to_aitbc'] == 100000
        assert data['aitbc_to_btc'] == 0.00001
        assert data['fee_percent'] == 0.5
        
        # Verify API call
        mock_client.get.assert_called_once_with(
            'http://test:8000/v1/exchange/rates',
            timeout=10
        )
    
    @patch('aitbc_cli.commands.exchange.httpx.Client')
    def test_rates_api_error(self, mock_client_class, runner, mock_config):
        """Test exchange rates with API error"""
        # Setup mock for error response
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 500
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(exchange, ['rates'], 
                             obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        assert 'Failed to get exchange rates: 500' in result.output


class TestExchangeCreatePaymentCommand:
    """Test exchange create-payment command"""
    
    @patch('aitbc_cli.commands.exchange.httpx.Client')
    def test_create_payment_with_aitbc_amount(self, mock_client_class, runner, mock_config):
        """Test creating payment with AITBC amount"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        
        # Mock rates response
        rates_response = Mock()
        rates_response.status_code = 200
        rates_response.json.return_value = {
            "btc_to_aitbc": 100000,
            "aitbc_to_btc": 0.00001,
            "fee_percent": 0.5
        }
        
        # Mock payment creation response
        payment_response = Mock()
        payment_response.status_code = 200
        payment_response.json.return_value = {
            "payment_id": "pay_123456",
            "user_id": "cli_user",
            "aitbc_amount": 1000,
            "btc_amount": 0.01,
            "payment_address": "tb1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
            "status": "pending",
            "created_at": int(time.time()),
            "expires_at": int(time.time()) + 3600
        }
        
        mock_client.get.return_value = rates_response
        mock_client.post.return_value = payment_response
        
        # Run command
        result = runner.invoke(exchange, [
            'create-payment',
            '--aitbc-amount', '1000',
            '--user-id', 'test_user',
            '--notes', 'Test payment'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        assert 'Payment created: pay_123456' in result.output
        assert 'Send 0.01000000 BTC to:' in result.output
        
        # Verify API calls
        assert mock_client.get.call_count == 1  # Get rates
        assert mock_client.post.call_count == 1  # Create payment
        
        # Check payment creation call
        payment_call = mock_client.post.call_args
        assert payment_call[0][0] == 'http://test:8000/v1/exchange/create-payment'
        payment_data = payment_call[1]['json']
        assert payment_data['user_id'] == 'test_user'
        assert payment_data['aitbc_amount'] == 1000
        assert payment_data['btc_amount'] == 0.01
        assert payment_data['notes'] == 'Test payment'
    
    @patch('aitbc_cli.commands.exchange.httpx.Client')
    def test_create_payment_with_btc_amount(self, mock_client_class, runner, mock_config):
        """Test creating payment with BTC amount"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        
        # Mock rates response
        rates_response = Mock()
        rates_response.status_code = 200
        rates_response.json.return_value = {
            "btc_to_aitbc": 100000,
            "aitbc_to_btc": 0.00001,
            "fee_percent": 0.5
        }
        
        # Mock payment creation response
        payment_response = Mock()
        payment_response.status_code = 200
        payment_response.json.return_value = {
            "payment_id": "pay_789012",
            "user_id": "cli_user",
            "aitbc_amount": 500,
            "btc_amount": 0.005,
            "payment_address": "tb1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
            "status": "pending",
            "created_at": int(time.time()),
            "expires_at": int(time.time()) + 3600
        }
        
        mock_client.get.return_value = rates_response
        mock_client.post.return_value = payment_response
        
        # Run command
        result = runner.invoke(exchange, [
            'create-payment',
            '--btc-amount', '0.005'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        assert 'Payment created: pay_789012' in result.output
        
        # Check payment data
        payment_call = mock_client.post.call_args
        payment_data = payment_call[1]['json']
        assert payment_data['aitbc_amount'] == 500
        assert payment_data['btc_amount'] == 0.005
    
    def test_create_payment_no_amount(self, runner, mock_config):
        """Test creating payment without specifying amount"""
        # Run command without amount
        result = runner.invoke(exchange, ['create-payment'], 
                             obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        assert 'Either --aitbc-amount or --btc-amount must be specified' in result.output
    
    def test_create_payment_invalid_aitbc_amount(self, runner, mock_config):
        """Test creating payment with invalid AITBC amount"""
        # Run command with invalid amount
        result = runner.invoke(exchange, [
            'create-payment',
            '--aitbc-amount', '0'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        assert 'AITBC amount must be greater than 0' in result.output
    
    def test_create_payment_invalid_btc_amount(self, runner, mock_config):
        """Test creating payment with invalid BTC amount"""
        # Run command with invalid amount
        result = runner.invoke(exchange, [
            'create-payment',
            '--btc-amount', '-0.01'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        assert 'BTC amount must be greater than 0' in result.output
    
    @patch('aitbc_cli.commands.exchange.httpx.Client')
    def test_create_payment_rates_error(self, mock_client_class, runner, mock_config):
        """Test creating payment when rates API fails"""
        # Setup mock for rates error
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        rates_response = Mock()
        rates_response.status_code = 500
        mock_client.get.return_value = rates_response
        
        # Run command
        result = runner.invoke(exchange, [
            'create-payment',
            '--aitbc-amount', '1000'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        assert 'Failed to get exchange rates' in result.output


class TestExchangePaymentStatusCommand:
    """Test exchange payment-status command"""
    
    @patch('aitbc_cli.commands.exchange.httpx.Client')
    def test_payment_status_pending(self, mock_client_class, runner, mock_config):
        """Test checking pending payment status"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "payment_id": "pay_123456",
            "user_id": "test_user",
            "aitbc_amount": 1000,
            "btc_amount": 0.01,
            "payment_address": "tb1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
            "status": "pending",
            "created_at": int(time.time()),
            "expires_at": int(time.time()) + 3600,
            "confirmations": 0
        }
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(exchange, [
            'payment-status',
            '--payment-id', 'pay_123456'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        assert 'Payment pay_123456 is pending confirmation' in result.output
        
        # Verify API call
        mock_client.get.assert_called_once_with(
            'http://test:8000/v1/exchange/payment-status/pay_123456',
            timeout=10
        )
    
    @patch('aitbc_cli.commands.exchange.httpx.Client')
    def test_payment_status_confirmed(self, mock_client_class, runner, mock_config):
        """Test checking confirmed payment status"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "payment_id": "pay_123456",
            "user_id": "test_user",
            "aitbc_amount": 1000,
            "btc_amount": 0.01,
            "payment_address": "tb1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
            "status": "confirmed",
            "created_at": int(time.time()),
            "expires_at": int(time.time()) + 3600,
            "confirmations": 1,
            "confirmed_at": int(time.time())
        }
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(exchange, [
            'payment-status',
            '--payment-id', 'pay_123456'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        assert 'Payment pay_123456 is confirmed!' in result.output
        assert 'AITBC amount: 1000' in result.output
    
    @patch('aitbc_cli.commands.exchange.httpx.Client')
    def test_payment_status_expired(self, mock_client_class, runner, mock_config):
        """Test checking expired payment status"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "payment_id": "pay_123456",
            "user_id": "test_user",
            "aitbc_amount": 1000,
            "btc_amount": 0.01,
            "payment_address": "tb1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
            "status": "expired",
            "created_at": int(time.time()),
            "expires_at": int(time.time()) - 3600,  # Expired
            "confirmations": 0
        }
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(exchange, [
            'payment-status',
            '--payment-id', 'pay_123456'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        assert 'Payment pay_123456 has expired' in result.output
    
    @patch('aitbc_cli.commands.exchange.httpx.Client')
    def test_payment_status_not_found(self, mock_client_class, runner, mock_config):
        """Test checking status for non-existent payment"""
        # Setup mock for 404 response
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 404
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(exchange, [
            'payment-status',
            '--payment-id', 'nonexistent'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        assert 'Failed to get payment status: 404' in result.output


class TestExchangeMarketStatsCommand:
    """Test exchange market-stats command"""
    
    @patch('aitbc_cli.commands.exchange.httpx.Client')
    def test_market_stats_success(self, mock_client_class, runner, mock_config):
        """Test successful market stats retrieval"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "price": 0.00001,
            "price_change_24h": 5.2,
            "daily_volume": 50000,
            "daily_volume_btc": 0.5,
            "total_payments": 10,
            "pending_payments": 2
        }
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(exchange, ['market-stats'], 
                             obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        assert 'Exchange market statistics:' in result.output
        
        # Extract and verify JSON
        import re
        clean_output = re.sub(r'\x1b\[[0-9;]*m', '', result.output)
        lines = clean_output.strip().split('\n')
        
        json_lines = []
        in_json = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('{'):
                in_json = True
                json_lines.append(stripped)
            elif in_json:
                json_lines.append(stripped)
                if stripped.endswith('}'):
                    break
        
        json_str = '\n'.join(json_lines)
        assert json_str, "No JSON found in output"
        data = json.loads(json_str)
        assert data['price'] == 0.00001
        assert data['price_change_24h'] == 5.2
        assert data['daily_volume'] == 50000
        assert data['total_payments'] == 10
        assert data['pending_payments'] == 2
        
        # Verify API call
        mock_client.get.assert_called_once_with(
            'http://test:8000/v1/exchange/market-stats',
            timeout=10
        )


class TestExchangeWalletCommands:
    """Test exchange wallet commands"""
    
    @patch('aitbc_cli.commands.exchange.httpx.Client')
    def test_wallet_balance_success(self, mock_client_class, runner, mock_config):
        """Test successful wallet balance retrieval"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "address": "tb1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
            "balance": 1.5,
            "unconfirmed_balance": 0.1,
            "total_received": 10.0,
            "total_sent": 8.5
        }
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(exchange, ['wallet', 'balance'], 
                             obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        assert 'Bitcoin wallet balance:' in result.output
        
        # Verify API call
        mock_client.get.assert_called_once_with(
            'http://test:8000/v1/exchange/wallet/balance',
            timeout=10
        )
    
    @patch('aitbc_cli.commands.exchange.httpx.Client')
    def test_wallet_info_success(self, mock_client_class, runner, mock_config):
        """Test successful wallet info retrieval"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "address": "tb1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
            "balance": 1.5,
            "unconfirmed_balance": 0.1,
            "total_received": 10.0,
            "total_sent": 8.5,
            "transactions": [],
            "network": "testnet",
            "block_height": 2500000
        }
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(exchange, ['wallet', 'info'], 
                             obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        assert 'Bitcoin wallet information:' in result.output
        
        # Verify API call
        mock_client.get.assert_called_once_with(
            'http://test:8000/v1/exchange/wallet/info',
            timeout=10
        )


class TestExchangeIntegration:
    """Test exchange integration workflows"""
    
    @patch('aitbc_cli.commands.exchange.httpx.Client')
    def test_complete_exchange_workflow(self, mock_client_class, runner, mock_config):
        """Test complete exchange workflow: rates → create payment → check status"""
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        
        # Step 1: Get rates
        rates_response = Mock()
        rates_response.status_code = 200
        rates_response.json.return_value = {
            "btc_to_aitbc": 100000,
            "aitbc_to_btc": 0.00001,
            "fee_percent": 0.5
        }
        
        # Step 2: Create payment
        payment_response = Mock()
        payment_response.status_code = 200
        payment_response.json.return_value = {
            "payment_id": "pay_workflow_123",
            "user_id": "cli_user",
            "aitbc_amount": 1000,
            "btc_amount": 0.01,
            "payment_address": "tb1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
            "status": "pending",
            "created_at": int(time.time()),
            "expires_at": int(time.time()) + 3600
        }
        
        # Step 3: Check payment status
        status_response = Mock()
        status_response.status_code = 200
        status_response.json.return_value = {
            "payment_id": "pay_workflow_123",
            "user_id": "cli_user",
            "aitbc_amount": 1000,
            "btc_amount": 0.01,
            "payment_address": "tb1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
            "status": "pending",
            "created_at": int(time.time()),
            "expires_at": int(time.time()) + 3600,
            "confirmations": 0
        }
        
        # Configure mock to return different responses for different calls
        mock_client.get.side_effect = [rates_response, status_response]
        mock_client.post.return_value = payment_response
        
        # Execute workflow
        # Get rates
        result1 = runner.invoke(exchange, ['rates'], 
                              obj={'config': mock_config, 'output_format': 'json'})
        assert result1.exit_code == 0
        
        # Create payment
        result2 = runner.invoke(exchange, [
            'create-payment',
            '--aitbc-amount', '1000'
        ], obj={'config': mock_config, 'output_format': 'json'})
        assert result2.exit_code == 0
        
        # Check payment status
        result3 = runner.invoke(exchange, [
            'payment-status',
            '--payment-id', 'pay_workflow_123'
        ], obj={'config': mock_config, 'output_format': 'json'})
        assert result3.exit_code == 0
        
        # Verify all API calls were made
        assert mock_client.get.call_count == 3  # rates (standalone) + rates (create-payment) + payment status
        assert mock_client.post.call_count == 1  # create payment
