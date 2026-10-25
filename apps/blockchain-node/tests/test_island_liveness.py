"""DEAD-ISLAND-GOSSIP-1 (#393): two-tier dead-island detection.

Spec (ISLAND-ID-PLAN.md, "dead-island gossip", A's v2):
- tier 1 `gossip-degraded`: no gossip block for 2 x max_empty_block_interval
  while pull sync still answers. Warn + metric only, no state change.
- tier 2 `island-degraded`: ALL of — no hub observation for T_dead on any
  path; zero hub-proposed blocks for K consecutive expected slots
  (K = 3 x len(VALIDATOR_SET), read at runtime); head still advancing.
- T_dead = max(10 min, K x max_empty_block_interval).
- The hub never evaluates itself (plain proposer-id identity check).
- Detection only: no persisted state, no failover.
"""

from aitbc_chain.island_liveness import Tier, evaluate_island_state

BEACON = 60.0  # max_empty_block_interval seconds


def _state(**kw):
    base = {
        "seconds_since_gossip_block": 0.0,
        "seconds_since_hub_observation": 0.0,
        "consecutive_missed_hub_slots": 0,
        "head_advancing": True,
        "self_is_hub": False,
        "validator_count": 4,
        "beacon_interval": BEACON,
    }
    base.update(kw)
    return base


def test_healthy_when_hub_observed():
    assert evaluate_island_state(**_state()) is Tier.HEALTHY


def test_gossip_degraded_when_only_push_path_silent():
    # gossip quiet for >2 intervals, pull still answering (hub observed)
    assert evaluate_island_state(**_state(seconds_since_gossip_block=125)) is Tier.GOSSIP_DEGRADED


def test_gossip_silence_under_threshold_is_healthy():
    assert evaluate_island_state(**_state(seconds_since_gossip_block=119)) is Tier.HEALTHY


def test_island_degraded_needs_all_three_conditions():
    # silence long enough + K missed slots + head advancing -> degraded
    s = _state(
        seconds_since_gossip_block=900,
        seconds_since_hub_observation=900,
        consecutive_missed_hub_slots=12,  # K = 3 x 4
        head_advancing=True,
    )
    assert evaluate_island_state(**s) is Tier.ISLAND_DEGRADED


def test_head_stalled_is_not_island_degraded():
    # dead-island must not double-fire on a full-chain stall
    s = _state(
        seconds_since_gossip_block=900,
        seconds_since_hub_observation=900,
        consecutive_missed_hub_slots=12,
        head_advancing=False,
    )
    assert evaluate_island_state(**s) is not Tier.ISLAND_DEGRADED


def test_missing_slots_below_K_is_not_island_degraded():
    s = _state(seconds_since_hub_observation=900, consecutive_missed_hub_slots=11)
    assert evaluate_island_state(**s) is not Tier.ISLAND_DEGRADED


def test_t_dead_floor_binds_small_validator_sets():
    # K=3x2=6 -> K*60=360s < 600s floor: 500s silence must NOT be island-degraded
    s = _state(
        seconds_since_gossip_block=500,
        seconds_since_hub_observation=500,
        consecutive_missed_hub_slots=6,
        validator_count=2,
    )
    assert evaluate_island_state(**s) is not Tier.ISLAND_DEGRADED


def test_hub_never_evaluates_itself():
    # identity skip: a hub observing silence reports HEALTHY/not-applicable
    s = _state(self_is_hub=True, seconds_since_hub_observation=9999, consecutive_missed_hub_slots=99)
    assert evaluate_island_state(**s) is Tier.HEALTHY


def test_follower_still_evaluates():
    s = _state(self_is_hub=False, seconds_since_hub_observation=900, consecutive_missed_hub_slots=12)
    assert evaluate_island_state(**s) is Tier.ISLAND_DEGRADED


# ── monitor / gauges / deferral (#393 remaining surface) ──────────────


def _monitor(**kw):
    from aitbc_chain.island_monitor import IslandMonitor

    base = {"beacon_interval": 60.0, "is_hub_self": False, "validator_count": 4}
    base.update(kw)
    return IslandMonitor(**base)


def test_health_payload_reports_tier_and_silence():
    m = _monitor()
    m.tick(100)
    h = m.health()
    assert h["degraded"] == "none"
    assert h["hub_silence_seconds"] >= 0 and h["gossip_silence_seconds"] >= 0


def test_gauges_refresh_on_tick():
    import time as _t
    from aitbc_chain import island_monitor as im

    m = _monitor()
    m.last_hub_observation_at = _t.monotonic() - 30
    m.tick(100)
    assert im.island_hub_silence_seconds() >= 30


def test_defer_off_by_default_changes_nothing(monkeypatch):
    monkeypatch.delenv("ISLAND_DEFER_ENABLED", raising=False)
    import importlib
    from aitbc_chain import island_monitor as im

    importlib.reload(im)
    m = im.IslandMonitor(beacon_interval=60.0, is_hub_self=False, validator_count=4)
    m._tier = im_island_degraded()
    assert m.defer_if_island_degraded("offer-publish") is False


def im_island_degraded():
    from aitbc_chain.island_liveness import Tier

    return Tier.ISLAND_DEGRADED


def test_defer_only_when_flag_on_and_island_degraded(monkeypatch):
    monkeypatch.setenv("ISLAND_DEFER_ENABLED", "true")
    import importlib
    from aitbc_chain import island_monitor as im

    importlib.reload(im)
    m = im.IslandMonitor(beacon_interval=60.0, is_hub_self=False, validator_count=4)
    from aitbc_chain.island_liveness import Tier

    m._tier = Tier.GOSSIP_DEGRADED
    assert m.defer_if_island_degraded("offer-publish") is False  # tier1 never defers
    m._tier = Tier.ISLAND_DEGRADED
    assert m.defer_if_island_degraded("offer-publish") is True
    assert m.defer_if_island_degraded("job-submit") is True
    monkeypatch.delenv("ISLAND_DEFER_ENABLED", raising=False)
    importlib.reload(im)


# ── call-site wiring (#393): flag-off changes nothing ─────────────────


def test_monitor_off_when_hub_id_unset(monkeypatch):
    from aitbc_chain import config

    monkeypatch.setattr(config.settings, "island_hub_proposer_id", "", raising=False)
    from aitbc_chain.island_monitor import build_monitor_from_settings

    assert build_monitor_from_settings() is None


def test_monitor_built_when_hub_id_set(monkeypatch):
    from aitbc_chain import config

    monkeypatch.setattr(config.settings, "island_hub_proposer_id", "0xHUB", raising=False)
    monkeypatch.setattr(config.settings, "validator_set", "0xHUB,0xA,0xB,0xC", raising=False)
    monkeypatch.setattr(config.settings, "proposer_id", "0xA", raising=False)
    from aitbc_chain.island_monitor import build_monitor_from_settings

    m = build_monitor_from_settings()
    assert m is not None and m.validator_count == 4 and m.is_hub_self is False


def test_monitor_identity_skip_for_hub(monkeypatch):
    from aitbc_chain import config

    monkeypatch.setattr(config.settings, "island_hub_proposer_id", "0xHUB", raising=False)
    monkeypatch.setattr(config.settings, "validator_set", "0xHUB,0xA", raising=False)
    monkeypatch.setattr(config.settings, "proposer_id", "0xHUB", raising=False)
    from aitbc_chain.island_monitor import build_monitor_from_settings

    assert build_monitor_from_settings().is_hub_self is True


def test_sync_manager_health_shape_off(monkeypatch):
    from aitbc_chain.sync_manager import SyncManager

    m = SyncManager(chains=[], use_gossip=False, use_subscription=False)
    if m._island_monitor is None:
        assert m.island_health()["degraded"] == "monitor-off"
    else:
        assert "degraded" in m.island_health()
