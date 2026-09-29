#!/usr/bin/env python3
"""Emit the fleet digest spec JSON consumed by ``state-digest-remote.py``.

Single source of truth: the table classification lives in
``aitbc_chain.state.block_deltas`` (CONSENSUS_STATE_TABLES /
SERVICE_STATE_TABLES / AUX_SHIPPED_TABLES / CONSENSUS_SENSITIVE_WATCH /
VOLATILE_DIGEST_COLUMNS / DIGEST_ADDRESS_COLUMNS / DIGEST_COLUMN_ALLOWLIST /
DIGEST_JSON_DROP_KEYS) and the aux natural keys in ``aux_state.AUX_TABLES``.
``fleet-config-check.sh`` runs this once on the control host so every node
digests the same spec even mid-deploy; when no importable checkout exists
the script falls back to the embedded copy, which
``apps/blockchain-node/tests/test_fleet_digest_spec.py`` keeps in parity.

Run from the repo root with ``venv/bin/python``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "apps" / "blockchain-node" / "src"))


def build_spec() -> dict:
    from aitbc_chain.aux_state import AUX_TABLES
    from aitbc_chain.state.block_deltas import (
        AUX_SHIPPED_TABLES,
        CONSENSUS_SENSITIVE_WATCH,
        CONSENSUS_STATE_TABLES,
        DIGEST_ADDRESS_COLUMNS,
        DIGEST_COLUMN_ALLOWLIST,
        DIGEST_JSON_DROP_FALSY,
        DIGEST_JSON_DROP_KEYS,
        SERVICE_STATE_TABLES,
        VOLATILE_DIGEST_COLUMNS,
    )

    tables = {}
    for t in sorted(set(CONSENSUS_STATE_TABLES) | set(SERVICE_STATE_TABLES)):
        cls = (
            "consensus"
            if t in CONSENSUS_STATE_TABLES
            else "aux"
            if t in AUX_SHIPPED_TABLES
            else "watch"
            if t in CONSENSUS_SENSITIVE_WATCH
            else "service"
        )
        allow = DIGEST_COLUMN_ALLOWLIST.get(t)
        tables[t] = {"class": cls, "allow": sorted(allow) if allow else None}
    dupkeys = {}
    for spec in AUX_TABLES.values():
        dupkeys[spec.model.__tablename__] = {
            "key": list(spec.key_fields),
            "addr": list(spec.address_fields),
        }
    # bridge_validators is service-local but carries the same
    # checksum/lowercase twin risk on its (address, epoch) natural key.
    dupkeys["bridge_validators"] = {"key": ["address", "epoch"], "addr": ["address"]}
    return {
        "tables": tables,
        "volatile": sorted(VOLATILE_DIGEST_COLUMNS),
        "addr_cols": sorted(DIGEST_ADDRESS_COLUMNS),
        "json_drop": {k: sorted(v) for k, v in DIGEST_JSON_DROP_KEYS.items()},
        "json_drop_falsy": {k: sorted(v) for k, v in DIGEST_JSON_DROP_FALSY.items()},
        "dupkeys": dupkeys,
    }


if __name__ == "__main__":
    json.dump(build_spec(), sys.stdout, separators=(",", ":"), sort_keys=True)
    print()
