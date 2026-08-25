"""Model registry and public-input helpers for the receipt_model ZK circuit.

The receipt_model circuit proves a deterministic model execution.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)

_BN128_FQ = 21888242871839275222246405745257275088696311157297823662689037894645226208583
_ZK_CIRCUITS_NODE_MODULES = Path(os.getenv("COORDINATOR_SNARKJS_NODE_PATH", "/opt/aitbc/apps/zk-circuits/node_modules"))


def _node_env() -> dict[str, str]:
    """Environment for a ``node`` subprocess that can require poseidon-lite and snarkjs."""
    env = dict(os.environ)
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


def hash_to_field(value: Any) -> int:
    """Deterministically map an arbitrary value to a bn128 field element."""
    raw = str(value) if value is not None else "0"
    return int(hashlib.sha256(raw.encode()).hexdigest()[:32], 16)


def text_to_field_array(text: Any, n: int) -> list[int]:
    """Map a string to ``n`` field elements."""
    if not isinstance(text, str):
        text = str(text)
    out: list[int] = []
    chunk_size = max(1, len(text) // n + 1)
    for i in range(n):
        chunk = text[i * chunk_size : (i + 1) * chunk_size]
        if not chunk:
            chunk = f"pad-{i}"
        out.append(hash_to_field(chunk))
    return out


def float_to_field(value: Any) -> int:
    """Encode a scalar as a field element."""
    if not isinstance(value, int | float):
        value = float(str(value))
    scaled = int(round(value * 1_000_000))
    return scaled % _BN128_FQ


@dataclass(frozen=True)
class ModelCircuit:
    """A deterministic model that has a receipt_model circuit."""

    name: str
    model_id: int
    input_len: int
    output_len: int
    weight_len: int
    weights: list[int]
    scope: str = ""

    def compute_output(self, input_values: list[int]) -> list[int]:
        """Compute the deterministic output for this model."""
        if len(input_values) != self.output_len:
            raise ValueError(f"input length {len(input_values)} != expected {self.output_len}")
        weight = self.weights[0]
        bias = self.weights[1]
        return [(in_val * weight + bias) % _BN128_FQ for in_val in input_values]

    def get_model_hash(self) -> int:
        """Compute/return the Poseidon hash of the model weights."""
        return _poseidon(self.weights)


_LINEAR_WEIGHT = float_to_field(2.0)
_LINEAR_BIAS = float_to_field(1.0)
LINEAR_MODEL = ModelCircuit(
    name="linear-1",
    model_id=0,
    input_len=4,
    output_len=4,
    weight_len=2,
    weights=[_LINEAR_WEIGHT, _LINEAR_BIAS],
    scope="simple element-wise linear model",
)

MODEL_CIRCUITS: dict[str, ModelCircuit] = {
    LINEAR_MODEL.name: LINEAR_MODEL,
}


def get_model(model_id: str | int | None) -> ModelCircuit | None:
    """Look up a registered model by name or integer model_id."""
    if model_id is None:
        return None
    model_id = str(model_id)
    if model_id in MODEL_CIRCUITS:
        return MODEL_CIRCUITS[model_id]
    for m in MODEL_CIRCUITS.values():
        if str(m.model_id) == model_id:
            return m
    return None


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
    model_hash = model.get_model_hash()
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
