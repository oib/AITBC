"""
Market Handler Tests
Tests for marketplace command handlers
"""

from unittest.mock import Mock, patch

import pytest
from handlers.market import (
    handle_market_buy,
    handle_market_create,
    handle_market_delete,
    handle_market_get,
    handle_market_gpu_list,
    handle_market_gpu_register,
    handle_market_list_plugins,
    handle_market_listings,
    handle_market_orders,
    handle_market_sell,
)


class TestHandleMarketListings:
    """Test handle_market_listings function"""

    @patch("handlers.market.requests.get")
    @patch("builtins.print")
    def test_handle_market_listings_json(self, mock_print, mock_get):
        """Test marketplace listings with JSON output"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"id": 1, "model": "RTX 4090", "price_per_hour": 100}]
        mock_get.return_value = mock_response

        args = Mock()
        args.marketplace_url = None
        args.chain_id = None

        def output_format(args):
            return "json"

        def render_mapping(title, data):
            pass

        handle_market_listings(args, "http://localhost:8203", output_format, render_mapping)

        mock_get.assert_called_once()

    @patch("handlers.market.requests.get")
    @patch("builtins.print")
    def test_handle_market_listings_text(self, mock_print, mock_get):
        """Test marketplace listings with text output"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"id": 1, "model": "RTX 4090", "price_per_hour": 100}]
        mock_get.return_value = mock_response

        args = Mock()
        args.marketplace_url = None
        args.chain_id = None

        def output_format(args):
            return "text"

        def render_mapping(title, data):
            pass

        handle_market_listings(args, "http://localhost:8203", output_format, render_mapping)

        mock_get.assert_called_once()


class TestHandleMarketCreate:
    """Test handle_market_create function"""

    @patch("handlers.market.requests.post")
    @patch("handlers.market.logger")
    def test_handle_market_create_success(self, mock_logger, mock_post):
        """Test successful marketplace listing creation"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": 1, "status": "active"}
        mock_post.return_value = mock_response

        args = Mock()
        args.marketplace_url = None
        args.chain_id = None
        args.wallet = "wallet1"
        args.item = "service"
        args.item_type = None
        args.price = 100
        args.description = "Test service"
        args.password_file = None

        def read_password(args):
            return "password"

        def render_mapping(title, data):
            pass

        handle_market_create(args, "http://localhost:8203", read_password, render_mapping)

        mock_post.assert_called_once()

    @patch("handlers.market.logger")
    def test_handle_market_create_missing_params(self, mock_logger):
        """Test marketplace creation with missing parameters"""
        args = Mock()
        args.marketplace_url = None
        args.chain_id = None
        args.wallet = None
        args.item = None
        args.item_type = None
        args.price = None

        def read_password(args):
            return "password"

        def render_mapping(title, data):
            pass

        handle_market_create(args, "http://localhost:8203", read_password, render_mapping)

        mock_logger.error.assert_called()


class TestHandleMarketGet:
    """Test handle_market_get function"""

    @patch("handlers.market.requests.get")
    @patch("handlers.market.logger")
    def test_handle_market_get_success(self, mock_logger, mock_get):
        """Test successful marketplace listing retrieval"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": 1, "model": "RTX 4090"}
        mock_get.return_value = mock_response

        args = Mock()
        args.marketplace_url = None
        args.chain_id = None
        args.listing_id = 1

        handle_market_get(args, "http://localhost:8202")

        mock_get.assert_called_once()

    @patch("handlers.market.logger")
    def test_handle_market_get_missing_id(self, mock_logger):
        """Test marketplace retrieval with missing listing ID"""
        args = Mock()
        args.marketplace_url = None
        args.chain_id = None
        args.listing_id = None

        handle_market_get(args, "http://localhost:8202")

        mock_logger.error.assert_called()


class TestHandleMarketDelete:
    """Test handle_market_delete function"""

    @patch("handlers.market.requests.delete")
    @patch("handlers.market.logger")
    def test_handle_market_delete_success(self, mock_logger, mock_delete):
        """Test successful marketplace deletion"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True}
        mock_delete.return_value = mock_response

        args = Mock()
        args.marketplace_url = None
        args.listing_id = 1
        args.order = None
        args.wallet = None
        args.password_file = None

        def read_password(args):
            return "password"

        def render_mapping(title, data):
            pass

        handle_market_delete(args, "http://localhost:8203", read_password, render_mapping)

        mock_delete.assert_called_once()

    @patch("handlers.market.logger")
    def test_handle_market_delete_missing_id(self, mock_logger):
        """Test marketplace deletion with missing ID"""
        args = Mock()
        args.marketplace_url = None
        args.listing_id = None
        args.order = None

        def read_password(args):
            return "password"

        def render_mapping(title, data):
            pass

        handle_market_delete(args, "http://localhost:8203", read_password, render_mapping)

        mock_logger.error.assert_called()


class TestHandleMarketGpuRegister:
    """Test handle_market_gpu_register function"""

    @patch("subprocess.run")
    @patch("handlers.market.requests.post")
    @patch("handlers.market.logger")
    @patch("builtins.print")
    def test_handle_market_gpu_register_success(self, mock_print, mock_logger, mock_post, mock_subprocess):
        """Test successful GPU registration"""
        mock_subprocess_result = Mock()
        mock_subprocess_result.returncode = 0
        mock_subprocess_result.stdout = "NVIDIA GeForce RTX 4060 Ti, 16380 MiB, 8.9"
        mock_subprocess.return_value = mock_subprocess_result

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"blockchain_registered": True, "transaction_id": "tx_123"}
        mock_post.return_value = mock_response

        args = Mock()
        args.gpu_url = "http://localhost:8101"
        args.price_per_hour = 100
        args.cuda_cores = None
        args.description = "Test GPU"
        args.miner_id = "miner1"
        args.wallet = "wallet1"
        args.signature = None
        args.region = None

        handle_market_gpu_register(args, "http://localhost:8203")

        mock_post.assert_called_once()

    @patch("subprocess.run")
    @patch("handlers.market.logger")
    def test_handle_market_gpu_register_nvidia_smi_fail(self, mock_logger, mock_subprocess):
        """Test GPU registration with nvidia-smi failure"""
        mock_subprocess_result = Mock()
        mock_subprocess_result.returncode = 1
        mock_subprocess.return_value = mock_subprocess_result

        args = Mock()
        args.gpu_url = "http://localhost:8101"
        args.price_per_hour = 100

        handle_market_gpu_register(args, "http://localhost:8203")

        mock_logger.error.assert_called()

    @patch("handlers.market.logger")
    def test_handle_market_gpu_register_missing_price(self, mock_logger):
        """Test GPU registration with missing price"""
        args = Mock()
        args.gpu_url = "http://localhost:8101"
        args.price_per_hour = None

        handle_market_gpu_register(args, "http://localhost:8203")

        mock_logger.error.assert_called()


class TestHandleMarketGpuList:
    """Test handle_market_gpu_list function"""

    @patch("handlers.market.requests.get")
    @patch("builtins.print")
    def test_handle_market_gpu_list_json(self, mock_print, mock_get):
        """Test GPU list with JSON output"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"id": 1, "model": "RTX 4090", "memory_gb": 24}]
        mock_get.return_value = mock_response

        args = Mock()
        args.gpu_url = "http://localhost:8101"
        args.available = None
        args.price_max = None
        args.region = None
        args.model = None
        args.limit = None

        def output_format(args):
            return "json"

        handle_market_gpu_list(args, "http://localhost:8203", output_format)

        mock_get.assert_called_once()

    @patch("handlers.market.requests.get")
    @patch("builtins.print")
    def test_handle_market_gpu_list_text(self, mock_print, mock_get):
        """Test GPU list with text output"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"id": 1, "model": "RTX 4090", "memory_gb": 24}]
        mock_get.return_value = mock_response

        args = Mock()
        args.gpu_url = "http://localhost:8101"
        args.available = True
        args.price_max = None
        args.region = None
        args.model = None
        args.limit = None

        def output_format(args):
            return "text"

        handle_market_gpu_list(args, "http://localhost:8203", output_format)

        mock_get.assert_called_once()


class TestHandleMarketBuy:
    """Test handle_market_buy function"""

    @patch("handlers.market.requests.post")
    @patch("handlers.market.logger")
    def test_handle_market_buy_success(self, mock_logger, mock_post):
        """Test successful marketplace purchase"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"order_id": "order_123", "status": "pending"}
        mock_post.return_value = mock_response

        args = Mock()
        args.marketplace_url = None
        args.item = "item1"
        args.wallet = "wallet1"
        args.price = 100
        args.password_file = None

        def read_password(args):
            return "password"

        def render_mapping(title, data):
            pass

        handle_market_buy(args, "http://localhost:8203", read_password, render_mapping)

        mock_post.assert_called_once()

    @patch("handlers.market.logger")
    def test_handle_market_buy_missing_params(self, mock_logger):
        """Test marketplace purchase with missing parameters"""
        args = Mock()
        args.marketplace_url = None
        args.item = None
        args.wallet = None

        def read_password(args):
            return "password"

        def render_mapping(title, data):
            pass

        handle_market_buy(args, "http://localhost:8203", read_password, render_mapping)

        mock_logger.error.assert_called()


class TestHandleMarketSell:
    """Test handle_market_sell function"""

    @patch("handlers.market.handle_market_create")
    def test_handle_market_sell(self, mock_create):
        """Test marketplace sell (delegates to create)"""
        args = Mock()

        def read_password(args):
            return "password"

        def render_mapping(title, data):
            pass

        handle_market_sell(args, "http://localhost:8203", read_password, render_mapping)

        mock_create.assert_called_once()


class TestHandleMarketOrders:
    """Test handle_market_orders function"""

    @patch("handlers.market.requests.get")
    @patch("handlers.market.logger")
    def test_handle_market_orders_json(self, mock_logger, mock_get):
        """Test marketplace orders with JSON output"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"id": 1, "order_type": "buy", "status": "pending"}]
        mock_get.return_value = mock_response

        args = Mock()
        args.marketplace_url = None
        args.wallet = "wallet1"

        def output_format(args):
            return "json"

        def render_mapping(title, data):
            pass

        handle_market_orders(args, "http://localhost:8203", output_format, render_mapping)

        mock_get.assert_called_once()

    @patch("handlers.market.requests.get")
    @patch("handlers.market.logger")
    def test_handle_market_orders_text(self, mock_logger, mock_get):
        """Test marketplace orders with text output"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"orders": [{"id": 1, "order_type": "buy", "status": "pending"}]}
        mock_get.return_value = mock_response

        args = Mock()
        args.marketplace_url = None
        args.wallet = None

        def output_format(args):
            return "text"

        def render_mapping(title, data):
            pass

        handle_market_orders(args, "http://localhost:8203", output_format, render_mapping)

        mock_get.assert_called_once()


class TestHandleMarketListPlugins:
    """Test handle_market_list_plugins function"""

    @patch("handlers.market.requests.get")
    @patch("handlers.market.logger")
    def test_handle_market_list_plugins_json(self, mock_logger, mock_get):
        """Test plugin listing with JSON output"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"id": 1, "name": "plugin1", "type": "inference"}]
        mock_get.return_value = mock_response

        args = Mock()
        args.marketplace_url = None

        def output_format(args):
            return "json"

        def render_mapping(title, data):
            pass

        handle_market_list_plugins(args, "http://localhost:8203", output_format, render_mapping)

        mock_get.assert_called_once()

    @patch("handlers.market.requests.get")
    @patch("handlers.market.logger")
    def test_handle_market_list_plugins_text(self, mock_logger, mock_get):
        """Test plugin listing with text output"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"plugins": [{"id": 1, "name": "plugin1", "type": "inference"}]}
        mock_get.return_value = mock_response

        args = Mock()
        args.marketplace_url = None

        def output_format(args):
            return "text"

        def render_mapping(title, data):
            pass

        handle_market_list_plugins(args, "http://localhost:8203", output_format, render_mapping)

        mock_get.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
