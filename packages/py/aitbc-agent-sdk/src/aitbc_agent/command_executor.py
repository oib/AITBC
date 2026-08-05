"""Command executor for CLI subprocess calls"""

import asyncio
import json
import shutil
import subprocess
from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class CommandExecutor:
    """Execute CLI commands via subprocess"""

    def __init__(self, cli_path: str | None = None):
        """
        Initialize command executor

        Args:
            cli_path: Path to the CLI executable. Defaults to whichever ``aitbc`` is on
                PATH, falling back to the bare name.

        The previous default was the literal path ``/opt/aitbc/aitbc-cli``, which is not
        where the CLI installs: ``cli/setup.py`` registers a console script named
        ``aitbc``. Any environment that installed the package normally via pip or poetry
        got FileNotFoundError from every call.
        """
        self.cli_path = cli_path or shutil.which("aitbc") or "aitbc"

    def execute_command(self, command: str | list[str], args: list[str]) -> dict[str, Any]:
        """Execute CLI command and return result.

        ``command`` may be a list of argv tokens, which is preferred. A plain string is
        still accepted and split on whitespace for backwards compatibility, but that
        breaks any argument containing a space -- pass a list to avoid it.
        """
        try:
            command_parts = list(command) if isinstance(command, list) else command.split()
            cmd = [self.cli_path] + command_parts + args
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
