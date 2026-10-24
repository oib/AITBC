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

import argparse
import json
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

SEVERITY = {"STOP": "STOP", "INVESTIGATE": "INVESTIGATE", "NOTE": "NOTE"}

GATE_NAMES = [f"STATE_TRANSITION_V{i}_HEIGHT" for i in range(2, 15)] + [
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
        except Exception:
            return e.code, {}
    except Exception as e:
        return -1, {"error": str(e)}


def real_http_post(url: str, body: dict, timeout: int = 5) -> tuple[int, dict]:
    req = urllib.request.Request(  # nosec B310
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
        except Exception:
            return e.code, {}
    except Exception as e:
        return -1, {"error": str(e)}


def real_host_sh(ssh_target: str | None, cmd: str, timeout: int = 15) -> str | None:
    argv = ["ssh", ssh_target, cmd] if ssh_target else ["sh", "-c", cmd]
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return out.stdout if out.returncode == 0 else None
    except Exception:
        return None


def sh(ctx: Ctx, hspec: dict, cmd: str) -> str | None:
    return ctx.host_sh(hspec.get("ssh"), cmd)


def _ssh_curl(ctx: Ctx, alias: str, argv_tail: list[str]) -> tuple[int, dict]:
    """One HTTP request through ``ssh <alias> curl`` — for listeners bound
    to the remote loopback that no local tunnel reaches (manifest
    ``rpc_via_ssh``/``prom_via_ssh``). The remote curl prints the body,
    then ``\\n%{http_code}``; the last stdout line is the status and
    everything above it the body. ``(-1, …)`` marks a transport failure —
    the ssh leg died or curl never printed a status — so ``_retry`` treats
    it exactly like an unanswered socket."""
    cmd = "curl -s -m 10 -w '\\n%{http_code}' " + " ".join(argv_tail)
    out = ctx.host_sh(alias, cmd)
    if not out:
        return -1, {"error": f"ssh {alias} curl: no output"}
    lines = out.splitlines()
    try:
        code = int(lines[-1].strip())
    except (IndexError, ValueError):
        return -1, {"error": f"ssh {alias} curl: bad status line {out[-80:]!r}"}
    try:
        return code, json.loads("\n".join(lines[:-1]))
    except Exception:
        return code, {}


def _get_via_ssh(ctx: Ctx, hspec: dict, url: str) -> tuple[int, dict]:
    alias = hspec.get("ssh")
    if not alias:
        return -1, {"error": "rpc_via_ssh set but host has no ssh alias"}
    return _retry(ctx, lambda: _ssh_curl(ctx, alias, [shlex.quote(url)]))


def hget(ctx: Ctx, hspec: dict, path: str) -> tuple[int, dict]:
    url = hspec["rpc"].rstrip("/") + path
    if hspec.get("rpc_via_ssh"):
        return _get_via_ssh(ctx, hspec, url)
    return _get(ctx, url)


def hpost(ctx: Ctx, hspec: dict, path: str, body: dict) -> tuple[int, dict]:
    url = hspec["rpc"].rstrip("/") + path
    if not hspec.get("rpc_via_ssh"):
        return ctx.http_post(url, body)
    return _retry(
        ctx,
        lambda: _ssh_curl(
            ctx,
            hspec["ssh"],
            [
                "-X",
                "POST",
                "-H",
                shlex.quote("Content-Type: application/json"),
                "--data",
                shlex.quote(json.dumps(body)),
                shlex.quote(url),
            ],
        ),
    )


def _get(ctx: Ctx, url: str) -> tuple[int, dict]:
    return _retry(ctx, lambda: ctx.http_get(url))


def _retry(ctx: Ctx, fetch) -> tuple[int, dict]:
    """Bounded retry on transport failures only.

    ``code == -1`` means the request never got an HTTP answer — timeout,
    refused, or a dropped leg (the ssh-curl legs stall under load the same
    way a dead tunnel does); a short backoff absorbs that without masking
    definitive answers: real status codes, even 5xx, return on the first
    attempt. Tunables: expected.http_attempts (default 3),
    expected.http_retry_backoff_s (default 0.4, doubled per retry).
    """
    exp = ctx.manifest.get("expected") or {}
    attempts = max(1, int(exp.get("http_attempts", 3)))
    backoff = float(exp.get("http_retry_backoff_s", 0.4))
    code, body = fetch()
    for i in range(attempts - 1):
        if code != -1:
            break
        time.sleep(backoff * (2**i))
        code, body = fetch()
    return code, body


# --- HTTP checks ----------------------------------------------------------


def check_proposer_route(ctx: Ctx, name: str, h: dict) -> list[Result]:
    exp = ctx.manifest["expected"]
    code, body = hget(ctx, h, "/rpc/proposer")
    if code != 200:
        return [Result("chain-id-live", name, "STOP", False, "200", str(code))]
    cid = body.get("chain_id")
    sup = body.get("supported_chains")
    ok = cid == exp["chain_id"] and sup == [exp["chain_id"]]
    return [
        Result(
            "chain-id-live",
            name,
            "STOP",
            ok,
            f"{exp['chain_id']} + supported=[{exp['chain_id']}]",
            f"{cid} + supported={sup}",
            f"proposer={body.get('proposer_id')}",
        )
    ]


def check_heads(ctx: Ctx) -> list[Result]:
    out: list[Result] = []
    for name, h in ctx.manifest["hosts"].items():
        code, body = hget(ctx, h, "/rpc/head")
        if code != 200:
            ctx.heads[name] = None
            out.append(Result("head-read", name, "STOP", False, "200", str(code)))
            continue
        ctx.heads[name] = body
        out.append(Result("head-read", name, "STOP", True, "200", "200", f"height={body.get('height')}"))
    heads = {n: (b.get("height"), b.get("hash")) for n, b in ctx.heads.items() if b}
    uniq = set(heads.values())
    out.append(
        Result(
            "head-equality",
            "fleet",
            "STOP",
            len(uniq) == 1 and len(heads) == len(ctx.manifest["hosts"]),
            "one (height, hash) across all hosts",
            f"{len(uniq)} distinct: {sorted(heads.items())}",
        )
    )
    return out


def check_block0(ctx: Ctx) -> list[Result]:
    exp_cid = ctx.manifest["expected"]["chain_id"]
    found: dict[str, tuple] = {}
    fails = []
    for name, h in ctx.manifest["hosts"].items():
        code, body = hget(ctx, h, "/rpc/blocks/0")
        if code != 200:
            fails.append(name)
            continue
        found[name] = (body.get("hash"), body.get("state_root"), body.get("chain_id"))
    uniq = set(found.values())
    ok = not fails and len(uniq) == 1 and next(iter(uniq))[2] == exp_cid and len(found) == len(ctx.manifest["hosts"])
    return [
        Result(
            "block0-equality",
            "fleet",
            "STOP",
            ok,
            f"identical hash+state_root, chain_id={exp_cid}",
            f"{len(uniq)} distinct, unreadable={fails or '-'}",
        )
    ]


def check_quorum(ctx: Ctx) -> list[Result]:
    vals = set(ctx.manifest["expected"].get("validators") or [])
    ref = ctx.heads.get("hub") or next((b for b in ctx.heads.values() if b), None)
    if not ref:
        return [Result("quorum-sweep", "fleet", "STOP", None, "a head to sweep", "no head read")]
    top = min(int(ref.get("height", 0)), 50)
    if top < 1:
        return [Result("quorum-sweep", "fleet", "INVESTIGATE", True, ">=1 produced block", "height 0 — sweep later")]
    bad_heights, proposers = [], set()
    for hgt in range(1, top + 1):
        code, body = hget(ctx, next(iter(ctx.manifest["hosts"].values())), f"/rpc/blocks/{hgt}")
        if code != 200:
            bad_heights.append(f"{hgt}:unreadable")
            continue
        proposers.add(body.get("proposer"))
        meta = body.get("block_metadata") or "{}"
        try:
            atts = json.loads(meta).get("attestations") or []
        except Exception:
            atts = []
        if len(atts) < 2:
            bad_heights.append(f"{hgt}:atts={len(atts)}")
    rows = [
        Result(
            "quorum-sweep",
            "fleet",
            "STOP",
            not bad_heights,
            ">=2 attestations on every produced block",
            f"bad={bad_heights or 'none'} (1..{top})",
        )
    ]
    if vals:
        missing = vals - proposers
        rows.append(
            Result(
                "proposer-rotation",
                "fleet",
                "INVESTIGATE",
                not missing,
                "every validator has proposed",
                f"missing={sorted(missing) or 'none'} seen={len(proposers & vals)}/{len(vals)}",
            )
        )
    return rows


# SOAK-GATE-WINDOW-1: the 23 Oct hub outage (2h14m dark, zero proposals in
# ~135 consecutive blocks) passed every point-in-time row because
# proposer-rotation only asks presence in the sweep range. These checks
# answer "was every validator working through the window", not "is every
# validator working now". Thresholds are manifest-tunable under expected.*.


def check_head_progression(ctx: Ctx) -> list[Result]:
    """head_at_run must strictly exceed the baseline-capture head.

    Catches the hub-only-proposer-stall case where head-equality goes green
    on equal stale heads. Needs expected.baseline_head_height in the
    manifest (set from the baseline capture's head).
    """
    base = ctx.manifest["expected"].get("baseline_head_height")
    if base is None:
        return [Result("head-progression", "fleet", "INVESTIGATE", None, "expected.baseline_head_height", "not configured")]
    heights = {n: int(b.get("height", 0)) for n, b in ctx.heads.items() if b}
    if not heights:
        return [Result("head-progression", "fleet", "STOP", None, "a head read", "no head read")]
    head = max(heights.values())
    return [
        Result(
            "head-progression",
            "fleet",
            "INVESTIGATE",
            head > int(base),
            f"head > baseline {base}",
            f"head={head}",
        )
    ]


def _proposer(b: dict) -> str:
    return (b.get("proposer") or "").lower()


def check_validator_coverage(ctx: Ctx) -> list[Result]:
    """Per-validator windowed coverage: max silent run and proposal share.

    Window = (window_start, head_at_run] read from hub's block table via
    /rpc/blocks-range?start&end (proposer column only — attestations add
    nothing per the 23 Oct data). expected.window_start picks the window's
    start height (baseline 5 = whole post-cut history incl. the 21-22 Oct
    stall era; a later pick scopes to the soak after it). Falls back to
    expected.baseline_head_height when unset — head-progression always
    uses baseline_head_height, they answer different questions.

    A validator fails when its longest run of consecutive blocks it did
    not propose exceeds expected.coverage_max_silent_run (default 40,
    ~45 min at 66 s cadence), or its in-window proposals fall below
    expected.coverage_min_share x window_blocks/n_validators (default
    0.4 — tolerates single missed slots, not hours-long absences).
    """
    exp = ctx.manifest["expected"]
    vals = exp.get("validators") or []
    base = exp.get("window_start", exp.get("baseline_head_height"))
    if not vals or base is None:
        return [
            Result(
                "validator-coverage",
                "fleet",
                "INVESTIGATE",
                None,
                "expected.validators + window_start|baseline_head_height",
                "not configured",
            )
        ]
    ref = ctx.heads.get("hub") or next((b for b in ctx.heads.values() if b), None)
    head = int(ref.get("height", 0)) if ref else 0
    start = int(base) + 1
    if head < start:
        return [
            Result(
                "validator-coverage",
                "fleet",
                "INVESTIGATE",
                None,
                f"non-empty window ({start}..head]",
                f"head={head} baseline={base}",
            )
        ]
    hub = ctx.manifest["hosts"].get("hub") or next(iter(ctx.manifest["hosts"].values()))
    code, body = hget(ctx, hub, f"/rpc/blocks-range?start={start}&end={head}&include_tx=false")
    if code != 200:
        return [Result("validator-coverage", "fleet", "INVESTIGATE", None, "200", str(code))]
    blocks = body.get("blocks") or []
    window = len(blocks)
    max_silent = int(exp.get("coverage_max_silent_run", 40))
    share_floor = float(exp.get("coverage_min_share", 0.4))
    expected_share = window / len(vals)
    rows: list[Result] = []
    for v in vals:
        vl = v.lower()
        proposals = 0
        silent = run = 0
        for b in blocks:
            if _proposer(b) == vl:
                proposals += 1
                run = 0
            else:
                run += 1
                silent = max(silent, run)
        ok = silent <= max_silent and proposals >= expected_share * share_floor
        rows.append(
            Result(
                "validator-coverage",
                v[:8],
                "INVESTIGATE",
                ok,
                f"silent<={max_silent} proposals>={share_floor}x{expected_share:.1f}",
                f"silent={silent} proposals={proposals}/{window}",
            )
        )
    return rows


def _snapshot_accounts(body: dict) -> dict[str, int]:
    out = {}
    for a in body.get("accounts") or []:
        try:
            out[a["address"]] = int(a.get("balance", 0))
        except Exception:
            continue
    return out


def check_supply_alloc(ctx: Ctx) -> list[Result]:
    exp = ctx.manifest["expected"]
    hub = ctx.manifest["hosts"].get("hub") or next(iter(ctx.manifest["hosts"].values()))
    code, body = hget(ctx, hub, "/rpc/state/snapshot")
    if code != 200:
        return [Result("supply-total", "fleet", "STOP", None, "200", str(code))]
    accounts = _snapshot_accounts(body)
    total = sum(accounts.values())
    rows = [
        Result(
            "supply-total",
            "fleet",
            "STOP",
            str(total) == str(exp["supply_units"]),
            exp["supply_units"],
            str(total),
            f"{len(accounts)} accounts",
        )
    ]
    alloc_file = exp.get("allocations_file")
    if alloc_file:
        try:
            allocs = {a["address"]: int(a["balance"]) for a in json.loads(open(alloc_file).read())}
        except Exception as e:
            allocs = None
            rows.append(Result("alloc-classes", "fleet", "STOP", False, "allocations file parses", str(e)))
        if allocs is not None:
            mism = [a for a, bal in allocs.items() if accounts.get(a) != bal]
            extra = [a for a in accounts if a not in allocs]
            rows.append(
                Result(
                    "alloc-classes",
                    "fleet",
                    "STOP",
                    not mism and not extra,
                    f"{len(allocs)} addresses at file balances",
                    f"mismatched={len(mism)} unexpected={len(extra)}",
                    (f"first={mism[:2] + extra[:2]}" if (mism or extra) else ""),
                )
            )
    return rows


def check_bridge(ctx: Ctx) -> list[Result]:
    rows: list[Result] = []
    hub = ctx.manifest["hosts"].get("hub") or next(iter(ctx.manifest["hosts"].values()))
    code, _ = hget(ctx, hub, "/rpc/bridge/pending")
    rows.append(Result("bridge-route", "hub", "INVESTIGATE", code == 200, "200", str(code)))
    if not ctx.probe:
        # Default pause evidence stays the env grep + the GET reads — the
        # POST is a write-shaped request and runs only on the operator's
        # line via --probe.
        rows.append(
            Result(
                "bridge-paused-probe",
                "hub",
                "STOP",
                None,
                "POST lock → 503",
                "not run (pass --probe with the operator's line)",
            )
        )
    else:
        # Schema-minimal body: pydantic validation runs before the pause
        # fence, but the fence still raises ahead of signature verification
        # and all bridge work — the dummy signature is never checked, so the
        # probe stays refuse-only and cannot lock anything even unpaused.
        probe = {
            "target_chain": "probe",
            "sender": "0x0000000000000000000000000000000000000001",
            "recipient": "0x0000000000000000000000000000000000000001",
            "amount": 1,
            "signature": "0x00",
        }
        code, body = hpost(ctx, hub, "/rpc/bridge/lock", probe)
        detail = json.dumps(body)[:80]
        ok = code == 503
        rows.append(
            Result(
                "bridge-paused-probe",
                "hub",
                "STOP",
                ok,
                "503 (admission refuses before signing)",
                str(code),
                detail,
            )
        )
    return rows


def check_mempool(ctx: Ctx) -> list[Result]:
    hub = ctx.manifest["hosts"].get("hub") or next(iter(ctx.manifest["hosts"].values()))
    code, body = hget(ctx, hub, "/rpc/mempool")
    if code != 200:
        return [Result("mempool", "hub", "NOTE", None, "200", str(code))]
    n = len(body.get("transactions") or body.get("txs") or body.get("pending") or [])
    return [Result("mempool", "hub", "NOTE", True, "read ok", f"{n} pending")]


def check_pages(ctx: Ctx) -> list[Result]:
    rows: list[Result] = []
    cid = ctx.manifest["expected"]["chain_id"]
    for name, h in ctx.manifest["hosts"].items():
        for key, chk in (("explorer_url", "explorer"), ("website_url", "website")):
            url = h.get(key)
            if not url:
                continue
            code, body = _get(ctx, url)
            text = json.dumps(body)[:400] if isinstance(body, (dict, list)) else str(body)[:400]
            rows.append(Result(chk, name, "INVESTIGATE", code == 200, "200 + bc-2 visible", f"{code} {cid in text}"))
    if not rows:
        rows.append(Result("pages", "fleet", "INVESTIGATE", None, "explorer_url/website_url in manifest", "none configured"))
    return rows


def check_alerts(ctx: Ctx) -> list[Result]:
    prom = ctx.manifest.get("prom_url")
    if not prom:
        return [Result("alerts-quiet", "fleet", "NOTE", None, "prom_url in manifest", "not configured")]
    if ctx.manifest.get("prom_via_ssh"):
        # loopback-only Prometheus (e.g. hub 127.0.0.1:9090): fetch through
        # ``ssh <alias> curl`` instead of a dead local tunnel end.
        pspec = {"ssh": ctx.manifest["prom_via_ssh"], "rpc": prom, "rpc_via_ssh": True}
        code, body = hget(ctx, pspec, "/api/v1/alerts")
    else:
        code, body = _get(ctx, prom.rstrip("/") + "/api/v1/alerts")
    if code != 200:
        return [Result("alerts-quiet", "fleet", "INVESTIGATE", False, "200", str(code))]
    firing = [a["labels"]["alertname"] for a in body.get("data", {}).get("alerts", []) if a.get("state") == "firing"]
    allowed = set(ctx.manifest["expected"].get("expected_noise") or [])
    # SOAK-GATE-WINDOW-1 card ruling: the V9 pair fires for hours on
    # healthy chains. expected.v9_alert_mode picks the treatment — a
    # one-line manifest change flips the ruling either way:
    #   "split"   (default, confirmed ruling): expected noise only while
    #             the pair fires alone with uniform heads; flag on
    #             co-occurrence with AttestationArrivalDegraded or any
    #             mempool alert, or on non-uniform heads.
    #   "surface": the pair is always unexpected when firing.
    #   "noise"  : the pair is always expected noise.
    v9_pair = {"V9AttestationRefusal", "V9ShadowRejection"}
    mode = ctx.manifest["expected"].get("v9_alert_mode", "split")
    flag_v9 = False
    if mode == "noise":
        allowed |= v9_pair
    elif mode == "split":
        co = [a for a in firing if a == "AttestationArrivalDegraded" or "empool" in a]
        heads = {(b.get("height"), b.get("hash")) for b in ctx.heads.values() if b}
        if len(heads) == 1 and not co:
            allowed |= v9_pair
        else:
            flag_v9 = bool(v9_pair & set(firing))
    # "surface": the pair is simply never added to allowed.
    unexpected = [a for a in firing if a not in allowed]
    return [
        Result(
            "alerts-quiet",
            "fleet",
            "INVESTIGATE" if unexpected else "NOTE",
            not unexpected,
            f"only expected noise {sorted(allowed) or '[]'}",
            f"firing={firing or 'none'}",
            "flag_v9" if flag_v9 else "",
        )
    ]


# --- Host-shell checks (ssh or local) -------------------------------------


def check_env(ctx: Ctx, name: str, h: dict) -> list[Result]:
    env_dir = h.get("env_dir")
    if not env_dir:
        return [Result("env-pins", name, "STOP", None, "env_dir in manifest", "absent")]
    exp_env: dict = ctx.manifest["expected"].get("env") or {}
    bad, missing, denied = [], [], []
    for ename, want in exp_env.items():
        if ename not in ALLOWED_ENV_NAMES:
            denied.append(ename)
            continue
        out = sh(ctx, h, f"grep -h '^{ename}=' {env_dir}/*.env 2>/dev/null")
        vals = [ln.split("=", 1)[1].strip() for ln in (out or "").splitlines() if "=" in ln]
        # Shell-sourced env files (rehearsal instance.env) quote values; the
        # process sees the unquoted string — compare like-for-like.
        lines = [v[1:-1] if len(v) > 1 and v[0] == v[-1] and v[0] in "'\"" else v for v in vals]
        if not lines:
            missing.append(ename)
            continue
        for v in lines:
            if v != str(want):
                bad.append(f"{ename}={v} (want {want})")
    ok = not bad and not missing and not denied
    return [
        Result(
            "env-pins",
            name,
            "STOP",
            ok,
            f"{len(exp_env)} names pinned in every file holding them",
            f"bad={bad or 'none'} missing={missing or 'none'} denied={denied or 'none'}",
        )
    ]


def check_genesis_file(ctx: Ctx, name: str, h: dict) -> list[Result]:
    exp = ctx.manifest["expected"]
    want = exp.get("genesis_sha256")
    path = f"{h.get('data_dir', '/var/lib/aitbc/data')}/{exp['chain_id']}/genesis.json"
    if not want:
        return [Result("genesis-file", name, "STOP", None, "expected.genesis_sha256", "absent")]
    out = sh(ctx, h, f"sha256sum {shlex.quote(path)}")
    got = out.split()[0] if out else None
    return [Result("genesis-file", name, "STOP", got == want, want[:16] + "…", (got or "unreadable")[:16] + "…")]


def check_no_stray_dbs(ctx: Ctx, name: str, h: dict) -> list[Result]:
    exp = ctx.manifest["expected"]
    data_dir = h.get("data_dir", "/var/lib/aitbc/data")
    out = sh(ctx, h, f"find {shlex.quote(data_dir)} -name chain.db 2>/dev/null")
    paths = [p for p in (out or "").splitlines() if p.strip()]
    allowed = f"/{exp['chain_id']}/chain.db"
    stray = [p for p in paths if not p.endswith(allowed)]
    return [
        Result(
            "no-stray-chaindb",
            name,
            "STOP",
            not stray,
            f"only */{exp['chain_id']}/chain.db under data/",
            str(stray or "clean"),
        )
    ]


def _systemd_ts_epoch(ctx: Ctx, h: dict, unit: str) -> int | None:
    # systemd prints e.g. 'Mon 2026-10-20 07:40:00 UTC'; convert on the host.
    out = sh(
        ctx,
        h,
        "ts=$(systemctl show " + shlex.quote(unit) + ' -p ActiveEnterTimestamp --value); [ -n "$ts" ] && date -d "$ts" +%s',
    )
    try:
        return int((out or "").strip())
    except ValueError:
        return None


def check_units(ctx: Ctx, name: str, h: dict) -> list[Result]:
    rows: list[Result] = []
    units = h.get("units") or []
    if not units:
        return [Result("units-fresh", name, "STOP", None, "units list in manifest", "empty")]
    bad, stale = [], []
    for u in units:
        out = sh(ctx, h, f"systemctl is-active {shlex.quote(u)}")
        if (out or "").strip() != "active":
            bad.append(u)
            continue
        if ctx.window_start_epoch:
            ts = _systemd_ts_epoch(ctx, h, u)
            if ts is None or ts < ctx.window_start_epoch:
                stale.append(u)
    rows.append(
        Result(
            "units-fresh",
            name,
            "STOP",
            not bad and not stale,
            f"{len(units)} units active" + (" + fresh timestamps" if ctx.window_start_epoch else ""),
            f"inactive={bad or 'none'} stale={stale or 'none'}",
        )
    )
    expected_inactive = h.get("expected_inactive") or {}
    if expected_inactive:
        up = []
        for u in expected_inactive:
            out = sh(ctx, h, f"systemctl is-active {shlex.quote(u)}")
            if (out or "").strip() == "active":
                up.append(u)
        rows.append(
            Result(
                "units-expected-inactive",
                name,
                "STOP",
                not up,
                f"{len(expected_inactive)} units expected inactive (oneshot/held)",
                f"unexpectedly-active={up or 'none'}",
            )
        )
    return rows


def check_journal(ctx: Ctx, name: str, h: dict) -> list[Result]:
    node_log = h.get("node_log")  # harness nodes log to a file, not journald
    if node_log:
        out = sh(ctx, h, f"cat {shlex.quote(node_log)} 2>/dev/null")
    else:
        unit = h.get("node_unit")
        if not unit:
            return [Result("journal-evidence", name, "STOP", None, "node_unit/node_log in manifest", "absent")]
        since = f'--since "{ctx.manifest.get("window_start")}"' if ctx.manifest.get("window_start") else ""
        out = sh(ctx, h, f"journalctl -u {shlex.quote(unit)} {since} -o cat --no-pager 2>/dev/null")
    if out is None:
        return [Result("journal-evidence", name, "STOP", None, "journal/log readable", "no output")]
    created = out.count("Successfully created genesis block from genesis.json")
    init = out.count("Initializing databases for chains")
    cid = ctx.manifest["expected"]["chain_id"]
    init_bc2 = f"['{cid}']" in out or f'["{cid}"]' in out
    # SOAK-GATE-WINDOW-1 baseline refresh: genesis-created markers age out
    # of journal retention, so absence is no longer a fail — but a count
    # above 1 would still mean the chain was re-created.
    ok = created <= 1 and init >= 1 and init_bc2
    return [
        Result(
            "journal-evidence",
            name,
            "STOP",
            ok,
            f"genesis-created <=1 + init ['{cid}']",
            f"created={created} init={init} bc2={init_bc2}",
        )
    ]


def check_timers(ctx: Ctx, name: str, h: dict) -> list[Result]:
    timers = h.get("timers") or []
    if not timers:
        return [Result("timers-resumed", name, "INVESTIGATE", None, "timers list in manifest", "none listed")]
    inactive = []
    for t in timers:
        out = sh(ctx, h, f"systemctl is-active {shlex.quote(t)}")
        if (out or "").strip() != "active":
            inactive.append(t)
    return [
        Result(
            "timers-resumed",
            name,
            "INVESTIGATE",
            not inactive,
            f"{len(timers)} timers active again (B0 restore)",
            f"inactive={inactive or 'none'}",
        )
    ]


def check_stores(ctx: Ctx, name: str, h: dict) -> list[Result]:
    stores = h.get("stores") or {}
    if not stores:
        return [Result("service-stores", name, "INVESTIGATE", None, "stores map in manifest", "none listed")]
    data_dir = h.get("data_dir", "/var/lib/aitbc/data")
    bad = []
    count_tables = "SELECT count(*) FROM sqlite_master WHERE type='table'"
    for db, want in stores.items():
        db_path = f"{data_dir}/{db}"
        out = sh(
            ctx,
            h,
            f"[ -f {shlex.quote(db_path)} ] && sqlite3 -readonly 'file:{db_path}?mode=ro' \"{count_tables}\"",  # nosec B608 — constant query; only the file URI interpolates
        )
        try:
            got = int((out or "").strip())
        except ValueError:
            got = -1
        if got != int(want):
            bad.append(f"{db}={got}!={want}")
    return [
        Result(
            "service-stores",
            name,
            "INVESTIGATE",
            not bad,
            "table counts per manifest",
            f"bad={bad or 'none'}",
        )
    ]


# --- runner ----------------------------------------------------------------


def _apply_overrides(h: dict, produced: list[Result]) -> list[Result]:
    """Honor per-host ``check_overrides`` manifest entries.

    ``check_overrides.<check-name>.skip: true`` replaces the check's
    results with a SKIP row carrying ``reason`` — used for checks that
    can never pass again (e.g. journal-evidence after journald rotates
    past the genesis window) so the gate stops reporting them as FAIL.
    """
    overrides = h.get("check_overrides") or {}
    out: list[Result] = []
    for r in produced:
        ov = overrides.get(r.check) or {}
        if ov.get("skip"):
            out.append(
                Result(
                    r.check,
                    r.host,
                    r.severity,
                    None,
                    "check_overrides.skip",
                    ov.get("reason", "skipped by manifest"),
                )
            )
        else:
            out.append(r)
    return out


def per_host_env_checks(ctx: Ctx) -> list[Result]:
    rows: list[Result] = []
    for name, h in ctx.manifest["hosts"].items():
        for fn in (
            check_env,
            check_genesis_file,
            check_no_stray_dbs,
            check_units,
            check_journal,
            check_timers,
            check_stores,
        ):
            rows.extend(_apply_overrides(h, fn(ctx, name, h)))
        rows.extend(_apply_overrides(h, check_proposer_route(ctx, name, h)))
    return rows


def run(ctx: Ctx) -> list[Result]:
    rows: list[Result] = []
    rows.extend(check_heads(ctx))
    rows.extend(check_block0(ctx))
    rows.extend(check_quorum(ctx))
    rows.extend(check_head_progression(ctx))
    rows.extend(check_validator_coverage(ctx))
    rows.extend(check_supply_alloc(ctx))
    rows.extend(check_bridge(ctx))
    rows.extend(check_mempool(ctx))
    rows.extend(check_pages(ctx))
    rows.extend(check_alerts(ctx))
    rows.extend(per_host_env_checks(ctx))
    return rows


def worst(rows: list[Result]) -> int:
    return 1 if any(r.ok is False for r in rows) else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--window-start", default=None, help="recorded cut start; enables fresh-timestamp checks")
    ap.add_argument("--window-start-epoch", type=int, default=None)
    ap.add_argument(
        "--probe",
        action="store_true",
        help="run the POST /rpc/bridge/lock refuse-probe — a write-shaped request that needs the operator's line; off by default",
    )
    ap.add_argument("--output", choices=["table", "json"], default="table")
    args = ap.parse_args(argv)

    manifest = json.loads(open(args.manifest).read())
    if args.window_start:
        manifest["window_start"] = args.window_start
    epoch = args.window_start_epoch
    if epoch is None and args.window_start:
        out = subprocess.run(["date", "-d", args.window_start, "+%s"], capture_output=True, text=True)
        if out.returncode == 0:
            epoch = int(out.stdout.strip())

    ctx = Ctx(
        manifest=manifest,
        http_get=real_http_get,
        http_post=real_http_post,
        host_sh=real_host_sh,
        window_start_epoch=epoch,
        probe=args.probe,
    )
    rows = run(ctx)

    if args.output == "json":
        print(json.dumps([r.__dict__ for r in rows], indent=2))
    else:
        for r in rows:
            print(r.line())
        fails = [r for r in rows if r.ok is False]
        skips = sum(1 for r in rows if r.ok is None)
        print(f"--- {len(rows) - len(fails) - skips} PASS, {len(fails)} FAIL, {skips} SKIP")
    return worst(rows)


if __name__ == "__main__":
    sys.exit(main())
