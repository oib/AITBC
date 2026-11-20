"""Model registry and public-input helpers for the receipt_model ZK circuit.

The receipt_model circuit proves a deterministic model execution.

The pure-Python registry (``ModelCircuit``, ``MODEL_CIRCUITS``, ``get_model``,
field encoding) lives in ``aitbc.zk_model_circuits`` so the miner can execute
registered circuit models locally (#2330); this module re-exports those names
and keeps the coordinator-only Poseidon/snarkjs helpers.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.utils.env import subprocess_env
from aitbc.zk_model_circuits import (
    LINEAR_MODEL,
    MODEL_CIRCUITS,
    ModelCircuit,
    float_to_field,
    get_model,
    hash_to_field,
    text_to_field_array,
)

__all__ = [
    "LINEAR_MODEL",
    "MODEL_CIRCUITS",
    "ModelCircuit",
    "compute_public_inputs",
    "expected_public_signals",
    "float_to_field",
    "get_model",
    "get_model_hash",
    "hash_to_field",
    "resolve_model_id",
    "text_to_field_array",
]

logger = get_logger(__name__)

# Default derived relative to this file rather than hardcoded to /opt/aitbc: the
# CI runner checks the repo out to its own ephemeral workspace, not /opt/aitbc.
_REPO_ROOT = Path(__file__).resolve().parents[7]
_ZK_CIRCUITS_NODE_MODULES = Path(os.getenv("COORDINATOR_SNARKJS_NODE_PATH", str(_REPO_ROOT / "apps/zk-circuits/node_modules")))


def _node_env() -> dict[str, str]:
    """Environment for a ``node`` subprocess that can require poseidon-lite and snarkjs."""
    env = subprocess_env()
    inherited = env.get("NODE_PATH", "")
    env["NODE_PATH"] = f"{_ZK_CIRCUITS_NODE_MODULES}{os.pathsep}{inherited}" if inherited else str(_ZK_CIRCUITS_NODE_MODULES)
    return env


def _poseidon(inputs: list[int]) -> int:
    """Compute Poseidon hash of ``inputs`` using poseidon-lite."""
    n = len(inputs)
    if not 1 <= n <= 16:
        raise ValueError(f"poseidon-lite supports 1-16 inputs, got {n}")
    fn = f"poseidon{n}"
    script = (
        f"const {{{fn}}} = require('poseidon-lite');\n"
        f"const inputs = {json.dumps([str(v) for v in inputs])}.map(BigInt);\n"
        f"console.log({fn}(inputs).toString());\n"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
        f.write(script)
        script_file = f.name
    try:
        result = subprocess.run(
            ["node", script_file],
            capture_output=True,
            text=True,
            env=_node_env(),
        )
        if result.returncode != 0:
            raise RuntimeError(f"Poseidon computation failed: {result.stderr}")
        return int(result.stdout.strip())
    finally:
        os.unlink(script_file)


def get_model_hash(model: ModelCircuit) -> int:
    """Compute the Poseidon hash of a circuit model's weights.

    Coordinator-side: needs the node/poseidon-lite toolchain, so it cannot
    live in the shared ``aitbc.zk_model_circuits`` module the miner imports.
    """
    return _poseidon(model.weights)


def resolve_model_id(job: Any, result: Any) -> str | None:
    """Extract the model identifier from a job and result."""
    if job and job.payload:
        if job.payload.get("model"):
            return str(job.payload["model"])
        if job.payload.get("model_id"):
            return str(job.payload["model_id"])
    constraints = getattr(job, "constraints", None) or {}
    if isinstance(constraints, dict):
        models = constraints.get("models")
        if models:
            return str(models[0])
        if constraints.get("model"):
            return str(constraints["model"])
    if isinstance(result, dict):
        if result.get("model"):
            return str(result["model"])
        if result.get("model_id"):
            return str(result["model_id"])
    return None


def compute_public_inputs(
    job: Any,
    result: Any,
    model: ModelCircuit,
) -> dict[str, Any]:
    """Return the public inputs and private witness for a receipt_model proof."""
    input_text = ""
    if job and job.payload:
        input_text = str(job.payload.get("prompt", job.payload.get("input", "")))
    if isinstance(result, dict):
        str(result.get("output") or result.get("result") or "")
    elif result is not None:
        str(result)

    input_values = text_to_field_array(input_text, model.input_len)
    output_values = model.compute_output(input_values)

    input_hash = _poseidon(input_values)
    model_hash = get_model_hash(model)
    output_hash = _poseidon(output_values)

    return {
        "public_inputs": {
            "input_hash": str(input_hash),
            "model_hash": str(model_hash),
            "output_hash": str(output_hash),
            "model_id": str(model.model_id),
        },
        "private_inputs": {
            "input_values": [str(v) for v in input_values],
            "weights": [str(v) for v in model.weights],
            "output_values": [str(v) for v in output_values],
        },
    }


def expected_public_signals(public_inputs: dict[str, Any]) -> list[str]:
    """Return the ordered public signals expected from a receipt_model proof."""
    return [
        str(public_inputs["input_hash"]),
        str(public_inputs["model_hash"]),
        str(public_inputs["output_hash"]),
        str(public_inputs["model_id"]),
    ]
