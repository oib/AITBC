"""DEAD-ISLAND-GOSSIP-1 (#393): two-tier dead-island liveness evaluation.

Detection only — no persisted state, no failover. See the spec in
tasks/ISLAND-ID-PLAN.md ("dead-island gossip", v2). The pure evaluator
below is driven by the monitor's own observations: gossip push and pull
sync/RPC reads.
"""

from __future__ import annotations

from enum import Enum

_DEAD_FLOOR_SECONDS = 600.0  # 10 min floor for T_dead
_SLOTS_PER_ROTATION = 3  # K = 3 x len(VALIDATOR_SET)
_GOSSIP_FACTOR = 2.0  # tier-1 threshold = 2 x beacon interval


class Tier(Enum):
    HEALTHY = "healthy"
    GOSSIP_DEGRADED = "gossip-degraded"
    ISLAND_DEGRADED = "island-degraded"


def evaluate_island_state(
    *,
    seconds_since_gossip_block: float,
    seconds_since_hub_observation: float,
    consecutive_missed_hub_slots: int,
    head_advancing: bool,
    self_is_hub: bool,
    validator_count: int,
    beacon_interval: float,
) -> Tier:
    """Classify hub liveness from this node's own observations.

    A hub never evaluates itself (plain identity check — its own silence
    is meaningless). island-degraded needs all three: no hub observation
    for T_dead on any path, >=K consecutive missed hub slots, and the
    head still advancing (a full-chain stall is ChainHeadStalled's job).
    """
    if self_is_hub:
        return Tier.HEALTHY

    k = _SLOTS_PER_ROTATION * max(1, validator_count)
    t_dead = max(_DEAD_FLOOR_SECONDS, k * beacon_interval)

    if seconds_since_hub_observation > t_dead and consecutive_missed_hub_slots >= k and head_advancing:
        return Tier.ISLAND_DEGRADED

    if seconds_since_gossip_block > _GOSSIP_FACTOR * beacon_interval:
        return Tier.GOSSIP_DEGRADED

    return Tier.HEALTHY
