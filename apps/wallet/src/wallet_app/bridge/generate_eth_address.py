#!/usr/bin/env python3
"""Generate Ethereum wallet address for ETH-AIT bridge."""

from eth_account import Account

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


def generate_eth_address() -> tuple[str, str]:
    """Generate a new Ethereum address and private key.

    Returns:
        Tuple of (address, private_key_hex). The private key is returned
        to the caller; this function never logs or prints it.
    """
    # Enable mnemonic features
    Account.enable_unaudited_hdwallet_features()

    # Create new account
    account = Account.create()

    address = account.address
    private_key = account.key.hex()

    logger.info("Generated Ethereum wallet address: %s", address)
    logger.warning(
        "Store the private key securely, add the address to "
        "/etc/aitbc/exchange.env as ETH_WALLET_ADDRESS, and fund it with ETH."
    )

    return address, private_key


if __name__ == "__main__":
    generate_eth_address()
