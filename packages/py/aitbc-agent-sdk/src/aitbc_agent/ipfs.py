"""IPFS operations using CLI commands"""

from typing import cast

import os
import tempfile
from pathlib import Path

from aitbc.aitbc_logging import get_logger

from .command_executor import CommandExecutor

logger = get_logger(__name__)


class IPFSOperations:
    """IPFS operations via CLI"""

    def __init__(self, cli_path: str | None = None):
        self.executor = CommandExecutor(cli_path)

    def store_ipfs(self, data: bytes, pin: bool = True, name: str | None = None) -> str:
        """Store data on IPFS"""
        try:
            # Write data to temp file
            with tempfile.NamedTemporaryFile(delete=False, mode="wb") as f:
                f.write(data)
                temp_path = f.name

            # Build command args
            args = ["upload", "--file", temp_path]
            if pin:
                args.append("--pin")
            if name:
                args.extend(["--name", name])

            # Execute command
            result = self.executor.execute_command("ipfs", args)

            # Clean up temp file
            os.unlink(temp_path)

            if result["success"]:
                return cast(str, result["data"].get("cid"))
            else:
                logger.error("IPFS store failed: %s", result.get("error"))
                raise Exception(result.get("error"))
        except Exception as e:
            logger.error("store_ipfs failed: %s", e)
            raise

    def retrieve_ipfs(self, cid: str, output_path: str | None = None) -> bytes:
        """Retrieve data from IPFS"""
        try:
            args = ["download", cid]
            if output_path:
                args.extend(["--output", output_path])

            result = self.executor.execute_command("ipfs", args)

            if result["success"]:
                file_path = result["data"].get("file_path")
                if output_path:
                    target = Path(output_path)
                elif file_path:
                    target = Path(file_path)
                else:
                    raise Exception("No file path in IPFS download response")
                with target.open("rb") as f:
                    return f.read()
            else:
                logger.error("IPFS retrieve failed: %s", result.get("error"))
                raise Exception(result.get("error"))
        except Exception as e:
            logger.error("retrieve_ipfs failed: %s", e)
            raise

    def pin_ipfs(self, cid: str) -> bool:
        """Pin content on IPFS"""
        try:
            result = self.executor.execute_command("ipfs", ["pin", cid])
            if result["success"]:
                return cast(bool, result["data"].get("pinned", False))
            else:
                logger.error("IPFS pin failed: %s", result.get("error"))
                raise Exception(result.get("error"))
        except Exception as e:
            logger.error("pin_ipfs failed: %s", e)
            raise

    def list_ipfs(self) -> list:
        """List all stored IPFS content"""
        try:
            result = self.executor.execute_command("ipfs", ["list"])
            if result["success"]:
                return cast(list, result["data"].get("items", []))
            else:
                logger.error("IPFS list failed: %s", result.get("error"))
                raise Exception(result.get("error"))
        except Exception as e:
            logger.error("list_ipfs failed: %s", e)
            raise

    async def store_ipfs_async(self, data: bytes, pin: bool = True, name: str | None = None) -> str:
        """Async version of store_ipfs"""
        # Write data to temp file
        with tempfile.NamedTemporaryFile(delete=False, mode="wb") as f:
            f.write(data)
            temp_path = f.name

        # Build command args
        args = ["upload", "--file", temp_path]
        if pin:
            args.append("--pin")
        if name:
            args.extend(["--name", name])

        try:
            result = await self.executor.execute_command_async("ipfs", args)
            os.unlink(temp_path)

            if result["success"]:
                return cast(str, result["data"].get("cid"))
            else:
                logger.error("IPFS store async failed: %s", result.get("error"))
                raise Exception(result.get("error"))
        except Exception as e:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            logger.error("store_ipfs_async failed: %s", e)
            raise

    async def retrieve_ipfs_async(self, cid: str, output_path: str | None = None) -> bytes:
        """Async version of retrieve_ipfs"""
        args = ["download", cid]
        if output_path:
            args.extend(["--output", output_path])

        result = await self.executor.execute_command_async("ipfs", args)
        if result["success"]:
            file_path = result["data"].get("file_path")
            if output_path:
                target = Path(output_path)
            elif file_path:
                target = Path(file_path)
            else:
                raise Exception("No file path in IPFS download response")
            with target.open("rb") as f:
                return f.read()
        else:
            logger.error("IPFS retrieve async failed: %s", result.get("error"))
            raise Exception(result.get("error"))
