"""
Blockchain and Wallet Setup Module
Handles genesis allocation, faucet wallet setup, and training wallet funding
"""

import logging
import subprocess
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class BlockchainSetup:
    """Blockchain and wallet setup for training environment"""

    def __init__(
        self, aitbc_dir: str = "/opt/aitbc", genesis_password_path: str = "/var/lib/aitbc/keystore/.genesis_password"
    ):
        """
        Initialize blockchain setup

        Args:
            aitbc_dir: AITBC directory path
            genesis_password_path: Path to genesis wallet password file
        """
        self.aitbc_dir = Path(aitbc_dir)
        self.genesis_password_path = Path(genesis_password_path)
        self.genesis_password = self._load_genesis_password()

    def _load_genesis_password(self) -> str:
        """Load genesis wallet password from password file."""
        try:
            if self.genesis_password_path.exists():
                password = self.genesis_password_path.read_text().strip()
                log.info("Genesis password loaded from %s", self.genesis_password_path)
                return password
            else:
                log.warning("Genesis password file not found at %s", self.genesis_password_path)
                return ""
        except Exception as e:
            log.error("Failed to load genesis password: %s", e)
            return ""

    def create_genesis_allocation(self) -> dict[str, Any]:
        """
        Check genesis wallet and blockchain status.
        Genesis block already exists, so we skip initialization.

        Returns:
            Dictionary with allocation status
        """
        log.info("Checking genesis wallet and blockchain status...")
        aitbc_cli = self.aitbc_dir / "aitbc-cli"
        try:
            result = subprocess.run(
                [str(aitbc_cli), "wallet", "list"], cwd=self.aitbc_dir, capture_output=True, text=True, timeout=10
            )
            if "genesis" in result.stdout:
                log.info("✓ Genesis wallet exists")
            else:
                log.warning("Genesis wallet not found, may need manual setup")
        except Exception as e:
            log.warning("Genesis wallet check failed: %s", e)
        try:
            result = subprocess.run(
                [str(aitbc_cli), "wallet", "balance", "genesis"],
                cwd=self.aitbc_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                log.info("✓ Genesis wallet balance: %s", result.stdout.strip())
            else:
                log.warning("Genesis balance check: %s", result.stderr)
        except Exception as e:
            log.warning("Genesis balance check failed: %s", e)
        log.info("Genesis block already exists, initialization skipped")
        return {"status": "completed", "note": "Genesis block already exists"}

    def setup_faucet_wallet(self) -> dict[str, Any]:
        """
        Check genesis wallet status for funding.
        Genesis wallet is pre-funded with 999,999,890 AIT and used as funding source.

        Returns:
            Dictionary with funding source status
        """
        log.info("Checking genesis wallet as funding source...")
        aitbc_cli = self.aitbc_dir / "aitbc-cli"
        try:
            result = subprocess.run(
                [str(aitbc_cli), "wallet", "balance", "genesis"],
                cwd=self.aitbc_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                balance = result.stdout.strip()
                log.info("✓ Genesis wallet balance: %s", balance)
                log.info("Genesis wallet will be used as funding source for training wallets")
            else:
                log.warning("Genesis balance check: %s", result.stderr)
        except Exception as e:
            log.warning("Genesis balance check failed: %s", e)
        return {"status": "completed", "funding_source": "genesis", "note": "Genesis wallet used as funding source"}

    def fund_training_wallet(self, wallet_name: str, faucet_amount: int = 1000, password: str | None = None) -> dict[str, Any]:
        if password is None:
            raise ValueError("password is required and must not be empty")
        """
        Fund a training wallet from genesis.

        Args:
            wallet_name: Name of the wallet to fund
            faucet_amount: Amount to fund
            password: Wallet password

        Returns:
            Dictionary with funding status
        """
        log.info("Funding training wallet: %s", wallet_name)
        aitbc_cli = self.aitbc_dir / "aitbc-cli"
        try:
            result = subprocess.run(
                [str(aitbc_cli), "wallet", "list"], cwd=self.aitbc_dir, capture_output=True, text=True, timeout=10
            )
            if wallet_name not in result.stdout:
                create_result = subprocess.run(
                    [str(aitbc_cli), "wallet", "create", wallet_name, password],
                    cwd=self.aitbc_dir,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if create_result.returncode == 0:
                    log.info("✓ Wallet %s created", wallet_name)
                else:
                    log.warning("Wallet creation: %s", create_result.stderr)
        except Exception as e:
            log.warning("Wallet creation check failed: %s", e)
        try:
            result = subprocess.run(
                [str(aitbc_cli), "wallet", "send", "genesis", wallet_name, str(faucet_amount), self.genesis_password],
                cwd=self.aitbc_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                log.info("✓ Wallet %s funded with %s AIT from genesis", wallet_name, faucet_amount)
            else:
                log.warning("Funding failed: %s", result.stderr)
                return {"status": "failed", "error": result.stderr}
        except Exception as e:
            log.warning("Funding failed: %s", e)
            return {"status": "failed", "error": str(e)}
        return {"status": "completed", "wallet": wallet_name, "amount": faucet_amount}

    def check_wallet_balance(self, wallet_name: str) -> dict[str, Any]:
        """
        Check wallet balance.

        Args:
            wallet_name: Name of the wallet

        Returns:
            Dictionary with balance status
        """
        log.info("Checking wallet balance: %s", wallet_name)
        aitbc_cli = self.aitbc_dir / "aitbc-cli"
        try:
            result = subprocess.run(
                [str(aitbc_cli), "wallet", "balance", wallet_name],
                cwd=self.aitbc_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                balance = result.stdout.strip()
                log.info("✓ Wallet %s balance: %s", wallet_name, balance)
                return {"status": "completed", "wallet": wallet_name, "balance": balance}
            else:
                log.warning("Balance check failed: %s", result.stderr)
                return {"status": "failed", "error": result.stderr}
        except Exception as e:
            log.warning("Balance check failed: %s", e)
            return {"status": "failed", "error": str(e)}

    def get_wallet_name(self, index: int) -> str:
        """
        Get training wallet name by index.

        Args:
            index: Wallet index

        Returns:
            Wallet name (e.g., "training-w1", "training-w10")
        """
        return f"training-w{index}"
