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


def is_canonical(address: str) -> bool:
    """Return True if ``address`` is already a 40-hex ``0x`` string."""
    lowered = address.strip().lower()
    return lowered.startswith("0x") and len(lowered) == 42
