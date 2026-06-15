"""
Contract Handler Tests
Tests for contract command handlers
"""

from unittest.mock import Mock, patch

import pytest
from handlers.contract import (
    handle_contract_call,
    handle_contract_deploy,
    handle_contract_list,
    handle_contract_verify,
)


class TestHandleContractList:
    """Test handle_contract_list function"""

    @patch("handlers.contract.requests.get")
    @patch("handlers.contract.logger")
    def test_handle_contract_list_success(self, mock_logger, mock_get):
        """Test successful contract list"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "contracts": [
                {"address": "0x123", "type": "zk-verifier", "deployed_at": "2024-01-01"},
                {"address": "0x456", "type": "escrow", "deployed_at": "2024-01-02"},
            ],
        }
        mock_get.return_value = mock_response

        args = Mock()
        args.rpc_url = "http://localhost:8006"

        handle_contract_list(args, "http://localhost:8006")

        mock_get.assert_called_once()
        mock_logger.info.assert_called()

    @patch("handlers.contract.requests.get")
    @patch("handlers.contract.logger")
    def test_handle_contract_list_empty(self, mock_logger, mock_get):
        """Test contract list with no contracts"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True, "contracts": []}
        mock_get.return_value = mock_response

        args = Mock()
        args.rpc_url = "http://localhost:8006"

        handle_contract_list(args, "http://localhost:8006")

        mock_logger.info.assert_called()

    @patch("handlers.contract.requests.get")
    @patch("handlers.contract.logger")
    def test_handle_contract_list_default_rpc(self, mock_logger, mock_get):
        """Test contract list with default RPC URL"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"contracts": [{"address": "0x123", "type": "zk-verifier"}]}
        mock_get.return_value = mock_response

        args = Mock()
        args.rpc_url = None

        handle_contract_list(args, "http://default:8006")

        mock_get.assert_called_once()

    @patch("handlers.contract.requests.get")
    @patch("handlers.contract.logger")
    def test_handle_contract_list_http_error(self, mock_logger, mock_get):
        """Test contract list with HTTP error"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        args = Mock()
        args.rpc_url = "http://localhost:8006"

        handle_contract_list(args, "http://localhost:8006")

        mock_logger.error.assert_called()

    @patch("handlers.contract.requests.get")
    @patch("handlers.contract.logger")
    def test_handle_contract_list_exception(self, mock_logger, mock_get):
        """Test contract list with exception"""
        mock_get.side_effect = Exception("Connection error")

        args = Mock()
        args.rpc_url = "http://localhost:8006"

        handle_contract_list(args, "http://localhost:8006")

        mock_logger.error.assert_called()


class TestHandleContractDeploy:
    """Test handle_contract_deploy function"""

    @patch("handlers.contract.requests.post")
    @patch("handlers.contract.logger")
    def test_handle_contract_deploy_success(self, mock_logger, mock_post):
        """Test successful contract deployment"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True, "address": "0x123"}
        mock_post.return_value = mock_response

        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.name = "test-contract"
        args.type = "zk-verifier"
        args.password = "testpass"

        def read_password(args):
            return "testpass"

        def render_mapping(title, data):
            pass

        handle_contract_deploy(args, "http://localhost:8006", read_password, render_mapping)

        mock_post.assert_called_once()

    @patch("handlers.contract.logger")
    def test_handle_contract_deploy_missing_name(self, mock_logger):
        """Test contract deployment with missing name"""
        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.name = None
        args.type = "zk-verifier"

        def read_password(args):
            return "testpass"

        def render_mapping(title, data):
            pass

        handle_contract_deploy(args, "http://localhost:8006", read_password, render_mapping)

        mock_logger.error.assert_called()

    @patch("handlers.contract.logger")
    def test_handle_contract_deploy_missing_password(self, mock_logger):
        """Test contract deployment with missing password"""
        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.name = "test-contract"
        args.type = "zk-verifier"

        def read_password(args):
            return None

        def render_mapping(title, data):
            pass

        handle_contract_deploy(args, "http://localhost:8006", read_password, render_mapping)

        mock_logger.error.assert_called()

    @patch("handlers.contract.requests.post")
    @patch("handlers.contract.logger")
    def test_handle_contract_deploy_http_error(self, mock_logger, mock_post):
        """Test contract deployment with HTTP error"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response

        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.name = "test-contract"
        args.type = "zk-verifier"
        args.password = "testpass"

        def read_password(args):
            return "testpass"

        def render_mapping(title, data):
            pass

        handle_contract_deploy(args, "http://localhost:8006", read_password, render_mapping)

        mock_logger.error.assert_called()


class TestHandleContractCall:
    """Test handle_contract_call function"""

    @patch("handlers.contract.requests.post")
    @patch("handlers.contract.logger")
    def test_handle_contract_call_success(self, mock_logger, mock_post):
        """Test successful contract call"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True, "result": "0xabc"}
        mock_post.return_value = mock_response

        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.address = "0x123"
        args.method = "verify"
        args.password = "testpass"
        args.params = None

        def read_password(args):
            return "testpass"

        handle_contract_call(args, "http://localhost:8006", read_password)

        mock_post.assert_called_once()
        mock_logger.info.assert_called()

    @patch("handlers.contract.logger")
    def test_handle_contract_call_missing_address(self, mock_logger):
        """Test contract call with missing address"""
        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.address = None
        args.method = "verify"

        def read_password(args):
            return "testpass"

        handle_contract_call(args, "http://localhost:8006", read_password)

        mock_logger.error.assert_called()

    @patch("handlers.contract.logger")
    def test_handle_contract_call_missing_method(self, mock_logger):
        """Test contract call with missing method"""
        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.address = "0x123"
        args.method = None

        def read_password(args):
            return "testpass"

        handle_contract_call(args, "http://localhost:8006", read_password)

        mock_logger.error.assert_called()

    @patch("handlers.contract.requests.post")
    @patch("handlers.contract.logger")
    def test_handle_contract_call_with_params(self, mock_logger, mock_post):
        """Test contract call with parameters"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True, "result": "0xabc"}
        mock_post.return_value = mock_response

        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.address = "0x123"
        args.method = "verify"
        args.password = "testpass"
        args.params = {"arg1": "value1"}

        def read_password(args):
            return "testpass"

        handle_contract_call(args, "http://localhost:8006", read_password)

        mock_post.assert_called_once()


class TestHandleContractVerify:
    """Test handle_contract_verify function"""

    @patch("handlers.contract.requests.post")
    @patch("handlers.contract.logger")
    def test_handle_contract_verify_success(self, mock_logger, mock_post):
        """Test successful contract verification"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True, "result": {"valid": True, "receipt_hash": "0xxyz"}}
        mock_post.return_value = mock_response

        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.address = "0x123"
        args.password = "testpass"
        args.proof_file = None

        def read_password(args):
            return "testpass"

        handle_contract_verify(args, "http://localhost:8006", read_password)

        mock_post.assert_called_once()
        mock_logger.info.assert_called()

    @patch("handlers.contract.logger")
    def test_handle_contract_verify_missing_address(self, mock_logger):
        """Test contract verification with missing address"""
        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.address = None

        def read_password(args):
            return "testpass"

        handle_contract_verify(args, "http://localhost:8006", read_password)

        mock_logger.error.assert_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
