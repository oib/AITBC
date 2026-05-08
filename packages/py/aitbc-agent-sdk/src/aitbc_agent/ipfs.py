"""IPFS operations using CLI commands"""

import tempfile
import os
from typing import Optional
from .command_executor import CommandExecutor
from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class IPFSOperations:
    """IPFS operations via CLI"""
    
    def __init__(self, cli_path: str = "/opt/aitbc/aitbc-click"):
        self.executor = CommandExecutor(cli_path)
    
    def store_ipfs(self, data: bytes, pin: bool = True, name: Optional[str] = None) -> str:
        """Store data on IPFS"""
        try:
            # Write data to temp file
            with tempfile.NamedTemporaryFile(delete=False, mode='wb') as f:
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
                return result["data"].get("cid")
            else:
                logger.error(f"IPFS store failed: {result.get('error')}")
                raise Exception(result.get("error"))
        except Exception as e:
            logger.error(f"store_ipfs failed: {e}")
            raise
    
    def retrieve_ipfs(self, cid: str, output_path: Optional[str] = None) -> bytes:
        """Retrieve data from IPFS"""
        try:
            args = ["download", cid]
            if output_path:
                args.extend(["--output", output_path])
            
            result = self.executor.execute_command("ipfs", args)
            
            if result["success"]:
                # If output path specified, read from file
                if output_path:
                    with open(output_path, 'rb') as f:
                        return f.read()
                # Otherwise, return the file path from result
                return result["data"].get("file_path", "")
            else:
                logger.error(f"IPFS retrieve failed: {result.get('error')}")
                raise Exception(result.get("error"))
        except Exception as e:
            logger.error(f"retrieve_ipfs failed: {e}")
            raise
    
    def pin_ipfs(self, cid: str) -> bool:
        """Pin content on IPFS"""
        try:
            result = self.executor.execute_command("ipfs", ["pin", cid])
            if result["success"]:
                return result["data"].get("pinned", False)
            else:
                logger.error(f"IPFS pin failed: {result.get('error')}")
                raise Exception(result.get("error"))
        except Exception as e:
            logger.error(f"pin_ipfs failed: {e}")
            raise
    
    def list_ipfs(self) -> list:
        """List all stored IPFS content"""
        try:
            result = self.executor.execute_command("ipfs", ["list"])
            if result["success"]:
                return result["data"].get("items", [])
            else:
                logger.error(f"IPFS list failed: {result.get('error')}")
                raise Exception(result.get("error"))
        except Exception as e:
            logger.error(f"list_ipfs failed: {e}")
            raise
    
    async def store_ipfs_async(self, data: bytes, pin: bool = True, name: Optional[str] = None) -> str:
        """Async version of store_ipfs"""
        # Write data to temp file
        with tempfile.NamedTemporaryFile(delete=False, mode='wb') as f:
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
                return result["data"].get("cid")
            else:
                logger.error(f"IPFS store async failed: {result.get('error')}")
                raise Exception(result.get("error"))
        except Exception as e:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            logger.error(f"store_ipfs_async failed: {e}")
            raise
    
    async def retrieve_ipfs_async(self, cid: str, output_path: Optional[str] = None) -> bytes:
        """Async version of retrieve_ipfs"""
        args = ["download", cid]
        if output_path:
            args.extend(["--output", output_path])
        
        result = await self.executor.execute_command_async("ipfs", args)
        if result["success"]:
            if output_path:
                with open(output_path, 'rb') as f:
                    return f.read()
            return result["data"].get("file_path", "")
        else:
            logger.error(f"IPFS retrieve async failed: {result.get('error')}")
            raise Exception(result.get("error"))
