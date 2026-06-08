"""Bridge monitor service - polls Ethereum for ETH deposits and sends AIT."""

import os
import sys
import time
import json
from decimal import Decimal
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../.."))

from aitbc.ethereum_rpc import EthereumRPCClient
from aitbc.oracles.price_oracle import get_price_oracle
from aitbc.aitbc_logging import get_logger
from .storage import init_db, create_deposit, update_deposit, get_deposit, BridgeDepositStatus

logger = get_logger(__name__)


class BridgeMonitor:
    """Monitor Ethereum wallet for deposits and bridge to AIT."""
    
    def __init__(self):
        self.eth_rpc = EthereumRPCClient()
        self.price_oracle = get_price_oracle()
        
        bridge_eth = os.getenv("BRIDGE_ETH_ADDRESS")
        if not bridge_eth:
            raise RuntimeError("BRIDGE_ETH_ADDRESS environment variable is required")
        self.bridge_eth_address = bridge_eth.lower()
        
        self.genesis_wallet_address = os.getenv("GENESIS_WALLET_ADDRESS")
        if not self.genesis_wallet_address:
            raise RuntimeError("GENESIS_WALLET_ADDRESS environment variable is required")
        
        self.genesis_private_key = os.getenv("GENESIS_WALLET_PRIVATE_KEY")
        if not self.genesis_private_key:
            logger.warning("GENESIS_WALLET_PRIVATE_KEY not set - cannot sign AIT transfers")
        
        self.poll_interval = int(os.getenv("BRIDGE_POLL_INTERVAL", "30"))
        self.min_eth_deposit = Decimal(os.getenv("MIN_ETH_DEPOSIT", "0.001"))
        
        self.blockchain_rpc_url = os.getenv("BLOCKCHAIN_RPC_URL", "http://127.0.0.1:8202")
        
        init_db()
        logger.info(f"BridgeMonitor initialized - watching {self.bridge_eth_address}")
    
    def parse_ait_recipient(self, tx_data: str) -> Optional[str]:
        """Parse AIT recipient address from transaction data field."""
        if not tx_data or tx_data == "0x":
            return None
        
        # Try to decode as UTF-8 string (if user sent plain text)
        try:
            # Remove 0x prefix
            data = tx_data[2:] if tx_data.startswith("0x") else tx_data
            # Pad to even length
            if len(data) % 2:
                data = "0" + data
            # Try UTF-8 decode
            decoded = bytes.fromhex(data).decode("utf-8")
            # Check if it looks like an AIT address
            if decoded.startswith("ait1") or decoded.startswith("aitbc1"):
                return decoded
        except (ValueError, UnicodeDecodeError):
            pass
        
        # Try hex string (if user sent hex-encoded address)
        try:
            data = tx_data[2:] if tx_data.startswith("0x") else tx_data
            if len(data) == 40:  # 20 bytes = 40 hex chars
                # Convert to checksummed address
                return "0x" + data
        except ValueError:
            pass
        
        return None
    
    def calculate_ait_amount(self, eth_amount: Decimal) -> Optional[Decimal]:
        """Calculate AIT amount based on ETH amount and oracle prices."""
        try:
            eth_usd_result = self.price_oracle.get_price("ETH", "USD")
            ait_usd_result = self.price_oracle.get_price("AIT", "USD")
            
            if eth_usd_result is None or ait_usd_result is None:
                logger.error("Cannot get prices for ETH/USD or AIT/USD")
                return None
            
            eth_usd = eth_usd_result.price
            ait_usd = ait_usd_result.price
            
            if ait_usd == 0:
                logger.error("AIT/USD price is zero")
                return None
            
            # AIT amount = (ETH amount * ETH/USD) / (AIT/USD)
            ait_amount = (eth_amount * eth_usd) / ait_usd
            logger.info(f"Price calculation: {eth_amount} ETH * ${eth_usd} / ${ait_usd} = {ait_amount} AIT")
            return ait_amount
        except Exception as e:
            logger.error(f"Error calculating AIT amount: {e}")
            return None
    
    def submit_ait_transfer(self, to_address: str, amount: Decimal) -> Optional[str]:
        """Submit AIT transfer transaction to AITBC blockchain."""
        if not self.genesis_private_key:
            logger.error("Cannot submit AIT transfer - no private key")
            return None
        
        try:
            import httpx
            
            # Resolve sender address to get nonce
            sender_response = httpx.get(
                f"{self.blockchain_rpc_url}/rpc/accounts/{self.genesis_wallet_address}"
            )
            if sender_response.status_code != 200:
                logger.error(f"Failed to get sender account: {sender_response.text}")
                return None
            
            sender_data = sender_response.json()
            nonce = sender_data.get("nonce", 0)
            
            # Resolve recipient address to validate it exists
            recipient_response = httpx.get(
                f"{self.blockchain_rpc_url}/rpc/accounts/{to_address}"
            )
            if recipient_response.status_code != 200:
                logger.warning(f"Recipient address may not exist: {to_address}")
            
            # Build transaction payload for marketplace transaction (simple transfer)
            tx_payload = {
                "from": self.genesis_wallet_address,
                "to": to_address,
                "value": str(int(amount)),
                "nonce": nonce,
                "gas_limit": 21000,
                "gas_price": "1",
                "type": "TRANSFER"
            }
            
            # Submit transaction
            submit_response = httpx.post(
                f"{self.blockchain_rpc_url}/rpc/transactions/marketplace",
                json=tx_payload
            )
            
            if submit_response.status_code == 200:
                result = submit_response.json()
                tx_hash = result.get("tx_hash")
                logger.info(f"AIT transfer submitted: {tx_hash}")
                return tx_hash
            else:
                logger.error(f"Failed to submit AIT transfer: {submit_response.text}")
                return None
        except Exception as e:
            logger.error(f"Error submitting AIT transfer: {e}")
            return None
    
    def process_deposit(self, tx_hash: str, from_address: str, eth_amount: Decimal, tx_data: str):
        """Process a single ETH deposit."""
        logger.info(f"Processing deposit: {tx_hash} from {from_address}, amount: {eth_amount} ETH")
        
        # Check if already processed
        existing = get_deposit(tx_hash)
        if existing:
            logger.info(f"Deposit {tx_hash} already processed, skipping")
            return
        
        # Parse AIT recipient
        ait_recipient = self.parse_ait_recipient(tx_data)
        if not ait_recipient:
            logger.warning(f"Could not parse AIT recipient from tx data: {tx_data}")
            # Create deposit record with error
            create_deposit(tx_hash, from_address, str(eth_amount), "")
            update_deposit(tx_hash, status=BridgeDepositStatus.FAILED, error_message="Invalid AIT recipient address")
            return
        
        # Calculate AIT amount
        ait_amount = self.calculate_ait_amount(eth_amount)
        if not ait_amount:
            logger.error("Could not calculate AIT amount")
            create_deposit(tx_hash, from_address, str(eth_amount), ait_recipient)
            update_deposit(tx_hash, status=BridgeDepositStatus.FAILED, error_message="Price calculation failed")
            return
        
        # Create deposit record
        deposit_id = create_deposit(tx_hash, from_address, str(eth_amount), ait_recipient)
        if not deposit_id:
            logger.info(f"Deposit {tx_hash} already exists in database")
            return
        
        # Update with calculated amounts
        eth_usd_result = self.price_oracle.get_price("ETH", "USD")
        ait_usd_result = self.price_oracle.get_price("AIT", "USD")
        eth_usd = eth_usd_result.price if eth_usd_result else None
        ait_usd = ait_usd_result.price if ait_usd_result else None
        update_deposit(
            tx_hash,
            ait_amount=str(ait_amount),
            eth_usd_price=str(eth_usd) if eth_usd else None,
            ait_usd_price=str(ait_usd) if ait_usd else None,
            status=BridgeDepositStatus.PROCESSING
        )
        
        # Submit AIT transfer
        ait_tx_hash = self.submit_ait_transfer(ait_recipient, ait_amount)
        if ait_tx_hash:
            update_deposit(
                tx_hash,
                ait_tx_hash=ait_tx_hash,
                status=BridgeDepositStatus.COMPLETED
            )
            logger.info(f"Successfully bridged {eth_amount} ETH to {ait_amount} AIT for {ait_recipient}")
        else:
            update_deposit(tx_hash, status=BridgeDepositStatus.FAILED, error_message="Failed to submit AIT transfer")
    
    def poll_ethereum(self):
        """Poll Ethereum for new transactions to bridge address."""
        try:
            # Use web3.py directly to get full transactions
            from web3 import Web3
            w3 = self.eth_rpc._get_web3()
            
            # Get latest block number
            latest_block = w3.eth.block_number
            logger.debug(f"Latest block: {latest_block}")
            
            # Scan recent blocks (last 10 blocks to catch any missed transactions)
            start_block = max(0, latest_block - 10)
            
            for block_num in range(start_block, latest_block + 1):
                block = w3.eth.get_block(block_num, full_transactions=True)
                if not block or not block.get("transactions"):
                    continue
                
                for tx in block["transactions"]:
                    # Check if transaction is to bridge address
                    to_address = tx.get("to", "")
                    if to_address and to_address.lower() == self.bridge_eth_address:
                        # Check if it's a value transfer (ETH)
                        value = tx.get("value", 0)
                        eth_amount = Decimal(value) / Decimal(10**18)
                        
                        if eth_amount < self.min_eth_deposit:
                            logger.debug(f"Skipping small deposit: {eth_amount} ETH")
                            continue
                        
                        tx_hash = tx.hash.hex()
                        from_address = tx.get("from", "")
                        tx_data = tx.get("input", "0x")
                        
                        logger.info(f"Found deposit: {tx_hash} from {from_address}, amount: {eth_amount} ETH")
                        
                        self.process_deposit(tx_hash, from_address, eth_amount, tx_data)
        
        except Exception as e:
            logger.error(f"Error polling Ethereum: {e}")
    
    def run(self):
        """Main polling loop."""
        logger.info("Starting bridge monitor polling loop")
        
        while True:
            try:
                self.poll_ethereum()
            except Exception as e:
                logger.error(f"Error in polling loop: {e}")
            
            time.sleep(self.poll_interval)


def main():
    """Main entry point."""
    monitor = BridgeMonitor()
    monitor.run()


if __name__ == "__main__":
    main()
