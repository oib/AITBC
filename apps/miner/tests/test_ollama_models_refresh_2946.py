"""#2946: the Ollama model list must not freeze at startup.

Pre-fix the miner probed ``/api/tags`` once in ``_initialize`` and threaded
that list through the process lifetime. A reboot/warmup race — Ollama up but
the model not yet pulled, or Ollama still starting — left the list empty
forever: every inference job failed "No models available" and the default
ollama offer never published until an operator restarted ``aitbc-miner``.

The list is now a TTL cache (``get_available_models``) refreshed in the main
loop, so models appearing after boot are picked up without a restart.
"""

from __future__ import annotations

import asyncio

import production_miner as pm


def _reset_cache(monkeypatch):
    monkeypatch.setattr(pm, "_models_cache", [])
    monkeypatch.setattr(pm, "_models_cache_at", 0.0)


def _probe_sequence(monkeypatch, results):
    """Patch check_ollama with a sequence of (available, models) outcomes."""
    calls = {"n": 0}

    def fake_check():
        calls["n"] += 1
        return results[min(calls["n"] - 1, len(results) - 1)]

    monkeypatch.setattr(pm, "check_ollama", fake_check)
    return calls


class TestTTLCache:
    def test_cache_hit_within_ttl_probes_once(self, monkeypatch):
        _reset_cache(monkeypatch)
        calls = _probe_sequence(monkeypatch, [(True, ["qwen3:8b"])])
        assert pm.get_available_models(now=1000.0) == ["qwen3:8b"]
        assert pm.get_available_models(now=1000.0 + pm.MODEL_CACHE_TTL - 1) == ["qwen3:8b"]
        assert calls["n"] == 1

    def test_warmup_race_models_picked_up_after_ttl(self, monkeypatch):
        """The exact #2946 repro: startup probe empty (warmup race), models
        appear later — after TTL expiry the miner must see them."""
        _reset_cache(monkeypatch)
        _probe_sequence(monkeypatch, [(True, []), (True, ["qwen3:8b"])])
        assert pm.get_available_models(now=1000.0) == []
        # inside TTL: still the cached empty list
        assert pm.get_available_models(now=1000.0 + 5) == []
        # after TTL: re-probe picks up the pulled model
        assert pm.get_available_models(now=1000.0 + pm.MODEL_CACHE_TTL + 1) == ["qwen3:8b"]

    def test_failed_probe_keeps_last_known_list(self, monkeypatch):
        _reset_cache(monkeypatch)
        _probe_sequence(monkeypatch, [(True, ["qwen3:8b"]), (False, [])])
        assert pm.get_available_models(now=1000.0) == ["qwen3:8b"]
        # probe fails after TTL — last known good list survives
        assert pm.get_available_models(now=1000.0 + pm.MODEL_CACHE_TTL + 1) == ["qwen3:8b"]

    def test_failed_probe_advances_clock_no_probe_spam(self, monkeypatch):
        """A down Ollama must not be re-probed on every loop iteration —
        the probe blocks up to 5s in the main loop."""
        _reset_cache(monkeypatch)
        calls = _probe_sequence(monkeypatch, [(False, [])])
        assert pm.get_available_models(now=1000.0) == []
        pm.get_available_models(now=1001.0)
        pm.get_available_models(now=1002.0)
        assert calls["n"] == 1


class TestStartupSeeding:
    def test_initialize_seeds_cache(self, monkeypatch):
        """The startup probe primes the cache — the first loop iteration
        must not immediately re-probe."""
        _reset_cache(monkeypatch)
        pm._seed_models_cache(["qwen3:8b"])
        calls = _probe_sequence(monkeypatch, [(True, ["qwen3:8b"])])
        assert pm.get_available_models(now=pm._models_cache_at + 1) == ["qwen3:8b"]
        assert calls["n"] == 0


class TestMainLoopWiring:
    def test_loop_passes_refreshed_models_to_poll_and_heartbeats(self, monkeypatch):
        """Mutation pin on the wiring: the main loop must hand the TTL-cache
        value — not the frozen startup list — to dispatch and offer publish.
        Pre-fix this captured the startup ``[]`` forever."""
        captured = {}

        async def fake_initialize():
            return ([], 1)  # startup probe empty — the warmup race

        monkeypatch.setattr(pm, "_initialize", fake_initialize)
        monkeypatch.setattr(pm, "get_available_models", lambda: ["qwen3:8b"])

        async def fake_heartbeats(current_time, last_hb, last_pool_hb, last_offer, models):
            captured["heartbeat_models"] = models
            return last_hb, last_pool_hb, last_offer

        monkeypatch.setattr(pm, "_periodic_heartbeats", fake_heartbeats)

        def fake_poll(models, max_concurrent_jobs):
            captured["poll_models"] = models

        monkeypatch.setattr(pm, "_poll_and_dispatch", fake_poll)
        monkeypatch.setattr(pm, "_poll_interval_seconds", lambda: 0.0)

        # End the loop after the first iteration.
        def stop(_seconds):
            raise KeyboardInterrupt

        monkeypatch.setattr(pm.time, "time", lambda: 10_000.0)
        monkeypatch.setattr(pm, "AGENT_EXECUTOR_ENABLED", False)
        real_sleep = asyncio.sleep

        async def fake_sleep(seconds):
            if seconds == 1:
                raise KeyboardInterrupt
            await real_sleep(0)

        monkeypatch.setattr(pm.asyncio, "sleep", fake_sleep)
        monkeypatch.setattr(pm, "IPFS_PIN_SWEEP_INTERVAL", 999999.0)
        monkeypatch.setattr(pm, "MARKET_GPU_REREGISTER_INTERVAL", 999999.0)

        asyncio.run(pm.main())

        assert captured["poll_models"] == ["qwen3:8b"]
        assert captured["heartbeat_models"] == ["qwen3:8b"]
