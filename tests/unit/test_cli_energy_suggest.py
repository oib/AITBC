"""Unit tests for `aitbc energy suggest` — hardware -> price suggestion."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from aitbc_cli.commands.energy import energy
from aitbc_cli.utils.hardware_probe import GpuInfo

GPU_4060TI = GpuInfo(index=0, name="NVIDIA GeForce RTX 4060 Ti", memory_gb=16, power_limit_w=165, uuid="GPU-x")
LSCPU_5950X = "AMD Ryzen 9 5950X 16-Core Processor"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def probed(monkeypatch):
    # probes are imported lazily inside the command; patch at the source module
    monkeypatch.setattr(
        "aitbc_cli.utils.hardware_probe.probe_gpus", lambda timeout=10: [GPU_4060TI]
    )
    monkeypatch.setattr(
        "aitbc_cli.utils.hardware_probe.probe_cpu_model", lambda timeout=10: LSCPU_5950X
    )
    # deterministic config: no env files, no on-chain rate read
    fake_config = SimpleNamespace(
        evm_rpc_url=None,
        energy_pricing_contract_address=None,
        energy_pricing_chain_id=1,
        energy_eur_per_kwh=None,
        shop_region=None,
    )
    monkeypatch.setattr("aitbc_cli.commands.energy.get_config", lambda: fake_config)


def test_suggest_reference_rig(runner, probed):
    result = runner.invoke(
        energy, ["suggest", "--region", "de", "--json-output"], catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["gpu_model"] == "rtx_4060_ti_16gb"
    assert data["gpu_tbp_watts"] == 165
    assert data["gpu_tbp_source"] == "nvidia-smi power limit"
    assert data["cpu_watts"] == 120
    # (165 + 120 + 60) / 0.9 = 384
    assert data["node_wall_watts"] == 384
    assert data["register_watts"] == 384
    assert data["eur_per_kwh"] == "0.33"
    assert "region table (de)" in data["tariff_source"]
    # floor: 384W * 0.33 EUR/kWh * 4 AIT/EUR = 0.5068 AIT/h
    floor = float(data["energy_floor_ait_per_hour"])
    assert 0.50 < floor < 0.52
    assert data["suggested_ait_per_hour"] == "1.0"


def test_suggest_manual_overrides(runner, probed):
    result = runner.invoke(
        energy,
        ["suggest", "--gpu-model", "RTX 4090", "--eur-per-kwh", "0.20", "--ait-per-eur", "5",
         "--cpu-watts", "150", "--json-output"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["gpu_model"] == "rtx_4090"
    assert data["gpu_tbp_watts"] == 450  # catalog, since gpu-model skips probe
    assert data["cpu_watts"] == 150
    assert data["eur_per_kwh"] == "0.2"
    assert data["ait_per_eur"] == "5.0"
    assert data["suggested_ait_per_hour"] == "2.5"


def test_suggest_multi_gpu_platform_share(runner, probed):
    result = runner.invoke(
        energy,
        ["suggest", "--gpu-model", "RTX 4090", "--node-gpu-count", "2",
         "--eur-per-kwh", "0.30", "--json-output"],
        catch_exceptions=False,
    )
    data = json.loads(result.output)
    # register = (450 + 180/2)/0.9 = 600; wall = (450*2 + 180)/0.9 = 1200
    assert data["register_watts"] == 600
    assert data["node_wall_watts"] == 1200


def test_suggest_unknown_gpu_floor_only(runner, probed):
    result = runner.invoke(
        energy,
        ["suggest", "--gpu-model", "Mystery Card 9000", "--tbp-watts", "200",
         "--eur-per-kwh", "0.30", "--json-output"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["gpu_tbp_watts"] == 200
    assert data["suggested_ait_per_hour"] is None  # no multiplier entry


def test_suggest_requires_tariff(runner, probed, monkeypatch):
    monkeypatch.delenv("ENERGY_EUR_PER_KWH", raising=False)
    monkeypatch.delenv("SHOP_REGION", raising=False)
    result = runner.invoke(energy, ["suggest", "--json-output"])
    assert result.exit_code != 0
    assert "tariff" in result.output.lower()


def test_suggest_register_requires_ids(runner, probed):
    result = runner.invoke(
        energy, ["suggest", "--region", "de", "--register"], catch_exceptions=False
    )
    assert result.exit_code != 0
    assert "resource-id" in result.output
