#!/usr/bin/env python3
"""post-cut-verify.py — one read-only verification sweep across the bc-2 fleet.

RESET-POSTCUT-1 (#337). After the cut the operator needs a single run that
says the new chain is right: same genesis everywhere, heads equal and
moving, the decided env set landed on every file that carries each name,
bridges paused at the admission gate, balances match the allocation file,
units came up fresh, and nothing still points at the old chain.

Every check is a small function returning ``CheckResult`` rows
(check, host, status, expected, found, detail) so unit tests feed canned
responses and the same code runs against the rehearsal harness
(``--manifest`` describing scratch instances) and the live fleet.

Read layers per the tooling order: HTTP GET against each node's rpc
listener first, plain HTTP probes second, and a host shell (``ssh <host>``
or local commands when ``ssh`` is absent from the manifest) only for what
has no HTTP surface — env-file name reads (anchored ``^NAME=`` only, never
values beyond the compared names), ``systemctl show``, ``journalctl``,
``sha256sum`` and read-only ``sqlite3``. Nothing here opens a wallet or
keystore; the only write-shaped request is the bridge-lock probe, which
the admission gate refuses before any envelope is signed — it is off by
default and runs only under ``--probe`` on the operator's line.

Manifest (JSON):

    {
      "expected": {
        "chain_id": "bc-2",
        "genesis_sha256": "…",
        "supply_units": "3600009216000000",
        "allocations_file": "allocations.json",   # builder format [{address,balance}]
        "env": {"CHAIN_ID": "bc-2", "STATE_TRANSITION_V2_HEIGHT": "1", …},
        "validators": ["0x…", …],
        "trusted_proposers": "genesis,0x…,…",
        "old_chain_glob": "ait-hub*",             # names that must NOT appear under data/
        "expected_noise": ["BackupSizeCollapse", …]
      },
      "prom_url": "http://127.0.0.1:9090",   # optional; "prom_via_ssh": "<alias>"
                                             # fetches it through ssh <alias> curl
      "hosts": {
        "hub": {"ssh": "hub", "rpc": "http://hub:8303", "env_dir": "/etc/aitbc",
                "data_dir": "/var/lib/aitbc/data", "node_unit": "aitbc-blockchain-node",
                "units": ["aitbc-blockchain-node", …], "timers": ["aitbc-backup.timer", …],
                "stores": {"coordinator_api.db": 170},
                "explorer_url": "http://…", "validator": true},
        "n0": {"ssh": "n0", "rpc": "http://127.0.0.1:8202", "rpc_via_ssh": true, …},
               # rpc_via_ssh: rpc names the REMOTE loopback listener; every
               # GET/POST runs as `ssh n0 curl …` — no local tunnel needed.
        "i0": {"rpc": "http://127.0.0.1:18402", "env_dir": "<scratch>/i0",
               "data_dir": "<scratch>/i0/data", "node_unit": "bc2-i0-node.service", …}
      }
    }

A host without ``ssh`` runs its file/systemd commands locally — that is how
the rehearsal harness exercises the same checks: manifest entries point at
scratch env files, scratch data dirs and the transient systemd-run units.

Usage:
    post-cut-verify.py --manifest fleet.json [--window-start "2026-10-20 08:00 UTC"]
                       [--probe] [--output table|json]

Exit codes: 0 = every check PASS/NOTE/SKIP, 1 = any FAIL, 2 = run error.
"""

from __future__ import annotations
import importlib.util
from pathlib import Path

import http.client
import json
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field

SEVERITY = {"STOP": "STOP", "INVESTIGATE": "INVESTIGATE", "NOTE": "NOTE"}

GATE_NAMES = [f"STATE_TRANSITION_V{i}_HEIGHT" for i in range(2, 22)] + [
    "BRIDGE_LOCK_LEAF_V2_HEIGHT",
    "ESCROW_FEE_SWEEP_PASS_MIN_HEIGHT",
]

# env-pin names the manifest may ask this script to grep. Deliberately
# excludes secret/key-bearing names (PROPOSER_KEY, VALIDATOR_KEYS,
# DB_PASS, DATABASE_URL, *_API_KEY, wallet material): a manifest must not
# be able to point the verifier at a name whose value would land in the
# output. Extend only deliberately.
ALLOWED_ENV_NAMES = frozenset(GATE_NAMES) | frozenset(
    """
    AITBC_CHAIN_ENV_FILE AITBC_CONFIG_DIR AITBC_DATA_DIR AITBC_DEFAULT_WALLET
    AITBC_LOG_DIR AITBC_SYNC_IMPORT_URL AITBC_SYNC_SOURCE
    ATTESTATION_POST_QUORUM_LINGER_SECONDS AUTO_SYNC_ENABLED AUTO_SYNC_THRESHOLD
    BLOCK_PRODUCTION_CHAINS BLOCK_TIME_SECONDS BLOCKCHAIN_RPC_URL
    BOND_BURN_ADDRESS BOND_SLASH_AUTHORITY_ADDRESS
    BRIDGE_ADMIN_ADDRESS BRIDGE_ADMIN_ADDRESSES BRIDGE_BLOCK_SIGNATURE_REQUIRED
    BRIDGE_FINALITY_BLOCKS BRIDGE_LOCK_LEAF_V2 BRIDGE_LOCK_REQUIRE_REPLAY_GUARD
    BRIDGE_LOCKS_PAUSED BRIDGE_MAX_LOCK_AMOUNT BRIDGE_MIN_CONFIRMATIONS
    BRIDGE_MULTISIG_ENABLED BRIDGE_MULTISIG_THRESHOLD BRIDGE_MULTISIG_TIMEOUT
    BRIDGE_MULTISIG_VALIDATORS BRIDGE_RELAYER_ENABLED BRIDGE_RELEASE_AUTHORITY
    BRIDGE_RELEASE_ENABLED BRIDGE_REQUIRE_MERKLE_PROOF BRIDGE_ROOT_SHADOW_CHECK
    BRIDGE_SUPPORTED_CHAINS BRIDGE_VALIDATOR_SET_GRACE_PERIOD
    BRIDGE_VERIFICATION_MODE CHAIN_ID CROSS_CHAIN_REQUIRE_REPLAY_GUARD
    DB_TYPE DEFAULT_PEER_RPC_URL ENABLE_BLOCK_PRODUCTION ESCROW_FEE_RECIPIENT
    ESCROW_RELEASE_ADDRESS GENESIS_ADDRESS GENESIS_WALLET_ADDRESS
    GOSSIP_AUTH_ENABLED GOSSIP_BACKEND GOSSIP_MAX_CONCURRENT_CONNECTIONS_PER_IP
    GOSSIP_MESH_PEER_URLS GOSSIP_PROTOCOL_VERSION GOSSIP_WEBSOCKET_URL
    GPU_RETIRED_IDS HUB_BLOCKCHAIN_RPC_URL HUB_DISCOVERY_URL HUB_RPC_URL
    MARKET_ROLE MAX_EMPTY_BLOCK_INTERVAL MEMPOOL_BACKEND
    MULTI_VALIDATOR_ATTESTATION_TIMEOUT_SECONDS MULTI_VALIDATOR_CONSENSUS_ENABLED
    MULTI_VALIDATOR_MIN_ATTESTATIONS NATIVE_CHAIN_ID NETWORK_ID
    P2P_BIND_HOST P2P_BIND_PORT P2P_NODE_ID PARALLEL_TX_VALIDATION
    PBFT_CONSENSUS_ENABLED PBFT_VIEW_CHANGE_TIMEOUT POOL_HUB_URL PROPOSER_ID
    RPC_BIND_HOST RPC_BIND_PORT SIDE_ROOT_SHADOW_ENABLED STATE_SYNC_MAX_GAP
    STATE_TRANSITION_V2 SUBSCRIPTION_ENABLED SUBSCRIPTION_TRANSPORT
    SUPPORTED_CHAINS SYNC_MANAGER_ENABLED SYNC_STATE_ROOT_VALIDATION_ENABLED
    SYNC_VALIDATE_SIGNATURES TRUSTED_PROPOSERS VALIDATOR_SET WALLET_DIR
    WALLET_PORT
    """.split()
)


@dataclass
class Result:
    check: str
    host: str
    severity: str
    ok: bool | None  # None = SKIP
    expected: str
    found: str
    detail: str = ""

    def line(self) -> str:
        status = "SKIP" if self.ok is None else ("PASS" if self.ok else "FAIL")
        return f"{status:4} {self.severity:11} {self.host:7} {self.check:22} expected {self.expected} found {self.found} {self.detail}".rstrip()


@dataclass
class Ctx:
    manifest: dict
    http_get: object = None
    http_post: object = None
    host_sh: object = None
    window_start_epoch: int | None = None
    probe: bool = False
    heads: dict = field(default_factory=dict)


# --- I/O layers (injected for tests) -------------------------------------


def real_http_get(url: str, timeout: int = 5) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:  # nosec B310
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except (OSError, RecursionError, ValueError, http.client.HTTPException):
            return e.code, {}
    except (OSError, RecursionError, ValueError, http.client.HTTPException) as e:
        return -1, {"error": str(e)}


def real_http_post(url: str, body: dict, timeout: int = 5) -> tuple[int, dict]:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # nosec B310
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except (OSError, RecursionError, ValueError, http.client.HTTPException):
            return e.code, {}
    except (OSError, RecursionError, ValueError, http.client.HTTPException) as e:
        return -1, {"error": str(e)}


def real_host_sh(ssh_target: str | None, cmd: str, timeout: int = 15) -> str | None:
    argv = ["ssh", ssh_target, cmd] if ssh_target else ["sh", "-c", cmd]
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return out.stdout if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


# Shared host-HTTP transport: ops_http.py sits next to this file and is
# loaded by location because tests load this script via
# spec_from_file_location (no package import is possible). Names are
# re-bound so every existing caller — including run-postcut.py's
# ``pcv.`` attribute access — keeps working.
_spec = importlib.util.spec_from_file_location("aitbc_ops_http", Path(__file__).resolve().with_name("ops_http.py"))
_ops_http = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ops_http)

sh = _ops_http.sh
_ssh_curl = _ops_http._ssh_curl
_get_via_ssh = _ops_http._get_via_ssh
hget = _ops_http.hget
hpost = _ops_http.hpost
_get = _ops_http._get
_retry = _ops_http._retry


# --- checks (moved verbatim to post_cut_checks.py, #1860 band split) ------
#
# exec'd in this module's globals so ``pcv.check_*`` attribute access and
# the injected ``Ctx.http_get``/``host_sh`` transport keep working exactly
# as before; the fragment is not importable on its own.
_checks_path = Path(__file__).resolve().with_name("post_cut_checks.py")
exec(compile(_checks_path.read_text(encoding="utf-8"), str(_checks_path), "exec"), globals())  # nosec


if __name__ == "__main__":
    sys.exit(main())  # noqa: F821 — defined by the exec'd fragment
