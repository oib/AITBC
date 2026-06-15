"""
Wallet Handler Tests
Tests for wallet command handlers
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest
from handlers.wallet import (
    handle_wallet_backup,
    handle_wallet_balance,
    handle_wallet_create,
    handle_wallet_delete,
    handle_wallet_export,
    handle_wallet_import,
    handle_wallet_list,
    handle_wallet_rename,
    handle_wallet_sync,
    handle_wallet_transactions,
)


class TestHandleWalletCreate:
    """Test handle_wallet_create function"""

    @patch("handlers.wallet.logger")
    @patch("sys.exit")
    def test_handle_wallet_create_success(self, mock_exit, mock_logger):
        """Test successful wallet creation"""
        args = Mock()
        args.wallet_name = "wallet1"
        args.wallet_name_opt = None

        def first(*args):
            return args[0] if args else None

        def read_password(args, field):
            return "password"

        def create_wallet(name, password):
            return "0x1234567890abcdef"

        handle_wallet_create(args, create_wallet, read_password, first)

        mock_logger.info.assert_called()

    @patch("handlers.wallet.logger")
    @patch("sys.exit")
    def test_handle_wallet_create_missing_params(self, mock_exit, mock_logger):
        """Test wallet creation with missing parameters"""
        args = Mock()
        args.wallet_name = None
        args.wallet_name_opt = None

        def first(*args):
            return args[0] if args else None

        def read_password(args, field):
            return None

        def create_wallet(name, password):
            return "0x1234567890abcdef"

        handle_wallet_create(args, create_wallet, read_password, first)

        mock_exit.assert_called_with(1)


class TestHandleWalletList:
    """Test handle_wallet_list function"""

    @patch("builtins.print")
    def test_handle_wallet_list_json(self, mock_print):
        """Test wallet list with JSON output"""
        args = Mock()

        def list_wallets():
            return [{"name": "wallet1", "address": "0x123"}]

        def output_format(args):
            return "json"

        handle_wallet_list(args, list_wallets, output_format)

        mock_print.assert_called()

    @patch("builtins.print")
    def test_handle_wallet_list_text(self, mock_print):
        """Test wallet list with text output"""
        args = Mock()

        def list_wallets():
            return [{"name": "wallet1", "address": "0x123"}]

        def output_format(args):
            return "text"

        handle_wallet_list(args, list_wallets, output_format)

        mock_print.assert_called()


class TestHandleWalletBalance:
    """Test handle_wallet_balance function"""

    @patch("handlers.wallet.logger")
    @patch("sys.exit")
    def test_handle_wallet_balance_all(self, mock_exit, mock_logger):
        """Test wallet balance for all wallets"""
        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.all = True

        def list_wallets():
            return [{"name": "wallet1"}]

        def get_balance(name, rpc_url):
            return {"wallet_name": name, "balance": 100, "nonce": 0}

        def first(*args):
            return args[0] if args else None

        handle_wallet_balance(args, "http://localhost:8006", list_wallets, get_balance, first)

        mock_logger.info.assert_called()

    @patch("handlers.wallet.logger")
    @patch("sys.exit")
    def test_handle_wallet_balance_single(self, mock_exit, mock_logger):
        """Test wallet balance for single wallet"""
        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.all = False
        args.wallet_name = "wallet1"
        args.wallet_name_opt = None

        def list_wallets():
            return [{"name": "wallet1"}]

        def get_balance(name, rpc_url):
            return {"wallet_name": name, "balance": 100, "nonce": 0, "address": "0x123"}

        def first(*args):
            return args[0] if args else None

        handle_wallet_balance(args, "http://localhost:8006", list_wallets, get_balance, first)

        mock_logger.info.assert_called()

    @patch("handlers.wallet.logger")
    @patch("sys.exit")
    def test_handle_wallet_balance_missing_name(self, mock_exit, mock_logger):
        """Test wallet balance with missing wallet name"""
        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.all = False
        args.wallet_name = None
        args.wallet_name_opt = None

        def list_wallets():
            return [{"name": "wallet1"}]

        def get_balance(name, rpc_url):
            return {"wallet_name": name, "balance": 100, "address": "0x123", "nonce": 0}

        def first(*args):
            return args[0] if args else None

        handle_wallet_balance(args, "http://localhost:8006", list_wallets, get_balance, first)

        mock_exit.assert_called_with(1)


class TestHandleWalletTransactions:
    """Test handle_wallet_transactions function"""

    @patch("handlers.wallet.logger")
    @patch("sys.exit")
    def test_handle_wallet_transactions_json(self, mock_exit, mock_logger):
        """Test wallet transactions with JSON output"""
        args = Mock()
        args.wallet_name = "wallet1"
        args.wallet_name_opt = None
        args.rpc_url = "http://localhost:8006"
        args.limit = 10

        def first(*args):
            return args[0] if args else None

        def get_transactions(name, limit, rpc_url):
            return [{"hash": "0xabc", "value": 100, "fee": 1, "type": "transfer"}]

        def output_format(args):
            return "json"

        handle_wallet_transactions(args, get_transactions, output_format, first)

        mock_logger.info.assert_called()

    @patch("handlers.wallet.logger")
    @patch("sys.exit")
    def test_handle_wallet_transactions_text(self, mock_exit, mock_logger):
        """Test wallet transactions with text output"""
        args = Mock()
        args.wallet_name = "wallet1"
        args.wallet_name_opt = None
        args.rpc_url = "http://localhost:8006"
        args.limit = 10

        def first(*args):
            return args[0] if args else None

        def get_transactions(name, limit, rpc_url):
            return [{"hash": "0xabc", "value": 100, "fee": 1, "type": "transfer"}]

        def output_format(args):
            return "text"

        handle_wallet_transactions(args, get_transactions, output_format, first)

        mock_logger.info.assert_called()

    @patch("handlers.wallet.logger")
    @patch("sys.exit")
    def test_handle_wallet_transactions_missing_name(self, mock_exit, mock_logger):
        """Test wallet transactions with missing wallet name"""
        args = Mock()
        args.wallet_name = None
        args.wallet_name_opt = None
        args.rpc_url = "http://localhost:8006"
        args.limit = 10

        def first(*args):
            return args[0] if args else None

        def get_transactions(name, limit, rpc_url):
            return []

        def output_format(args):
            return "json"

        handle_wallet_transactions(args, get_transactions, output_format, first)

        mock_exit.assert_called_with(1)


class TestHandleWalletImport:
    """Test handle_wallet_import function"""

    @patch("handlers.wallet.logger")
    @patch("sys.exit")
    def test_handle_wallet_import_success(self, mock_exit, mock_logger):
        """Test successful wallet import"""
        args = Mock()
        args.wallet_name = "wallet1"
        args.wallet_name_opt = None
        args.private_key_arg = "0x123"
        args.private_key_opt = None

        def first(*args):
            return args[0] if args else None

        def read_password(args, field):
            return "password"

        def import_wallet(name, key, password):
            return "0xabcdef"

        handle_wallet_import(args, import_wallet, read_password, first)

        mock_logger.info.assert_called()

    @patch("handlers.wallet.logger")
    @patch("sys.exit")
    def test_handle_wallet_import_missing_params(self, mock_exit, mock_logger):
        """Test wallet import with missing parameters"""
        args = Mock()
        args.wallet_name = None
        args.wallet_name_opt = None
        args.private_key_arg = None
        args.private_key_opt = None

        def first(*args):
            return args[0] if args else None

        def read_password(args, field):
            return "password"

        def import_wallet(name, key, password):
            return "0xabcdef"

        handle_wallet_import(args, import_wallet, read_password, first)

        mock_exit.assert_called_with(1)


class TestHandleWalletExport:
    """Test handle_wallet_export function"""

    @patch("handlers.wallet.logger")
    @patch("sys.exit")
    def test_handle_wallet_export_success(self, mock_exit, mock_logger):
        """Test successful wallet export"""
        args = Mock()
        args.wallet_name = "wallet1"
        args.wallet_name_opt = None

        def first(*args):
            return args[0] if args else None

        def read_password(args, field):
            return "password"

        def export_wallet(name, password):
            return "0xabcdef"

        handle_wallet_export(args, export_wallet, read_password, first)

        mock_logger.info.assert_called()

    @patch("handlers.wallet.logger")
    @patch("sys.exit")
    def test_handle_wallet_export_missing_params(self, mock_exit, mock_logger):
        """Test wallet export with missing parameters"""
        args = Mock()
        args.wallet_name = None
        args.wallet_name_opt = None

        def first(*args):
            return args[0] if args else None

        def read_password(args, field):
            return "password"

        def export_wallet(name, password):
            return "0xabcdef"

        handle_wallet_export(args, export_wallet, read_password, first)

        mock_exit.assert_called_with(1)


class TestHandleWalletDelete:
    """Test handle_wallet_delete function"""

    @patch("handlers.wallet.logger")
    @patch("sys.exit")
    def test_handle_wallet_delete_success(self, mock_exit, mock_logger):
        """Test successful wallet deletion"""
        args = Mock()
        args.wallet_name = "wallet1"
        args.wallet_name_opt = None
        args.confirm = True

        def first(*args):
            return args[0] if args else None

        def delete_wallet(name):
            return True

        handle_wallet_delete(args, delete_wallet, first)

        mock_exit.assert_not_called()

    @patch("handlers.wallet.logger")
    @patch("sys.exit")
    def test_handle_wallet_delete_missing_params(self, mock_exit, mock_logger):
        """Test wallet deletion with missing parameters"""
        args = Mock()
        args.wallet_name = None
        args.wallet_name_opt = None
        args.confirm = True

        def first(*args):
            return args[0] if args else None

        def delete_wallet(name):
            return True

        handle_wallet_delete(args, delete_wallet, first)

        mock_exit.assert_called_with(1)


class TestHandleWalletRename:
    """Test handle_wallet_rename function"""

    @patch("handlers.wallet.logger")
    @patch("sys.exit")
    def test_handle_wallet_rename_success(self, mock_exit, mock_logger):
        """Test successful wallet rename"""
        args = Mock()
        args.old_name_arg = "wallet1"
        args.old_name = None
        args.new_name_arg = "wallet2"
        args.new_name = None

        def first(*args):
            return args[0] if args else None

        def rename_wallet(old, new):
            return True

        handle_wallet_rename(args, rename_wallet, first)

        mock_exit.assert_not_called()

    @patch("handlers.wallet.logger")
    @patch("sys.exit")
    def test_handle_wallet_rename_missing_params(self, mock_exit, mock_logger):
        """Test wallet rename with missing parameters"""
        args = Mock()
        args.old_name_arg = None
        args.old_name = None
        args.new_name_arg = None
        args.new_name = None

        def first(*args):
            return args[0] if args else None

        def rename_wallet(old, new):
            return True

        handle_wallet_rename(args, rename_wallet, first)

        mock_exit.assert_called_with(1)


class TestHandleWalletBackup:
    """Test handle_wallet_backup function"""

    @patch("handlers.wallet.logger")
    @patch("sys.exit")
    def test_handle_wallet_backup_success(self, mock_exit, mock_logger):
        """Test successful wallet backup"""
        args = Mock()
        args.wallet_name = "wallet1"
        args.wallet_name_opt = None

        def first(*args):
            return args[0] if args else None

        handle_wallet_backup(args, first)

        mock_logger.info.assert_called()

    @patch("handlers.wallet.logger")
    @patch("sys.exit")
    def test_handle_wallet_backup_missing_name(self, mock_exit, mock_logger):
        """Test wallet backup with missing wallet name"""
        args = Mock()
        args.wallet_name = None
        args.wallet_name_opt = None

        def first(*args):
            return args[0] if args else None

        handle_wallet_backup(args, first)

        mock_exit.assert_called_with(1)


class TestHandleWalletSync:
    """Test handle_wallet_sync function"""

    @patch("handlers.wallet.logger")
    @patch("sys.exit")
    def test_handle_wallet_sync_all(self, mock_exit, mock_logger):
        """Test wallet sync for all wallets"""
        args = Mock()
        args.wallet_name = None
        args.wallet_name_opt = None
        args.all = True

        def first(*args):
            return args[0] if args else None

        handle_wallet_sync(args, first)

        mock_logger.info.assert_called()

    @patch("handlers.wallet.logger")
    @patch("sys.exit")
    def test_handle_wallet_sync_single(self, mock_exit, mock_logger):
        """Test wallet sync for single wallet"""
        args = Mock()
        args.wallet_name = "wallet1"
        args.wallet_name_opt = None
        args.all = False

        def first(*args):
            return args[0] if args else None

        handle_wallet_sync(args, first)

        mock_logger.info.assert_called()

    @patch("handlers.wallet.logger")
    @patch("sys.exit")
    def test_handle_wallet_sync_missing_params(self, mock_exit, mock_logger):
        """Test wallet sync with missing parameters"""
        args = Mock()
        args.wallet_name = None
        args.wallet_name_opt = None
        args.all = False

        def first(*args):
            return args[0] if args else None

        handle_wallet_sync(args, first)

        mock_exit.assert_called_with(1)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
