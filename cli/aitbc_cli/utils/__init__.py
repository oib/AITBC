"""CLI utility functions for output formatting and error handling."""

# Output helpers first: they are used by error_handling and most other utils,
# so they must be defined before any module that imports error_handling is loaded.
from .output import (
    OUTPUT_FORMAT_OPTION,
    decode_value,
    encode_value,
    error,
    info,
    output,
    resolve_output_format,
    setup_logging,
    success,
    warning,
)

# Core helper modules (error_handling is safe once output symbols are exported)
from . import address, blockchain, chain_id, escrow, island_credentials, wallet, wallet_loader
from .address import is_canonical, to_canonical
from .blockchain import get_blockchain_analytics, get_chain_info, get_network_status
from .escrow import (
    build_escrow_lock_tx,
    create_signed_escrow_lock,
    get_buyer_nonce,
    get_node_wallet,
    sign_escrow_lock_tx,
)
from .money import DECIMAL, DecimalParamType, wallet_amount
from .wallet_loader import load_wallet_for_payment
from .wallet import decrypt_private_key


__all__ = [
    "DECIMAL",
    "DecimalParamType",
    "wallet_amount",
    "output",
    "error",
    "success",
    "info",
    "warning",
    "encode_value",
    "decode_value",
    "setup_logging",
    "wallet",
    "blockchain",
    "chain_id",
    "island_credentials",
    "decrypt_private_key",
    "get_chain_info",
    "get_network_status",
    "get_blockchain_analytics",
    "to_canonical",
    "is_canonical",
    "load_wallet_for_payment",
    "build_escrow_lock_tx",
    "sign_escrow_lock_tx",
    "create_signed_escrow_lock",
    "get_node_wallet",
    "get_buyer_nonce",
    "resolve_output_format",
    "OUTPUT_FORMAT_OPTION",
]
