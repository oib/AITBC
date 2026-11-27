"""Reward-pipeline enablement gate (#3058).

AUDIT-POOLHUB-REWARD-PIPELINE-1: ``enable_reward_distribution`` existed as a
settings flag that nothing ever read — the pipeline was dead scaffold, and
"just flip the flag" would have shipped every latent defect at once
(nonce collisions, no reconciliation, cross-replica double-pay, memory-only
shares, no finality gate, self-reported shares, wallet wipe).

This module is the fail-closed check the scheduler runs before starting:
flipping the flag with any blocker present refuses to start the loop and
logs the reasons. The pipeline stays dead by default AND stays dead when
misconfigured.
"""

from __future__ import annotations

import logging
import os
import socket

from ..settings import Settings

logger = logging.getLogger(__name__)


def reward_enablement_blockers(settings: Settings) -> list[str]:
    """Return every reason the reward pipeline must NOT run, or [] when safe.

    Checks are deliberately cheap and local — anything that cannot be
    verified here (e.g. whether a remote replica shares the payout DB) is
    covered by configuration requirements documented in settings.py.
    """
    blockers: list[str] = []

    if not settings.enable_reward_distribution:
        blockers.append("POOLHUB_ENABLE_REWARD_DISTRIBUTION is not set")

    # The payout signer is read from the environment by the client; an
    # unverifiable or mismatched key pair fails at sign time, so require
    # presence here and let submit-time verification do the rest.
    if not os.environ.get("POOL_REWARD_ADDRESS"):
        blockers.append("POOL_REWARD_ADDRESS is not set")
    if not os.environ.get("POOL_REWARD_PRIVATE_KEY"):
        blockers.append("POOL_REWARD_PRIVATE_KEY is not set")

    if settings.reward_finality_blocks < 1:
        blockers.append("POOLHUB_REWARD_FINALITY_BLOCKS must be >= 1")
    blockers.extend(_numeric_setting_blockers(settings))

    # Cross-replica single-writer: hub and hub1 both run pool-hub. The DB
    # advisory lock only excludes replicas sharing the payout database;
    # deployments with per-replica databases MUST pin the distributor to
    # one hostname so exactly one node can ever pay.
    pinned = settings.reward_distribution_node
    if pinned and socket.gethostname() != pinned:
        blockers.append(f"this node ({socket.gethostname()}) is not the pinned reward distributor ({pinned})")
    elif not pinned:
        # No machine-readable replica-count hint exists in settings, so
        # this cannot fail closed — but an unpinned enablement on a
        # multi-replica fleet with per-node databases is exactly the
        # double-pay topology the audit flagged. Warn loudly; the operator
        # must either pin POOLHUB_REWARD_DISTRIBUTION_NODE or confirm all
        # replicas share the payout DB (advisory lock covers that case).
        logger.warning(
            "Reward distribution enabled WITHOUT POOLHUB_REWARD_DISTRIBUTION_NODE: "
            "safe only if every pool-hub replica shares the payout database "
            "(advisory lock arbitrates). Per-node databases REQUIRE the pin."
        )

    return blockers


def _numeric_setting_blockers(settings: Settings) -> list[str]:
    """Respin hardening: every numeric knob that drives the money loop must
    be sane — a zero/negative value is never a valid operating point
    (poll interval <= 0 busy-loops the scheduler; min_age < 0 races
    in-flight submits; attempts < 1 disables the bound; submission cap
    < 1 would either block all payouts or, if misread, unbound the batch).
    """
    blockers: list[str] = []
    if settings.reward_poll_interval_seconds < 1:
        blockers.append("POOLHUB_REWARD_POLL_INTERVAL_SECONDS must be >= 1")
    if settings.reward_reconcile_min_age_seconds < 0:
        blockers.append("POOLHUB_REWARD_RECONCILE_MIN_AGE_SECONDS must be >= 0")
    if settings.reward_max_reconcile_attempts < 1:
        blockers.append("POOLHUB_REWARD_MAX_RECONCILE_ATTEMPTS must be >= 1")
    if settings.reward_max_submissions_per_cycle < 1:
        blockers.append("POOLHUB_REWARD_MAX_SUBMISSIONS_PER_CYCLE must be >= 1")
    return blockers
