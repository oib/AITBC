"""CONSENSUS-PIN-DIGEST-1 (#1723): a comparable digest of the effective
consensus pins and consensus-visible flags.

Partial arming cannot be detected from one node — stripping a
``CONSENSUS_*_HEIGHT`` pin forked mesh-2's hub on 10 Nov (#1301). This
module hashes the effective values so /health and one startup log line let
a serial arm compare digests across validators before arming.

Scope (deliberately narrow — the digest must be IDENTICAL on correctly
configured validators, so node-local tuning stays out):

* every ``state_transition_v*_height`` activation pin (the same set
  ``scripts/monitoring/fleet-config-check.sh`` watches, v2–v25),
* ``consensus_*``, ``pbft_*`` and ``multi_validator_*`` settings — the
  consensus rule flags, thresholds and round timings that change what a
  validator will attest/propose,
* ``sync_require_state_root_height``-style ``*_height`` pins are covered
  only when they live under those prefixes; bridge/finality knobs are
  service-local and excluded on purpose.

No secrets: every covered field is a height, flag, count or timeout.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .config import ChainSettings, settings

_CONSENSUS_PREFIXES = ("state_transition_", "consensus_", "pbft_", "multi_validator_")


def consensus_config_fields(cfg: ChainSettings | None = None) -> dict[str, Any]:
    """Effective consensus-visible settings, sorted by field name."""
    cfg = cfg if cfg is not None else settings
    return {name: getattr(cfg, name) for name in sorted(type(cfg).model_fields) if name.startswith(_CONSENSUS_PREFIXES)}


def consensus_config_digest(cfg: ChainSettings | None = None) -> str:
    """SHA-256 over the canonical JSON of the consensus-visible fields.

    Two validators agree iff their effective pins/flags agree — compare the
    hex strings, never the field map (which stays server-side).
    """
    payload = json.dumps(
        consensus_config_fields(cfg),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
