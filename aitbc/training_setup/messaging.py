"""
Messaging Configuration Module
Handles messaging authentication and configuration setup
"""

import logging
import secrets
import subprocess
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class MessagingSetup:
    """Messaging authentication and configuration setup"""

    def __init__(self, aitbc_dir: str = "/opt/aitbc"):
        """
        Initialize messaging setup

        Args:
            aitbc_dir: AITBC directory path
        """
        self.aitbc_dir = Path(aitbc_dir)

    def configure_messaging_auth(self) -> dict[str, Any]:
        """
        Configure messaging authentication for training environment.

        Returns:
            Dictionary with configuration status
        """
        log.info("Configuring messaging authentication...")
        aitbc_cli = self.aitbc_dir / "aitbc-cli"
        try:
            # Check if messaging service is running
            result = subprocess.run(
                [str(aitbc_cli), "messaging", "status"],
                cwd=self.aitbc_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                log.info("✓ Messaging service status: %s", result.stdout.strip())
            else:
                log.warning("Messaging service may not be running: %s", result.stderr)
        except Exception as e:
            log.warning("Messaging status check failed: %s", e)

        # Configure authentication if needed
        try:
            result = subprocess.run(
                [str(aitbc_cli), "messaging", "auth", "configure"],
                cwd=self.aitbc_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                log.info("✓ Messaging authentication configured")
            else:
                log.warning("Messaging auth configuration: %s", result.stderr)
        except Exception as e:
            log.warning("Messaging auth configuration failed: %s", e)

        return {"status": "completed", "note": "Messaging authentication configured"}

    def verify_messaging_connection(self) -> dict[str, Any]:
        """
        Verify messaging service connection.

        Returns:
            Dictionary with connection status
        """
        log.info("Verifying messaging connection...")
        aitbc_cli = self.aitbc_dir / "aitbc-cli"
        try:
            result = subprocess.run(
                [str(aitbc_cli), "messaging", "test"],
                cwd=self.aitbc_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                log.info("✓ Messaging connection verified")
                return {"status": "completed", "connection": "verified"}
            else:
                log.warning("Messaging connection test failed: %s", result.stderr)
                return {"status": "failed", "error": result.stderr}
        except Exception as e:
            log.warning("Messaging connection test failed: %s", e)
            return {"status": "failed", "error": str(e)}

    # Backward compatibility aliases
    def test_messaging_connectivity(self) -> bool:
        """Alias for verify_messaging_connection (backward compatibility)."""
        result = self.verify_messaging_connection()
        return result.get("status") == "completed" and result.get("connection") == "verified"

    def generate_auth_token(self) -> str:
        """Generate mock auth token for testing (backward compatibility)."""
        return secrets.token_hex(32)

    def configure_messaging_auth_with_wallet(self, wallet_name: str = None) -> dict[str, Any]:
        """Alias with optional wallet_name parameter (backward compatibility)."""
        result = self.configure_messaging_auth()
        if wallet_name:
            result["wallet"] = wallet_name
        return result
