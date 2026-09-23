"""Unit tests for the hardware power / price catalog used by `aitbc energy suggest`."""

from __future__ import annotations

from decimal import Decimal

from aitbc.market.hardware_catalog import (
    BASE_PLATFORM_W,
    PSU_EFFICIENCY,
    compute_multiplier,
    estimate_node_power,
    normalize_cpu_model,
    normalize_gpu_model,
    region_tariff,
    resolve_cpu_watts,
    resolve_gpu_tbp,
)


class TestNormalizeGpuModel:
    def test_nvidia_smi_name(self):
        assert normalize_gpu_model("NVIDIA GeForce RTX 4060 Ti") == "rtx_4060_ti"

    def test_16gb_variant_by_memory(self):
        assert normalize_gpu_model("NVIDIA GeForce RTX 4060 Ti", memory_gb=16) == "rtx_4060_ti_16gb"
        assert normalize_gpu_model("NVIDIA GeForce RTX 4060 Ti", memory_gb=8) == "rtx_4060_ti"

    def test_other_models(self):
        assert normalize_gpu_model("NVIDIA GeForce RTX 4090") == "rtx_4090"
        assert normalize_gpu_model("NVIDIA H100 80GB HBM3") == "h100_80gb_hbm3"
        assert normalize_gpu_model("AMD Radeon RX 7900 XTX") == "rx_7900_xtx"

    def test_unknown_normalizes(self):
        key = normalize_gpu_model("Some Mystery Card 9000")
        assert isinstance(key, str) and key


class TestNormalizeCpuModel:
    def test_lscpu_ryzen(self):
        assert normalize_cpu_model("AMD Ryzen 9 5950X 16-Core Processor") == "ryzen_9_5950x"

    def test_intel(self):
        assert normalize_cpu_model("Intel(R) Core(TM) i9-13900K") == "i9_13900k"

    def test_xeon_clock_suffix(self):
        assert normalize_cpu_model("Intel(R) Xeon(R) Platinum 8380 CPU @ 2.30GHz") == "xeon_platinum_8380"


class TestResolvers:
    def test_gpu_precedence(self):
        assert resolve_gpu_tbp("rtx_4090", 300, 999) == (999, "manual")
        assert resolve_gpu_tbp("rtx_4090", 300, None) == (300, "nvidia-smi power limit")
        assert resolve_gpu_tbp("rtx_4090", None, None) == (450, "catalog")
        assert resolve_gpu_tbp("unknown_gpu", None, None) == (0, "unknown")

    def test_cpu_precedence(self):
        assert resolve_cpu_watts("ryzen_9_5950x", 200) == (200, "manual")
        assert resolve_cpu_watts("ryzen_9_5950x", None) == (120, "catalog")
        w, src = resolve_cpu_watts("totally_unknown_cpu", None)
        assert w > 0 and src == "default estimate"

    def test_region_tariff(self):
        assert region_tariff("de") == Decimal("0.33")
        assert region_tariff("DE") == Decimal("0.33")
        assert region_tariff("xx") is None
        assert region_tariff(None) is None

    def test_multiplier(self):
        assert compute_multiplier("rtx_4060_ti_16gb") == Decimal("1.0")
        assert compute_multiplier("rtx_3060") == Decimal("0.7")
        assert compute_multiplier("rtx_4070") is None
        assert compute_multiplier(None) is None


class TestEstimateNodePower:
    def test_reference_rig_single_gpu(self):
        # node2 reference rig: 4060 Ti (165W) + 5950X (120W) + 60W platform
        est = estimate_node_power(
            gpu_tbp_w=165,
            gpu_w_source="nvidia-smi power limit",
            gpu_model_key="rtx_4060_ti_16gb",
            gpu_count=1,
            node_gpu_count=1,
            cpu_watts=120,
            cpu_w_source="catalog",
        )
        # (165 + 120 + 60) / 0.9 = 383.33 -> 384
        expected = int((Decimal(165 + 120 + BASE_PLATFORM_W) / PSU_EFFICIENCY).to_integral_value(rounding="ROUND_CEILING"))
        assert est.node_wall_watts == expected == 384
        assert est.register_watts == expected

    def test_multi_gpu_shares_platform(self):
        est = estimate_node_power(
            gpu_tbp_w=450,
            gpu_w_source="catalog",
            gpu_model_key="rtx_4090",
            gpu_count=1,
            node_gpu_count=2,
            cpu_watts=120,
            cpu_w_source="catalog",
        )
        # register = (450 + 180/2)/0.9 = 540/0.9 = 600; wall = (900+180)/0.9 = 1200
        assert est.register_watts == 600
        assert est.node_wall_watts == 1200

    def test_platform_override(self):
        est = estimate_node_power(
            gpu_tbp_w=100,
            gpu_w_source="manual",
            gpu_model_key=None,
            gpu_count=1,
            node_gpu_count=1,
            cpu_watts=50,
            cpu_w_source="manual",
            platform_watts=0,
        )
        # (100 + 50) / 0.9 = 166.67 -> ceil 167
        assert est.register_watts == 167
