from __future__ import annotations

from typing import Any, Dict

import json
from hashlib import sha256


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
