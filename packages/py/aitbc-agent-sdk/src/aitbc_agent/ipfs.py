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

    def host_market_ipfs(
        self,
        offer_id_or_plugin_id: str,
        cid_or_file: str,
        days: int = 1,
        wallet: str = "genesis",
        pin: bool = True,
    ) -> dict:
        """Host IPFS content through a marketplace offer."""
        args = [
            "--offer-id-or-plugin-id",
            offer_id_or_plugin_id,
            "--cid-or-file",
            cid_or_file,
            "--days",
            str(days),
        ]
        if not pin:
            args.append("--no-pin")
        result = self.executor.execute_command(["market", "--wallet", wallet, "host"], args)
        if result["success"]:
            return result["data"]
        logger.error("Market IPFS host failed: %s", result.get("error"))
        raise Exception(result.get("error"))

    def download_market_ipfs(
        self,
        cid: str | None = None,
        rental_id: str | None = None,
        access_key: str | None = None,
        access_secret: str | None = None,
        output_path: str | None = None,
    ) -> bytes:
        """Download IPFS content by marketplace job, access token, or free CID."""
        args: list[str] = ["download"]
        if cid:
            args.extend(["--cid", cid])
        if rental_id:
            args.extend(["--rental-id", rental_id])
        if access_key:
            args.extend(["--access-key", access_key])
        if access_secret:
            args.extend(["--access-secret", access_secret])
        if output_path:
            args.extend(["--output", output_path])

        result = self.executor.execute_command("market", args)
        if not result["success"]:
            logger.error("Market IPFS download failed: %s", result.get("error"))
            raise Exception(result.get("error"))

        file_path = result["data"].get("file_path")
        target = Path(output_path) if output_path else Path(file_path) if file_path else None
        if target is None:
            raise Exception("No file path in market IPFS download response")
        with target.open("rb") as f:
            return f.read()

    def list_market_ipfs_jobs(self, service_type: str = "ipfs", state: str | None = None) -> list:
        """List marketplace jobs for IPFS (or other service types)."""
        args = ["jobs"]
        if service_type:
            args.extend(["--service-type", service_type])
        if state:
            args.extend(["--state", state])

        result = self.executor.execute_command("market", args)
        if result["success"]:
            return cast(list, result["data"])
        logger.error("Market IPFS job list failed: %s", result.get("error"))
        raise Exception(result.get("error"))

    def cancel_market_ipfs_job(self, job_id: str, reason: str = "buyer_requested") -> dict:
        """Cancel a marketplace IPFS job and request a refund."""
        result = self.executor.execute_command(
            "market",
            ["cancel", "--job-id", job_id, "--reason", reason],
        )
        if result["success"]:
            return result["data"]
        logger.error("Market IPFS cancel failed: %s", result.get("error"))
        raise Exception(result.get("error"))

    async def host_market_ipfs_async(
        self,
        offer_id_or_plugin_id: str,
        cid_or_file: str,
        days: int = 1,
        wallet: str = "genesis",
        pin: bool = True,
    ) -> dict:
        """Async version of host_market_ipfs."""
        args = [
            "--offer-id-or-plugin-id",
            offer_id_or_plugin_id,
            "--cid-or-file",
            cid_or_file,
            "--days",
            str(days),
        ]
        if not pin:
            args.append("--no-pin")
        result = await self.executor.execute_command_async(["market", "--wallet", wallet, "host"], args)
        if result["success"]:
            return result["data"]
        logger.error("Market IPFS host async failed: %s", result.get("error"))
        raise Exception(result.get("error"))

    async def download_market_ipfs_async(
        self,
        cid: str | None = None,
        rental_id: str | None = None,
        access_key: str | None = None,
        access_secret: str | None = None,
        output_path: str | None = None,
    ) -> bytes:
        """Async version of download_market_ipfs."""
        args: list[str] = ["download"]
        if cid:
            args.extend(["--cid", cid])
        if rental_id:
            args.extend(["--rental-id", rental_id])
        if access_key:
            args.extend(["--access-key", access_key])
        if access_secret:
            args.extend(["--access-secret", access_secret])
        if output_path:
            args.extend(["--output", output_path])

        result = await self.executor.execute_command_async("market", args)
        if not result["success"]:
            logger.error("Market IPFS download async failed: %s", result.get("error"))
            raise Exception(result.get("error"))

        file_path = result["data"].get("file_path")
        target = Path(output_path) if output_path else Path(file_path) if file_path else None
        if target is None:
            raise Exception("No file path in market IPFS download response")
        with target.open("rb") as f:
            return f.read()

    async def list_market_ipfs_jobs_async(self, service_type: str = "ipfs", state: str | None = None) -> list:
        """Async version of list_market_ipfs_jobs."""
        args = ["jobs"]
        if service_type:
            args.extend(["--service-type", service_type])
        if state:
            args.extend(["--state", state])

        result = await self.executor.execute_command_async("market", args)
        if result["success"]:
            return cast(list, result["data"])
        logger.error("Market IPFS job list async failed: %s", result.get("error"))
        raise Exception(result.get("error"))

    async def cancel_market_ipfs_job_async(self, job_id: str, reason: str = "buyer_requested") -> dict:
        """Async version of cancel_market_ipfs_job."""
        result = await self.executor.execute_command_async(
            "market",
            ["cancel", "--job-id", job_id, "--reason", reason],
        )
        if result["success"]:
            return result["data"]
        logger.error("Market IPFS cancel async failed: %s", result.get("error"))
        raise Exception(result.get("error"))
