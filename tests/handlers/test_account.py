"""
Account Handler Tests
Tests for account-related CLI handlers
"""

import json
from unittest.mock import Mock, patch

import pytest
from handlers.account import (
    handle_account_get,
    render_mapping,
)

from aitbc.exceptions import NetworkError


class TestRenderMapping:
    """Test render_mapping function"""

    @patch("builtins.print")
    def test_render_mapping_basic(self, mock_print):
        """Test basic mapping rendering"""
        mapping = {"key1": "value1", "key2": "value2"}

        render_mapping("Test Title", mapping)

        # Check that print was called with title and key-value pairs
        assert mock_print.call_count == 3  # Title + 2 key-value pairs

    @patch("builtins.print")
    def test_render_mapping_empty(self, mock_print):
        """Test rendering empty mapping"""
        mapping = {}

        render_mapping("Test Title", mapping)

        # Should only print title
        assert mock_print.call_count == 1


class TestHandleAccountGet:
    """Test handle_account_get function"""

    @patch("handlers.account.AITBCHTTPClient")
    @patch("handlers.account.logger")
    def test_handle_account_get_success(self, mock_logger, mock_client_class):
        """Test successful account retrieval"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get.return_value = {"balance": 100, "nonce": 5}

        args = Mock()
        args.address = "0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C"
        args.rpc_url = "http://localhost:8202"
        args.chain_id = None

        def output_format(args):
            return "text"

        handle_account_get(args, "http://localhost:8202", output_format)

        mock_client.get.assert_called_once()
        mock_logger.info.assert_called()

    @patch("handlers.account.AITBCHTTPClient")
    @patch("handlers.account.logger")
    def test_handle_account_get_with_chain_id(self, mock_logger, mock_client_class):
        """Test account retrieval with chain_id parameter"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get.return_value = {"balance": 100}

        args = Mock()
        args.address = "0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C"
        args.rpc_url = "http://localhost:8202"
        args.chain_id = "ait-mainnet"

        def output_format(args):
            return "text"

        handle_account_get(args, "http://localhost:8202", output_format)

        # Check that chain_id was passed in params
        call_args = mock_client.get.call_args
        assert "params" in call_args[1]
        assert call_args[1]["params"]["chain_id"] == "ait-mainnet"

    @patch("handlers.account.logger")
    @patch("sys.exit")
    def test_handle_account_get_missing_address(self, mock_exit, mock_logger):
        """Test account retrieval with missing address"""
        args = Mock()
        args.address = None
        args.rpc_url = "http://localhost:8202"

        def output_format(args):
            return "text"

        handle_account_get(args, "http://localhost:8202", output_format)

        mock_logger.error.assert_called()
        mock_exit.assert_called_with(1)

    @patch("handlers.account.AITBCHTTPClient")
    @patch("handlers.account.logger")
    @patch("sys.exit")
    def test_handle_account_get_network_error(self, mock_exit, mock_logger, mock_client_class):
        """Test account retrieval with network error"""
        mock_client_class.side_effect = NetworkError("Connection failed")

        args = Mock()
        args.address = "0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C"
        args.rpc_url = "http://localhost:8202"
        args.chain_id = None

        def output_format(args):
            return "text"

        handle_account_get(args, "http://localhost:8202", output_format)

        mock_logger.error.assert_called()
        mock_exit.assert_called_with(1)

    @patch("handlers.account.AITBCHTTPClient")
    @patch("handlers.account.logger")
    @patch("sys.exit")
    def test_handle_account_get_generic_error(self, mock_exit, mock_logger, mock_client_class):
        """Test account retrieval with generic error"""
        mock_client_class.side_effect = Exception("Unexpected error")

        args = Mock()
        args.address = "0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C"
        args.rpc_url = "http://localhost:8202"
        args.chain_id = None

        def output_format(args):
            return "text"

        handle_account_get(args, "http://localhost:8202", output_format)

        mock_logger.error.assert_called()
        mock_exit.assert_called_with(1)

    @patch("handlers.account.AITBCHTTPClient")
    @patch("handlers.account.logger")
    def test_handle_account_get_json_output(self, mock_logger, mock_client_class):
        """Test account retrieval with JSON output format"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get.return_value = {"balance": 100, "nonce": 5}

        args = Mock()
        args.address = "0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C"
        args.rpc_url = "http://localhost:8202"
        args.chain_id = None

        def output_format(args):
            return "json"

        handle_account_get(args, "http://localhost:8202", output_format)

        # Check that JSON output was logged
        mock_logger.info.assert_called()
        # The logged message should be JSON
        logged_msg = mock_logger.info.call_args[0][0]
        assert isinstance(logged_msg, str)
        # Should be valid JSON
        json.loads(logged_msg)

    @patch("handlers.account.AITBCHTTPClient")
    @patch("handlers.account.logger")
    def test_handle_account_get_uses_default_rpc(self, mock_logger, mock_client_class):
        """Test that default RPC URL is used when args.rpc_url is None"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get.return_value = {"balance": 100}

        args = Mock()
        args.address = "0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C"
        args.rpc_url = None
        args.chain_id = None

        def output_format(args):
            return "text"

        default_rpc = "http://default:8202"
        handle_account_get(args, default_rpc, output_format)

        # Check that default RPC was used
        mock_client_class.assert_called_with(base_url=default_rpc, timeout=10)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
