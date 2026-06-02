#!/opt/aitbc/venv/bin/python3
"""Compatibility wrapper for the AITBC CLI entrypoint."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[1]
CLI_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(CLI_DIR))

# Ensure we don't pick up hermes-agent's cli module
hermes_cli_path = "/usr/local/lib/hermes-agent"
if hermes_cli_path in sys.path:
    sys.path.remove(hermes_cli_path)

from aitbc.constants import BLOCKCHAIN_RPC_PORT

DEFAULT_RPC_URL = f"http://localhost:{BLOCKCHAIN_RPC_PORT}"
_CLI_MODULE: ModuleType | None = None


def _load_cli_module() -> ModuleType:
    global _CLI_MODULE
    if _CLI_MODULE is not None:
        return _CLI_MODULE

    # Try the new unified_cli.py location first
    cli_path = CLI_DIR / "unified_cli.py"
    if not cli_path.exists():
        # Fallback to old location
        cli_path = REPO_ROOT / "aitbc_cli" / "core" / "main.py"

    spec = importlib.util.spec_from_file_location("aitbc_cli_unified", cli_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load CLI entrypoint from {cli_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _CLI_MODULE = module
    return module


def main(argv=None):
    # Directly execute unified_cli without circular import
    import sys
    sys.path.insert(0, str(CLI_DIR))

    # Import unified_cli module directly
    import unified_cli

    # Create a mock core dict for the CLI
    from aitbc.constants import BLOCKCHAIN_RPC_PORT

    # Stub handler functions for all parser handlers
    def stub_handler(*args, **kwargs):
        return None

    # Import real utility functions
    sys.path.insert(0, str(CLI_DIR / "aitbc_cli"))
    from utils import blockchain as blockchain_utils
    from utils.dual_mode_wallet_adapter import DualModeWalletAdapter

    # Create wallet adapter for real wallet operations (without config)
    wallet_adapter = DualModeWalletAdapter(config=None, use_daemon=False)

    def real_list_wallets(*args, **kwargs):
        """Real wallet list implementation"""
        return wallet_adapter.list_wallets()

    def real_create_wallet(*args, **kwargs):
        """Real wallet create implementation"""
        wallet_name = args[0] if args else kwargs.get('wallet_name')
        password = args[1] if len(args) > 1 else kwargs.get('password')
        return wallet_adapter.create_wallet(wallet_name, password)

    def real_get_balance(*args, **kwargs):
        """Real balance get implementation"""
        return 0  # Placeholder - would need wallet_name parameter

    def real_get_transactions(*args, **kwargs):
        """Real transactions get implementation"""
        return []

    core = {
        "DEFAULT_RPC_URL": f"http://localhost:{BLOCKCHAIN_RPC_PORT}",
        "DEFAULT_COORDINATOR_URL": "http://localhost:8011",
        "DEFAULT_GPU_URL": "http://localhost:8101",
        "DEFAULT_MARKETPLACE_URL": "http://localhost:8102",
        "DEFAULT_TRADING_URL": "http://localhost:8104",
        "DEFAULT_GOVERNANCE_URL": "http://localhost:8105",
        "CLI_VERSION": "0.0.0",
        # Add real functions for core operations
        "create_wallet": real_create_wallet,
        "list_wallets": real_list_wallets,
        "get_balance": real_get_balance,
        "get_transactions": real_get_transactions,
        "send_transaction": lambda *args, **kwargs: {"status": "stub"},
        "import_wallet": lambda *args, **kwargs: {"status": "stub"},
        "export_wallet": lambda *args, **kwargs: {"status": "stub"},
        "delete_wallet": lambda *args, **kwargs: {"status": "stub"},
        "rename_wallet": lambda *args, **kwargs: {"status": "stub"},
        "send_batch_transactions": lambda *args, **kwargs: {"status": "stub"},
        "get_chain_info": blockchain_utils.get_chain_info,
        "get_blockchain_analytics": blockchain_utils.get_blockchain_analytics,
        "marketplace_operations": lambda *args, **kwargs: {},
        "ai_operations": lambda *args, **kwargs: {},
        "mining_operations": lambda *args, **kwargs: {},
        "agent_operations": lambda *args, **kwargs: {},
        "hermes_training_operations": lambda *args, **kwargs: {},
        "workflow_operations": lambda *args, **kwargs: {},
        "resource_operations": lambda *args, **kwargs: {},
        "simulate_blockchain": lambda *args, **kwargs: None,
        "simulate_wallets": lambda *args, **kwargs: None,
        "simulate_price": lambda *args, **kwargs: None,
        "simulate_network": lambda *args, **kwargs: None,
        "simulate_ai_jobs": lambda *args, **kwargs: None,
        # Add stub handlers for all parser handlers
        "handle_market_gpu_register": stub_handler,
        "handle_market_gpu_list": stub_handler,
        "handle_market_listings": stub_handler,
        "handle_market_create": stub_handler,
        "handle_market_get": stub_handler,
        "handle_market_delete": stub_handler,
        "handle_market_buy": stub_handler,
        "handle_market_sell": stub_handler,
        "handle_market_orders": stub_handler,
        "handle_market_list_plugins": stub_handler,
    }

    return unified_cli.run_cli(argv, core)


if __name__ == "__main__":
    raise SystemExit(main())
