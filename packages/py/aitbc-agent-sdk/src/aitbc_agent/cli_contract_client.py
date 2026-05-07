"""
CLI-based contract client for AITBC
Provides the same interface as ContractClient but uses CLI commands
"""
import subprocess
import asyncio
import os
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

def set_logger(log):
    global logger
    logger = log

class CLIContractClient:
    """Contract client that uses AITBC CLI instead of Web3"""
    
    def __init__(self, config, private_key: Optional[str] = None):
        self.config = config
        self.private_key = private_key
        self.contracts: Dict[str, str] = {}  # Store addresses, not Web3 contracts
        self._load_contract_addresses()
        if logger:
            logger.info("CLIContractClient initialized")
    
    def _load_contract_addresses(self) -> None:
        """Load contract addresses from config"""
        # Store contract addresses by name
        if hasattr(self.config, 'cross_chain_atomic_swap') and self.config.cross_chain_atomic_swap:
            self.contracts["cross_chain_atomic_swap"] = self.config.cross_chain_atomic_swap
        if hasattr(self.config, 'payment_processor') and self.config.payment_processor:
            self.contracts["payment_processor"] = self.config.payment_processor
        if hasattr(self.config, 'agent_marketplace') and self.config.agent_marketplace:
            self.contracts["agent_marketplace"] = self.config.agent_marketplace
        if hasattr(self.config, 'staking_contract') and self.config.staking_contract:
            self.contracts["staking_contract"] = self.config.staking_contract
    
    async def send_transaction(
        self,
        contract_name: str,
        method_name: str,
        *args,
        **kwargs
    ) -> str:
        """Send transaction via CLI"""
        contract_address = self.contracts.get(contract_name)
        if not contract_address:
            raise ValueError(f"Contract {contract_name} not found")
        
        # Convert args to JSON params
        params_list = []
        for arg in args:
            if isinstance(arg, bytes):
                params_list.append(f"0x{arg.hex()}")
            elif isinstance(arg, int):
                params_list.append(str(arg))
            elif isinstance(arg, str):
                params_list.append(arg)
            else:
                params_list.append(json.dumps(arg))
        
        params_json = "[" + ", ".join(params_list) + "]"
        
        # Build CLI command
        cmd = [
            "python3", "/opt/aitbc/cli/unified_cli.py",
            "contract", "call",
            "--address", contract_address,
            "--method", method_name,
            "--params", params_json
        ]
        
        # Add password file if available
        password_file = "/var/lib/aitbc/keystore/.genesis_password"
        if os.path.exists(password_file):
            cmd.extend(["--password-file", password_file])
        
        try:
            if logger:
                logger.info(f"Calling CLI: {method_name} on {contract_name}")
            
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True, timeout=30
            )
            
            if result.returncode != 0:
                raise Exception(f"CLI call failed: {result.stderr}")
            
            if logger:
                logger.info(f"CLI call successful: {method_name}")
            
            # Return pseudo tx hash
            return f"cli-{method_name}-{int(asyncio.get_event_loop().time())}"
            
        except Exception as e:
            if logger:
                logger.error(f"CLI transaction failed: {e}")
            raise
    
    async def wait_for_transaction(self, tx_hash: str, timeout: int = 120) -> Dict:
        """Wait for transaction (CLI version - returns immediately)"""
        if logger:
            logger.info(f"Transaction {tx_hash} completed (CLI mode)")
        return {
            "status": "success",
            "block_number": 0,
            "gas_used": 0,
            "transaction_hash": tx_hash,
            "note": "CLI-based transaction"
        }
