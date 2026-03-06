from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import json
from hashlib import sha256

from pydantic import BaseModel


class Receipt(BaseModel):
    version: str
    receipt_id: str
    job_id: str
    provider: str
    client: str
    units: float
    unit_type: str
    started_at: int
    completed_at: int
    price: float | None = None
    model: str | None = None
    prompt_hash: str | None = None
    duration_ms: int | None = None
    artifact_hash: str | None = None
    coordinator_id: str | None = None
    nonce: str | None = None
    chain_id: int | None = None
    metadata: Dict[str, Any] | None = None


def canonical_json(receipt: Dict[str, Any]) -> str:
    def remove_none(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: remove_none(v) for k, v in obj.items() if v is not None}
        if isinstance(obj, list):
            return [remove_none(x) for x in obj if x is not None]
        return obj

    cleaned = remove_none(receipt)
    return json.dumps(cleaned, separators=(",", ":"), sort_keys=True)


def receipt_hash(receipt: Dict[str, Any]) -> bytes:
    data = canonical_json(receipt).encode("utf-8")
    return sha256(data).digest()
