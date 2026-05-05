"""
Training Environment Setup

Provides Python-based training environment setup with proper error handling,
logging, and integration with existing AITBC patterns.
"""

import subprocess
import json
import os
import logging
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime

from .exceptions import (
    TrainingSetupError,
    FundingError,
    MessagingError,
    FaucetError,
    PrerequisitesError,
)
from .stage_runner import StageRunner

# Configure logging
log = logging.getLogger(__name__)


class TrainingEnvironment:
    """
    Manages AITBC training environment setup including:
    - Account funding via genesis and faucet
    - Messaging authentication configuration
    - Faucet service deployment
    - Environment verification
    - Schema-driven stage execution
    """

    def __init__(
        self,
        aitbc_dir: str = "/opt/aitbc",
        log_dir: str = "/var/log/aitbc/training-setup",
        faucet_amount: int = 1000,
        genesis_allocation: int = 10000,
        wallet_prefix: str = "training-w",
        genesis_password_path: str = "/var/lib/aitbc/keystore/.genesis_password",
    ):
        self.aitbc_dir = Path(aitbc_dir)
        self.log_dir = Path(log_dir)
        self.faucet_amount = faucet_amount
        self.genesis_allocation = genesis_allocation
        self.wallet_prefix = wallet_prefix
        self.genesis_password_path = Path(genesis_password_path)
        
        # Load genesis password
        self.genesis_password = self._load_genesis_password()
        
        # Stage runner for schema-driven execution
        self.stage_runner = StageRunner(str(self.aitbc_dir / "aitbc-cli"))
        
        # Ensure directories exist
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup logging
        self._setup_logging()
        
        log.info("TrainingEnvironment initialized")
        log.info(f"AITBC directory: {self.aitbc_dir}")
        log.info(f"Log directory: {self.log_dir}")
        log.info(f"Wallet prefix: {self.wallet_prefix}")
        log.info(f"Genesis password loaded: {bool(self.genesis_password)}")

    def _setup_logging(self):
        """Setup logging configuration."""
        log_file = self.log_dir / "training_setup.log"
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler(),
            ],
        )

    def _load_genesis_password(self) -> str:
        """Load genesis wallet password from password file."""
        try:
            if self.genesis_password_path.exists():
                password = self.genesis_password_path.read_text().strip()
                log.info(f"Genesis password loaded from {self.genesis_password_path}")
                return password
            else:
                log.warning(f"Genesis password file not found at {self.genesis_password_path}")
                return ""
        except Exception as e:
            log.error(f"Failed to load genesis password: {e}")
            return ""

    def check_prerequisites(self) -> bool:
        """
        Check if basic prerequisites are met.
        
        Returns:
            True if prerequisites are met, raises PrerequisitesError otherwise
        """
        log.info("Checking prerequisites...")
        
        # Check AITBC CLI exists
        aitbc_cli = self.aitbc_dir / "aitbc-cli"
        if not aitbc_cli.exists():
            raise PrerequisitesError(f"AITBC CLI not found at {aitbc_cli}")
        
        log.info("✓ AITBC CLI found")
        
        # Check AITBC node status
        try:
            result = subprocess.run(
                [str(aitbc_cli), "blockchain", "info"],
                cwd=self.aitbc_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                log.info(f"✓ AITBC node: {result.stdout.split()[0] if result.stdout else 'running'}")
            else:
                log.warning("AITBC node may not be running")
        except subprocess.TimeoutExpired:
            log.warning("AITBC node check timed out")
        except Exception as e:
            log.warning(f"AITBC node check failed: {e}")
        
        log.info("Prerequisites check completed")
        return True

    def create_genesis_allocation(self) -> Dict[str, Any]:
        """
        Check genesis wallet and blockchain status.
        Genesis block already exists, so we skip initialization.
        
        Returns:
            Dictionary with allocation status
        """
        log.info("Checking genesis wallet and blockchain status...")
        
        aitbc_cli = self.aitbc_dir / "aitbc-cli"
        
        # Check if genesis wallet exists
        try:
            result = subprocess.run(
                [str(aitbc_cli), "wallet", "list"],
                cwd=self.aitbc_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if "genesis" in result.stdout:
                log.info("✓ Genesis wallet exists")
            else:
                log.warning("Genesis wallet not found, may need manual setup")
        except Exception as e:
            log.warning(f"Genesis wallet check failed: {e}")
        
        # Check genesis balance
        try:
            result = subprocess.run(
                [str(aitbc_cli), "wallet", "balance", "genesis"],
                cwd=self.aitbc_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                log.info(f"✓ Genesis wallet balance: {result.stdout.strip()}")
            else:
                log.warning(f"Genesis balance check: {result.stderr}")
        except Exception as e:
            log.warning(f"Genesis balance check failed: {e}")
        
        # Note: Genesis initialization skipped as block already exists
        log.info("Genesis block already exists, initialization skipped")
        
        return {"status": "completed", "note": "Genesis block already exists"}

    def setup_faucet_wallet(self) -> Dict[str, Any]:
        """
        Check genesis wallet status for funding.
        Genesis wallet is pre-funded with 999,999,890 AIT and used as funding source.
        
        Returns:
            Dictionary with funding source status
        """
        log.info("Checking genesis wallet as funding source...")
        
        aitbc_cli = self.aitbc_dir / "aitbc-cli"
        
        # Check genesis wallet balance
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
                log.info(f"✓ Genesis wallet balance: {balance}")
                log.info("Genesis wallet will be used as funding source for training wallets")
            else:
                log.warning(f"Genesis balance check: {result.stderr}")
        except Exception as e:
            log.warning(f"Genesis balance check failed: {e}")
        
        return {"status": "completed", "funding_source": "genesis", "note": "Genesis wallet used as funding source"}

    def fund_training_wallet(self, wallet_name: str, password: str = "training123") -> Dict[str, Any]:
        """
        Fund a training wallet from genesis.
        
        Args:
            wallet_name: Name of the wallet to fund
            password: Wallet password
            
        Returns:
            Dictionary with funding status
        """
        log.info(f"Funding training wallet: {wallet_name}")
        
        aitbc_cli = self.aitbc_dir / "aitbc-cli"
        
        # Create wallet if it doesn't exist
        try:
            result = subprocess.run(
                [str(aitbc_cli), "wallet", "list"],
                cwd=self.aitbc_dir,
                capture_output=True,
                text=True,
                timeout=10,
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
                    log.info(f"✓ Wallet {wallet_name} created")
                else:
                    log.warning(f"Wallet creation: {create_result.stderr}")
        except Exception as e:
            log.warning(f"Wallet creation check failed: {e}")
        
        # Fund from genesis (pre-funded wallet) - use actual genesis password (positional format)
        try:
            result = subprocess.run(
                [str(aitbc_cli), "wallet", "send", "genesis", wallet_name, str(self.faucet_amount), self.genesis_password],
                cwd=self.aitbc_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                log.info(f"✓ Wallet {wallet_name} funded with {self.faucet_amount} AIT from genesis")
            else:
                log.warning(f"Funding failed: {result.stderr}")
                raise FundingError(f"Failed to fund wallet {wallet_name}")
        except Exception as e:
            log.error(f"Funding failed: {e}")
            raise
        
        # Verify balance
        try:
            result = subprocess.run(
                [str(aitbc_cli), "wallet", "balance", wallet_name],
                cwd=self.aitbc_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                log.info(f"✓ Wallet {wallet_name} balance: {result.stdout.strip()}")
        except Exception as e:
            log.warning(f"Balance check failed: {e}")
        
        return {"status": "completed", "wallet": wallet_name, "amount": self.faucet_amount, "source": "genesis"}

    def generate_auth_token(self) -> str:
        """
        Generate authentication token for messaging.
        
        Returns:
            Generated token
        """
        import secrets
        
        token = secrets.token_hex(32)
        log.info("✓ Authentication token generated")
        return token

    def configure_messaging_auth(self, wallet_name: str, password: str = "training123") -> Dict[str, Any]:
        """
        Configure messaging authentication for a wallet.
        
        Args:
            wallet_name: Name of the wallet
            password: Wallet password
            
        Returns:
            Dictionary with configuration status
        """
        log.info(f"Configuring messaging authentication for: {wallet_name}")
        
        # Generate auth token
        token = self.generate_auth_token()
        
        # Store token
        auth_token_file = Path("/var/lib/aitbc/messaging-auth.token")
        auth_token_file.parent.mkdir(parents=True, exist_ok=True)
        auth_token_file.write_text(token)
        auth_token_file.chmod(0o600)
        log.info(f"✓ Auth token stored at {auth_token_file}")
        
        # Configure wallet for messaging
        aitbc_cli = self.aitbc_dir / "aitbc-cli"
        try:
            msg_cmd = [
                str(aitbc_cli),
                "agent",
                "message",
                "--wallet", wallet_name,
                "--password", password,
                "--auth-token", token
            ]
            result = subprocess.run(
                msg_cmd,
                cwd=self.aitbc_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                log.info(f"✓ Wallet {wallet_name} registered with messaging service")
            else:
                log.warning(f"Messaging registration: {result.stderr}")
                # Don't raise exception, messaging is optional
        except Exception as e:
            log.warning(f"Messaging configuration failed: {e}")
            # Don't raise exception, messaging is optional
        
        return {"status": "completed", "wallet": wallet_name, "token_file": str(auth_token_file)}

    def test_messaging_connectivity(self) -> bool:
        """
        Test messaging connectivity.
        
        Returns:
            True if connectivity test passes
        """
        log.info("Testing messaging connectivity...")
        
        aitbc_cli = self.aitbc_dir / "aitbc-cli"
        try:
            result = subprocess.run(
                [str(aitbc_cli), "agent", "message", "--topic", "test-topic", "--message", "test-message"],
                cwd=self.aitbc_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                log.info("✓ Messaging connectivity test passed")
                return True
            else:
                log.warning(f"Messaging connectivity test failed: {result.stderr}")
                return False
        except Exception as e:
            log.warning(f"Messaging connectivity test error: {e}")
            return False

    def verify_environment(self) -> Dict[str, Any]:
        """
        Verify training environment is properly configured.
        
        Returns:
            Dictionary with verification results
        """
        log.info("Verifying training environment...")
        
        aitbc_cli = self.aitbc_dir / "aitbc-cli"
        results = {}
        
        # Check wallet list
        try:
            result = subprocess.run(
                [str(aitbc_cli), "wallet", "list"],
                cwd=self.aitbc_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                wallet_count = result.stdout.count("ait1")
                log.info(f"✓ Wallets found: {wallet_count}")
                results["wallets"] = wallet_count
        except Exception as e:
            log.warning(f"Wallet list check failed: {e}")
            results["wallets"] = "error"
        
        # Check blockchain status
        try:
            result = subprocess.run(
                [str(aitbc_cli), "blockchain", "info"],
                cwd=self.aitbc_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                log.info(f"✓ Blockchain status: {result.stdout.split()[0] if result.stdout else 'running'}")
                results["blockchain"] = "running"
        except Exception as e:
            log.warning(f"Blockchain status check failed: {e}")
            results["blockchain"] = "error"
        
        log.info("Environment verification completed")
        return results

    def setup_full_environment(self) -> Dict[str, Any]:
        """
        Setup complete training environment.
        
        Returns:
            Dictionary with setup status
        """
        log.info("Starting full training environment setup...")
        
        results = {}
        
        # Check prerequisites
        try:
            self.check_prerequisites()
            results["prerequisites"] = "passed"
        except PrerequisitesError as e:
            log.error(f"Prerequisites check failed: {e}")
            results["prerequisites"] = "failed"
            return results
        
        # Setup genesis and faucet
        try:
            self.create_genesis_allocation()
            self.setup_faucet_wallet()
            results["funding"] = "completed"
        except Exception as e:
            log.error(f"Funding setup failed: {e}")
            results["funding"] = "failed"
        
        # Fund training wallets
        try:
            self.fund_training_wallet("training-wallet")
            self.fund_training_wallet("exam-wallet")
            results["wallets_funded"] = "completed"
        except Exception as e:
            log.error(f"Training wallet funding failed: {e}")
            results["wallets_funded"] = "failed"
        
        # Configure messaging
        try:
            self.configure_messaging_auth("training-wallet")
            self.configure_messaging_auth("exam-wallet")
            self.test_messaging_connectivity()
            results["messaging"] = "completed"
        except Exception as e:
            log.error(f"Messaging configuration failed: {e}")
            results["messaging"] = "failed"
        
        # Verify environment
        try:
            verification = self.verify_environment()
            results["verification"] = verification
        except Exception as e:
            log.error(f"Environment verification failed: {e}")
            results["verification"] = "error"
        
        log.info("Training environment setup completed")
        return results

    def get_wallet_name(self, index: int) -> str:
        """
        Generate deterministic wallet name based on index.
        
        Args:
            index: Wallet index (1-based)
            
        Returns:
            Deterministic wallet name
        """
        return f"{self.wallet_prefix}{index}"

    def run_stage_from_json(self, json_path: str) -> Dict[str, Any]:
        """
        Execute a training stage from JSON schema definition.
        
        Args:
            json_path: Path to stage JSON file
            
        Returns:
            Dictionary with stage execution results
        """
        log.info(f"Running stage from JSON: {json_path}")
        return self.stage_runner.run_stage_from_json(json_path)
