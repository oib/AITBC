"""
Transaction commands for AITBC CLI
"""

import json
from pathlib import Path
from typing import Optional, Dict, Any, List

import click

from ..utils import error, success
from ..utils.wallet import decrypt_private_key
from aitbc import AITBCHTTPClient, NetworkError, KEYSTORE_DIR, get_logger
from aitbc.exceptions import ValidationError
from aitbc.utils.validation import validate_address
from cryptography.hazmat.primitives.asymmetric import ed25519

logger = get_logger(__name__)

DEFAULT_RPC_URL = "http://localhost:8006"
DEFAULT_KEYSTORE_DIR = KEYSTORE_DIR


@click.group()
def transactions():
    """Transaction management commands"""
    pass


def _send_transaction_impl(from_wallet: str, to_address: str, amount: float, fee: float, 
                          password: str, keystore_dir: Path = DEFAULT_KEYSTORE_DIR, 
                          rpc_url: str = DEFAULT_RPC_URL) -> Optional[str]:
    """Send transaction from one wallet to another"""
    
    # Validate recipient address
    try:
        validate_address(to_address)
    except ValidationError as e:
        logger.error(f"Invalid recipient address: {e}")
        error(f"Invalid recipient address: {e}")
        return None
    
    # Validate amount
    if amount <= 0:
        logger.error(f"Invalid amount: {amount} must be positive")
        error("Amount must be positive")
        return None
    
    # Ensure keystore_dir is a Path object
    if keystore_dir is None:
        keystore_dir = DEFAULT_KEYSTORE_DIR
    if isinstance(keystore_dir, str):
        keystore_dir = Path(keystore_dir)
    
    # Get sender wallet info
    sender_keystore = keystore_dir / f"{from_wallet}.json"
    if not sender_keystore.exists():
        error(f"Wallet '{from_wallet}' not found")
        return None
    
    with open(sender_keystore) as f:
        sender_data = json.load(f)
    
    sender_address = sender_data['address']
    
    # Decrypt private key
    try:
        private_key_hex = decrypt_private_key(sender_keystore, password)
        private_key = ed25519.Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key_hex))
    except Exception as e:
        error(f"Error decrypting wallet: {e}")
        return None
    
    # Get chain_id from RPC health endpoint or use override
    from ..utils.chain_id import get_chain_id
    chain_id = get_chain_id(rpc_url, override=None, timeout=5)
    
    # Get actual nonce from blockchain
    actual_nonce = 0
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=5)
        account_data = http_client.get(f"/rpc/account/{sender_address}")
        actual_nonce = account_data.get("nonce", 0)
    except NetworkError:
        actual_nonce = 0
    except Exception:
        actual_nonce = 0
    
    # Create transaction
    transaction = {
        "type": "TRANSFER",
        "chain_id": chain_id,
        "from": sender_address,
        "nonce": actual_nonce,
        "fee": int(fee),
        "payload": {
            "recipient": to_address,
            "amount": int(amount)
        }
    }
    
    # Sign transaction
    message = json.dumps(transaction, sort_keys=True).encode()
    signature = private_key.sign(message)
    transaction["signature"] = signature.hex()
    
    # Submit to blockchain
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        result = http_client.post("/rpc/transaction", json=transaction)
        tx_hash = result.get("transaction_hash")
        success(f"Transaction submitted: {tx_hash}")
        logger.info(f"Transaction submitted: {tx_hash} from {from_wallet} to {to_address}")
        return tx_hash
    except NetworkError as e:
        logger.error(f"Network error submitting transaction: {e}")
        error(f"Error submitting transaction: {e}")
        return None
    except Exception as e:
        logger.error(f"Error submitting transaction: {e}")
        error(f"Error: {e}")
        return None


@transactions.command()
@click.option('--from', 'from_wallet', required=True, help='From wallet name')
@click.option('--to', 'to_address', required=True, help='To address')
@click.option('--amount', type=float, required=True, help='Amount to send')
@click.option('--fee', type=float, default=0.001, help='Transaction fee')
@click.option('--password', help='Wallet password')
@click.option('--password-file', help='File containing wallet password')
@click.option('--rpc-url', help='Blockchain RPC URL')
def send(from_wallet: str, to_address: str, amount: float, fee: float, password: Optional[str], password_file: Optional[str], rpc_url: Optional[str]):
    """Send transaction from one wallet to another"""
    if password_file:
        with open(password_file) as f:
            password = f.read().strip()
    elif not password:
        import getpass
        password = getpass.getpass("Enter wallet password: ")
    
    if not rpc_url:
        rpc_url = DEFAULT_RPC_URL
    
    tx_hash = _send_transaction_impl(from_wallet, to_address, amount, fee, password, rpc_url=rpc_url)
    if tx_hash:
        success(f"Transaction sent: {tx_hash}")


@transactions.command()
@click.option('--transactions-file', required=True, help='JSON file with batch transactions')
@click.option('--password', help='Wallet password')
@click.option('--password-file', help='File containing wallet password')
@click.option('--rpc-url', help='Blockchain RPC URL')
def batch(transactions_file: str, password: Optional[str], password_file: Optional[str], rpc_url: Optional[str]):
    """Send batch transactions"""
    if password_file:
        with open(password_file) as f:
            password = f.read().strip()
    elif not password:
        import getpass
        password = getpass.getpass("Enter wallet password: ")
    
    if not rpc_url:
        rpc_url = DEFAULT_RPC_URL
    
    with open(transactions_file) as f:
        transactions_data = json.load(f)
    
    results = []
    for tx in transactions_data:
        try:
            tx_hash = _send_transaction_impl(
                tx['from_wallet'],
                tx['to_address'],
                tx['amount'],
                tx.get('fee', 10.0),
                password,
                rpc_url=rpc_url
            )
            results.append({
                'transaction': tx,
                'hash': tx_hash,
                'success': tx_hash is not None
            })
            
            if tx_hash:
                success(f"Transaction sent: {tx['from_wallet']} → {tx['to_address']} ({tx['amount']} AIT)")
            else:
                error(f"Transaction failed: {tx['from_wallet']} → {tx['to_address']}")
                
        except Exception as e:
            results.append({
                'transaction': tx,
                'hash': None,
                'success': False,
                'error': str(e)
            })
            error(f"Transaction error: {e}")
    
    success(f"Batch completed: {len([r for r in results if r['success']])}/{len(results)} successful")


@transactions.command()
@click.argument('tx_hash')
@click.option('--rpc-url', help='Blockchain RPC URL')
def status(tx_hash: str, rpc_url: Optional[str]):
    """Get transaction status"""
    if not rpc_url:
        rpc_url = DEFAULT_RPC_URL
    
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        result = http_client.get(f"/rpc/transaction/{tx_hash}")
        success(f"Transaction status for {tx_hash}")
        click.echo(json.dumps(result, indent=2))
    except NetworkError as e:
        error(f"Error getting transaction status: {e}")
    except Exception as e:
        error(f"Error: {e}")


@transactions.command()
@click.option('--rpc-url', help='Blockchain RPC URL')
def pending(rpc_url: Optional[str]):
    """Get pending transactions"""
    if not rpc_url:
        rpc_url = DEFAULT_RPC_URL
    
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        data = http_client.get("/rpc/pending")
        transactions = data.get("transactions", [])
        success(f"Pending transactions: {len(transactions)}")
        for tx in transactions:
            click.echo(f"  - {tx.get('hash', 'unknown')}: {tx.get('amount', 0)} AIT")
    except NetworkError as e:
        error(f"Error getting pending transactions: {e}")
    except Exception as e:
        error(f"Error: {e}")


@transactions.command()
@click.option('--from', 'from_wallet', required=True, help='From wallet name')
@click.option('--to', 'to_address', required=True, help='To address')
@click.option('--amount', type=float, required=True, help='Amount to send')
@click.option('--rpc-url', help='Blockchain RPC URL')
def estimate_fee(from_wallet: str, to_address: str, amount: float, rpc_url: Optional[str]):
    """Estimate transaction fee"""
    if not rpc_url:
        rpc_url = DEFAULT_RPC_URL
    
    try:
        test_tx = {
            "sender": "",
            "recipient": to_address,
            "value": int(amount),
            "fee": 10,
            "nonce": 0,
            "type": "transfer",
            "payload": {}
        }
        
        try:
            http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
            fee_data = http_client.post("/rpc/estimateFee", json=test_tx)
            estimated_fee = fee_data.get("estimated_fee", 10.0)
            success(f"Estimated fee: {estimated_fee} AIT")
        except NetworkError:
            success(f"Estimated fee: 10.0 AIT (default)")
    except Exception as e:
        error(f"Error estimating fee: {e}")
        success(f"Estimated fee: 10.0 AIT (default)")
