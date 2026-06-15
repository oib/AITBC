"""Command executor for CLI subprocess calls"""

import asyncio
import json
import subprocess
from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class CommandExecutor:
    """Execute CLI commands via subprocess"""

    def __init__(self, cli_path: str = "/opt/aitbc/aitbc-cli"):
        """
        Initialize command executor

        Args:
            cli_path: Path to CLI executable (default: /opt/aitbc/aitbc-cli)
        """
        self.cli_path = cli_path

    def execute_command(self, command: str, args: list[str]) -> dict[str, Any]:
        """Execute CLI command and return result"""
        try:
            cmd = [self.cli_path] + command.split() + args
            logger.debug("Executing command: %s", " ".join(cmd))

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                try:
                    data = json.loads(result.stdout) if result.stdout else {}
                except json.JSONDecodeError:
                    data = {"output": result.stdout}

                return {"success": True, "output": result.stdout, "data": data}
            else:
                logger.error("Command failed: %s", result.stderr)
                return {"success": False, "error": result.stderr}
        except subprocess.TimeoutExpired:
            logger.error("Command timeout")
            return {"success": False, "error": "Command timeout"}
        except Exception as e:
            logger.error("Command execution failed: %s", e)
            return {"success": False, "error": str(e)}

    async def execute_command_async(self, command: str, args: list[str]) -> dict[str, Any]:
        """Execute CLI command asynchronously"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.execute_command, command, args)
