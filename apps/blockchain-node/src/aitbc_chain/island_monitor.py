"""DEAD-ISLAND-GOSSIP-1 (#393): observation feeds, gauges and deferral.

Detection only. The monitor holds in-memory observation state (no
persistence — a restart re-derives within one poll window) and exposes
the two silence gauges plus the /v1/island/health payload. The deferral
helper gates offer-publish and job-submission pauses on an explicit
flag that defaults OFF.
"""

from __future__ import annotations

import os
import time
from typing import Any
from dataclasses import dataclass, field

from aitbc_chain.island_liveness import Tier, evaluate_island_state

ISLAND_DEFER_ENABLED = os.getenv("ISLAND_DEFER_ENABLED", "").lower() in ("1", "true", "yes")


def build_monitor_from_settings() -> IslandMonitor | None:
    """The monitor's single construction site. Returns None unless
    island_hub_proposer_id is configured — flag-off by construction: an
    unconfigured node takes no monitor path at all. validator_count reads
    len(VALIDATOR_SET) at call time, never an env constant."""
    from aitbc_chain.config import settings

    hub_id = (settings.island_hub_proposer_id or "").strip()
    if not hub_id:
        return None
    vals = [v for v in (settings.validator_set or "").split(",") if v.strip()]
    return IslandMonitor(
        beacon_interval=float(getattr(settings, "max_empty_block_interval", 60.0)),
        is_hub_self=(settings.proposer_id or "").lower() == hub_id.lower(),
        validator_count=len(vals) or 1,
    )


_hub_silence_gauge = 0.0
_gossip_silence_gauge = 0.0


def island_hub_silence_seconds() -> float:
    return _hub_silence_gauge


def island_gossip_silence_seconds() -> float:
    return _gossip_silence_gauge


@dataclass
class IslandMonitor:
    """Feeds evaluate_island_state from this node's own observations.

    Callers record events; `tick()` re-evaluates and refreshes the gauges
    and the health payload. validator_count reads len(VALIDATOR_SET) at
    call time, never an env constant.
    """

    beacon_interval: float
    is_hub_self: bool
    validator_count: int
    last_gossip_block_at: float = field(default_factory=time.monotonic)
    last_hub_observation_at: float = field(default_factory=time.monotonic)
    consecutive_missed_hub_slots: int = 0
    head_height: int = 0
    _last_eval_head: int = 0
    _tier: Tier = Tier.HEALTHY
    _deferred_logged: set = field(default_factory=set)

    def on_gossip_block(self, proposer_is_hub: bool) -> None:
        self.last_gossip_block_at = time.monotonic()
        if proposer_is_hub:
            self.last_hub_observation_at = self.last_gossip_block_at
            self.consecutive_missed_hub_slots = 0
        else:
            self.consecutive_missed_hub_slots += 1

    def on_hub_observation(self) -> None:
        self.last_hub_observation_at = time.monotonic()

    def tick(self, head_height: int) -> Tier:
        now = time.monotonic()
        global _hub_silence_gauge, _gossip_silence_gauge
        _hub_silence_gauge = now - self.last_hub_observation_at
        _gossip_silence_gauge = now - self.last_gossip_block_at
        self._tier = evaluate_island_state(
            seconds_since_gossip_block=_gossip_silence_gauge,
            seconds_since_hub_observation=_hub_silence_gauge,
            consecutive_missed_hub_slots=self.consecutive_missed_hub_slots,
            head_advancing=head_height > self._last_eval_head,
            self_is_hub=self.is_hub_self,
            validator_count=self.validator_count,
            beacon_interval=self.beacon_interval,
        )
        self._last_eval_head = head_height
        return self._tier

    def health(self) -> dict[str, Any]:
        return {
            "degraded": "none" if self._tier is Tier.HEALTHY else self._tier.value,
            "hub_silence_seconds": round(_hub_silence_gauge, 1),
            "gossip_silence_seconds": round(_gossip_silence_gauge, 1),
        }

    def defer_if_island_degraded(self, action: str) -> bool:
        """True when `action` should defer this cycle. Flag-gated: with
        ISLAND_DEFER_ENABLED unset/off this ALWAYS returns False — detection
        only, off changes nothing. When on and the tier is island-degraded,
        logs once per (action, tier) per monitor instance."""
        if not ISLAND_DEFER_ENABLED or self._tier is not Tier.ISLAND_DEGRADED:
            return False
        if action not in self._deferred_logged:
            self._deferred_logged.add(action)
        return True
