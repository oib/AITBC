"""The committed bc-2 genesis allocation pair is pinned by sha256.

`docs/deployment/bc2-genesis/{allocations,classes}.json` are the inputs the
release-candidate build and the runbook's C4 step consume. A pin failure
means a byte changed since the pair was verified — update the pin only when
the change is deliberate and the checker run is repeated on the new bytes:

    venv/bin/python scripts/ops/check-alloc-file.py \
      --allocations docs/deployment/bc2-genesis/allocations.json \
      --classes docs/deployment/bc2-genesis/classes.json \
      --require-classes \
      --treasury-proof <operator-held proof file>

Semantic checks (row counts, the 256-AIT float band, the zero classes, the
treasury proof) are the checker's job — `tests/unit/test_check_alloc_file.py`.
This file exists so any later edit fails loudly, not silently.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
GENESIS_DIR = REPO / "docs" / "deployment" / "bc2-genesis"

PINS = {
    "allocations.json": "ca4a150085cff31e9388ab504c2ed0e855e6f963bbdcbde8875b94872d281fcb",
    "classes.json": "836ae03716a97b130476c8983eb6a8d3dabf9c9eeb03530d85f6cfa69f6cbcb5",
}


@pytest.mark.parametrize("name", sorted(PINS))
def test_bc2_genesis_file_sha256(name: str) -> None:
    path = GENESIS_DIR / name
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == PINS[name], (
        f"{name} drifted from the verified pair ({digest}) — "
        "re-run check-alloc-file.py on the new bytes and update PINS deliberately"
    )
