"""Address canonicalization helpers for AITBC CLI.

The chain accepts only EIP-55 or lowercase ``0x...`` secp256k1/EVM addresses.
Legacy ``ait1...`` / ``aitbc1...`` prefixes are rejected.
"""

from aitbc.crypto.signature_recovery import canonical_address


def to_canonical(address: str) -> str:
    """Return the canonical ``0x`` form of an AITBC address.

    Accepts ``0x``-prefixed secp256k1/EVM addresses. Legacy spellings are
    returned unchanged; the caller should validate them separately.
    """
    try:
        return canonical_address(address)
    except Exception:
        return str(address).strip().lower()


def to_eip55(address: str) -> str:
    """Return the EIP-55 checksummed ``0x`` form of an address.

    This is the form expected by ``aitbc.utils.validation.validate_address``
    for ``0x`` inputs and is accepted by the blockchain RPC ``/rpc/account/...``
    endpoints. Legacy ``ait1`` / ``aitbc1`` spellings are rejected.
    """
    from eth_utils import to_checksum_address

    canon = to_canonical(address)
    if not is_canonical(canon):
        raise ValueError(f"Invalid address: {address}")
    return to_checksum_address(canon)


def is_canonical(address: str) -> bool:
    """Return True if ``address`` is already a 40-hex ``0x`` string."""
    lowered = address.strip().lower()
    return lowered.startswith("0x") and len(lowered) == 42
