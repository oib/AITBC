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
the admission gate refuses before any envelope is signed.

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
      "hosts": {
        "hub": {"ssh": "hub", "rpc": "http://hub:8303", "env_dir": "/etc/aitbc",
                "data_dir": "/var/lib/aitbc/data", "node_unit": "aitbc-blockchain-node",
                "units": ["aitbc-blockchain-node", …], "timers": ["aitbc-backup.timer", …],
                "stores": {"coordinator_api.db": 170},
                "explorer_url": "http://…", "validator": true},
        "i0": {"rpc": "http://127.0.0.1:18402", "env_dir": "<scratch>/i0",
               "data_dir": "<scratch>/i0/data", "node_unit": "bc2-i0-node.service", …}
      }
    }

A host without ``ssh`` runs its file/systemd commands locally — that is how
the rehearsal harness exercises the same checks: manifest entries point at
scratch env files, scratch data dirs and the transient systemd-run units.

Usage:
    post-cut-verify.py --manifest fleet.json [--window-start "2026-10-20 08:00 UTC"]
                       [--skip-probe] [--output table|json]

Exit codes: 0 = every check PASS/NOTE/SKIP, 1 = any FAIL, 2 = run error.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field

SEVERITY = {"STOP": "STOP", "INVESTIGATE": "INVESTIGATE", "NOTE": "NOTE"}

GATE_NAMES = [f"STATE_TRANSITION_V{i}_HEIGHT" for i in range(2, 15)] + [
    "BRIDGE_LOCK_LEAF_V2_HEIGHT",
    "ESCROW_FEE_SWEEP_PASS_MIN_HEIGHT",
]


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
    skip_probe: bool = False
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


def hget(ctx: Ctx, hspec: dict, path: str) -> tuple[int, dict]:
    return ctx.http_get(hspec["rpc"].rstrip("/") + path)


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
    if ctx.skip_probe:
        rows.append(Result("bridge-paused-probe", "hub", "STOP", None, "POST lock → 503", "skipped (--skip-probe)"))
    else:
        code, body = ctx.http_post(hub["rpc"].rstrip("/") + "/rpc/bridge/lock", {})
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
            code, body = ctx.http_get(url)
            text = json.dumps(body)[:400] if isinstance(body, (dict, list)) else str(body)[:400]
            rows.append(Result(chk, name, "INVESTIGATE", code == 200, "200 + bc-2 visible", f"{code} {cid in text}"))
    if not rows:
        rows.append(Result("pages", "fleet", "INVESTIGATE", None, "explorer_url/website_url in manifest", "none configured"))
    return rows


def check_alerts(ctx: Ctx) -> list[Result]:
    prom = ctx.manifest.get("prom_url")
    if not prom:
        return [Result("alerts-quiet", "fleet", "NOTE", None, "prom_url in manifest", "not configured")]
    code, body = ctx.http_get(prom.rstrip("/") + "/api/v1/alerts")
    if code != 200:
        return [Result("alerts-quiet", "fleet", "INVESTIGATE", False, "200", str(code))]
    firing = [a["labels"]["alertname"] for a in body.get("data", {}).get("alerts", []) if a.get("state") == "firing"]
    allowed = set(ctx.manifest["expected"].get("expected_noise") or [])
    unexpected = [a for a in firing if a not in allowed]
    return [
        Result(
            "alerts-quiet",
            "fleet",
            "INVESTIGATE" if unexpected else "NOTE",
            not unexpected,
            f"only expected noise {sorted(allowed) or '[]'}",
            f"firing={firing or 'none'}",
        )
    ]


# --- Host-shell checks (ssh or local) -------------------------------------


def check_env(ctx: Ctx, name: str, h: dict) -> list[Result]:
    env_dir = h.get("env_dir")
    if not env_dir:
        return [Result("env-pins", name, "STOP", None, "env_dir in manifest", "absent")]
    exp_env: dict = ctx.manifest["expected"].get("env") or {}
    bad, missing = [], []
    for ename, want in exp_env.items():
        out = sh(ctx, h, f"grep -h '^{ename}=' {env_dir}/*.env 2>/dev/null")
        lines = [ln.split("=", 1)[1].strip() for ln in (out or "").splitlines() if "=" in ln]
        if not lines:
            missing.append(ename)
            continue
        for v in lines:
            if v != str(want):
                bad.append(f"{ename}={v} (want {want})")
    ok = not bad and not missing
    return [
        Result(
            "env-pins",
            name,
            "STOP",
            ok,
            f"{len(exp_env)} names pinned in every file holding them",
            f"bad={bad or 'none'} missing={missing or 'none'}",
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
    ok = created == 1 and init >= 1 and init_bc2
    return [
        Result(
            "journal-evidence",
            name,
            "STOP",
            ok,
            f"genesis-created ×1 + init ['{cid}']",
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
    for db, want in stores.items():
        out = sh(
            ctx,
            h,
            f"sqlite3 'file:{data_dir}/{db}?mode=ro' \"SELECT count(*) FROM sqlite_master WHERE type='table'\"",
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
            rows.extend(fn(ctx, name, h))
        rows.extend(check_proposer_route(ctx, name, h))
    return rows


def run(ctx: Ctx) -> list[Result]:
    rows: list[Result] = []
    rows.extend(check_heads(ctx))
    rows.extend(check_block0(ctx))
    rows.extend(check_quorum(ctx))
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
    ap.add_argument("--skip-probe", action="store_true", help="skip the POST /rpc/bridge/lock refuse-probe")
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
        skip_probe=args.skip_probe,
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
