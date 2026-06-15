"""
Training Environment Setup

Provides Python-based training environment setup with proper error handling,
logging, and integration with existing AITBC patterns.
"""

import logging
import subprocess
from pathlib import Path
from typing import Any
from .exceptions import FundingError, PrerequisitesError
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
        self.genesis_password = self._load_genesis_password()
        self.stage_runner = StageRunner(str(self.aitbc_dir / "aitbc-cli"))
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._setup_logging()
        log.info("TrainingEnvironment initialized")
        log.info("AITBC directory: %s", self.aitbc_dir)
        log.info("Log directory: %s", self.log_dir)
        log.info("Wallet prefix: %s", self.wallet_prefix)
        log.info("Genesis password loaded: %s", bool(self.genesis_password))

    def _setup_logging(self):
        """Setup logging configuration."""
        log_file = self.log_dir / "training_setup.log"
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
        )

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

    def fund_training_wallet(self, wallet_name: str, password: str = "training123") -> dict[str, Any]:
        """
        Fund a training wallet from genesis.

        Args:
            wallet_name: Name of the wallet to fund
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
                [str(aitbc_cli), "wallet", "send", "genesis", wallet_name, str(self.faucet_amount), self.genesis_password],
                cwd=self.aitbc_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                log.info("✓ Wallet %s funded with %s AIT from genesis", wallet_name, self.faucet_amount)
            else:
                log.warning("Funding failed: %s", result.stderr)
                raise FundingError(f"Failed to fund wallet {wallet_name}")
        except Exception as e:
            log.error("Funding failed: %s", e)
            raise
        try:
            result = subprocess.run(
                [str(aitbc_cli), "wallet", "balance", wallet_name],
                cwd=self.aitbc_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                log.info("✓ Wallet %s balance: %s", wallet_name, result.stdout.strip())
        except Exception as e:
            log.warning("Balance check failed: %s", e)
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

    def configure_messaging_auth(self, wallet_name: str, password: str = "training123") -> dict[str, Any]:
        """
        Configure messaging authentication for a wallet.

        Args:
            wallet_name: Name of the wallet
            password: Wallet password

        Returns:
            Dictionary with configuration status
        """
        log.info("Configuring messaging authentication for: %s", wallet_name)
        token = self.generate_auth_token()
        auth_token_file = Path("/var/lib/aitbc/messaging-auth.token")
        auth_token_file.parent.mkdir(parents=True, exist_ok=True)
        auth_token_file.write_text(token)
        auth_token_file.chmod(384)
        log.info("✓ Auth token stored at %s", auth_token_file)
        aitbc_cli = self.aitbc_dir / "aitbc-cli"
        try:
            msg_cmd = [
                str(aitbc_cli),
                "agent",
                "message",
                "--wallet",
                wallet_name,
                "--password",
                password,
                "--auth-token",
                token,
            ]
            result = subprocess.run(msg_cmd, cwd=self.aitbc_dir, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                log.info("✓ Wallet %s registered with messaging service", wallet_name)
            else:
                log.warning("Messaging registration: %s", result.stderr)
        except Exception as e:
            log.warning("Messaging configuration failed: %s", e)
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
                log.warning("Messaging connectivity test failed: %s", result.stderr)
                return False
        except Exception as e:
            log.warning("Messaging connectivity test error: %s", e)
            return False

    def verify_environment(self) -> dict[str, Any]:
        """
        Verify training environment is properly configured.

        Returns:
            Dictionary with verification results
        """
        log.info("Verifying training environment...")
        aitbc_cli = self.aitbc_dir / "aitbc-cli"
        results = {}
        try:
            result = subprocess.run(
                [str(aitbc_cli), "wallet", "list"], cwd=self.aitbc_dir, capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                wallet_count = result.stdout.count("ait1")
                log.info("✓ Wallets found: %s", wallet_count)
                results["wallets"] = wallet_count
        except Exception as e:
            log.warning("Wallet list check failed: %s", e)
            results["wallets"] = "error"
        try:
            result = subprocess.run(
                [str(aitbc_cli), "blockchain", "info"], cwd=self.aitbc_dir, capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                log.info("✓ Blockchain status: %s", result.stdout.split()[0] if result.stdout else "running")
                results["blockchain"] = "running"
        except Exception as e:
            log.warning("Blockchain status check failed: %s", e)
            results["blockchain"] = "error"
        log.info("Environment verification completed")
        return results

    def setup_full_environment(self) -> dict[str, Any]:
        """
        Setup complete training environment.

        Returns:
            Dictionary with setup status
        """
        log.info("Starting full training environment setup...")
        results = {}
        try:
            self.check_prerequisites()
            results["prerequisites"] = "passed"
        except PrerequisitesError as e:
            log.error("Prerequisites check failed: %s", e)
            results["prerequisites"] = "failed"
            return results
        try:
            self.create_genesis_allocation()
            self.setup_faucet_wallet()
            results["funding"] = "completed"
        except Exception as e:
            log.error("Funding setup failed: %s", e)
            results["funding"] = "failed"
        try:
            self.fund_training_wallet("training-wallet")
            self.fund_training_wallet("exam-wallet")
            results["wallets_funded"] = "completed"
        except Exception as e:
            log.error("Training wallet funding failed: %s", e)
            results["wallets_funded"] = "failed"
        try:
            self.configure_messaging_auth("training-wallet")
            self.configure_messaging_auth("exam-wallet")
            self.test_messaging_connectivity()
            results["messaging"] = "completed"
        except Exception as e:
            log.error("Messaging configuration failed: %s", e)
            results["messaging"] = "failed"
        try:
            verification = self.verify_environment()
            results["verification"] = verification
        except Exception as e:
            log.error("Environment verification failed: %s", e)
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

    def run_stage_from_json(self, json_path: str) -> dict[str, Any]:
        """
        Execute a training stage from JSON schema definition.

        Args:
            json_path: Path to stage JSON file

        Returns:
            Dictionary with stage execution results
        """
        log.info("Running stage from JSON: %s", json_path)
        return self.stage_runner.run_stage_from_json(json_path)
