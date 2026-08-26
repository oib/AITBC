"""Address canonicalization helpers for AITBC CLI.

The chain accepts multiple spellings of the same 20-byte address:
- EIP-55 checksummed ``0x...``
- lowercase ``0x...``
- legacy ``ait1...`` / ``aitbc1...`` prefixes

For most on-chain queries and transaction fields we want the same canonical
lowercase ``0x`` form that the node uses internally.  This module wraps the
chain's canonicaliser and provides a safe CLI-facing fallback.
"""

from aitbc.crypto.signature_recovery import canonical_address


def to_canonical(address: str) -> str:
    """Return the lowercase ``0x`` canonical form of an AITBC address.

    Accepts ``0x``, ``ait1``, or ``aitbc1`` spellings.  If the input cannot be
    canonicalised, it is returned lowercased and stripped; the caller should
    validate it separately.
    """
    try:
        return canonical_address(address)
    except Exception:
        return str(address).strip().lower()


def to_eip55(address: str) -> str:
    """Return the EIP-55 checksummed ``0x`` form of an address.

    This is the form expected by ``aitbc.utils.validation.validate_address``
    for ``0x`` inputs and is accepted by the blockchain RPC ``/rpc/account/...``
    endpoints.  Legacy ``ait1`` / ``aitbc1`` spellings are converted first.
    """
    from eth_utils import to_checksum_address

    canon = to_canonical(address)
    if canon.startswith("0x"):
        return to_checksum_address(canon)
    return canon


def is_canonical(address: str) -> bool:
    """Return True if ``address`` is already a 40-hex ``0x`` string."""
    lowered = address.strip().lower()
    return lowered.startswith("0x") and len(lowered) == 42
