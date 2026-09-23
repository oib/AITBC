"""Unit tests for `aitbc energy suggest` — hardware -> price suggestion."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from aitbc_cli.commands import energy as energy_mod
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
        coordinator_url=None,
        coordinator_api_url=None,
        api_key=None,
    )
    monkeypatch.setattr("aitbc_cli.commands.energy.get_config", lambda: fake_config)
    # no coordinator reachable in unit tests -> rate falls back to the reference
    def _no_coordinator(*args, **kwargs):
        raise RuntimeError("no coordinator in tests")

    monkeypatch.setattr("aitbc_cli.commands.energy._native_energy_request", _no_coordinator)


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


def test_suggest_uses_native_rate(runner, probed, monkeypatch):
    """With no EVM configured, the published native rate feeds the suggestion."""
    calls = []

    def fake_request(ctx, method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {"ait_per_eur": "4.0"}

    monkeypatch.setattr("aitbc_cli.commands.energy._native_energy_request", fake_request)
    result = runner.invoke(
        energy, ["suggest", "--region", "de", "--json-output"], catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["rate_source"] == "native rate"
    assert data["ait_per_eur"] == "4.0"
    assert calls == [("get", "/v1/marketplace/native-energy/rate", {"miner": True, "timeout": 10})]


def test_suggest_register_native_posts_profile(runner, probed, monkeypatch):
    """--register on the native rail upserts the profile via the coordinator API."""
    calls = []

    def fake_request(ctx, method, path, **kwargs):
        calls.append((method, path, kwargs))
        if method == "get":
            return {"ait_per_eur": "4.0"}
        return {"status": "ok"}

    monkeypatch.setattr("aitbc_cli.commands.energy._native_energy_request", fake_request)
    result = runner.invoke(
        energy,
        [
            "suggest", "--region", "de", "--register",
            "--resource-id", "node9-rtx4060ti", "--provider-address", "0xabc",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert "Native energy profile registered" in result.output
    post_calls = [c for c in calls if c[0] == "post"]
    assert len(post_calls) == 1
    _, path, kwargs = post_calls[0]
    assert path == "/v1/marketplace/native-energy/profile"
    assert kwargs["miner"] is True
    assert kwargs["json_body"] == {
        "resource_id": "node9-rtx4060ti",
        "provider": "0xabc",
        "model_id": "rtx_4060_ti_16gb",
        "tbp_watts": 384,
        "eur_per_kwh": 0.33,
    }


def test_floor_native_rail(runner, probed, monkeypatch):
    """`energy floor` reads the native floor endpoint when EVM is unconfigured."""
    calls = []

    def fake_request(ctx, method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {
            "settlement_unit_scale": 36_000_000,
            "net_floor_units": 1_658_880,
            "net_floor_ait": "0.04608",
        }

    monkeypatch.setattr("aitbc_cli.commands.energy._native_energy_request", fake_request)
    result = runner.invoke(
        energy,
        ["floor", "--resource-id", "node9", "--gpu-count", "1", "--duration-seconds", "3600"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert "native" in result.output
    assert "1658880" in result.output
    assert calls == [
        ("get", "/v1/marketplace/native-energy/floor",
         {"params": {"resource_id": "node9", "gpu_count": 1, "duration_seconds": 3600}, "timeout": 10})
    ]


def test_native_request_falls_back_to_hub(runner, monkeypatch):
    """When the local coordinator lacks the native tables, calls retry on the hub mount."""
    from aitbc_cli.utils.http_client import NetworkError

    # native rail: no EVM config (can't use `probed` — it stubs _native_energy_request)
    fake_config = SimpleNamespace(
        evm_rpc_url=None,
        energy_pricing_contract_address=None,
        energy_pricing_chain_id=1,
        coordinator_url=None,
        coordinator_api_url=None,
        api_key=None,
    )
    monkeypatch.setattr("aitbc_cli.commands.energy.get_config", lambda: fake_config)

    bases = []

    class FlakyClient:
        def __init__(self, base_url=None, **kwargs):
            self.base_url = base_url
            bases.append(base_url)

        def get(self, path, params=None):
            if "127.0.0.1" in (self.base_url or ""):
                raise NetworkError("404 native tables not provisioned")
            return {"settlement_unit_scale": 36_000_000, "net_floor_units": 1, "net_floor_ait": "0.0001"}

        def post(self, path, json=None):
            raise AssertionError("not used")

    import aitbc.config.hub as hub_mod

    monkeypatch.setattr(energy_mod, "AITBCHTTPClient", FlakyClient)
    monkeypatch.setattr(hub_mod, "hub_coordinator_url", lambda: "https://hub.example/c/v1")

    result = runner.invoke(
        energy,
        ["floor", "--resource-id", "r1", "--gpu-count", "1", "--duration-seconds", "60"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert "native" in result.output
    assert len(bases) == 2
    assert bases[0].startswith("http://127.0.0.1")
    assert bases[1] == "https://hub.example/c"  # /v1 suffix trimmed before joining paths
