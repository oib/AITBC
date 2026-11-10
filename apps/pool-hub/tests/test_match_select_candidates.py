"""_select_candidates filtering tests (pure function, no I/O).

#1398 (POOLHUB-FILTER-1): the hardware checks read
``if miner.gpu_vram_gb and miner.gpu_vram_gb < min_vram`` — a falsy value
(0.0, the registration default, or None) skips the comparison entirely, so a
miner with no usable GPU satisfies any min_vram_gb requirement.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace


from poolhub.app.routers.match import _select_candidates


def _miner(
    miner_id: str = "m-1",
    *,
    gpu_vram_gb: float = 24.0,
    ram_gb: float = 64.0,
    capabilities: list[str] | None = None,
    region: str | None = "eu-1",
) -> SimpleNamespace:
    return SimpleNamespace(
        miner_id=miner_id,
        addr=f"/ip4/10.0.0.{miner_id[-1]}/tcp/9000",
        proto="tcp",
        gpu_vram_gb=gpu_vram_gb,
        ram_gb=ram_gb,
        capabilities=capabilities if capabilities is not None else ["whisper", "ffmpeg"],
        region=region,
        base_price=Decimal("0.01"),
    )


def _entry(miner: SimpleNamespace, score: float = 0.5, queue_len: int = 0, latency: int | None = 100):
    status = SimpleNamespace(queue_len=queue_len, avg_latency_ms=latency)
    return (miner, status, score)


class TestHardwareMinimums:
    def test_min_vram_filters_underqualified_miner(self):
        miner = _miner(gpu_vram_gb=4.0)
        candidates = _select_candidates({"min_vram_gb": 8}, {}, [_entry(miner)], top_k=5)
        assert candidates == []

    def test_min_vram_keeps_qualified_miner(self):
        miner = _miner(gpu_vram_gb=16.0)
        candidates = _select_candidates({"min_vram_gb": 8}, {}, [_entry(miner)], top_k=5)
        assert [c["miner_id"] for c in candidates] == ["m-1"]

    def test_zero_vram_does_not_satisfy_min_vram(self):
        """A miner reporting 0 VRAM (the registration default) must not pass."""
        miner = _miner(gpu_vram_gb=0.0)
        candidates = _select_candidates({"min_vram_gb": 8}, {}, [_entry(miner)], top_k=5)
        assert candidates == []

    def test_zero_ram_does_not_satisfy_min_ram(self):
        miner = _miner(ram_gb=0.0)
        candidates = _select_candidates({"min_ram_gb": 32}, {}, [_entry(miner)], top_k=5)
        assert candidates == []

    def test_no_requirements_admits_all(self):
        miner = _miner(gpu_vram_gb=0.0, ram_gb=0.0)
        candidates = _select_candidates({}, {}, [_entry(miner)], top_k=5)
        assert len(candidates) == 1


class TestCapabilitiesAndRegion:
    def test_capabilities_any_requires_subset(self):
        miner = _miner(capabilities=["whisper"])
        req = {"capabilities_any": ["whisper", "ffmpeg"]}
        assert _select_candidates(req, {}, [_entry(miner)], top_k=5) == []

        miner2 = _miner(miner_id="m-2", capabilities=["whisper", "ffmpeg"])
        candidates = _select_candidates(req, {}, [_entry(miner2)], top_k=5)
        assert [c["miner_id"] for c in candidates] == ["m-2"]

    def test_region_hint_mismatch_excluded(self):
        miner = _miner(region="us-1")
        candidates = _select_candidates({}, {"region": "eu-1"}, [_entry(miner)], top_k=5)
        assert candidates == []

    def test_region_hint_match_kept(self):
        miner = _miner(region="eu-1")
        candidates = _select_candidates({}, {"region": "eu-1"}, [_entry(miner)], top_k=5)
        assert len(candidates) == 1


class TestRankingAndTopK:
    def test_sorted_by_score_desc(self):
        miners = [_entry(_miner("m-1"), score=0.3), _entry(_miner("m-2"), score=0.9), _entry(_miner("m-3"), score=0.6)]
        candidates = _select_candidates({}, {}, miners, top_k=5)
        assert [c["miner_id"] for c in candidates] == ["m-2", "m-3", "m-1"]

    def test_top_k_limits_results(self):
        miners = [_entry(_miner(f"m-{i}"), score=float(i)) for i in range(5)]
        candidates = _select_candidates({}, {}, miners, top_k=2)
        assert len(candidates) == 2
        assert candidates[0]["miner_id"] == "m-4"

    def test_candidate_payload_shape(self):
        miner = _miner()
        candidates = _select_candidates({}, {}, [_entry(miner, score=0.75, queue_len=3, latency=42)], top_k=1)
        assert len(candidates) == 1
        c = candidates[0]
        assert c["miner_id"] == "m-1"
        assert c["score"] == 0.75
        assert c["price"] == Decimal("0.01")
        assert "load=3" in c["explain"]
        assert "latency=42" in c["explain"]

    def test_missing_status_yields_null_eta(self):
        miner = _miner()
        candidates = _select_candidates({}, {}, [(miner, None, 0.5)], top_k=1)
        assert candidates[0]["eta_ms"] is None
        assert "latency=n/a" in candidates[0]["explain"]
