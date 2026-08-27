"""Prove a node can sign as the identity it declares, before it produces anything.

The deployed hub signed 12,353 blocks as the legacy `0xDb5247d03cA2e40f3995A583b2C097Ab703efD4d` spelling using a key
that controls `0xFe2d63FE…`, then produced block 105,627 with no signature at all. Nothing
raised: the keystore matched files on the `address` field they declared rather than the
address their key derives to, and a failed key load logged a warning and let start-up continue.

Both faults are unrecoverable once written, because the chain commits to them. Every
validating follower stalls at the first bad block forever, and the only remedy is manual
database surgery on each one (`scripts/ops/backfill-follower-gap.sh`). A node that refuses
to start is a five-minute fix; a chain with an unverifiable range in the middle is not.

So the check runs at the moment production actually begins, not at import: a node that
never proposes is never blocked by it.
"""

from __future__ import annotations

from pathlib import Path

from aitbc.crypto.signature_recovery import canonical_address

from .logger import get_logger

logger = get_logger(__name__)


def address_of(private_key_hex: str) -> str:
    """Return the secp256k1 address ``private_key_hex`` actually controls."""
    from eth_keys import keys

    return str(keys.PrivateKey(bytes.fromhex(private_key_hex.removeprefix("0x"))).public_key.to_checksum_address())


def assert_can_sign(proposer_id: str, proposer_key: str | None, keystore_path: Path | None = None) -> None:
    """Raise unless this node holds the key for ``proposer_id``.

    Args:
        proposer_id: The identity blocks will declare.
        proposer_key: Hex private key the node loaded, if any.
        keystore_path: Where keys were looked for, named in the error to make it actionable.

    Raises:
        RuntimeError: If the proposer id is empty, no key was loaded, or the key controls
            a different address.
    """
    where = f" Checked {keystore_path}." if keystore_path else ""

    if not proposer_id:
        raise RuntimeError(
            "Block production is enabled but PROPOSER_ID is empty. Refusing to start: this node would "
            "append blocks with no declared proposer."
        )

    if not proposer_key:
        raise RuntimeError(
            f"Block production is enabled but no usable signing key was found for proposer {proposer_id}. "
            f"Refusing to start: this node would append unsigned blocks that no peer can verify, and the "
            f"chain would commit to them permanently.{where} If a keystore file was rejected as mislabelled, "
            f"the reason is logged above."
        )

    controls = address_of(proposer_key)
    if canonical_address(controls) != canonical_address(proposer_id):
        raise RuntimeError(
            f"Proposer key mismatch: PROPOSER_ID is {proposer_id} but the loaded key controls {controls}. "
            f"Refusing to start: every block this node signed would declare an address it cannot prove, and "
            f"no validating peer could import any of them. Set PROPOSER_ID to {controls}, or supply the key "
            f"for {proposer_id}.{where}"
        )

    logger.info("Proposer key verified against declared identity", extra={"proposer_id": proposer_id})
