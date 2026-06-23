"""Bridge monitor service - polls Ethereum for ETH deposits and sends AIT."""

import os
import sys
import time
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../.."))
from aitbc.aitbc_logging import configure_logging, get_logger
from aitbc.ethereum_rpc import EthereumRPCClient
from aitbc.oracles.price_oracle import get_price_oracle

from .storage import (
    BridgeDepositStatus,
    create_deposit,
    get_cursor,
    get_deposit,
    get_deposits_for_retry,
    init_db,
    set_cursor,
    update_deposit,
)

configure_logging(level="INFO", service_name="bridge-monitor", to_file=True)
logger = get_logger(__name__)


class BridgeMonitor:
    """Monitor Ethereum wallet for deposits and bridge to AIT."""

    def __init__(self) -> None:
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
        logger.info("BridgeMonitor initialized - watching %s", self.bridge_eth_address)

    def parse_ait_recipient(self, tx_data: str) -> str | None:
        """Parse AIT recipient address from transaction data field."""
        if not tx_data or tx_data == "0x":
            return None
        try:
            data = tx_data[2:] if tx_data.startswith("0x") else tx_data
            if len(data) % 2:
                data = "0" + data
            decoded = bytes.fromhex(data).decode("utf-8")
            if decoded.startswith("ait1") or decoded.startswith("aitbc1"):
                return decoded
        except (ValueError, UnicodeDecodeError):
            pass
        try:
            data = tx_data[2:] if tx_data.startswith("0x") else tx_data
            if len(data) == 40:
                return "0x" + data
        except ValueError:
            pass
        return None

    def calculate_ait_amount(self, eth_amount: Decimal, eth_usd=None, ait_usd=None) -> Decimal | None:
        """Calculate AIT amount based on ETH amount and oracle prices.

        Accepts pre-fetched prices to avoid redundant oracle calls.
        """
        try:
            if eth_usd is None:
                eth_usd_result = self.price_oracle.get_price("ETH", "USD")
                eth_usd = eth_usd_result.price if eth_usd_result else None
            if ait_usd is None:
                ait_usd_result = self.price_oracle.get_price("AIT", "USD")
                ait_usd = ait_usd_result.price if ait_usd_result else None
            if eth_usd is None or ait_usd is None:
                logger.error("Cannot get prices for ETH/USD or AIT/USD")
                return None
            if ait_usd == 0:
                logger.error("AIT/USD price is zero")
                return None
            ait_amount = eth_amount * Decimal(eth_usd) / Decimal(ait_usd)
            logger.info("Price calculation: %s ETH * $%s / $%s = %s AIT", eth_amount, eth_usd, ait_usd, ait_amount)
            return ait_amount
        except Exception as e:
            logger.error("Error calculating AIT amount: %s", e)
            return None

    def submit_ait_transfer(self, to_address: str, amount: Decimal) -> str | None:
        """Submit AIT transfer transaction to AITBC blockchain."""
        if not self.genesis_private_key:
            logger.error("Cannot submit AIT transfer - no private key")
            return None
        try:
            import httpx
            import json
            from cryptography.hazmat.primitives.asymmetric import ed25519

            # Get current nonce
            sender_response = httpx.get(f"{self.blockchain_rpc_url}/rpc/account/{self.genesis_wallet_address}", timeout=5)
            if sender_response.status_code != 200:
                logger.error("Failed to get sender account: %s", sender_response.text)
                return None
            nonce = int(sender_response.json().get("nonce", 0))

            # Build and sign transaction
            tx_amount = int(amount)
            transaction = {
                "from": self.genesis_wallet_address,
                "to": to_address,
                "amount": tx_amount,
                "nonce": nonce,
                "fee": 36,
                "type": "TRANSFER",
            }
            private_key = ed25519.Ed25519PrivateKey.from_private_bytes(
                bytes.fromhex(self.genesis_private_key.removeprefix("0x"))
            )
            message = json.dumps(transaction, sort_keys=True).encode()
            signature = private_key.sign(message)
            transaction["signature"] = signature.hex()

            logger.info("Submitting AIT transfer: %s AIT to %s (nonce=%s)", tx_amount, to_address, nonce)
            submit_response = httpx.post(
                f"{self.blockchain_rpc_url}/rpc/transaction",
                json=transaction,
                timeout=10,
            )
            if submit_response.status_code == 200:
                result = submit_response.json()
                tx_hash: str | None = result.get("transaction_hash") or result.get("tx_hash")
                logger.info("AIT transfer submitted: %s", tx_hash)
                return tx_hash
            else:
                logger.error("Failed to submit AIT transfer: %s", submit_response.text)
                return None
        except Exception as e:
            logger.error("Error submitting AIT transfer: %s", e)
            return None

    def process_deposit(self, tx_hash: str, from_address: str, eth_amount: Decimal, tx_data: str) -> None:
        """Process a single ETH deposit."""
        logger.info("Processing deposit: %s from %s, amount: %s ETH", tx_hash, from_address, eth_amount)
        existing = get_deposit(tx_hash)
        if existing:
            logger.info("Deposit %s already processed, skipping", tx_hash)
            return
        ait_recipient = self.parse_ait_recipient(tx_data)
        if not ait_recipient:
            logger.warning("Could not parse AIT recipient from tx data: %s", tx_data)
            create_deposit(tx_hash, from_address, str(eth_amount), "")
            update_deposit(tx_hash, status=BridgeDepositStatus.FAILED, error_message="Invalid AIT recipient address")
            return
        # Fetch oracle prices once for both calculation and storage
        eth_usd_result = self.price_oracle.get_price("ETH", "USD")
        ait_usd_result = self.price_oracle.get_price("AIT", "USD")
        eth_usd = eth_usd_result.price if eth_usd_result else None
        ait_usd = ait_usd_result.price if ait_usd_result else None
        ait_amount = self.calculate_ait_amount(eth_amount, eth_usd=eth_usd, ait_usd=ait_usd)
        if not ait_amount:
            logger.error("Could not calculate AIT amount")
            create_deposit(tx_hash, from_address, str(eth_amount), ait_recipient)
            update_deposit(tx_hash, status=BridgeDepositStatus.FAILED, error_message="Price calculation failed")
            return
        deposit_id = create_deposit(tx_hash, from_address, str(eth_amount), ait_recipient)
        if not deposit_id:
            logger.info("Deposit %s already exists in database", tx_hash)
            return
        update_deposit(
            tx_hash,
            ait_amount=str(ait_amount),
            eth_usd_price=str(eth_usd) if eth_usd else None,
            ait_usd_price=str(ait_usd) if ait_usd else None,
            status=BridgeDepositStatus.PROCESSING,
        )
        ait_tx_hash = self.submit_ait_transfer(ait_recipient, ait_amount)
        if ait_tx_hash:
            update_deposit(tx_hash, ait_tx_hash=ait_tx_hash, status=BridgeDepositStatus.COMPLETED)
            logger.info("Successfully bridged %s ETH to %s AIT for %s", eth_amount, ait_amount, ait_recipient)
        else:
            self._mark_for_retry(tx_hash, "Failed to submit AIT transfer")

    def _mark_for_retry(self, tx_hash: str, error_message: str) -> None:
        """Mark a deposit for retry instead of immediate failure."""
        from datetime import UTC, datetime, timedelta

        deposit = get_deposit(tx_hash)
        retry_count = (deposit.get("retry_count", 0) if deposit else 0) + 1
        max_retries = 5
        if retry_count >= max_retries:
            logger.error("Deposit %s exhausted %s retries, marking FAILED", tx_hash, max_retries)
            update_deposit(
                tx_hash,
                status=BridgeDepositStatus.FAILED,
                error_message=error_message,
                retry_count=retry_count,
                next_retry_at=None,
            )
            return
        # Exponential backoff: 30s, 2m, 10m, 1h, 4h
        backoff_seconds = [30, 120, 600, 3600, 14400]
        delay = backoff_seconds[min(retry_count - 1, len(backoff_seconds) - 1)]
        next_retry = (datetime.now(UTC) + timedelta(seconds=delay)).isoformat()
        logger.warning(
            "Deposit %s marked PENDING_RETRY (attempt %s/%s, next in %ss): %s",
            tx_hash,
            retry_count,
            max_retries,
            delay,
            error_message,
        )
        update_deposit(
            tx_hash,
            status=BridgeDepositStatus.PENDING_RETRY,
            error_message=error_message,
            retry_count=retry_count,
            next_retry_at=next_retry,
        )

    def process_retry_queue(self) -> None:
        """Re-attempt deposits in PENDING_RETRY status whose next_retry_at has passed."""
        deposits = get_deposits_for_retry()
        if not deposits:
            return
        logger.info("Retry queue: %s deposit(s) to re-attempt", len(deposits))
        for d in deposits:
            tx_hash = d["eth_tx_hash"]
            ait_recipient = d["ait_recipient"]
            ait_amount_str = d.get("ait_amount")
            if not ait_amount_str:
                logger.error("Retry for %s: no ait_amount stored, marking FAILED", tx_hash)
                update_deposit(tx_hash, status=BridgeDepositStatus.FAILED, error_message="Retry failed: no AIT amount")
                continue
            ait_amount = Decimal(ait_amount_str)
            logger.info("Retrying deposit %s: %s AIT to %s", tx_hash, ait_amount, ait_recipient)
            update_deposit(tx_hash, status=BridgeDepositStatus.PROCESSING)
            ait_tx_hash = self.submit_ait_transfer(ait_recipient, ait_amount)
            if ait_tx_hash:
                update_deposit(
                    tx_hash, ait_tx_hash=ait_tx_hash, status=BridgeDepositStatus.COMPLETED, retry_count=d.get("retry_count", 0)
                )
                logger.info("Retry succeeded for deposit %s", tx_hash)
            else:
                self._mark_for_retry(tx_hash, "Retry: failed to submit AIT transfer")

    def poll_ethereum(self) -> None:
        """Poll Ethereum for new transactions to bridge address."""
        try:
            w3 = self.eth_rpc._get_web3()
            latest_block = w3.eth.block_number
            logger.debug("Latest block: %s", latest_block)

            # Use persistent cursor; bootstrap from latest_block - 10 on first run
            cursor = get_cursor("last_processed_block")
            if cursor is not None:
                start_block = cursor + 1
            else:
                start_block = max(0, latest_block - 10)

            if start_block > latest_block:
                logger.debug("No new blocks since cursor (%s)", start_block - 1)
                return

            for block_num in range(start_block, latest_block + 1):
                block = w3.eth.get_block(block_num, full_transactions=True)
                if not block or not block.get("transactions"):
                    set_cursor("last_processed_block", block_num)
                    continue
                for tx in block["transactions"]:
                    to_address = tx.get("to", "")
                    if to_address and to_address.lower() == self.bridge_eth_address:
                        value = tx.get("value", 0)
                        eth_amount = Decimal(value) / Decimal(10**18)
                        if eth_amount < self.min_eth_deposit:
                            logger.debug("Skipping small deposit: %s ETH", eth_amount)
                            continue
                        tx_hash = tx.hash.hex()
                        from_address = tx.get("from", "")
                        tx_data = tx.get("input", "0x")
                        logger.info("Found deposit: %s from %s, amount: %s ETH", tx_hash, from_address, eth_amount)
                        self.process_deposit(tx_hash, from_address, eth_amount, tx_data)
                # Advance cursor only after processing all deposits in this block
                set_cursor("last_processed_block", block_num)
        except Exception as e:
            logger.error("Error polling Ethereum: %s", e)

    def run(self) -> None:
        """Main polling loop."""
        logger.info("Starting bridge monitor polling loop")
        while True:
            try:
                self.poll_ethereum()
                self.process_retry_queue()
            except Exception as e:
                logger.error("Error in polling loop: %s", e)
            time.sleep(self.poll_interval)


def main() -> None:
    """Main entry point."""
    monitor = BridgeMonitor()
    monitor.run()


if __name__ == "__main__":
    main()
