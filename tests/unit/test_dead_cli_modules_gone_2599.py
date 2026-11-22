"""The fourteen unreferenced CLI modules deleted for AUDIT-DEAD-CLI-MODULES-1
(#2599) must stay gone.

They carried real defects (a path traversal in the dead ``core/plugins.py``
copy, invented analytics constants in ``utils/blockchain.py``, a broken
multisig sign/verify pair in ``utils/crypto_utils.py``) while their own tests
kept the suite green. Deleting the files alone does not stop a copy-paste
resurrection — this pins the paths.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_ROOT = REPO_ROOT / "cli"

DELETED_MODULE_FILES = [
    "aitbc_cli/core/plugins.py",
    "aitbc_cli/core/market.py",
    "aitbc_cli/core/agent_communication.py",
    "aitbc_cli/core/genesis_generator.py",
    "aitbc_cli/core/imports.py",
    "aitbc_cli/utils/blockchain.py",
    "aitbc_cli/utils/crypto_utils.py",
    "aitbc_cli/commands/exchange/payments.py",
    "aitbc_cli/commands/exchange/trading.py",
    "aitbc_cli/commands/exchange/bridge.py",
    "aitbc_cli/commands/exchange/wallet.py",
    "extended_features.py",
    "keystore_auth.py",
    "security/__init__.py",
    "security/translation_policy.py",
]


def test_deleted_modules_stay_deleted():
    present = [rel for rel in DELETED_MODULE_FILES if (CLI_ROOT / rel).exists()]
    assert not present, f"dead CLI modules are back: {present}"


def test_deleted_modules_not_importable():
    for name in (
        "aitbc_cli.core.plugins",
        "aitbc_cli.core.market",
        "aitbc_cli.core.agent_communication",
        "aitbc_cli.core.genesis_generator",
        "aitbc_cli.core.imports",
        "aitbc_cli.utils.blockchain",
        "aitbc_cli.utils.crypto_utils",
        "aitbc_cli.commands.exchange.payments",
        "aitbc_cli.commands.exchange.trading",
        "aitbc_cli.commands.exchange.bridge",
        "aitbc_cli.commands.exchange.wallet",
        "extended_features",
        "keystore_auth",
        "security",
        "security.translation_policy",
    ):
        try:
            spec = importlib.util.find_spec(name)
        except ModuleNotFoundError:
            spec = None
        assert spec is None, f"{name} is importable again"


def test_utils_init_no_longer_reexports_blockchain_helpers():
    from aitbc_cli import utils

    for name in ("get_chain_info", "get_network_status", "get_blockchain_analytics", "blockchain"):
        assert name not in utils.__all__, f"utils.__all__ still exports {name}"
