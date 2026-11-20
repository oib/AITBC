"""Shared registry of deterministic ZK circuit models.

These are the pure-Python parts of the coordinator's ``receipt_model``
registry: field encoding helpers, the ``ModelCircuit`` dataclass, and the
``MODEL_CIRCUITS``/``get_model`` lookup. Both ``coordinator-api`` (which
generates the Groth16 proof) and ``miner`` (which must still execute the
circuit locally for the job to COMPLETE, #2330) import from here.

Keep this module free of ``coordinator_api`` imports and of node/subprocess
dependencies — anything needing Poseidon or snarkjs stays in
``coordinator_api.contexts.zk_applications.services.model_registry``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

_BN128_FQ = 21888242871839275222246405745257275088696311157297823662689037894645226208583


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


__all__ = [
    "LINEAR_MODEL",
    "MODEL_CIRCUITS",
    "ModelCircuit",
    "float_to_field",
    "get_model",
    "hash_to_field",
    "text_to_field_array",
]
