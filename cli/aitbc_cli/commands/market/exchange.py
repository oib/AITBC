import os

"""
Exchange subgroup and exchange commands
"""

from decimal import Decimal

import click

from ...config import get_config
from ...utils import DECIMAL, error, info, success, warning
from aitbc.utils import ait_to_seconds
from ...utils.http_client import AITBCHTTPClient, NetworkError, get_logger

# Initialize logger
logger = get_logger(__name__)

from . import market


def _sign_transaction(tx_payload: dict, private_key: str) -> str:
    """Sign ``tx_payload`` the way the RPC endpoint verifies it.

    ``verify_transaction_signature`` (blockchain-node `rpc/utils.py`) drops the signature
    field, re-encodes the rest as canonical JSON — sorted keys, no whitespace — and recovers
    the signer from the keccak256 of those bytes. Any difference in separators or key order
    produces a different hash and a 403, so this must mirror it exactly.
    """
    import json as _json

    from eth_utils import keccak

    from aitbc.crypto.crypto import sign_transaction_hash

    unsigned = {k: v for k, v in tx_payload.items() if k != "signature"}
    message = _json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    return sign_transaction_hash("0x" + keccak(message).hex(), private_key)


@market.group(name="exchange")
def exchange():
    """ETH-AIT exchange and bridge operations"""
    pass


@exchange.command(name="price")
@click.pass_context
def exchange_price(ctx):
    """Get current ETH-AIT exchange rate"""
    try:
        config = get_config()
        client = AITBCHTTPClient(base_url="http://localhost:8108", timeout=10, api_key=config.api_key)

        response = client.get("/v1/exchange/price")

        # The /v1/exchange/price endpoint returns numeric values as strings,
        # so convert before formatting.
        eth_usd = Decimal(response.get("eth_usd", 0))
        ait_usd = Decimal(response.get("ait_usd", 0))
        exchange_rate = Decimal(response.get("exchange_rate", 0))

        info("ETH-AIT Exchange Rate:")
        info(f"  ETH Price: ${eth_usd:.2f} USD")
        info(f"  AIT Price: ${ait_usd:.2f} USD")
        info(f"  Exchange Rate: 1 ETH = {exchange_rate:.2f} AIT")
        info(f"  Timestamp: {response['timestamp']}")

    except NetworkError as e:
        error(f"Network error: {e}")
        raise click.Abort() from e
    except Exception as e:
        error(f"Error getting price: {e}")
        raise click.Abort() from e


@exchange.command(name="list-deposits")
@click.option("--status", default="pending", help="Filter by status (pending, verified, completed, rejected)")
@click.option("--limit", default=50, help="Maximum number of results")
@click.pass_context
def list_deposits(ctx, status: str, limit: int):
    """List ETH deposits"""
    try:
        config = get_config()
        client = AITBCHTTPClient(base_url="http://localhost:8108", timeout=10, api_key=config.api_key)

        response = client.get("/v1/exchange/deposits", params={"status": status, "limit": limit})
        deposits = response.get("deposits", [])

        if not deposits:
            info(f"No deposits found with status '{status}'")
            return

        info(f"ETH Deposits (status: {status}):")
        for deposit in deposits:
            amount_eth = Decimal(deposit.get("amount_eth", 0))
            amount_ait = Decimal(deposit.get("amount_ait", 0))
            info(f"  ID: {deposit['id']}")
            info(f"    TX Hash: {deposit['tx_hash']}")
            info(f"    From: {deposit['from_address']}")
            info(f"    Amount: {amount_eth:.6f} ETH → {amount_ait:.2f} AIT")
            info(f"    Status: {deposit['status']}")
            info(f"    Created: {deposit['created_at']}")
            info("")

    except NetworkError as e:
        error(f"Network error: {e}")
        raise click.Abort() from e
    except Exception as e:
        error(f"Error listing deposits: {e}")
        raise click.Abort() from e


@exchange.command(name="mint-ait")
@click.argument("deposit_id")
@click.pass_context
def mint_ait(ctx, deposit_id: str):
    """Mint AIT tokens for a verified ETH deposit"""
    try:
        config = get_config()
        client = AITBCHTTPClient(base_url="http://localhost:8108", timeout=10, api_key=config.api_key)

        # Get deposit details
        deposit_response = client.get(f"/v1/exchange/deposits/{deposit_id}")
        deposit = deposit_response

        if deposit["status"] != "pending":
            error(f"Deposit is not pending (current status: {deposit['status']})")
            raise click.Abort()

        deposit_amount_eth = Decimal(deposit.get("amount_eth", 0))
        deposit_amount_ait = Decimal(deposit.get("amount_ait", 0))
        info(f"Deposit: {deposit_amount_eth:.6f} ETH → {deposit_amount_ait:.2f} AIT")
        info(f"From: {deposit['from_address']}")

        if not click.confirm("Verify this deposit and mint AIT tokens?"):
            info("Cancelled")
            return

        # Verify deposit
        verify_response = client.post(f"/v1/exchange/deposits/{deposit_id}/verify")

        if not verify_response.get("success"):
            error(f"Failed to verify deposit: {verify_response}")
            raise click.Abort()

        success(f"Deposit verified: {deposit_id}")

        # Transfer AIT tokens from genesis wallet (fixed supply, no minting)
        wallet_address = getattr(config, "wallet_address", None) or os.environ.get("WALLET_ADDRESS")
        chain_id = getattr(config, "chain_id", None)
        genesis_wallet_address = getattr(config, "genesis_wallet_address", "")

        try:
            import httpx

            # Resolve sender address to get nonce
            blockchain_rpc_url = getattr(config, "blockchain_rpc_url", "http://localhost:8202")
            sender_response = httpx.get(f"{blockchain_rpc_url}/rpc/accounts/{genesis_wallet_address}")
            if sender_response.status_code != 200:
                # Name the address. The likely cause is GENESIS_WALLET_ADDRESS pointing at the
                # block proposer, which is a signing identity with no account and no balance —
                # a mix-up that has already been made in a deployed env file.
                error(f"Failed to get genesis wallet account {genesis_wallet_address}: {sender_response.text}")
                error("GENESIS_WALLET_ADDRESS must be the wallet holding the genesis allocation, not the proposer.")
                raise click.Abort()

            sender_data = sender_response.json()
            nonce = sender_data.get("nonce", 0)

            # Build transaction payload for AIT transfer
            fee_ait = Decimal("0.01")
            amount_seconds = ait_to_seconds(deposit_amount_ait)
            fee_seconds = ait_to_seconds(fee_ait)

            tx_payload = {
                "type": "TRANSFER",
                "chain_id": chain_id,
                "from": genesis_wallet_address,
                "to": wallet_address,
                "amount": amount_seconds,
                "fee": fee_seconds,
                "nonce": nonce,
                "payload": {"amount": amount_seconds},
            }

            # The endpoint has rejected unsigned transactions since v0.10.13 (403 "Signature
            # required"). This payload went out without a signature, so the command could not
            # have succeeded since then.
            secret = getattr(config, "genesis_wallet_private_key", None)
            if secret is None:
                error(f"No signing key for {genesis_wallet_address}; cannot authorise the transfer.")
                error("Set GENESIS_WALLET_PRIVATE_KEY to the key controlling that address.")
                raise click.Abort()

            tx_payload["signature"] = _sign_transaction(tx_payload, secret.get_secret_value())

            # Submit transaction to blockchain
            blockchain_response = httpx.post(f"{blockchain_rpc_url}/rpc/transaction", json=tx_payload)

            if blockchain_response.status_code != 200:
                error(f"Failed to submit transfer transaction: {blockchain_response.text}")
                raise click.Abort()

            tx_result = blockchain_response.json()
            tx_hash = tx_result.get("transaction_hash")

            if not tx_hash:
                error(f"Transaction submitted but no hash returned: {tx_result}")
                raise click.Abort()

            # Mark deposit as completed
            complete_response = client.post(f"/v1/exchange/deposits/{deposit_id}/complete", json={"tx_hash": tx_hash})

            if complete_response.get("success"):
                success(f"Transferred {deposit_amount_ait:.2f} AIT to {wallet_address} (tx: {tx_hash[:16]}...)")
            else:
                error(f"Failed to complete deposit: {complete_response}")
                raise click.Abort()

        except httpx.RequestError as e:
            error(f"Network error contacting blockchain: {e}")
            raise click.Abort() from e
        except Exception as e:
            error(f"Error transferring AIT: {e}")
            raise click.Abort() from e

    except NetworkError as e:
        error(f"Network error: {e}")
        raise click.Abort() from e
    except Exception as e:
        error(f"Error minting AIT: {e}")
        raise click.Abort() from e


@exchange.command(name="withdraw-eth")
@click.argument("amount", type=DECIMAL)
@click.argument("address")
@click.pass_context
def withdraw_eth(ctx, amount: Decimal, address: str):
    """Withdraw ETH from bridge wallet (admin only)"""
    try:
        config = get_config()

        if amount <= 0:
            error("Amount must be positive")
            raise click.Abort()

        info(f"Withdrawing {amount} ETH to {address}")

        if not click.confirm("Confirm withdrawal?"):
            info("Cancelled")
            return

        # Implement ETH withdrawal via web3.py
        try:
            import os

            import httpx
            from web3 import Web3

            # Get bridge configuration
            _ = getattr(config, "bridge_contract_address", None)
            eth_rpc_url = getattr(config, "eth_rpc_url", os.environ.get("ETH_RPC_URL"))
            bridge_private_key = getattr(config, "bridge_private_key", os.environ.get("BRIDGE_PRIVATE_KEY"))

            if not eth_rpc_url:
                error("ETH_RPC_URL not configured")
                raise click.Abort()

            if not bridge_private_key:
                error("Bridge private key not configured")
                raise click.Abort()

            # Initialize web3
            w3 = Web3(Web3.HTTPProvider(eth_rpc_url))

            if not w3.is_connected():
                error("Failed to connect to Ethereum RPC")
                raise click.Abort()

            # Convert ETH amount to wei
            amount_wei = w3.to_wei(amount, "ether")

            # Get current nonce
            bridge_account = w3.eth.account.from_key(bridge_private_key)
            nonce = w3.eth.get_transaction_count(bridge_account.address)

            # Build transaction
            tx = {
                "nonce": nonce,
                "to": address,
                "value": amount_wei,
                "gas": 21000,
                "gasPrice": w3.eth.gas_price,
                "chainId": 11155111,  # Sepolia testnet
            }

            # Sign transaction
            signed_tx = w3.eth.account.sign_transaction(tx, bridge_private_key)

            # Send transaction
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

            # Wait for confirmation
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

            if getattr(receipt, "status", 0) == 1:
                success(f"Withdrew {amount} ETH to {address}")
                info(f"Transaction hash: {tx_hash.hex()}")

                # Record withdrawal in exchange service
                try:
                    exchange_url = getattr(config, "exchange_url", "http://localhost:8106")
                    record_response = httpx.post(
                        f"{exchange_url}/v1/exchange/withdrawals",
                        json={
                            "amount": str(amount),
                            "to_address": address,
                            "tx_hash": tx_hash.hex(),
                            "status": "completed",
                        },
                    )
                    if record_response.status_code != 200:
                        warning("Withdrawal completed but failed to record in exchange service")
                except Exception as record_e:
                    warning(f"Withdrawal completed but failed to record: {record_e}")
            else:
                error("Transaction failed")
                raise click.Abort()

        except ImportError:
            error("web3.py not installed. Install with: pip install web3")
            raise click.Abort() from None
        except Exception as e:
            error(f"Error withdrawing ETH: {e}")
            raise click.Abort() from e

    except Exception as e:
        error(f"Error withdrawing ETH: {e}")
        raise click.Abort() from e


@exchange.command(name="status")
@click.pass_context
def exchange_status(ctx):
    """Get bridge service status"""
    try:
        config = get_config()
        client = AITBCHTTPClient(base_url="http://localhost:8108", timeout=10, api_key=config.api_key)

        response = client.get("/v1/exchange/status")

        info("Bridge Service Status:")
        info(f"  Enabled: {response['enabled']}")
        info(f"  Wallet Address: {response['wallet_address']}")
        info(f"  RPC URL: {response['rpc_url']}")
        info(f"  Poll Interval: {response['poll_interval']}s")

    except NetworkError as e:
        error(f"Network error: {e}")
        raise click.Abort() from e
    except Exception as e:
        error(f"Error getting status: {e}")
        raise click.Abort() from e
