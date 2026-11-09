"""#1301 L2: proposer-signed abandon statement.

When a proposer misses attestation quorum and drops its candidate block, the
validators that already voted for it stay journal-locked to a hash nobody will
ever seal (#1268), blocking every fresh-hash retry until the 300 s valve plus
an unavailability certificate. The proposer can say so itself: it signs
``abandon(chain, height, hash, round, proposer)``. A voter whose journal holds
an attest vote for exactly that hash *from that proposer* may release it --
the only party able to seal the hash has signed that it will not. A later seal
of the same hash by that proposer is equivocation evidence, not a new fork
class.

Default OFF (``vote_journal_abandon_enabled``); every function here is inert
without the flag.
"""

from __future__ import annotations

from typing import Any

from aitbc.crypto.consensus_signing import (
    DOMAIN_BLOCK_ABANDON,
    sign_consensus_message,
    sign_consensus_message_domain,
    verify_consensus_message,
    verify_consensus_message_domain,
)
from aitbc.crypto.signature_recovery import canonical_address

KIND = "abandon"


def abandon_topic(chain_id: str) -> str:
    return f"consensus.abandon.{chain_id}"


def abandon_enabled() -> bool:
    from ..config import settings

    return bool(getattr(settings, "vote_journal_abandon_enabled", False)) and bool(
        getattr(settings, "vote_journal_enabled", False)
    )


def _domain_active(height: int) -> bool:
    """#1298: at/above ``consensus_domain_separation_height`` the abandon
    statement is signed under its own domain (hard cutover, like attestations);
    below it the legacy preimage stays authoritative."""
    from ..config import settings

    activation = getattr(settings, "consensus_domain_separation_height", None)
    return activation is not None and height >= activation


def _message(chain_id: str, height: int, block_hash: str, round_: int | None, proposer: str) -> dict[str, Any]:
    return {
        "kind": KIND,
        "chain_id": chain_id,
        "height": int(height),
        "hash": block_hash,
        "round": round_,
        "proposer": canonical_address(proposer),
    }


def build_abandon(
    chain_id: str, height: int, block_hash: str, round_: int | None, proposer: str, private_key: str
) -> dict[str, Any]:
    msg = _message(chain_id, height, block_hash, round_, proposer)
    if _domain_active(int(height)):
        return {**msg, "signature": sign_consensus_message_domain(msg, private_key, DOMAIN_BLOCK_ABANDON)}
    return {**msg, "signature": sign_consensus_message(msg, private_key)}


def verify_abandon(chain_id: str, payload: Any) -> dict[str, Any] | None:
    """The validated statement fields, or None for anything malformed or forged."""
    if not isinstance(payload, dict) or payload.get("kind") != KIND or payload.get("chain_id") != chain_id:
        return None
    try:
        height = int(payload["height"])
        block_hash = str(payload["hash"])
        proposer = str(payload["proposer"])
        round_ = payload.get("round")
        round_ = int(round_) if round_ is not None else None
        msg = _message(chain_id, height, block_hash, round_, proposer)
        if not block_hash:
            return None
        signature = str(payload.get("signature", ""))
        if _domain_active(height):
            ok = verify_consensus_message_domain(msg, signature, proposer, DOMAIN_BLOCK_ABANDON)
        else:
            ok = verify_consensus_message(msg, signature, proposer)
        if not ok:
            return None
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    return msg
