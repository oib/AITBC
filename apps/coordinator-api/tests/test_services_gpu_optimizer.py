"""Coverage for MarketGPUOptimizer memory allocator + scheduler (#1289 residual).

simulation_mode=True gives deterministic simulated RTX 4090 devices —
no PyCUDA required. Pins the custom allocator (first-fit, fragmented
fallback, free-block merge), resource release, metrics, and system
status. #1367 regression pins: schedule_job used nonexistent pool keys
(pool["total_memory"]/pool["allocated_memory"]) and never decremented
gpu free_memory — both fixed.
"""

from __future__ import annotations

import pytest

from coordinator_api.contexts.trading.services.trading_market.gpu_optimizer import (
    MarketGPUOptimizer,
    optimize_market_batch,
)

GIB = 1024**3


@pytest.fixture
def opt() -> MarketGPUOptimizer:
    return MarketGPUOptimizer(simulation_mode=True)


# ---------------------------------------------------------------------------
# initialization / status
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_simulation_mode_two_gpus(opt):
    assert opt.simulation_mode is True
    assert len(opt.gpu_devices) == 2
    assert all(g["total_memory"] == 24 * GIB for g in opt.gpu_devices)
    assert set(opt.gpu_memory_pools) == {0, 1}


@pytest.mark.unit
def test_system_status_shape(opt):
    status = opt.get_system_status()
    assert status["active_jobs"] == 0
    assert len(status["devices"]) == 2
    assert status["devices"][0]["memory_total_gb"] == 24.0
    assert "overall_utilization_pct" in status["metrics"]


# ---------------------------------------------------------------------------
# optimize_resource_allocation
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_allocation_success_and_accounting(opt):
    before = opt.gpu_devices[0]["free_memory"]
    res = await opt.optimize_resource_allocation({"memory_bytes": GIB, "compute_units": 1.0})
    assert res["success"] is True
    assert res["job_id"].startswith("job_")
    gpu = next(g for g in opt.gpu_devices if g["id"] == res["gpu_id"])
    assert gpu["free_memory"] == before - GIB
    assert gpu["status"] == "active"
    assert res["job_id"] in opt.active_jobs


@pytest.mark.unit
async def test_allocation_rejects_oversized(opt):
    res = await opt.optimize_resource_allocation({"memory_bytes": 100 * GIB})
    assert res["success"] is False
    assert res["queued"] is True


@pytest.mark.unit
async def test_allocation_uses_job_id_from_requirements(opt):
    res = await opt.optimize_resource_allocation({"memory_bytes": GIB, "job_id": "fixed-job"})
    assert res["job_id"] == "fixed-job"
    assert "fixed-job" in opt.active_jobs


# ---------------------------------------------------------------------------
# allocator internals
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_allocate_memory_first_fit(opt):
    res = opt._allocate_memory(0, 2 * GIB, "j1")
    assert res["success"] is True
    pool = opt.gpu_memory_pools[0]
    assert pool["allocated_blocks"] == [{"job_id": "j1", "start": 0, "size": 2 * GIB}]
    assert pool["free_blocks"] == [{"start": 2 * GIB, "size": 22 * GIB}]


@pytest.mark.unit
def test_allocate_memory_fragmented_fallback(opt):
    # craft fragmented free space: three 4GiB blocks, no single block >= 6GiB
    pool = opt.gpu_memory_pools[0]
    pool["free_blocks"] = [
        {"start": 0, "size": 4 * GIB},
        {"start": 8 * GIB, "size": 4 * GIB},
        {"start": 16 * GIB, "size": 4 * GIB},
    ]
    res = opt._allocate_memory(0, 6 * GIB, "j2")
    assert res["success"] is True
    assert res.get("fragmented") is True
    j2_blocks = [b for b in pool["allocated_blocks"] if b["job_id"] == "j2"]
    assert len(j2_blocks) == 2  # 4GiB + 2GiB split across free blocks
    assert sum(b["size"] for b in j2_blocks) == 6 * GIB


@pytest.mark.unit
def test_release_resources_roundtrip(opt):
    res = opt._allocate_memory(0, GIB, "j1")
    assert res["success"]
    opt.active_jobs["j1"] = {
        "gpu_id": 0,
        "memory_allocated": GIB,
        "compute_allocated": 1.0,
        "priority": 1,
        "status": "running",
    }
    gpu = opt.gpu_devices[0]
    gpu["free_memory"] -= GIB
    assert opt.release_resources("j1") is True
    assert "j1" not in opt.active_jobs
    assert opt.gpu_memory_pools[0]["allocated_blocks"] == []
    assert opt.release_resources("j1") is False  # second release: gone


@pytest.mark.unit
def test_merge_free_blocks_coalesces_adjacent(opt):
    pool = opt.gpu_memory_pools[0]
    pool["free_blocks"] = [
        {"start": 0, "size": GIB},
        {"start": GIB, "size": GIB},
        {"start": 3 * GIB, "size": GIB},
    ]
    opt._merge_free_blocks(0)
    assert pool["free_blocks"] == [
        {"start": 0, "size": 2 * GIB},
        {"start": 3 * GIB, "size": GIB},
    ]


@pytest.mark.unit
def test_fragmentation_index(opt):
    pool = opt.gpu_memory_pools[0]
    pool["free_blocks"] = [{"start": 0, "size": 12 * GIB}, {"start": 12 * GIB, "size": 12 * GIB}]
    opt._recalculate_fragmentation(0)
    # two equal blocks -> max_block/total = 0.5 -> fragmentation 0.5
    assert pool["fragmentation"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# batch helper
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_optimize_market_batch(opt):
    # batch helper builds its own optimizer (auto simulation when no PyCUDA)
    results, status = await optimize_market_batch([{"memory_bytes": GIB}, {"memory_bytes": 100 * GIB}])
    assert results[0]["success"] is True
    assert results[1]["success"] is False
    assert status["active_jobs"] == 1


# ---------------------------------------------------------------------------
# schedule_job — #1367 regression pins (was strict-xfail pre-fix)
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_schedule_job_fitting_memory(opt):
    ok = await opt.schedule_job("j1", priority=5, memory_required=GIB, computation_complexity=1.0)
    assert ok is True
    assert "j1" in opt.active_jobs
