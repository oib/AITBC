"""Hardware power and compute-reference catalog for energy price suggestion.

Pure data + pure functions: no I/O, no config, no network. Consumed by the
``aitbc energy suggest`` CLI command (and its generated MCP wrapper).

Two kinds of data live here:

* ``GPU_TBP_W`` — approximate **total board power** per GPU model. This is the
  billing basis for the energy floor (whole card draw, not chip TDP). Values
  are typical reference-spec watts; when the node reports a real
  ``nvidia-smi`` power limit that reading wins (see ``resolve_gpu_tbp``).

* ``GPU_COMPUTE_MULTIPLIER`` — the marketplace price multiplier from
  ``docs/getting-started/ait-value-model.md``: 1 AIT = one compute-hour on the
  RTX 4060 Ti 16GB reference rig (EUR 0.25). Keep this table in sync with the
  doc; GPUs without an entry get a floor-only suggestion.

``CPU_TDP_W`` and ``REGION_EUR_PER_KWH`` are approximate sustained-watts and
estimated household/small-business tariffs (EUR/kWh). Both are intentionally
conservative estimates; operators should override with ``--cpu-watts`` /
``--eur-per-kwh`` (or ``SHOP_REGION`` / ``ENERGY_EUR_PER_KWH`` env) when they
know their real numbers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

# ---------------------------------------------------------------------------
# GPU total board power (watts)
# ---------------------------------------------------------------------------

GPU_TBP_W: dict[str, int] = {
    # Ampere consumer
    "rtx_3060": 170,
    "rtx_3060_ti": 200,
    "rtx_3070": 220,
    "rtx_3070_ti": 290,
    "rtx_3080": 320,
    "rtx_3080_ti": 350,
    "rtx_3090": 350,
    "rtx_3090_ti": 450,
    # Ada Lovelace consumer
    "rtx_4060": 115,
    "rtx_4060_ti": 160,
    "rtx_4060_ti_16gb": 165,
    "rtx_4070": 200,
    "rtx_4070_super": 220,
    "rtx_4070_ti": 285,
    "rtx_4080": 320,
    "rtx_4080_super": 320,
    "rtx_4090": 450,
    # Datacenter / workstation
    "l4": 72,
    "l40s": 350,
    "a100": 300,
    "h100": 700,
    "rtx_a6000": 300,
}

# Marketplace price multipliers — the normative table lives in
# docs/getting-started/ait-value-model.md ("Multi-GPU Scaling"); keep in sync.
GPU_COMPUTE_MULTIPLIER: dict[str, Decimal] = {
    "rtx_3060": Decimal("0.7"),
    "rtx_4060_ti_16gb": Decimal("1.0"),
    "rtx_3090": Decimal("1.5"),
    "rtx_4090": Decimal("2.5"),
    "h100": Decimal("10"),
}

# ---------------------------------------------------------------------------
# CPU sustained package power (watts) — approximate; override with --cpu-watts
# ---------------------------------------------------------------------------

CPU_TDP_W: dict[str, int] = {
    "ryzen_9_5950x": 120,
    "ryzen_9_7950x": 170,
    "ryzen_9_5900x": 105,
    "ryzen_7_5800x": 105,
    "ryzen_7_7800x3d": 90,
    "ryzen_5_5600x": 76,
    "i9_13900k": 150,
    "i7_13700k": 125,
    "i9_12900k": 150,
    "epyc_7742": 225,
    "epyc_9654": 360,
    "xeon_8380": 270,
}

DEFAULT_CPU_WATTS = 95

# Motherboard, RAM, storage, fans — everything that is not GPU or CPU package.
BASE_PLATFORM_W = 60

# 80+ Gold-class PSU conversion efficiency; DC-side component watts divided by
# this give the AC draw at the wall.
PSU_EFFICIENCY = Decimal("0.90")

# ---------------------------------------------------------------------------
# Estimated electricity tariffs (EUR/kWh) — static table, --eur-per-kwh wins
# ---------------------------------------------------------------------------

REGION_EUR_PER_KWH: dict[str, Decimal] = {
    "de": Decimal("0.33"),
    "fr": Decimal("0.24"),
    "nl": Decimal("0.29"),
    "be": Decimal("0.31"),
    "at": Decimal("0.27"),
    "es": Decimal("0.20"),
    "it": Decimal("0.28"),
    "pl": Decimal("0.19"),
    "cz": Decimal("0.24"),
    "sk": Decimal("0.22"),
    "se": Decimal("0.18"),
    "fi": Decimal("0.16"),
    "dk": Decimal("0.34"),
    "pt": Decimal("0.22"),
    "ie": Decimal("0.30"),
    "gr": Decimal("0.21"),
    "ro": Decimal("0.17"),
    "hu": Decimal("0.12"),
    "uk": Decimal("0.29"),
    "ch": Decimal("0.26"),
    "us": Decimal("0.17"),
    "eu": Decimal("0.28"),  # EU-average fallback
}

# ---------------------------------------------------------------------------
# Name normalization
# ---------------------------------------------------------------------------

_VENDOR_WORDS = ("nvidia", "geforce", "amd", "radeon", "intel", "graphics")


def normalize_gpu_model(name: str, memory_gb: int | None = None) -> str:
    """Reduce an nvidia-smi/product name to a catalog key.

    "NVIDIA GeForce RTX 4060 Ti" -> "rtx_4060_ti"; with memory_gb 16 the 16GB
    variant is preferred -> "rtx_4060_ti_16gb". Unknown names normalize too,
    so lookups simply miss the table instead of raising.
    """
    tokens = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    for w in _VENDOR_WORDS:
        tokens = re.sub(rf"(^|_){re.escape(w)}(_|$)", r"\1", tokens).strip("_")
    tokens = re.sub(r"_+", "_", tokens)
    if memory_gb and memory_gb >= 15 and f"{tokens}_16gb" in GPU_TBP_W:
        return f"{tokens}_16gb"
    return tokens


def normalize_cpu_model(name: str) -> str:
    """Reduce an lscpu "Model name" to a catalog key.

    "AMD Ryzen 9 5950X 16-Core Processor" -> "ryzen_9_5950x".
    """
    tokens = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    for w in _VENDOR_WORDS + ("core", "cores", "processor", "cpu"):
        tokens = re.sub(rf"(^|_){re.escape(w)}(_|$)", r"\1", tokens).strip("_")
    tokens = re.sub(r"_*\d+_core_*", "_", tokens)  # "16_core" count segment
    return re.sub(r"_+", "_", tokens).strip("_")


# ---------------------------------------------------------------------------
# Resolvers
# ---------------------------------------------------------------------------


def resolve_gpu_tbp(
    model_key: str | None = None,
    power_limit_w: int | None = None,
    explicit_watts: int | None = None,
) -> tuple[int, str]:
    """Pick the billing watts for one GPU. Returns (watts, source_label).

    Precedence: explicit flag > measured power limit > catalog table.
    """
    if explicit_watts and explicit_watts > 0:
        return int(explicit_watts), "manual"
    if power_limit_w and power_limit_w > 0:
        return int(power_limit_w), "nvidia-smi power limit"
    if model_key and model_key in GPU_TBP_W:
        return GPU_TBP_W[model_key], "catalog"
    return 0, "unknown"


def resolve_cpu_watts(model_key: str | None, explicit_watts: int | None = None) -> tuple[int, str]:
    if explicit_watts and explicit_watts > 0:
        return int(explicit_watts), "manual"
    if model_key and model_key in CPU_TDP_W:
        return CPU_TDP_W[model_key], "catalog"
    return DEFAULT_CPU_WATTS, "default estimate"


def region_tariff(region: str | None) -> Decimal | None:
    """EUR/kWh for a region code (case-insensitive); None when unknown."""
    if not region:
        return None
    return REGION_EUR_PER_KWH.get(region.strip().lower())


def compute_multiplier(model_key: str | None) -> Decimal | None:
    """Compute-hour price multiplier for a normalized GPU key; None if unlisted."""
    if model_key is None:
        return None
    return GPU_COMPUTE_MULTIPLIER.get(model_key)


# ---------------------------------------------------------------------------
# Whole-node power arithmetic
# ---------------------------------------------------------------------------


@dataclass
class NodePowerEstimate:
    """Power accounting for one shop node.

    ``register_watts`` is the per-GPU-equivalent figure that goes on-chain as
    ``tbp_watts``: the floor formula already multiplies watts by gpu_count, so
    platform draw is divided across the node's GPUs rather than per card.

    ``node_wall_watts`` is the whole-PC AC draw for transparency/billing.
    """

    gpu_model_key: str | None
    gpu_tbp_w: int
    gpu_w_source: str
    gpu_count: int
    node_gpu_count: int
    cpu_watts: int
    cpu_w_source: str
    platform_watts: int
    node_wall_watts: int
    register_watts: int


def estimate_node_power(
    *,
    gpu_tbp_w: int,
    gpu_w_source: str,
    gpu_model_key: str | None,
    gpu_count: int,
    node_gpu_count: int,
    cpu_watts: int,
    cpu_w_source: str,
    platform_watts: int = BASE_PLATFORM_W,
) -> NodePowerEstimate:
    """Split a whole-node draw into node wall watts and per-resource watts.

    register_watts = ceil((gpu_tbp + (cpu + platform) / node_gpu_count) / PSU_EFF)
    node_wall_watts = ceil((gpu_tbp * node_gpu_count + cpu + platform) / PSU_EFF)
    """
    node_gpu_count = max(1, node_gpu_count)
    gpu_count = max(1, gpu_count)
    platform_share = Decimal(cpu_watts + platform_watts) / node_gpu_count
    register = (Decimal(gpu_tbp_w) + platform_share) / PSU_EFFICIENCY
    node_wall = Decimal(gpu_tbp_w * node_gpu_count + cpu_watts + platform_watts) / PSU_EFFICIENCY
    return NodePowerEstimate(
        gpu_model_key=gpu_model_key,
        gpu_tbp_w=gpu_tbp_w,
        gpu_w_source=gpu_w_source,
        gpu_count=gpu_count,
        node_gpu_count=node_gpu_count,
        cpu_watts=cpu_watts,
        cpu_w_source=cpu_w_source,
        platform_watts=platform_watts,
        node_wall_watts=int(node_wall.to_integral_value(rounding=ROUND_CEILING)),
        register_watts=int(register.to_integral_value(rounding=ROUND_CEILING)),
    )
