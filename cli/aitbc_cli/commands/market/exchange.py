import os
import time

"""
Exchange subgroup and exchange commands
"""

from decimal import Decimal

import click

from aitbc.exceptions import ValidationError
from aitbc.utils.validation import validate_address_strict

from ...config import get_config
from ...utils import DECIMAL, error, info, success, warning
from ...utils.wallet_loader import load_wallet_for_payment
from aitbc.ethereum_rpc import EthereumRPCClient
from aitbc.utils import ait_to_units
from ...utils.http_client import AITBCHTTPClient, NetworkError, get_logger

# Initialize logger
logger = get_logger(__name__)

from ._group import market


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


@market.group(
    name="exchange",
    epilog="""Examples:

  aitbc market exchange price

  aitbc market exchange deposit-eth --amount 0.1""",
)
def exchange():
    """ETH-AIT exchange and bridge operations for market payments."""
    pass


@exchange.command(
    name="price",
    epilog="""Examples:

  aitbc market exchange price

  aitbc market exchange price --output json""",
)
@click.pass_context
def exchange_price(ctx):
    """Get the current ETH-AIT exchange rate."""
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


@exchange.command(
    name="list-deposits",
    epilog="""Examples:

  aitbc market exchange list-deposits

  aitbc market exchange list-deposits --status confirmed""",
)
@click.option("--status", default="pending", help="Filter by status (pending, verified, completed, rejected)")
@click.option("--limit", default=50, help="Maximum number of results")
@click.pass_context
def list_deposits(ctx, status: str, limit: int):
    """List ETH deposits and their status."""
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


def _mintable_deposit(client: AITBCHTTPClient, deposit_id: str) -> dict:
    """Fetch a deposit and require a mintable status.

    'verified' counts: a run that verified the deposit and then failed
    before completing must be resumable, or the row strands forever
    (#2545).
    """
    deposit = client.get(f"/v1/exchange/deposits/{deposit_id}")
    if deposit["status"] not in ("pending", "verified"):
        error(f"Deposit is not mintable (current status: {deposit['status']}); expected pending or verified")
        raise click.Abort()
    return deposit


def _confirm_mint(deposit: dict) -> bool:
    """Print deposit details and ask for confirmation."""
    deposit_amount_eth = Decimal(deposit.get("amount_eth", 0))
    deposit_amount_ait = Decimal(deposit.get("amount_ait", 0))
    info(f"Deposit: {deposit_amount_eth:.6f} ETH → {deposit_amount_ait:.2f} AIT")
    info(f"From: {deposit['from_address']}")
    return click.confirm("Verify this deposit and mint AIT tokens?")


def _verify_deposit(client: AITBCHTTPClient, deposit_id: str, status: str) -> None:
    if status == "verified":
        info("Deposit already verified; resuming the mint")
        return
    verify_response = client.post(f"/v1/exchange/deposits/{deposit_id}/verify")
    if not verify_response.get("success"):
        error(f"Failed to verify deposit: {verify_response}")
        raise click.Abort()
    success(f"Deposit verified: {deposit_id}")


def _mint_recipient(deposit: dict) -> str:
    """The deposit's recorded AIT recipient — the ETH sender named it at
    deposit time; paying the operator's configured wallet instead strands
    the minted AIT (#2547)."""
    recipient = str(deposit.get("recipient") or "").strip()
    if not recipient:
        error("Deposit carries no AIT recipient address; refusing to pay the operator wallet instead")
        raise click.Abort()
    try:
        return validate_address_strict(recipient)
    except ValidationError as exc:
        error(f"Deposit recipient is not a valid AIT address: {exc}")
        raise click.Abort() from exc


def _treasury_preflight(config, deposit: dict) -> None:
    """Every fallible transfer precondition that must pass BEFORE the deposit
    flips to 'verified' — a failure after the flip used to strand the row
    because the CLI refused to re-run it (#2545)."""
    genesis_wallet_address = getattr(config, "genesis_wallet_address", "")
    blockchain_rpc_url = getattr(config, "blockchain_rpc_url", "http://localhost:8202")
    secret = getattr(config, "genesis_wallet_private_key", None)
    if secret is None:
        error(f"No signing key for {genesis_wallet_address}; cannot authorise the transfer.")
        error("Set GENESIS_WALLET_PRIVATE_KEY to the key controlling that address.")
        raise click.Abort()
    _mint_recipient(deposit)
    _treasury_sender_nonce(genesis_wallet_address, blockchain_rpc_url)


def _treasury_sender_nonce(genesis_wallet_address: str, blockchain_rpc_url: str) -> int:
    """Resolve the treasury account nonce; aborts when the account is unknown."""
    import httpx

    sender_response = httpx.get(f"{blockchain_rpc_url}/rpc/accounts/{genesis_wallet_address}")
    if sender_response.status_code != 200:
        # Name the address. The likely cause is GENESIS_WALLET_ADDRESS pointing at the
        # block proposer, which is a signing identity with no account and no balance —
        # a mix-up that has already been made in a deployed env file.
        error(f"Failed to get treasury (genesis) wallet account {genesis_wallet_address}: {sender_response.text}")
        error("GENESIS_WALLET_ADDRESS must be the treasury wallet holding the genesis allocation, not the proposer.")
        raise click.Abort()

    sender_data = sender_response.json()
    nonce: int = sender_data.get("nonce", 0)
    return nonce


def _treasury_next_nonce(genesis_wallet_address: str, sealed_nonce: int, chain_id, blockchain_rpc_url: str) -> int:
    """Sealed nonce advanced past the sender's pending mempool slots (#2546):
    the account nonce does not move while earlier transfers sit in the
    mempool, so consecutive mints signing it collide on the (sender, nonce)
    slot."""
    from ...utils.nonce import pending_nonce_floor

    client = AITBCHTTPClient(base_url=blockchain_rpc_url, timeout=10)
    floor = pending_nonce_floor(client, genesis_wallet_address, sealed_nonce, chain_id)
    if floor is None:
        warning(
            f"Pending-nonce probe failed for {genesis_wallet_address}; using sealed nonce "
            f"{sealed_nonce} — a concurrent mint can collide on the nonce slot"
        )
        return sealed_nonce
    return floor


def _treasury_transfer_tx(
    config,
    genesis_wallet_address: str,
    recipient: str,
    deposit_amount_ait: Decimal,
    chain_id,
    blockchain_rpc_url: str,
    deposit_id: str,
) -> str:
    """Sign and submit the treasury AIT transfer; return the tx hash."""
    import httpx

    sealed_nonce = _treasury_sender_nonce(genesis_wallet_address, blockchain_rpc_url)
    nonce = _treasury_next_nonce(genesis_wallet_address, sealed_nonce, chain_id, blockchain_rpc_url)

    # Build transaction payload for AIT transfer
    fee_ait = Decimal("0.01")
    amount_seconds = ait_to_units(deposit_amount_ait)
    fee_seconds = ait_to_units(fee_ait)

    tx_payload = {
        "type": "TRANSFER",
        "chain_id": chain_id,
        "from": genesis_wallet_address,
        "to": recipient,
        "amount": amount_seconds,
        "fee": fee_seconds,
        "nonce": nonce,
        # deposit_id binds the transfer to its deposit on-chain so a resumed
        # mint can find and adopt this submission instead of paying twice.
        "payload": {"amount": amount_seconds, "deposit_id": deposit_id},
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
    tx_hash: str | None = tx_result.get("transaction_hash")

    if not tx_hash:
        error(f"Transaction submitted but no hash returned: {tx_result}")
        raise click.Abort()
    return tx_hash


def _complete_mint(client: AITBCHTTPClient, deposit_id: str, tx_hash) -> None:
    complete_response = client.post(f"/v1/exchange/deposits/{deposit_id}/complete", json={"tx_hash": tx_hash})
    if complete_response.get("success"):
        return
    error(f"Failed to complete deposit: {complete_response}")
    raise click.Abort()


_MINT_SEAL_TIMEOUT_SECONDS = 300.0
_MINT_SEAL_POLL_SECONDS = 5.0


def _mint_chain_get(path: str, blockchain_rpc_url: str):
    """GET a chain RPC path; aborts when the answer cannot be trusted.

    The dedup and seal-wait probes are money-path reads: an unreadable
    answer cannot prove there is no earlier transfer, so the run stops
    rather than risk a second payment.
    """
    import httpx

    try:
        resp = httpx.get(f"{blockchain_rpc_url}{path}", timeout=10)
    except httpx.RequestError as e:
        error(f"Chain RPC unreachable at {blockchain_rpc_url}: {e}")
        raise click.Abort() from e
    if resp.status_code != 200:
        error(f"Chain RPC GET {path} failed: {resp.status_code} {resp.text[:200]}")
        raise click.Abort()
    return resp.json()


def _mint_tx_queries(deposit_id: str, sender: str, chain_id, blockchain_rpc_url: str) -> tuple[str | None, bool]:
    """``(sealed mint tx_hash | None, pending mint tx seen)`` for ``deposit_id``.

    Scans the sealed transaction table first, then the proposer mempool, both
        filtered client-side on ``payload.deposit_id`` — the binding the transfer
        itself carries (#2545/#2546).
    """
    query = f"?transaction_type=TRANSFER&sender={sender}&limit=100"
    if chain_id:
        query += f"&chain_id={chain_id}"
    sealed = _mint_chain_get(f"/rpc/transactions{query}", blockchain_rpc_url)
    for tx in sealed if isinstance(sealed, list) else []:
        if not isinstance(tx, dict):
            continue
        payload = tx.get("payload") or {}
        if payload.get("deposit_id") == deposit_id and tx.get("tx_hash"):
            return str(tx["tx_hash"]), True

    mempool_query = f"?limit=500{('&chain_id=' + str(chain_id)) if chain_id else ''}"
    mempool = _mint_chain_get(f"/rpc/mempool{mempool_query}", blockchain_rpc_url)
    pending = False
    for tx in (mempool.get("transactions") if isinstance(mempool, dict) else None) or []:
        if not isinstance(tx, dict):
            continue
        payload = tx.get("payload") or {}
        tx_sender = str(tx.get("from") or tx.get("sender") or "")
        if payload.get("deposit_id") == deposit_id and tx_sender.lower() == sender.lower():
            pending = True
            break
    return None, pending


def _prior_mint_tx_hash(deposit: dict, sender: str, chain_id, blockchain_rpc_url: str) -> str | None:
    """tx_hash of an earlier mint transfer for this deposit, if one exists.

    A ``ait_tx_hash`` already recorded on the row wins outright. Otherwise
    the chain is asked: a sealed match is adopted directly; a pending match
    means a previous run's transfer is still in flight — wait for it to seal
    or die rather than signing a second payment for the same deposit.
    """
    recorded = deposit.get("ait_tx_hash")
    if recorded:
        return str(recorded)

    deposit_id = str(deposit.get("id") or "")
    if not deposit_id:
        return None
    sealed_hash, pending_seen = _mint_tx_queries(deposit_id, sender, chain_id, blockchain_rpc_url)
    if sealed_hash:
        return sealed_hash
    if not pending_seen:
        return None

    deadline = time.monotonic() + _MINT_SEAL_TIMEOUT_SECONDS
    while True:
        if time.monotonic() >= deadline:
            error(
                f"An earlier mint transfer for deposit {deposit_id} is still pending after "
                f"{_MINT_SEAL_TIMEOUT_SECONDS:.0f}s; retry mint-ait later instead of risking a second payment"
            )
            raise click.Abort()
        time.sleep(_MINT_SEAL_POLL_SECONDS)
        sealed_hash, pending_seen = _mint_tx_queries(deposit_id, sender, chain_id, blockchain_rpc_url)
        if sealed_hash:
            return sealed_hash
        if not pending_seen:
            # Dropped from the mempool without sealing — safe to submit fresh.
            return None


def _wait_tx_sealed(tx_hash: str, config) -> None:
    """Block until the transfer is sealed before /complete runs (#2546):
    mempool admission is not payment — an unsealed hash can still die, and
    the deposit would read 'completed' for money that never landed."""
    import httpx

    chain_id = getattr(config, "chain_id", None)
    blockchain_rpc_url = getattr(config, "blockchain_rpc_url", "http://localhost:8202")
    query = f"?chain_id={chain_id}" if chain_id else ""
    deadline = time.monotonic() + _MINT_SEAL_TIMEOUT_SECONDS
    while True:
        try:
            resp = httpx.get(f"{blockchain_rpc_url}/rpc/transaction/{tx_hash}{query}", timeout=10)
        except httpx.RequestError as e:
            error(f"Chain RPC unreachable at {blockchain_rpc_url}: {e}")
            raise click.Abort() from e
        if resp.status_code == 200:
            body = resp.json() or {}
            if body.get("status") == "confirmed" and body.get("block_height") is not None:
                return
            if body.get("status") == "rejected":
                error(f"Mint transfer {tx_hash} was rejected on-chain; deposit left verified — investigate before re-running")
                raise click.Abort()
        elif resp.status_code != 404:
            error(f"Transaction lookup for {tx_hash} failed: {resp.status_code} {resp.text[:200]}")
            raise click.Abort()
        if time.monotonic() >= deadline:
            error(
                f"Mint transfer {tx_hash} did not seal within {_MINT_SEAL_TIMEOUT_SECONDS:.0f}s; "
                "deposit left verified — re-run mint-ait to resume"
            )
            raise click.Abort()
        time.sleep(_MINT_SEAL_POLL_SECONDS)


def _transfer_ait(
    config,
    deposit: dict,
    deposit_amount_ait: Decimal,
    recipient: str,
) -> str:
    """Return the tx hash paying the deposit's AIT amount to its recipient.

    Adopts an earlier submission for the same deposit — recorded on the row,
    sealed, or still pending — instead of signing a second payment, so a
    resumed run can never double-mint (#2545/#2546).
    """
    import httpx

    genesis_wallet_address = getattr(config, "genesis_wallet_address", "")
    chain_id = getattr(config, "chain_id", None)
    blockchain_rpc_url = getattr(config, "blockchain_rpc_url", "http://localhost:8202")
    deposit_id = str(deposit.get("id") or "")

    try:
        prior_hash = _prior_mint_tx_hash(deposit, genesis_wallet_address, chain_id, blockchain_rpc_url)
        if prior_hash:
            info(f"Reusing earlier mint transfer {prior_hash[:18]}… for this deposit")
            return prior_hash

        return _treasury_transfer_tx(
            config,
            genesis_wallet_address,
            recipient,
            deposit_amount_ait,
            chain_id,
            blockchain_rpc_url,
            deposit_id,
        )
    except httpx.RequestError as e:
        error(f"Network error contacting blockchain: {e}")
        raise click.Abort() from e
    except Exception as e:
        error(f"Error transferring AIT: {e}")
        raise click.Abort() from e


@exchange.command(
    name="mint-ait",
    epilog="""Examples:

  aitbc market exchange mint-ait --deposit-id dep-123

  aitbc market exchange mint-ait --deposit-id dep-123 --output json""",
)
@click.option("--deposit-id", "deposit_id", required=True, help="The Deposit id.")
@click.pass_context
def mint_ait(ctx, deposit_id: str):
    """Mint AIT tokens for a verified ETH deposit."""
    try:
        config = get_config()
        client = AITBCHTTPClient(base_url="http://localhost:8108", timeout=10, api_key=config.api_key)

        deposit = _mintable_deposit(client, deposit_id)
        deposit_amount_ait = Decimal(deposit.get("amount_ait", 0))

        if not _confirm_mint(deposit):
            info("Cancelled")
            return

        # Every fallible transfer precondition runs BEFORE the status flip:
        # verifying first and then failing on the key, the treasury account
        # or the submit used to strand the deposit at 'verified' with no way
        # to re-run (#2545). The deposit's own recipient is paid, never the
        # operator wallet (#2547).
        recipient = _mint_recipient(deposit)
        _treasury_preflight(config, deposit)

        _verify_deposit(client, deposit_id, deposit["status"])
        tx_hash = _transfer_ait(config, deposit, deposit_amount_ait, recipient)
        _wait_tx_sealed(tx_hash, config)
        _complete_mint(client, deposit_id, tx_hash)
        success(f"Transferred {deposit_amount_ait:.2f} AIT to {recipient} (tx: {tx_hash[:16]}...)")

    except NetworkError as e:
        error(f"Network error: {e}")
        raise click.Abort() from e
    except Exception as e:
        error(f"Error minting AIT: {e}")
        raise click.Abort() from e


@exchange.command(
    name="withdraw-eth",
    epilog="""Examples:

  aitbc market exchange withdraw-eth --amount 0.1 --address 0x...

  aitbc market exchange withdraw-eth --amount 0.1 --address 0x... --output json""",
)
@click.option("--amount", "amount", required=True, type=DECIMAL, help="Amount of AIT.")
@click.option("--address", "address", required=True, help="Blockchain address to fund.")
@click.pass_context
def withdraw_eth(ctx, amount: Decimal, address: str):
    """Withdraw ETH from the bridge wallet (admin only)."""
    try:
        config = get_config()

        if amount <= 0:
            error("Amount must be positive")
            raise click.Abort()

        info(f"Withdrawing {amount} ETH to {address}")

        if not click.confirm("Confirm withdrawal?"):
            info("Cancelled")
            return

        _execute_eth_withdrawal(config, amount, address)

    except Exception as e:
        error(f"Error withdrawing ETH: {e}")
        raise click.Abort() from e


def _execute_eth_withdrawal(config, amount: Decimal, address: str) -> None:
    """Send the ETH withdrawal via web3.py and record it in the exchange service."""
    try:
        import os

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

            _record_withdrawal(config, amount, address, tx_hash)
        else:
            error("Transaction failed")
            raise click.Abort()

    except ImportError:
        error("web3.py not installed. Install with: pip install web3")
        raise click.Abort() from None
    except Exception as e:
        error(f"Error withdrawing ETH: {e}")
        raise click.Abort() from e


def _record_withdrawal(config, amount: Decimal, address: str, tx_hash) -> None:
    """Record the completed withdrawal in the exchange service (best effort)."""
    import httpx

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
    except (httpx.HTTPError, OSError, ValueError, TypeError, AttributeError, RuntimeError) as record_e:
        warning(f"Withdrawal completed but failed to record: {record_e}")


@exchange.command(
    name="status",
    epilog="""Examples:

  aitbc market exchange status

  aitbc market exchange status --output json""",
)
@click.pass_context
def exchange_status(ctx):
    """Get the current bridge service status."""
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


@exchange.command(
    name="deposit-eth",
    epilog="""Examples:

  aitbc market exchange deposit-eth --amount 0.1

  aitbc market exchange deposit-eth --amount 0.1 --ait-address 0x...""",
)
@click.option("--amount", "amount", required=True, type=DECIMAL, help="Amount of AIT.")
@click.option("--ait-address", help="AIT address that will receive minted AIT (defaults to the sending wallet address)")
@click.option(
    "--bridge-address", default=None, help="Sepolia ETH bridge deposit address (default: BRIDGE_ETH_ADDRESS env var)"
)
@click.option("--gas", "gas_limit", default=30000, type=int, help="Gas limit for the deposit transaction")
@click.pass_context
def deposit_eth(ctx, amount: Decimal, ait_address: str | None, bridge_address: str | None, gas_limit: int):
    """Deposit Sepolia ETH to the bridge and mint AIT."""
    try:
        from web3 import Web3

        eth_rpc = EthereumRPCClient()
        w3 = eth_rpc._get_web3()

        # Validate every argument that needs no wallet BEFORE touching the wallet,
        # so a bad --bridge-address is refused the same way on every host instead
        # of dying on a missing default-wallet key first (#2115).
        if not bridge_address:
            bridge_address = os.environ.get("BRIDGE_ETH_ADDRESS")
        if not bridge_address:
            error("Bridge deposit address is required: set --bridge-address or BRIDGE_ETH_ADDRESS")
            raise click.Abort()
        if not Web3.is_address(bridge_address):
            error(f"Invalid bridge deposit address: {bridge_address}")
            raise click.Abort()
        if ait_address and not Web3.is_address(ait_address):
            error(f"Invalid AIT recipient address: {ait_address}")
            raise click.Abort()
        if amount <= 0:
            error("Amount must be greater than 0")
            raise click.Abort()

        wallet_name = ctx.obj.get("market_wallet")
        wallet_path = ctx.obj.get("market_wallet_path")
        password = ctx.obj.get("market_password")
        address, private_key, _ = load_wallet_for_payment(
            ctx,
            wallet_name=wallet_name,
            wallet_path=wallet_path,
            password=password,
            password_file=ctx.obj.get("market_password_file"),
            password_stdin=ctx.obj.get("market_password_stdin", False),
            require_private_key=True,
        )

        if not ait_address:
            ait_address = address

        value_wei = w3.to_wei(str(amount), "ether")
        gas_price = w3.eth.gas_price
        nonce = w3.eth.get_transaction_count(address, "pending")

        tx = {
            "nonce": nonce,
            "to": Web3.to_checksum_address(bridge_address),
            "value": value_wei,
            "gas": gas_limit,
            "gasPrice": gas_price,
            "chainId": 11155111,
            "data": Web3.to_checksum_address(ait_address),
        }
        signed = w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)

        success(f"Deposited {amount} Sepolia ETH to bridge {bridge_address}")
        info(f"Sepolia tx hash: {tx_hash.hex()}")
        info(f"AIT recipient: {Web3.to_checksum_address(ait_address)}")
        info("The bridge monitor will mint AIT once the deposit is confirmed.")

    except ImportError:
        error("web3.py not installed. Install with: pip install web3")
        raise click.Abort() from None
    except Exception as e:
        error(f"Error depositing ETH: {e}")
        raise click.Abort() from e
