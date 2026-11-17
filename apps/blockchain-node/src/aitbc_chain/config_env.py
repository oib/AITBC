from __future__ import annotations

import os
import uuid

from pydantic import BaseModel

# Re-exported from aitbc.constants rather than spelled out again. This module used to hold its
# own `Path("/var/lib/aitbc")`, which is the same value the shared constant already resolves
# to -- except that the shared one honours `AITBC_DATA_DIR` and this copy did not. That is how
# the test suite came to create `chain-a/` and `chain-sig/`, named after test-only chain IDs,
# inside the deployed data directory: nothing the tests could set moved this path (V23-73).
from aitbc.constants import DATA_DIR

KEYSTORE_DIR = DATA_DIR / "keystore"

# AITBC_CHAIN_ENV_FILE lets tests (and alternate deployments) override the env file
# the chain settings are loaded from. Set it to "" to load no env file.
_chain_env_raw = os.environ.get("AITBC_CHAIN_ENV_FILE")
if _chain_env_raw is None:
    _CHAIN_ENV_FILES: list[str] = ["/etc/aitbc/blockchain.env"]
elif _chain_env_raw:
    _CHAIN_ENV_FILES = [p for p in _chain_env_raw.split(",") if p]
else:
    _CHAIN_ENV_FILES = []


class ProposerConfig(BaseModel):
    chain_id: str
    proposer_id: str
    interval_seconds: int
    max_block_size_bytes: int
    max_txs_per_block: int
    default_peer_rpc_url: str | None = None


# Default island ID for new installations
DEFAULT_ISLAND_ID = str(uuid.uuid4())

# Deliberately unreachable sentinel for the ``state_transition_v*_height``
# thresholds: the chain can never produce block 2**62, so a threshold set to
# it parks that version's rules as dead code (the STOP-rule "cancel the
# activation" path moves both v13 and v14 here).
V13_HEIGHT_NOT_ARMED = 2**62

# Shared ACT-1 activation height (H). From H: v13 binds GOVERNANCE_EXECUTE to
# the sealed GOVERNANCE_PROPOSE's stored execution_payload (V-2); v14 commits
# the 13-table side-table root into the block header as aux_state_root (V-3)
# and turns the bridge-lock missing-data guard from dry-run counting into a
# refusal (V-4). Operator decision 12 Oct: "tomorrow" — about 18:00 UTC on
# 13 Oct at ~68 s per block (head was 44,827 at 18:11 UTC). Environment
# overrides STATE_TRANSITION_V13_HEIGHT / STATE_TRANSITION_V14_HEIGHT keep the
# heights movable (the STOP-rule "move H" path sets BOTH on every host).
SHARED_ACTIVATION_HEIGHT = 46100


UC_TIMING_MARGIN_SECONDS = 5.0  # slack on top of evidence + collect for signing/propagation
