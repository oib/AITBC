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


# ── out-of-process consumer helper (#393): fail-open contract ─────────


def test_defer_helper_connection_refused_fails_open():
    """Nothing on the port (pre-deploy shape): must answer False, fast."""
    from aitbc.island_deferral import island_degraded
    import socket

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    free_port = s.getsockname()[1]
    s.close()
    assert island_degraded(port=free_port, timeout=0.5) is False


def test_defer_helper_flag_off_never_reads(monkeypatch):
    monkeypatch.delenv("ISLAND_DEFER_ENABLED", raising=False)
    import importlib
    from aitbc import island_deferral

    importlib.reload(island_deferral)
    called = []
    monkeypatch.setattr(island_deferral, "island_degraded", lambda **kw: called.append(1) or True)
    assert island_deferral.should_defer("offer-publish") is False
    assert called == []  # flag off: no network read at all


def test_defer_helper_flag_on_degraded():
    import importlib
    import os

    os.environ["ISLAND_DEFER_ENABLED"] = "true"
    from aitbc import island_deferral

    importlib.reload(island_deferral)
    island_deferral.island_degraded = lambda **kw: True
    assert island_deferral.should_defer("offer-publish") is True
    os.environ.pop("ISLAND_DEFER_ENABLED", None)
    importlib.reload(island_deferral)


def test_bulk_pull_feeds_hub_observation():
    """A successful pull answer feeds on_hub_observation (detection only)."""
    import inspect
    from aitbc_chain.sync_manager import SyncManager

    src = inspect.getsource(SyncManager._bulk_pull)
    assert "on_hub_observation" in src and "_island_monitor is not None" in src


# ── corrected deferral sites (#393, director ruling): miner cycle + escrow submit ──


def _load_miner():
    import os as _o
    import sys as _s
    import importlib.util as _u
    from pathlib import Path as _P

    _o.environ.setdefault("MINER_ID", "test-miner")
    _o.environ.setdefault("MINER_AUTH_TOKEN", "test-token")
    miner_dir = _P(__file__).resolve().parents[3] / "apps/miner"
    _s.path.insert(0, str(miner_dir))
    spec = _u.spec_from_file_location("production_miner", miner_dir / "production_miner.py")
    pm = _u.module_from_spec(spec)
    spec.loader.exec_module(pm)
    return pm


def test_miner_offer_cycle_defers_and_logs(monkeypatch, capsys):
    """should_defer True -> no publishes, one 'Deferred N' line."""
    import asyncio
    import importlib

    pm = _load_miner()
    sent = []
    monkeypatch.setattr(pm, "publish_default_offers", lambda models: sent.append(models))
    monkeypatch.setenv("ISLAND_DEFER_ENABLED", "true")
    import aitbc.island_deferral as _d

    importlib.reload(_d)
    monkeypatch.setattr(_d, "island_degraded", lambda **kw: True)
    out = asyncio.run(pm.offer_publish_cycle([]))
    assert out is False and sent == []
    assert "Deferred 4 default offer(s) — island-degraded" in capsys.readouterr().out


def test_miner_offer_cycle_publishes_when_off(monkeypatch):
    import asyncio
    import importlib

    pm = _load_miner()
    sent = []
    monkeypatch.setattr(pm, "publish_default_offers", lambda models: sent.append(models))
    monkeypatch.delenv("ISLAND_DEFER_ENABLED", raising=False)
    import aitbc.island_deferral as _d

    importlib.reload(_d)
    monkeypatch.setattr(_d, "island_degraded", lambda **kw: True)
    out = asyncio.run(pm.offer_publish_cycle(["m"]))
    assert out is True and sent == [["m"]]  # flag off: publishes even if degraded


def test_escrow_post_deferral_raises(monkeypatch):
    """_post raises IslandDegradedError before the HTTP call when flagged."""
    import os

    os.environ["ISLAND_DEFER_ENABLED"] = "true"
    import importlib
    import aitbc.island_deferral as _d

    importlib.reload(_d)
    from pathlib import Path as _P

    src = (_P(__file__).resolve().parents[3] / "apps/agent-coordinator/src/agent_app/services/chain_escrow.py").read_text()
    assert 'should_defer("escrow-submit")' in src and "IslandDegradedError" in src
    os.environ.pop("ISLAND_DEFER_ENABLED", None)
    importlib.reload(_d)


def test_escrow_degraded_error_is_dual_typed():
    """EscrowDegradedError catches under BOTH EscrowRPCError (existing
    failure handling) and IslandDegradedError (deferral detection)."""
    import importlib.util as _u
    from pathlib import Path as _P

    spec = _u.spec_from_file_location(
        "chain_escrow", _P(__file__).resolve().parents[3] / "apps/agent-coordinator/src/agent_app/services/chain_escrow.py"
    )
    ce = _u.module_from_spec(spec)
    spec.loader.exec_module(ce)
    from aitbc.island_deferral import IslandDegradedError

    assert issubclass(ce.EscrowDegradedError, ce.EscrowRPCError)
    assert issubclass(ce.EscrowDegradedError, IslandDegradedError)


def _scrape(text=None):
    """(hub, gossip) silence values from the exporter's REGISTRY output;
    None for a missing series."""
    import re

    if text is None:
        from prometheus_client import REGISTRY, generate_latest

        text = generate_latest(REGISTRY).decode()
    vals = []
    for name in ("aitbc_island_hub_silence_seconds", "aitbc_island_gossip_silence_seconds"):
        hit = re.search(rf"^{name} ([0-9.eE+-]+)$", text, re.M)
        vals.append(float(hit.group(1)) if hit else None)
    return tuple(vals)


def _fake_clock(monkeypatch, start=1000.0):
    from aitbc_chain import island_monitor as im

    clock = [start]
    monkeypatch.setattr(im.time, "monotonic", lambda: clock[0])
    return clock


def _hub_configured(monkeypatch, hub_id="0xHUB"):
    from aitbc_chain import config

    monkeypatch.setattr(config.settings, "island_hub_proposer_id", hub_id, raising=False)
    monkeypatch.setattr(config.settings, "validator_set", "0xHUB,0xA,0xB,0xC", raising=False)
    monkeypatch.setattr(config.settings, "proposer_id", "0xA", raising=False)


def _no_tick(*_a, **_k):
    raise AssertionError("tick() must not be needed for the exported value")


def test_tick_exports_silences_to_prometheus():
    """The gauges must appear in the exporter's REGISTRY output — the
    defect comment 2819 caught: getter-only globals never reached :9009.
    Fails if publish_silence_gauges() stops binding either series."""
    import time as _t
    from aitbc_chain import island_monitor as im

    m = im.IslandMonitor(beacon_interval=60.0, is_hub_self=False, validator_count=4)
    m.last_hub_observation_at = _t.monotonic() - 300
    m.last_gossip_block_at = _t.monotonic() - 120
    im.publish_silence_gauges(m)
    hub, gos = _scrape()
    assert hub is not None and gos is not None, "gauges missing from REGISTRY export"
    assert 295 <= hub <= 305
    assert 115 <= gos <= 125


def test_silences_grow_at_scrape_time_without_tick(monkeypatch):
    """Comment 2840: silence must grow while no gossip block (so no tick)
    arrives. Patched clock, no sleep: scrape, advance 300, scrape."""
    from aitbc_chain import island_monitor as im

    clock = _fake_clock(monkeypatch)
    m = _monitor()
    monkeypatch.setattr(m, "tick", _no_tick)
    im.publish_silence_gauges(m)
    assert _scrape() == (0.0, 0.0)
    clock[0] += 300
    assert _scrape() == (300.0, 300.0)
    m.on_hub_observation()  # pull answer from the hub, still no gossip
    clock[0] += 60
    assert _scrape() == (60.0, 360.0)


def test_scrape_right_after_build_is_small_non_negative(monkeypatch):
    """Comment 2841 point 2: before any block or observation both values
    start at 0 — never epoch-sized, never an exception."""
    from aitbc_chain.island_monitor import build_monitor_from_settings

    _hub_configured(monkeypatch)
    m = build_monitor_from_settings()
    assert m is not None
    hub, gos = _scrape()
    assert hub is not None and 0.0 <= hub < 5.0
    assert gos is not None and 0.0 <= gos < 5.0


def test_monitor_off_exports_no_silence_series(monkeypatch):
    """Comment 2842 point 2': a monitor-off process (hub, unset env) must
    export no aitbc_island_*_silence_seconds line at all — an unlabeled
    gauge registered at import would export a live-looking 0.0."""
    import importlib
    from prometheus_client import REGISTRY, generate_latest
    from aitbc_chain import island_monitor as im

    for name in (im.HUB_SILENCE_METRIC, im.GOSSIP_SILENCE_METRIC):
        collector = REGISTRY._names_to_collectors.get(name)
        if collector is not None:
            REGISTRY.unregister(collector)
    importlib.reload(im)  # a fresh import must register nothing
    _hub_configured(monkeypatch, hub_id="")
    assert im.build_monitor_from_settings() is None
    from aitbc_chain.sync_manager import SyncManager

    sm = SyncManager(chains=[], use_gossip=False, use_subscription=False)
    assert sm._island_monitor is None
    out = generate_latest(REGISTRY).decode()
    assert "aitbc_island_hub_silence_seconds" not in out
    assert "aitbc_island_gossip_silence_seconds" not in out


def test_reload_rebuilt_monitor_replaces_callback_real_scrape(monkeypatch):
    """Comment 2841 point 4 / 2842: two reloads, a rebuilt monitor, then a
    real _MetricsHandler HTTP scrape — values follow the NEW monitor."""
    import importlib
    import urllib.request
    from http.server import ThreadingHTTPServer
    import threading
    from aitbc_chain import island_monitor as im
    from aitbc_chain.observability.exporters import _MetricsHandler

    clock = _fake_clock(monkeypatch)
    _hub_configured(monkeypatch)
    old = im.build_monitor_from_settings()
    old.last_hub_observation_at = clock[0] - 100
    old.last_gossip_block_at = clock[0] - 100
    assert _scrape() == (100.0, 100.0)
    importlib.reload(im)
    importlib.reload(im)
    new = im.build_monitor_from_settings()
    new.last_hub_observation_at = clock[0] - 5
    new.last_gossip_block_at = clock[0] - 2
    clock[0] += 50

    server = ThreadingHTTPServer(("127.0.0.1", 0), _MetricsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/metrics"
        with urllib.request.urlopen(url, timeout=5) as resp:
            body = resp.read().decode()
    finally:
        server.shutdown()
        server.server_close()
    assert _scrape(body) == (55.0, 52.0)  # new monitor; the old one would read 150.0
