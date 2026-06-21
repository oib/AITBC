"""
Exchange subgroup and exchange commands
"""

import click

from ...config import get_config
from ...utils import error, info, success, warning
from ...utils.http_client import AITBCHTTPClient, NetworkError, get_logger

# Initialize logger
logger = get_logger(__name__)

from . import market


@market.group(name="exchange")
def exchange():
    """ETH-AIT exchange and bridge operations"""
    pass


@exchange.command(name="price")
@click.pass_context
def exchange_price(ctx):
    """Get current ETH-AIT exchange rate"""
    try:
        client = AITBCHTTPClient(base_url="http://localhost:8108", timeout=10)

        response = client.get("/v1/exchange/price")

        info("ETH-AIT Exchange Rate:")
        info(f"  ETH Price: ${response['eth_usd']:.2f} USD")
        info(f"  AIT Price: ${response['ait_usd']:.2f} USD")
        info(f"  Exchange Rate: 1 ETH = {response['exchange_rate']:.2f} AIT")
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
        client = AITBCHTTPClient(base_url="http://localhost:8108", timeout=10)

        response = client.get("/v1/exchange/deposits", params={"status": status, "limit": limit})
        deposits = response.get("deposits", [])

        if not deposits:
            info(f"No deposits found with status '{status}'")
            return

        info(f"ETH Deposits (status: {status}):")
        for deposit in deposits:
            info(f"  ID: {deposit['id']}")
            info(f"    TX Hash: {deposit['tx_hash']}")
            info(f"    From: {deposit['from_address']}")
            info(f"    Amount: {deposit['amount_eth']:.6f} ETH → {deposit['amount_ait']:.2f} AIT")
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
        client = AITBCHTTPClient(base_url="http://localhost:8108", timeout=10)

        # Get deposit details
        deposit_response = client.get(f"/v1/exchange/deposits/{deposit_id}")
        deposit = deposit_response

        if deposit["status"] != "pending":
            error(f"Deposit is not pending (current status: {deposit['status']})")
            raise click.Abort()

        info(f"Deposit: {deposit['amount_eth']:.6f} ETH → {deposit['amount_ait']:.2f} AIT")
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
        wallet_address = config.wallet_address
        chain_id = config.chain_id
        genesis_wallet_address = config.get("genesis_wallet_address", "ait1db5247d03ca2e40f3995a583b2c097ab703efd4d")

        try:
            import httpx

            # Resolve sender address to get nonce
            sender_response = httpx.get(
                f"{config.get('blockchain_rpc_url', 'http://localhost:8202')}/rpc/accounts/{genesis_wallet_address}"
            )
            if sender_response.status_code != 200:
                error(f"Failed to get genesis wallet account: {sender_response.text}")
                raise click.Abort()

            sender_data = sender_response.json()
            nonce = sender_data.get("nonce", 0)

            # Build transaction payload for AIT transfer
            tx_payload = {
                "from": genesis_wallet_address,
                "to": wallet_address,
                "value": str(int(deposit["amount_ait"] * 1000)),  # Convert to milli-AIT
                "nonce": nonce,
                "gas_limit": 21000,
                "gas_price": "1",
                "type": "TRANSFER",
                "chain_id": chain_id,
            }

            # Submit transaction to blockchain
            blockchain_response = httpx.post(
                f"{config.get('blockchain_rpc_url', 'http://localhost:8202')}/rpc/transactions/marketplace", json=tx_payload
            )

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
                success(f"Transferred {deposit['amount_ait']:.2f} AIT to {wallet_address} (tx: {tx_hash[:16]}...)")
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
@click.argument("amount", type=float)
@click.argument("address")
@click.pass_context
def withdraw_eth(ctx, amount: float, address: str):
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
            _ = config.get("bridge_contract_address", "0x24403CCff489D9355A534D34d4F88bC5b3EcF6FA")
            eth_rpc_url = config.get("eth_rpc_url", os.environ.get("ETH_RPC_URL"))
            bridge_private_key = config.get("bridge_private_key", os.environ.get("BRIDGE_PRIVATE_KEY"))

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

            if receipt.status == 1:
                success(f"Withdrew {amount} ETH to {address}")
                info(f"Transaction hash: {tx_hash.hex()}")

                # Record withdrawal in exchange service
                try:
                    record_response = httpx.post(
                        f"{config.get('exchange_url', 'http://localhost:8106')}/v1/exchange/withdrawals",
                        json={"amount": amount, "to_address": address, "tx_hash": tx_hash.hex(), "status": "completed"},
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
        client = AITBCHTTPClient(base_url="http://localhost:8108", timeout=10)

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
