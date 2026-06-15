"""
Blockchain Handler Tests
Tests for blockchain command handlers
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest  # noqa: E402
from handlers.blockchain import (  # noqa: E402
    handle_blockchain_block,
    handle_blockchain_blocks_range,
    handle_blockchain_export,
    handle_blockchain_genesis,
    handle_blockchain_height,
    handle_blockchain_import,
    handle_blockchain_info,
    handle_blockchain_init,
    handle_blockchain_mempool,
    handle_blockchain_transactions,
)


class TestHandleBlockchainInfo:
    """Test handle_blockchain_info function"""

    @patch("handlers.blockchain.logger")
    def test_handle_blockchain_info_success(self, mock_logger):
        """Test successful blockchain info retrieval"""
        args = Mock()
        args.rpc_url = "http://localhost:8006"

        mock_chain_info = {"height": 100, "hash": "0x123"}

        def get_chain_info(rpc_url):
            return mock_chain_info

        def render_mapping(title, data):
            pass

        handle_blockchain_info(args, get_chain_info, render_mapping)

        # Should not exit if chain_info is truthy

    @patch("handlers.blockchain.logger")
    @patch("sys.exit")
    def test_handle_blockchain_info_no_info(self, mock_exit, mock_logger):
        """Test blockchain info with no data"""
        args = Mock()
        args.rpc_url = "http://localhost:8006"

        def get_chain_info(rpc_url):
            return None

        def render_mapping(title, data):
            pass

        handle_blockchain_info(args, get_chain_info, render_mapping)

        mock_exit.assert_called_with(1)


class TestHandleBlockchainHeight:
    """Test handle_blockchain_height function"""

    @patch("builtins.print")
    def test_handle_blockchain_height_success(self, mock_print):
        """Test successful blockchain height retrieval"""
        args = Mock()
        args.rpc_url = "http://localhost:8006"

        mock_chain_info = {"height": 100}

        def get_chain_info(rpc_url):
            return mock_chain_info

        handle_blockchain_height(args, get_chain_info)

        mock_print.assert_called()

    @patch("builtins.print")
    def test_handle_blockchain_height_no_info(self, mock_print):
        """Test blockchain height with no data"""
        args = Mock()
        args.rpc_url = "http://localhost:8006"

        def get_chain_info(rpc_url):
            return None

        handle_blockchain_height(args, get_chain_info)

        mock_print.assert_called_with(0)


class TestHandleBlockchainBlock:
    """Test handle_blockchain_block function"""

    @patch("handlers.blockchain.requests.get")
    @patch("builtins.print")
    @patch("sys.exit")
    def test_handle_blockchain_block_success(self, mock_exit, mock_print, mock_get):
        """Test successful block retrieval"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"hash": "0x123", "timestamp": "2024-01-01", "tx_count": 5, "proposer": "miner1"}
        mock_get.return_value = mock_response

        args = Mock()
        args.number = 100
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None

        handle_blockchain_block(args, "http://localhost:8006")

        mock_get.assert_called_once()

    @patch("builtins.print")
    @patch("sys.exit")
    def test_handle_blockchain_block_missing_number(self, mock_exit, mock_print):
        """Test block retrieval with missing block number"""
        args = Mock()
        args.number = None

        handle_blockchain_block(args, "http://localhost:8006")

        mock_exit.assert_called_with(1)

    @patch("handlers.blockchain.requests.get")
    @patch("builtins.print")
    @patch("sys.exit")
    def test_handle_blockchain_block_http_error(self, mock_exit, mock_print, mock_get):
        """Test block retrieval with HTTP error"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        args = Mock()
        args.number = 100
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None

        handle_blockchain_block(args, "http://localhost:8006")

        mock_exit.assert_called_with(1)


class TestHandleBlockchainInit:
    """Test handle_blockchain_init function"""

    @patch("handlers.blockchain.requests.get")
    @patch("handlers.blockchain.logger")
    @patch("sys.exit")
    def test_handle_blockchain_init_initialized(self, mock_exit, mock_logger, mock_get):
        """Test blockchain init when already initialized"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"hash": "0x123", "number": 0}
        mock_get.return_value = mock_response

        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.force = False

        handle_blockchain_init(args, "http://localhost:8006")

        mock_logger.info.assert_called()

    @patch("handlers.blockchain.requests.get")
    @patch("handlers.blockchain.logger")
    @patch("sys.exit")
    def test_handle_blockchain_init_not_initialized(self, mock_exit, mock_logger, mock_get):
        """Test blockchain init when not initialized"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.force = False

        handle_blockchain_init(args, "http://localhost:8006")

        mock_exit.assert_called_with(1)


class TestHandleBlockchainGenesis:
    """Test handle_blockchain_genesis function"""

    @patch("handlers.blockchain.requests.get")
    @patch("handlers.blockchain.logger")
    @patch("sys.exit")
    def test_handle_blockchain_genesis_create_exists(self, mock_exit, mock_logger, mock_get):
        """Test genesis create when block already exists"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"hash": "0x123", "number": 0}
        mock_get.return_value = mock_response

        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.create = True

        handle_blockchain_genesis(args, "http://localhost:8006")

        mock_logger.info.assert_called()

    @patch("handlers.blockchain.requests.get")
    @patch("handlers.blockchain.logger")
    @patch("sys.exit")
    def test_handle_blockchain_genesis_inspect_success(self, mock_exit, mock_logger, mock_get):
        """Test genesis inspect success"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "hash": "0x123",
            "number": 0,
            "timestamp": "2024-01-01",
            "miner": "miner1",
            "reward": 100,
        }
        mock_get.return_value = mock_response

        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.create = False

        handle_blockchain_genesis(args, "http://localhost:8006")

        mock_logger.info.assert_called()


class TestHandleBlockchainImport:
    """Test handle_blockchain_import function"""

    @patch("handlers.blockchain.logger")
    @patch("sys.exit")
    def test_handle_blockchain_import_missing_input(self, mock_exit, mock_logger):
        """Test block import with missing input"""
        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None
        args.file = None
        args.json = None

        def render_mapping(title, data):
            pass

        handle_blockchain_import(args, "http://localhost:8006", render_mapping)

        mock_exit.assert_called_with(1)


class TestHandleBlockchainExport:
    """Test handle_blockchain_export function"""

    @patch("handlers.blockchain.requests.get")
    @patch("handlers.blockchain.logger")
    @patch("sys.exit")
    def test_handle_blockchain_export_to_file(self, mock_exit, mock_logger, mock_get):
        """Test successful chain export to file"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"blocks": []}
        mock_get.return_value = mock_response

        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None
        args.output = "/path/to/export.json"

        with patch("builtins.open", new_callable=Mock):
            handle_blockchain_export(args, "http://localhost:8006")

        mock_get.assert_called_once()

    @patch("handlers.blockchain.requests.get")
    @patch("handlers.blockchain.logger")
    @patch("sys.exit")
    def test_handle_blockchain_export_to_stdout(self, mock_exit, mock_logger, mock_get):
        """Test successful chain export to stdout"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"blocks": []}
        mock_get.return_value = mock_response

        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None
        args.output = None

        handle_blockchain_export(args, "http://localhost:8006")

        mock_get.assert_called_once()


class TestHandleBlockchainImportChain:
    """Test handle_blockchain_import_chain function"""


class TestHandleBlockchainBlocksRange:
    """Test handle_blockchain_blocks_range function"""

    @patch("handlers.blockchain.requests.get")
    @patch("handlers.blockchain.logger")
    @patch("sys.exit")
    def test_handle_blockchain_blocks_range_json(self, mock_exit, mock_logger, mock_get):
        """Test blocks range with JSON output"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"height": 100, "hash": "0x123"}]
        mock_get.return_value = mock_response

        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None
        args.limit = 10
        args.start = None
        args.end = None

        def output_format(args):
            return "json"

        handle_blockchain_blocks_range(args, "http://localhost:8006", output_format)

        mock_get.assert_called_once()

    @patch("handlers.blockchain.requests.get")
    @patch("handlers.blockchain.logger")
    @patch("sys.exit")
    def test_handle_blockchain_blocks_range_text(self, mock_exit, mock_logger, mock_get):
        """Test blocks range with text output"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"height": 100, "hash": "0x123"}]
        mock_get.return_value = mock_response

        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None
        args.limit = 10
        args.start = 100
        args.end = 200

        def output_format(args):
            return "text"

        handle_blockchain_blocks_range(args, "http://localhost:8006", output_format)

        mock_get.assert_called_once()


class TestHandleBlockchainTransactions:
    """Test handle_blockchain_transactions function"""

    @patch("handlers.blockchain.requests.get")
    @patch("handlers.blockchain.logger")
    @patch("sys.exit")
    def test_handle_blockchain_transactions_success(self, mock_exit, mock_logger, mock_get):
        """Test successful transactions query"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"hash": "0x123", "from": "0xabc", "to": "0xdef", "value": 100}]
        mock_get.return_value = mock_response

        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None
        args.address = None
        args.limit = 10
        args.offset = 0

        handle_blockchain_transactions(args, "http://localhost:8006")

        mock_get.assert_called_once()

    @patch("handlers.blockchain.requests.get")
    @patch("handlers.blockchain.logger")
    @patch("sys.exit")
    def test_handle_blockchain_transactions_with_address(self, mock_exit, mock_logger, mock_get):
        """Test transactions query with address filter"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None
        args.address = "0xabc"
        args.limit = 10
        args.offset = 0

        handle_blockchain_transactions(args, "http://localhost:8006")

        mock_get.assert_called_once()


class TestHandleBlockchainMempool:
    """Test handle_blockchain_mempool function"""

    @patch("handlers.blockchain.requests.get")
    @patch("handlers.blockchain.logger")
    @patch("sys.exit")
    def test_handle_blockchain_mempool_success(self, mock_exit, mock_logger, mock_get):
        """Test successful mempool query"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"hash": "0x123", "from": "0xabc", "value": 100}]
        mock_get.return_value = mock_response

        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None

        handle_blockchain_mempool(args, "http://localhost:8006")

        mock_get.assert_called_once()

    @patch("handlers.blockchain.requests.get")
    @patch("handlers.blockchain.logger")
    @patch("sys.exit")
    def test_handle_blockchain_mempool_with_chain_id(self, mock_exit, mock_logger, mock_get):
        """Test mempool query with chain_id"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.chain_id = "ait-mainnet"

        handle_blockchain_mempool(args, "http://localhost:8006")

        mock_get.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
