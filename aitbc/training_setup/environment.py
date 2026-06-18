"""
Training Environment Setup

Provides Python-based training environment setup with proper error handling,
logging, and integration with existing AITBC patterns.
"""

import logging
import subprocess
from pathlib import Path
from typing import Any

from .blockchain import BlockchainSetup
from .exceptions import PrerequisitesError
from .messaging import MessagingSetup
from .services import ServiceDeployment
from .stage_runner import StageRunner

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
        self.blockchain_setup = BlockchainSetup(str(self.aitbc_dir), str(self.genesis_password_path))
        self.messaging_setup = MessagingSetup(str(self.aitbc_dir))
        self.service_deployment = ServiceDeployment(str(self.aitbc_dir))
        self.stage_runner = StageRunner(str(self.aitbc_dir / "aitbc-cli"))
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._setup_logging()
        log.info("TrainingEnvironment initialized")
        log.info("AITBC directory: %s", self.aitbc_dir)
        log.info("Log directory: %s", self.log_dir)
        log.info("Wallet prefix: %s", self.wallet_prefix)
        log.info("Genesis password loaded: %s", bool(self.blockchain_setup.genesis_password))

    def _setup_logging(self):
        """Setup logging configuration."""
        log_file = self.log_dir / "training_setup.log"
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
        )

    def check_prerequisites(self) -> bool:
        """
        Check if basic prerequisites are met.

        Returns:
            True if prerequisites are met, raises PrerequisitesError otherwise
        """
        log.info("Checking prerequisites...")
        aitbc_cli = self.aitbc_dir / "aitbc-cli"
        if not aitbc_cli.exists():
            raise PrerequisitesError(f"AITBC CLI not found at {aitbc_cli}")
        log.info("✓ AITBC CLI found")
        try:
            result = subprocess.run(
                [str(aitbc_cli), "blockchain", "info"], cwd=self.aitbc_dir, capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                log.info("✓ AITBC node: %s", result.stdout.split()[0] if result.stdout else "running")
            else:
                log.warning("AITBC node may not be running")
        except subprocess.TimeoutExpired:
            log.warning("AITBC node check timed out")
        except Exception as e:
            log.warning("AITBC node check failed: %s", e)
        log.info("Prerequisites check completed")
        return True

    def verify_environment(self) -> dict[str, Any]:
        """
        Verify training environment is properly configured.

        Returns:
            Dictionary with verification status
        """
        log.info("Verifying training environment...")
        results = {
            "prerequisites": self.check_prerequisites(),
            "genesis_allocation": self.blockchain_setup.create_genesis_allocation(),
            "faucet_wallet": self.blockchain_setup.setup_faucet_wallet(),
            "messaging_auth": self.messaging_setup.configure_messaging_auth(),
            "faucet_service": self.service_deployment.deploy_faucet_service(),
        }
        log.info("Environment verification completed")
        return results

    def setup_training_wallet(self, wallet_name: str, password: str = "training123") -> dict[str, Any]:
        """
        Setup a training wallet with funding.

        Args:
            wallet_name: Name of the wallet
            password: Wallet password

        Returns:
            Dictionary with setup status
        """
        log.info("Setting up training wallet: %s", wallet_name)
        funding_result = self.blockchain_setup.fund_training_wallet(wallet_name, self.faucet_amount, password)
        balance_result = self.blockchain_setup.check_wallet_balance(wallet_name)
        return {"funding": funding_result, "balance": balance_result}

    def setup_complete_environment(self) -> dict[str, Any]:
        """
        Setup complete training environment with all components.

        Returns:
            Dictionary with overall setup status
        """
        log.info("Setting up complete training environment...")
        results = {
            "prerequisites": self.check_prerequisites(),
            "genesis": self.blockchain_setup.create_genesis_allocation(),
            "faucet": self.blockchain_setup.setup_faucet_wallet(),
            "messaging": self.messaging_setup.configure_messaging_auth(),
            "service": self.service_deployment.deploy_faucet_service(),
            "service_start": self.service_deployment.start_faucet_service(),
        }
        log.info("Complete environment setup finished")
        return results

    # Backward compatibility aliases
    def setup_full_environment(self) -> dict[str, Any]:
        """Alias for setup_complete_environment (backward compatibility)."""
        return self.setup_complete_environment()

    def run_stage_from_json(self, json_path: str) -> dict[str, Any]:
        """Alias for stage_runner.run_stage_from_json (backward compatibility)."""
        return self.stage_runner.run_stage_from_json(json_path)

    def get_wallet_name(self, index: int) -> str:
        """Alias for BlockchainSetup.get_wallet_name (backward compatibility)."""
        return self.blockchain_setup.get_wallet_name(index)
