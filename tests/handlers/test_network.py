"""
Network Handler Tests
Tests for network status and peer management handlers
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest
from handlers.network import (
    handle_network_force_sync,
    handle_network_peers,
    handle_network_ping,
    handle_network_propagate,
    handle_network_status,
    handle_network_sync,
)


class TestHandleNetworkStatus:
    """Test handle_network_status function"""

    @patch('click.echo')
    def test_handle_network_status_success(self, mock_echo):
        """Test successful network status query"""
        args = Mock()
        args.rpc_url = "http://localhost:8006"

        def get_network_snapshot(rpc_url):
            return {
                "connected_count": 3,
                "sync_status": "synced",
                "nodes": [
                    {"name": "local", "healthy": True},
                    {"name": "peer1", "healthy": True},
                    {"name": "peer2", "healthy": False}
                ]
            }

        handle_network_status(args, "http://localhost:8006", get_network_snapshot)

        mock_echo.assert_called()


class TestHandleNetworkPeers:
    """Test handle_network_peers function"""

    @patch('handlers.network.logger')
    def test_handle_network_peers_success(self, mock_logger):
        """Test successful network peers query"""
        args = Mock()
        args.rpc_url = "http://localhost:8006"

        def get_network_snapshot(rpc_url):
            return {
                "nodes": [
                    {"name": "peer1", "rpc_url": "http://localhost:8006", "healthy": True, "error": None},
                    {"name": "peer2", "rpc_url": "http://localhost:8007", "healthy": False, "error": "timeout"}
                ]
            }

        handle_network_peers(args, "http://localhost:8006", get_network_snapshot)

        mock_logger.info.assert_called()


class TestHandleNetworkSync:
    """Test handle_network_sync function"""

    @patch('click.echo')
    def test_handle_network_sync_success(self, mock_echo):
        """Test successful network sync status query"""
        args = Mock()
        args.rpc_url = "http://localhost:8006"

        def get_network_snapshot(rpc_url):
            return {
                "sync_status": "synced",
                "nodes": [
                    {"name": "local", "height": 100, "timestamp": "2024-01-01"},
                    {"name": "peer1", "height": 100}
                ]
            }

        handle_network_sync(args, "http://localhost:8006", get_network_snapshot)

        mock_echo.assert_called()


class TestHandleNetworkPing:
    """Test handle_network_ping function"""

    @patch('builtins.print')
    def test_handle_network_ping_success(self, mock_print):
        """Test successful network ping"""
        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.node_opt = "localhost:8007"
        args.node = None

        def read_blockchain_env():
            return {"rpc_bind_port": "8006", "chain_id": "ait-testnet"}

        def normalize_rpc_url(url):
            return ("http", "localhost", 8006)

        def first(*args):
            for arg in args:
                if arg is not None:
                    return arg
            return None

        def probe_rpc_node(name, url, chain_id):
            return {"healthy": True, "rpc_url": url, "latency_ms": 10}

        handle_network_ping(args, "http://localhost:8006", read_blockchain_env, normalize_rpc_url, first, probe_rpc_node)

        mock_print.assert_called()


class TestHandleNetworkPropagate:
    """Test handle_network_propagate function"""

    @patch('builtins.print')
    def test_handle_network_propagate_success(self, mock_print):
        """Test successful network data propagation"""
        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.data_opt = None
        args.data = "test-data"

        def get_network_snapshot(rpc_url):
            return {
                "connected_count": 2,
                "nodes": [
                    {"name": "peer1", "healthy": True},
                    {"name": "peer2", "healthy": True}
                ]
            }

        def first(*args):
            return args[0] if args else None

        handle_network_propagate(args, "http://localhost:8006", get_network_snapshot, first)

        mock_print.assert_called()


class TestHandleNetworkForceSync:
    """Test handle_network_force_sync function"""

    @patch('handlers.network.requests.post')
    @patch('handlers.network.logger')
    @patch('sys.exit')
    def test_handle_network_force_sync_success(self, mock_exit, mock_logger, mock_post):
        """Test successful network force sync"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True}
        mock_post.return_value = mock_response

        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None
        args.peer = "peer1"

        def render_mapping(title, data):
            pass

        handle_network_force_sync(args, "http://localhost:8006", render_mapping)

        mock_post.assert_called_once()

    @patch('handlers.network.logger')
    @patch('sys.exit')
    def test_handle_network_force_sync_missing_peer(self, mock_exit, mock_logger):
        """Test network force sync with missing peer"""
        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None
        args.peer = None

        def render_mapping(title, data):
            pass

        handle_network_force_sync(args, "http://localhost:8006", render_mapping)

        mock_exit.assert_called_with(1)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
