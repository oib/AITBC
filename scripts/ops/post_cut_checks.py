#!/usr/bin/env python3
"""post_cut_checks.py — check functions for post-cut-verify.py (#1860 band split).

This file is NOT a standalone module: post-cut-verify.py loads it with
``exec(..., globals())`` so every check keeps resolving ``Result``, ``Ctx``,
``hget``/``hpost``/``sh``/``_get`` and the manifest constants in the
verifying script's own namespace — the same surface tests reach through
``spec_from_file_location``. Do not import it directly.
"""

# ruff: noqa: F821
# (names resolve in post-cut-verify.py's globals at exec time)

import argparse
import shlex

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
        except (RecursionError, ValueError, TypeError, AttributeError):
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
        except (KeyError, OverflowError, TypeError, ValueError, AttributeError):
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
        except (OSError, OverflowError, ValueError, KeyError, TypeError) as e:
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
                # Deliberately opt-in — a skipped probe verifies nothing but is
                # not a gate failure; NOTE keeps it out of the STOP-SKIP=2 rule.
                "NOTE",
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
            # 200 alone proves nothing — the old chain's explorer answers 200
            # too; the new chain id must appear in the body (#1004).
            rows.append(
                Result(chk, name, "INVESTIGATE", code == 200 and cid in text, "200 + bc-2 visible", f"{code} {cid in text}")
            )
    if not rows:
        rows.append(Result("pages", "fleet", "INVESTIGATE", None, "explorer_url/website_url in manifest", "none configured"))
    return rows


def check_alerts(ctx: Ctx) -> list[Result]:
    prom = ctx.manifest.get("prom_url")
    if not prom:
        return [Result("alerts-quiet", "fleet", "NOTE", None, "prom_url in manifest", "not configured")]
    prom_alias = ctx.manifest.get("prom_via_ssh")
    if prom_alias and not isinstance(prom_alias, str):
        # "prom_via_ssh": true fails cryptically inside host_sh — name the
        # expected type instead (unlike rpc_via_ssh, this takes the alias).
        return [Result("alerts-quiet", "fleet", "INVESTIGATE", False, "prom_via_ssh = ssh alias string", repr(prom_alias))]
    if prom_alias:
        # loopback-only Prometheus (e.g. hub 127.0.0.1:9090): fetch through
        # ``ssh <alias> curl`` instead of a dead local tunnel end.
        pspec = {"ssh": prom_alias, "rpc": prom, "rpc_via_ssh": True}
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
    out = sh(ctx, h, f"find {shlex.quote(data_dir)} -name chain.db -printf '%s %p\\n' 2>/dev/null")
    if out is None:
        # No output at all is an unreadable host, not an empty result (#1003).
        return [
            Result(
                "no-stray-chaindb",
                name,
                "STOP",
                None,
                f"only */{exp['chain_id']}/chain.db under data/",
                "unreadable",
                "host command returned nothing",
            )
        ]
    allowed = f"/{exp['chain_id']}/chain.db"
    glob_pat = exp.get("old_chain_glob")
    if glob_pat:
        old_dirs = sh(ctx, h, f"find {shlex.quote(data_dir)} -maxdepth 2 -name {shlex.quote(glob_pat)} 2>/dev/null")
        if old_dirs and old_dirs.strip():
            return [
                Result(
                    "no-stray-chaindb",
                    name,
                    "STOP",
                    False,
                    f"no {glob_pat} under data/",
                    old_dirs.strip(),
                    "leftover old-chain directory",
                )
            ]
    empty, nonempty = [], []
    for line in (out or "").splitlines():
        size, _, path = line.strip().partition(" ")
        if path and not path.endswith(allowed):
            (nonempty if size not in ("", "0") else empty).append(path)
    if nonempty:
        return [
            Result(
                "no-stray-chaindb",
                name,
                "STOP",
                False,
                f"only */{exp['chain_id']}/chain.db under data/",
                str(sorted(nonempty + empty)),
                f"non-empty stray chain.db: {nonempty}",
            )
        ]
    return [
        Result(
            "no-stray-chaindb",
            name,
            "INVESTIGATE" if empty else "STOP",
            True,
            f"only */{exp['chain_id']}/chain.db under data/",
            str(sorted(empty) or "clean"),
            "zero-byte stray(s) — sqlite auto-create accident, not state" if empty else "",
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
    # A SKIP on a STOP-severity row means the gate could not read the thing it
    # exists to verify — that is a run error (2), not a pass (#1003). The only
    # exempt SKIP is an operator's check_overrides entry, which is deliberate.
    if any(r.ok is False for r in rows):
        return 1
    if any(r.ok is None and r.severity == "STOP" and r.expected != "check_overrides.skip" for r in rows):
        return 2
    return 0


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
