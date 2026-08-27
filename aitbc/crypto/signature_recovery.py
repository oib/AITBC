"""Canonical secp256k1 signature recovery for AITBC (V23-01 … V23-05).

Every ECDSA recovery in this repository goes through this module. There were nine
independent implementations; eight of them constructed ``eth_keys.Signature(sig_bytes)``
directly, and that constructor requires a recovery id of 0 or 1 while every standard
Ethereum signer — including this repo's own ``sign_transaction_hash`` — emits 27 or 28.
``eth_keys`` raised ``BadSignature`` and a broad ``except Exception`` turned it into
"signature invalid", so correctly signed messages were rejected across the RPC path, the
bridge validator, dispute evidence and consensus.

Two things follow from that history, and both are deliberate here.

**Parse failure is not verification failure.** A signature that cannot be decoded is an
encoding fault or a bug; a signature that decodes and recovers to the wrong address is a
failed check, or an attack. The original code could not tell them apart, so a node
rejecting every honest block and a node under attack produced the same log line
(V23-04). :func:`recover_address` raises :class:`SignatureMalformed` for the first and
returns an address for the second, leaving the caller to decide how loudly to complain.

**One implementation, not nine.** ``tests/security/test_signature_recovery_is_canonical.py``
fails if ``keys.Signature(`` appears anywhere outside this file, so a tenth copy cannot be
added quietly (V23-05).
"""

from __future__ import annotations

import re
from typing import Final

# Ethereum encodes the recovery id as 27 or 28 (or 35+ for EIP-155 chain-bound
# signatures). eth_keys wants the raw 0 or 1.
_ETH_RECOVERY_OFFSET: Final = 27
SIGNATURE_LENGTH: Final = 65


class SignatureMalformed(ValueError):
    """The signature could not be decoded — an encoding fault, not a failed check.

    Raised for a wrong length, non-hex characters, or a recovery id that is not 0/1
    after normalisation. It deliberately does not cover "recovered a different address",
    which is a verification result rather than a malformed input.
    """


def normalize_signature(signature: str | bytes) -> bytes:
    """Return ``signature`` as 65 raw bytes with the recovery id reduced to 0 or 1.

    Accepts a hex string with or without a ``0x`` prefix, or raw bytes.

    Raises:
        SignatureMalformed: If the input is not 65 bytes of valid hex, or if the
            recovery id is not 0 or 1 once the Ethereum offset is removed.
    """
    if isinstance(signature, str):
        try:
            sig_bytes = bytes.fromhex(signature.removeprefix("0x"))
        except ValueError as e:
            raise SignatureMalformed(f"signature is not valid hex: {e}") from e
    else:
        sig_bytes = bytes(signature)

    if len(sig_bytes) != SIGNATURE_LENGTH:
        raise SignatureMalformed(f"signature must be {SIGNATURE_LENGTH} bytes, got {len(sig_bytes)}")

    recovery_id = sig_bytes[64]
    if recovery_id >= _ETH_RECOVERY_OFFSET:
        recovery_id -= _ETH_RECOVERY_OFFSET
    if recovery_id not in (0, 1):
        raise SignatureMalformed(f"recovery id {sig_bytes[64]} is not 0/1 or 27/28")

    return sig_bytes[:64] + bytes([recovery_id])


def recover_address(msg_hash: bytes, signature: str | bytes) -> str:
    """Recover the checksum address that signed ``msg_hash``.

    Args:
        msg_hash: The 32-byte digest that was signed.
        signature: 65-byte ``r‖s‖v`` signature, hex or raw bytes.

    Returns:
        The recovered address, EIP-55 checksummed.

    Raises:
        SignatureMalformed: If the signature cannot be decoded or recovery fails.
            Recovery failing is itself a malformed-input condition: a well-formed
            signature over a 32-byte hash always yields some public key, so a failure
            here means the inputs were not what they claimed to be.
    """
    from eth_keys import keys
    from eth_keys.exceptions import BadSignature, ValidationError

    sig_bytes = normalize_signature(signature)
    try:
        sig = keys.Signature(sig_bytes)
        pub_key = sig.recover_public_key_from_msg_hash(msg_hash)
    except (BadSignature, ValidationError) as e:
        raise SignatureMalformed(f"could not recover public key: {e}") from e
    return str(pub_key.to_checksum_address())


_EVM_ADDRESS_RE: Final = re.compile(r"^0x[0-9a-fA-F]{40}$")


def canonical_address(address: str) -> str:
    """Normalize an address to the EIP-55 checksummed 0x form used for comparison.

    Valid secp256k1/EVM addresses (``0x`` + 40 hex) are returned as EIP-55 checksum
    addresses. Anything else — including the legacy ``ait1`` and ``aitbc1`` prefixes —
    is returned unchanged (lower-cased). This means legacy spellings no longer compare
    equal to their 0x counterpart, effectively rejecting them at comparison boundaries
    without raising in the middle of consensus code.
    """
    from eth_utils import to_checksum_address

    value = address.strip()
    lowered = value.lower()
    if _EVM_ADDRESS_RE.fullmatch(lowered):
        return to_checksum_address(lowered)
    return lowered


def verify_signature(msg_hash: bytes, signature: str | bytes, expected_address: str) -> bool:
    """Return True iff ``signature`` over ``msg_hash`` recovers to ``expected_address``.

    Address comparison is case-insensitive for valid ``0x`` secp256k1/EVM addresses,
    because :func:`canonical_address` returns the EIP-55 form. Legacy ``ait1``/``aitbc1``
    spellings are not accepted and will not compare equal to their ``0x`` counterpart.

    Raises:
        SignatureMalformed: If the signature cannot be decoded. Callers that want a
            plain boolean for every input should catch it — and log it differently from
            a False return, which is the whole point of the distinction.
    """
    if not signature or not expected_address:
        return False
    recovered = recover_address(msg_hash, signature)
    return canonical_address(recovered) == canonical_address(expected_address)
