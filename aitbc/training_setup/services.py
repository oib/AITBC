"""
Service Deployment Module
Handles faucet service deployment and management
"""

import logging
import subprocess
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class ServiceDeployment:
    """Service deployment for training environment"""

    def __init__(self, aitbc_dir: str = "/opt/aitbc"):
        """
        Initialize service deployment

        Args:
            aitbc_dir: AITBC directory path
        """
        self.aitbc_dir = Path(aitbc_dir)

    def deploy_faucet_service(self) -> dict[str, Any]:
        """
        Deploy faucet service for training environment.

        Returns:
            Dictionary with deployment status
        """
        log.info("Deploying faucet service...")
        aitbc_cli = self.aitbc_dir / "aitbc-cli"
        try:
            # Check if faucet service already exists
            result = subprocess.run(
                [str(aitbc_cli), "service", "list"],
                cwd=self.aitbc_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if "faucet" in result.stdout:
                log.info("✓ Faucet service already deployed")
                return {"status": "completed", "note": "Faucet service already deployed"}

            # Deploy faucet service
            result = subprocess.run(
                [str(aitbc_cli), "service", "deploy", "faucet"],
                cwd=self.aitbc_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                log.info("✓ Faucet service deployed successfully")
                return {"status": "completed", "service": "faucet"}
            else:
                log.warning("Faucet service deployment failed: %s", result.stderr)
                return {"status": "failed", "error": result.stderr}
        except Exception as e:
            log.warning("Faucet service deployment failed: %s", e)
            return {"status": "failed", "error": str(e)}

    def start_faucet_service(self) -> dict[str, Any]:
        """
        Start faucet service.

        Returns:
            Dictionary with start status
        """
        log.info("Starting faucet service...")
        aitbc_cli = self.aitbc_dir / "aitbc-cli"
        try:
            result = subprocess.run(
                [str(aitbc_cli), "service", "start", "faucet"],
                cwd=self.aitbc_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                log.info("✓ Faucet service started")
                return {"status": "completed", "service": "faucet"}
            else:
                log.warning("Faucet service start failed: %s", result.stderr)
                return {"status": "failed", "error": result.stderr}
        except Exception as e:
            log.warning("Faucet service start failed: %s", e)
            return {"status": "failed", "error": str(e)}

    def verify_faucet_service(self) -> dict[str, Any]:
        """
        Verify faucet service status.

        Returns:
            Dictionary with service status
        """
        log.info("Verifying faucet service status...")
        aitbc_cli = self.aitbc_dir / "aitbc-cli"
        try:
            result = subprocess.run(
                [str(aitbc_cli), "service", "status", "faucet"],
                cwd=self.aitbc_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                log.info("✓ Faucet service status: %s", result.stdout.strip())
                return {"status": "completed", "service": "faucet", "status_output": result.stdout.strip()}
            else:
                log.warning("Faucet service status check failed: %s", result.stderr)
                return {"status": "failed", "error": result.stderr}
        except Exception as e:
            log.warning("Faucet service status check failed: %s", e)
            return {"status": "failed", "error": str(e)}
