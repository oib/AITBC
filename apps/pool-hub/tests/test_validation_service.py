"""HardwareValidator tests — registry access is mocked, no network.

Covers services/validation.py: hardware requirement checks, configuration
parameter validation, score computation, performance-impact estimation, and
compatible-service ranking.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from poolhub.models import Miner
from poolhub.services.validation import HardwareValidator


def _miner(
    *,
    gpu_vram_gb: float = 24.0,
    gpu_name: str | None = "RTX 4090",
    cpu_cores: int = 16,
    ram_gb: float = 64.0,
    tags: dict | None = None,
    capabilities: list[str] | None = None,
) -> Miner:
    return Miner(
        miner_id="m-1",
        api_key_hash="x" * 64,
        addr="/ip4/127.0.0.1/tcp/9000",
        proto="tcp",
        gpu_vram_gb=gpu_vram_gb,
        gpu_name=gpu_name,
        cpu_cores=cpu_cores,
        ram_gb=ram_gb,
        max_parallel=4,
        base_price=Decimal("0.01"),
        tags=tags or {},
        capabilities=capabilities or [],
    )


def _service(**overrides) -> dict:
    service = {
        "id": "test_service",
        "requirements": [],
        "input_parameters": [],
    }
    service.update(overrides)
    return service


@pytest.fixture
def validator() -> HardwareValidator:
    return HardwareValidator()


def _stub_registry(validator: HardwareValidator, service: dict | None) -> None:
    validator._get_service_definition = AsyncMock(return_value=service)  # type: ignore[method-assign]


class TestServiceLookup:
    async def test_unknown_service_is_invalid(self, validator):
        _stub_registry(validator, None)
        result = await validator.validate_service_for_miner(_miner(), "nope", {})
        assert result.valid is False
        assert any("not found" in e for e in result.errors)


class TestHardwareRequirements:
    async def test_meets_min_and_recommended(self, validator):
        service = _service(requirements=[{"component": "vram", "min_value": 8, "recommended": 16, "unit": "GB"}])
        _stub_registry(validator, service)
        result = await validator.validate_service_for_miner(_miner(gpu_vram_gb=24.0), "svc", {})
        assert result.valid is True
        assert result.errors == []
        assert result.score == 100

    async def test_below_recommended_warns_and_penalizes(self, validator):
        service = _service(requirements=[{"component": "vram", "min_value": 8, "recommended": 16, "unit": "GB"}])
        _stub_registry(validator, service)
        result = await validator.validate_service_for_miner(_miner(gpu_vram_gb=12.0), "svc", {})
        assert result.valid is True
        assert any("below recommended" in w for w in result.warnings)
        assert result.score == 95  # one warning: 100 - 5

    async def test_below_minimum_is_invalid_with_missing_requirement(self, validator):
        service = _service(requirements=[{"component": "vram", "min_value": 16, "unit": "GB"}])
        _stub_registry(validator, service)
        result = await validator.validate_service_for_miner(_miner(gpu_vram_gb=8.0), "svc", {})
        assert result.valid is False
        assert result.missing_requirements == [{"component": "vram", "have": 8.0, "need": 16, "unit": "GB"}]
        assert result.score == 80  # one error: 100 - 20

    async def test_unverifiable_component_warns_not_fails(self, validator):
        service = _service(requirements=[{"component": "storage", "min_value": 100, "unit": "GB"}])
        _stub_registry(validator, service)
        result = await validator.validate_service_for_miner(_miner(), "svc", {})
        assert result.valid is True
        assert any("Cannot verify storage" in w for w in result.warnings)

    async def test_gpu_component_is_binary(self, validator):
        service = _service(requirements=[{"component": "gpu", "min_value": 1, "unit": ""}])
        _stub_registry(validator, service)
        with_gpu = await validator.validate_service_for_miner(_miner(gpu_name="RTX 4090"), "svc", {})
        without_gpu = await validator.validate_service_for_miner(_miner(gpu_name=None), "svc", {})
        assert with_gpu.valid is True
        assert without_gpu.valid is False

    async def test_cuda_version_from_tags(self, validator):
        miner = _miner(tags={"CUDA": "11.8"})
        assert validator._get_cuda_version(miner) == 11.8

    async def test_cuda_version_unparseable_is_zero(self, validator):
        miner = _miner(tags={"CUDA": "not-a-version"})
        assert validator._get_cuda_version(miner) == 0.0

    async def test_cuda_tag_case_insensitive(self, validator):
        miner = _miner(tags={"cuda": "12.1"})
        assert validator._get_cuda_version(miner) == 12.1


class TestConfigurationParameters:
    async def test_missing_required_parameter(self, validator):
        service = _service(input_parameters=[{"name": "steps", "type": "integer", "required": True}])
        _stub_registry(validator, service)
        result = await validator.validate_service_for_miner(_miner(), "svc", {})
        assert result.valid is False
        assert any("Missing required parameter: steps" in e for e in result.errors)

    async def test_optional_parameter_may_be_absent(self, validator):
        service = _service(input_parameters=[{"name": "steps", "type": "integer", "required": False}])
        _stub_registry(validator, service)
        result = await validator.validate_service_for_miner(_miner(), "svc", {})
        assert result.valid is True

    async def test_integer_type_rejects_string(self, validator):
        service = _service(input_parameters=[{"name": "steps", "type": "integer", "required": True}])
        _stub_registry(validator, service)
        # A string fails the isinstance check AND then crashes the min_value
        # comparison ('<' between str and int) — the outer catch turns it into
        # a generic "Validation error". Either way it must not validate.
        result = await validator.validate_service_for_miner(_miner(), "svc", {"steps": "fifty"})
        assert result.valid is False

    async def test_integer_type_rejects_float(self, validator):
        service = _service(input_parameters=[{"name": "steps", "type": "integer", "required": True}])
        _stub_registry(validator, service)
        result = await validator.validate_service_for_miner(_miner(), "svc", {"steps": 1.5})
        assert result.valid is False
        assert any("must be an integer" in e for e in result.errors)

    async def test_float_type_accepts_int_and_float(self, validator):
        service = _service(input_parameters=[{"name": "temperature", "type": "float", "required": True}])
        _stub_registry(validator, service)
        ok = await validator.validate_service_for_miner(_miner(), "svc", {"temperature": 0.7})
        ok_int = await validator.validate_service_for_miner(_miner(), "svc", {"temperature": 1})
        bad = await validator.validate_service_for_miner(_miner(), "svc", {"temperature": "hot"})
        assert ok.valid is True
        assert ok_int.valid is True
        assert bad.valid is False

    async def test_array_type(self, validator):
        service = _service(input_parameters=[{"name": "images", "type": "array", "required": True}])
        _stub_registry(validator, service)
        ok = await validator.validate_service_for_miner(_miner(), "svc", {"images": ["a.png"]})
        bad = await validator.validate_service_for_miner(_miner(), "svc", {"images": "a.png"})
        assert ok.valid is True
        assert bad.valid is False

    async def test_min_max_value_constraints(self, validator):
        service = _service(
            input_parameters=[{"name": "steps", "type": "integer", "required": True, "min_value": 1, "max_value": 100}]
        )
        _stub_registry(validator, service)
        low = await validator.validate_service_for_miner(_miner(), "svc", {"steps": 0})
        high = await validator.validate_service_for_miner(_miner(), "svc", {"steps": 101})
        ok = await validator.validate_service_for_miner(_miner(), "svc", {"steps": 50})
        assert low.valid is False and any(">= 1" in e for e in low.errors)
        assert high.valid is False and any("<= 100" in e for e in high.errors)
        assert ok.valid is True

    async def test_options_constraint(self, validator):
        service = _service(input_parameters=[{"name": "model", "type": "string", "required": True, "options": ["a", "b"]}])
        _stub_registry(validator, service)
        bad = await validator.validate_service_for_miner(_miner(), "svc", {"model": "c"})
        ok = await validator.validate_service_for_miner(_miner(), "svc", {"model": "a"})
        assert bad.valid is False
        assert ok.valid is True


class TestPerformanceImpact:
    @pytest.mark.parametrize(
        ("service_id", "vram", "expected_level", "expected_bottleneck"),
        [
            ("stable_diffusion", 4.0, "high", "VRAM"),
            ("stable_diffusion", 12.0, "medium", None),
            ("stable_diffusion", 24.0, "low", None),
            ("llm_inference", 4.0, "high", "VRAM"),
            ("llm_inference", 24.0, "low", None),
            ("video_transcoding", 2.0, "high", "GPU Memory"),
            ("3d_rendering", 24.0, "low", None),
        ],
    )
    async def test_impact_tiers(self, validator, service_id, vram, expected_level, expected_bottleneck):
        service = _service(id=service_id)
        impact = validator._estimate_performance_impact(_miner(gpu_vram_gb=vram), service, {})
        assert impact["level"] == expected_level
        assert impact["bottleneck"] == expected_bottleneck

    async def test_unknown_service_defaults_to_low(self, validator):
        impact = validator._estimate_performance_impact(_miner(), _service(id="mystery"), {})
        assert impact["level"] == "low"
        assert impact["recommendations"] == []

    async def test_vram_bottleneck_adds_recommendations(self, validator):
        impact = validator._estimate_performance_impact(_miner(gpu_vram_gb=4.0), _service(id="stable_diffusion"), {})
        assert any("VRAM" in r for r in impact["recommendations"])


class TestCompatibleServices:
    async def test_incompatible_service_is_excluded(self, validator, monkeypatch):
        miner = _miner(gpu_vram_gb=4.0)
        services = [
            {"id": "gpu_hungry", "requirements": [{"component": "vram", "min_value": 16}], "input_parameters": []},
            {"id": "cheap_service", "requirements": [{"component": "vram", "min_value": 2}], "input_parameters": []},
        ]

        class _Resp:
            status_code = 200

            def __init__(self, payload):
                self._payload = payload

            def json(self):
                return self._payload

        def fake_get(url, timeout=0):
            if url.endswith("/services"):
                return _Resp(services)
            sid = url.rsplit("/", 1)[-1]
            return _Resp(next(s for s in services if s["id"] == sid))

        monkeypatch.setattr("poolhub.services.validation.requests.get", fake_get)
        compatible = await validator.get_compatible_services(miner)
        assert [sid for sid, _ in compatible] == ["cheap_service"]

    async def test_registry_failure_returns_empty_list(self, validator, monkeypatch):
        class _Resp:
            status_code = 500

            def json(self):
                return {}

        monkeypatch.setattr("poolhub.services.validation.requests.get", lambda *a, **k: _Resp())
        assert await validator.get_compatible_services(_miner()) == []
