"""Data oracle operations using CLI commands"""

import asyncio
from collections.abc import Callable

from aitbc.aitbc_logging import get_logger

from .command_executor import CommandExecutor

logger = get_logger(__name__)


class DataOracleOperations:
    """Data oracle operations via CLI"""

    def __init__(self, cli_path: str = "/opt/aitbc/aitbc-click"):
        self.executor = CommandExecutor(cli_path)

    def announce_data_availability(self, cid: str, price: float, description: str = "") -> str:
        """Announce data availability"""
        try:
            args = ["store", "--cid", cid, "--price", str(price)]
            if description:
                args.extend(["--description", description])

            result = self.executor.execute_command("oracle", args)
            if result["success"]:
                return result["data"].get("announcement_id", cid)
            else:
                logger.error("Data oracle announce failed: %s", result.get('error'))
                raise Exception(result.get("error"))
        except Exception as e:
            logger.error("announce_data_availability failed: %s", e)
            raise

    def retrieve_data(self, cid: str) -> bytes:
        """Retrieve data by CID"""
        try:
            # For now, use IPFS retrieve
            from .ipfs import IPFSOperations
            ipfs = IPFSOperations(self.executor.cli_path)
            return ipfs.retrieve_ipfs(cid)
        except Exception as e:
            logger.error("retrieve_data failed: %s", e)
            raise

    async def listen_for_requests(self, callback: Callable):
        """Listen for data retrieval requests (async)"""
        # This would need to implement a polling mechanism or webhook
        # For now, use a polling approach checking oracle listings
        try:
            while True:
                result = await self.executor.execute_command_async("oracle", ["listings"])
                if result["success"]:
                    # Process listings and call callback
                    listings = result["data"].get("listings", [])
                    for listing in listings:
                        await callback(listing)
                await asyncio.sleep(10)
        except Exception as e:
            logger.error("listen_for_requests failed: %s", e)
            raise

    async def announce_data_availability_async(self, cid: str, price: float, description: str = "") -> str:
        """Async version of announce_data_availability"""
        args = ["store", "--cid", cid, "--price", str(price)]
        if description:
            args.extend(["--description", description])

        result = await self.executor.execute_command_async("oracle", args)
        if result["success"]:
            return result["data"].get("announcement_id", cid)
        else:
            logger.error("Data oracle announce async failed: %s", result.get('error'))
            raise Exception(result.get("error"))
