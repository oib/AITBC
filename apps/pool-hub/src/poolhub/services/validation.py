"""
Hardware validation service for service configurations
"""

import asyncio
from typing import Any

import logging

import requests

from ..models import Miner
from ..settings import settings

logger = logging.getLogger(__name__)

# Expected operational failure surface: registry HTTP calls plus the
# data-shape errors validation arithmetic/dict access can raise.
_OPS_ERRORS = (
    requests.exceptions.RequestException,
    TypeError,
    ValueError,
    KeyError,
    AttributeError,
    ArithmeticError,
)


# (max_vram_gb exclusive upper bound, level, metric value, bottleneck) per
# service tier; first threshold the miner's VRAM falls under wins.
_SERVICE_PERF_TIERS: dict[str, tuple[str, list[tuple[float, str, str, str | None]]]] = {
    "stable_diffusion": (
        "expected_fps",
        [
            (8, "high", "0.1-0.5 images/sec", "VRAM"),
            (16, "medium", "0.5-2 images/sec", None),
            (float("inf"), "low", "2-5 images/sec", None),
        ],
    ),
    "image_generation": (
        "expected_fps",
        [
            (8, "high", "0.1-0.5 images/sec", "VRAM"),
            (16, "medium", "0.5-2 images/sec", None),
            (float("inf"), "low", "2-5 images/sec", None),
        ],
    ),
    "llm_inference": (
        "expected_throughput",
        [
            (8, "high", "1-5 tokens/sec", "VRAM"),
            (16, "medium", "5-20 tokens/sec", None),
            (float("inf"), "low", "20-50+ tokens/sec", None),
        ],
    ),
    "video_transcoding": (
        "expected_fps",
        [
            (4, "high", "10-30 fps (720p)", "GPU Memory"),
            (8, "medium", "30-60 fps (1080p)", None),
            (float("inf"), "low", "60+ fps (4K)", None),
        ],
    ),
    "ffmpeg": (
        "expected_fps",
        [
            (4, "high", "10-30 fps (720p)", "GPU Memory"),
            (8, "medium", "30-60 fps (1080p)", None),
            (float("inf"), "low", "60+ fps (4K)", None),
        ],
    ),
    "3d_rendering": (
        "expected_throughput",
        [
            (8, "high", "0.01-0.1 samples/sec", "VRAM"),
            (16, "medium", "0.1-1 samples/sec", None),
            (float("inf"), "low", "1-5+ samples/sec", None),
        ],
    ),
    "blender": (
        "expected_throughput",
        [
            (8, "high", "0.01-0.1 samples/sec", "VRAM"),
            (16, "medium", "0.1-1 samples/sec", None),
            (float("inf"), "low", "1-5+ samples/sec", None),
        ],
    ),
}


class ValidationResult:
    """Validation result for a service configuration"""

    def __init__(self) -> None:
        self.valid = True
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.score = 0  # 0-100 score indicating how well the hardware matches
        self.missing_requirements: list[dict[str, Any]] = []
        self.performance_impact: dict[str, Any] | None = None


class HardwareValidator:
    """Validates service configurations against miner hardware"""

    def __init__(self) -> None:
        self.registry_url = f"{settings.coordinator_billing_url}/v1/registry"

    async def validate_service_for_miner(self, miner: Miner, service_id: str, config: dict[str, Any]) -> ValidationResult:
        """Validate if a miner can run a specific service"""
        result = ValidationResult()

        try:
            # Get service definition from registry
            service = await self._get_service_definition(service_id)
            if not service:
                result.valid = False
                result.errors.append(f"Service {service_id} not found")
                return result

            # Check hardware requirements
            hw_result = self._check_hardware_requirements(miner, service)
            result.errors.extend(hw_result.errors)
            result.warnings.extend(hw_result.warnings)
            result.score = hw_result.score
            result.missing_requirements = hw_result.missing_requirements

            # Check configuration parameters
            config_result = self._check_configuration_parameters(service, config)
            result.errors.extend(config_result.errors)
            result.warnings.extend(config_result.warnings)

            # Calculate performance impact
            result.performance_impact = self._estimate_performance_impact(miner, service, config)

            # Overall validity
            result.valid = len(result.errors) == 0

        except _OPS_ERRORS as e:
            result.valid = False
            result.errors.append(f"Validation error: {str(e)}")

        return result

    async def _get_service_definition(self, service_id: str) -> dict[str, Any] | None:
        """Fetch service definition from registry"""
        try:
            response = await asyncio.to_thread(requests.get, f"{self.registry_url}/services/{service_id}", timeout=30)
            if response.status_code == 200:
                return response.json()  # type: ignore
            return None
        except _OPS_ERRORS:
            return None

    def _check_hardware_requirements(self, miner: Miner, service: dict[str, Any]) -> ValidationResult:
        """Check if miner meets hardware requirements"""
        result = ValidationResult()
        requirements = service.get("requirements", [])

        for req in requirements:
            component = req["component"]
            min_value = req["min_value"]
            recommended = req.get("recommended")
            unit = req.get("unit", "")

            # Map component to miner attributes
            miner_value = self._get_miner_hardware_value(miner, component)
            if miner_value is None:
                result.warnings.append(f"Cannot verify {component} requirement")
                continue

            # Check minimum requirement
            if not self._meets_requirement(miner_value, min_value, component):
                result.valid = False
                result.errors.append(f"Insufficient {component}: have {miner_value}{unit}, need {min_value}{unit}")
                result.missing_requirements.append(
                    {"component": component, "have": miner_value, "need": min_value, "unit": unit}
                )
            # Check against recommended
            elif recommended and not self._meets_requirement(miner_value, recommended, component):
                result.warnings.append(
                    f"{component} below recommended: have {miner_value}{unit}, recommended {recommended}{unit}"
                )
                result.score -= 10  # Penalize for below recommended

        # Calculate base score
        result.score = max(0, 100 - len(result.errors) * 20 - len(result.warnings) * 5)

        return result

    def _get_miner_hardware_value(self, miner: Miner, component: str) -> float | None:
        """Get hardware value from miner model"""
        mapping = {
            "gpu": 1 if miner.gpu_name else 0,  # Binary: has GPU or not
            "vram": miner.gpu_vram_gb,
            "cpu": miner.cpu_cores,
            "ram": miner.ram_gb,
            "storage": None,  # Not measured; caller warns "cannot verify"
            "cuda": self._get_cuda_version(miner),
            "network": None,  # Not measured; caller warns "cannot verify"
        }
        return mapping.get(component)

    def _get_cuda_version(self, miner: Miner) -> float:
        """Extract CUDA version from capabilities or tags"""
        # Check tags for CUDA version
        for tag, value in miner.tags.items():
            if tag.lower() == "cuda":
                # Extract version number (e.g., "11.8" -> 11.8)
                try:
                    return float(value)
                except ValueError:
                    pass
        return 0.0  # No CUDA info

    def _meets_requirement(self, have: float, need: float, component: str) -> bool:
        """Check if hardware meets requirement"""
        if component == "gpu":
            return have >= need  # Both are 0 or 1
        return have >= need

    def _check_configuration_parameters(self, service: dict[str, Any], config: dict[str, Any]) -> ValidationResult:
        """Check if configuration parameters are valid"""
        result = ValidationResult()
        input_params = service.get("input_parameters", [])

        # Check for required parameters
        required_params = {p["name"] for p in input_params if p.get("required", True)}
        provided_params = set(config.keys())

        missing = required_params - provided_params
        if missing:
            result.errors.extend([f"Missing required parameter: {p}" for p in missing])

        # Validate parameter values
        for param in input_params:
            name = param["name"]
            if name not in config:
                continue

            value = config[name]
            param_type = param.get("type")

            # Type validation
            if param_type == "integer" and not isinstance(value, int):
                result.errors.append(f"Parameter {name} must be an integer")
            elif param_type == "float" and not isinstance(value, int | float):
                result.errors.append(f"Parameter {name} must be a number")
            elif param_type == "array" and not isinstance(value, list):
                result.errors.append(f"Parameter {name} must be an array")

            # Value constraints
            if "min_value" in param and value < param["min_value"]:
                result.errors.append(f"Parameter {name} must be >= {param['min_value']}")
            if "max_value" in param and value > param["max_value"]:
                result.errors.append(f"Parameter {name} must be <= {param['max_value']}")
            if "options" in param and value not in param["options"]:
                result.errors.append(f"Parameter {name} must be one of: {', '.join(param['options'])}")

        return result

    def _estimate_performance_impact(self, miner: Miner, service: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        """Estimate performance impact based on hardware and configuration"""
        impact: dict[str, Any] = {
            "level": "low",  # low, medium, high
            "expected_fps": None,
            "expected_throughput": None,
            "bottleneck": None,
            "recommendations": [],
        }

        # Analyze based on service type
        service_id = service["id"]
        tiers = _SERVICE_PERF_TIERS.get(service_id)
        if tiers is not None:
            metric_key, thresholds = tiers
            for max_vram, level, value, bottleneck in thresholds:
                if miner.gpu_vram_gb < max_vram:
                    impact["level"] = level
                    if bottleneck:
                        impact["bottleneck"] = bottleneck
                    impact[metric_key] = value
                    break

        # Add recommendations based on bottlenecks
        if impact["bottleneck"] == "VRAM":
            impact["recommendations"].append("Consider upgrading GPU with more VRAM")
            impact["recommendations"].append("Reduce batch size or resolution")
        elif impact["bottleneck"] == "GPU Memory":
            impact["recommendations"].append("Use GPU acceleration if available")
            impact["recommendations"].append("Lower resolution or bitrate settings")

        return impact

    async def get_compatible_services(self, miner: Miner) -> list[tuple[str, int]]:
        """Get list of services compatible with miner hardware"""
        try:
            # Get all services from registry
            response = await asyncio.to_thread(requests.get, f"{self.registry_url}/services", timeout=30)
            if response.status_code != 200:
                return []

            services = response.json()
            compatible = []

            for service in services:
                service_id = service["id"]
                # Quick validation without config
                result = await self.validate_service_for_miner(miner, service_id, {})
                if result.valid:
                    compatible.append((service_id, result.score))

            # Sort by score (best match first)
            compatible.sort(key=lambda x: x[1], reverse=True)
            return compatible

        except _OPS_ERRORS as exc:
            # #1374: an empty list is indistinguishable from "no compatible
            # services" — log the failure so matching outages are visible.
            logger.warning("Service compatibility check failed: %s", exc)
            return []
