"""Domain-separated attestation sign/verify helpers (#1950 pure-move split)."""

from __future__ import annotations

from __future__ import annotations
from __future__ import annotations

import sqlite3
from typing import Any

from sqlalchemy.exc import OperationalError

from aitbc.aitbc_logging import get_logger
from aitbc.crypto.consensus_signing import (
    sign_consensus_message,
    verify_consensus_message,
)
from aitbc.crypto.signature_recovery import canonical_address

from ..config import legacy_attestation_dual_accept_open, settings
from ..metrics import metrics_registry


def _attestation_domain_active(height: int | None) -> bool:
    """#1298: attestation signatures are domain-separated at/above the armed
    activation height; below it the legacy shared preimage stays authoritative."""
    activation = getattr(settings, "consensus_domain_separation_height", None)
    return activation is not None and height is not None and height >= activation


def _active_signature_domain(height: int | None, domain: str) -> str | None:
    """#1298: the domain tag for a signature minted at ``height`` — ``domain``
    at/above the armed activation height, else None (legacy shared preimage).

    The return value is stamped on evidence records as ``signature_domain``
    so on-chain verification rebuilds the exact preimage the signer used.
    """
    activation = getattr(settings, "consensus_domain_separation_height", None)
    if activation is None or height is None or height < activation:
        return None
    return domain


def _attestation_signature_domain(height: int | None) -> str | None:
    """#1298: the ``signature_domain`` an attestation signing at ``height`` is
    minted under — ``DOMAIN_BLOCK_ATTESTATION`` at/above the armed activation
    height, else None (legacy shared preimage). Used to key the in-memory and
    durable acceptance/dedup state so a proposal-domain and an
    attestation-domain signing of the same (height, hash) never collide."""
    if not _attestation_domain_active(height):
        return None
    from aitbc.crypto.consensus_signing import DOMAIN_BLOCK_ATTESTATION

    return DOMAIN_BLOCK_ATTESTATION


def _sign_attestation(message: dict[str, Any], private_key: str, height: int | None) -> str:
    if _attestation_domain_active(height):
        from aitbc.crypto.consensus_signing import DOMAIN_BLOCK_ATTESTATION, sign_consensus_message_domain

        return sign_consensus_message_domain(message, private_key, DOMAIN_BLOCK_ATTESTATION)
    return sign_consensus_message(message, private_key)


def _verify_attestation(message: dict[str, Any], signature: str, validator: str, height: int | None) -> bool:
    if _attestation_domain_active(height):
        from aitbc.crypto.consensus_signing import DOMAIN_BLOCK_ATTESTATION, verify_consensus_message_domain

        if verify_consensus_message_domain(message, signature, validator, DOMAIN_BLOCK_ATTESTATION):
            return True
        # #1298 dual-accept window [H, S): inside it a legacy shared-preimage
        # attestation signature still counts while the fleet converges; at
        # heights >= S (or with the window unset) it is rejected outright.
        # The accepted legacy signature is counted for the migration metric.
        if legacy_attestation_dual_accept_open(height) and verify_consensus_message(message, signature, validator):
            metrics_registry.increment("consensus_legacy_attestation_accepted_total")
            return True
        return False
    return verify_consensus_message(message, signature, validator)


def _attestation_message(header: dict[str, Any], chain_id: str, round_: int | None = None) -> dict[str, Any]:
    """The exact dict an attestation signature covers — shared by the domain
    and legacy verify paths. ``round`` is included whenever the caller passes
    it: under round-lock at any height, and unconditionally at/above the
    domain-separation height (#1298 T7a)."""
    message = {
        "chain_id": header.get("chain_id", chain_id),
        "height": header.get("height", 0),
        "hash": header.get("hash", ""),
        "parent_hash": header.get("parent_hash", ""),
        "proposer": header.get("proposer", ""),
        "state_root": header.get("state_root", ""),
        "bridge_state_root": header.get("bridge_state_root", ""),
    }
    if round_ is not None:
        message["round"] = round_
    return message


logger = get_logger(__name__)

# The v9 attestation check opens its own database session. A validator that
# cannot read its own state must not attest, but SQLite lock contention (a long
# writer on the same file) says nothing about the block: the whole check is
# retried once before it fails closed. The proposer waits
# ``multi_validator_attestation_timeout_seconds`` plus 0.5 s per missing
# attestation for answers, so one extra attempt still lands inside that window.
# #1245: heights of "already signed" memory kept when the tip cannot be read.
SIGNED_ONCE_MAX_HEIGHTS = 256
# #1278: deferred (off-loop) persistence of proposer-side equivocation evidence.
DEFERRED_SAVE_ATTEMPTS = 8
DEFERRED_SAVE_RETRY_DELAY = 1.0
DEFERRED_SAVE_RETRY_MAX_DELAY = 30.0
V9_CHECK_ATTEMPTS = 2
V9_CHECK_RETRY_DELAY_S = 0.5


def _is_transient_db_lock(exc: BaseException) -> bool:
    """True for SQLite's transient "database is locked" / "database is busy" errors."""
    if not isinstance(exc, (OperationalError, sqlite3.OperationalError)):
        return False
    message = str(exc).lower()
    return "database is locked" in message or "database is busy" in message


def _same_address(a: str, b: str) -> bool:
    """Compare two 0x EVM addresses (case-insensitive)."""
    return canonical_address(a) == canonical_address(b)


def _lock_lapse_seconds() -> float:
    """#1298 (design v2.2 O1 / v2.6): the effective attestation-lock lapse —
    proposer round window + header max-age + future skew (130s at defaults).
    An honest re-attestation after this window is guaranteed to land in a
    new derived round. The durable lock journal prunes at 2x this — the
    round-lock journal's "two windows" rule applied to the CORRECT window
    (v2.6 defect 1: pruning at 2x the 60s round would drop a record 10s
    before its 130s lock lapsed) — so a record is never dropped while its
    lock could still bind."""
    return (
        float(getattr(settings, "consensus_proposer_round_seconds", 60))
        + float(getattr(settings, "attestation_header_max_age_seconds", 60.0))
        + float(getattr(settings, "attestation_header_future_skew_seconds", 10.0))
    )


def attestation_lock_window_seconds(height: int | None) -> float:
    """#1298 T15 (design v2.2 proposer coupling, v2.6 single derived
    constant): the binding attestation-lock lapse window for signings at
    ``height``. Attester lock call sites AND the proposer suppression in
    ``_honor_attestation_lock`` both consume this one function so the two
    windows cannot drift.

    At/above the armed ``consensus_domain_separation_height`` the window is
    ``_lock_lapse_seconds()`` (round + header max-age + future skew = 130s
    at defaults): an honest re-attestation after it provably lands in a
    new derived round, so same-round multi-hash stays equivocation, period.
    Below the armed height the legacy ``consensus_proposer_round_seconds``
    window stays byte-identical — the 60→130s resize bundles into
    activation (design rollout), so pre-activation behaviour is
    replay-unchanged. The durable journal keeps pruning at 2x the lapse
    unconditionally: a longer keep is conservative, never a coverage hole.
    """
    if _attestation_domain_active(height):
        return _lock_lapse_seconds()
    return float(getattr(settings, "consensus_proposer_round_seconds", 60))
