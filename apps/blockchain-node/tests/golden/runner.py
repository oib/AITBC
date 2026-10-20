"""Golden-corpus runner: record expected outputs, check code against them, diff profiles.

Usage (from ``apps/blockchain-node``, with ``src`` and ``tests`` importable):

    cd apps/blockchain-node
    PYTHONPATH=src:tests python -m golden.runner record --profile deployed

    runner.py record --profile deployed
    runner.py record --profile gates0
    runner.py check  --profile deployed      # exit 1 on any divergence
    runner.py diff   deployed gates0         # per-vector profile comparison
    runner.py coverage                       # what the corpus exercises

``record``/``check`` run every case in ``cases/`` (the real-history stream
plus every ``cases/synthetic/*.json``) under the named profile and either
write or compare ``expected/<profile>/...``. Running ``record`` twice on the
same code and comparing the trees byte-for-byte is the determinism proof.
"""

from __future__ import annotations

import argparse
import atexit
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

GOLDEN_DIR = Path(__file__).resolve().parent
CASES_DIR = GOLDEN_DIR / "cases"
EXPECTED_DIR = GOLDEN_DIR / "expected"
STREAM_CHAIN_ID = "gv-real-history"


def _chain_env(data_dir: Path) -> None:
    """Point the chain at a scratch data dir and away from any deployment
    env file BEFORE aitbc_chain is imported (settings binds env at import)."""
    os.environ["AITBC_DATA_DIR"] = str(data_dir)
    os.environ.setdefault("AITBC_CHAIN_ENV_FILE", "")
    os.environ.setdefault("AITBC_ENABLE_RATE_LIMITING", "false")


def _imports():
    """Late imports so env is bound first when running as a CLI."""
    from aitbc_chain.config import settings

    from . import engine, profiles

    return settings, engine, profiles


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _load_cases(cases_dir: Path) -> list[dict[str, Any]]:
    cases = []
    for path in sorted((cases_dir / "synthetic").glob("*.json")):
        cases.append(json.loads(path.read_text()))
    return cases


def _load_stream(cases_dir: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[dict[str, Any]]]:
    """Return (genesis_state, manifest, tx-bearing blocks in height order)."""
    genesis_path = cases_dir / "genesis-state.json"
    manifest_path = cases_dir / "stream-manifest.json"
    stream_dir = cases_dir / "stream"
    genesis = json.loads(genesis_path.read_text()) if genesis_path.exists() else None
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else None
    blocks = [json.loads(p.read_text()) for p in sorted(stream_dir.glob("*.json"))] if stream_dir.is_dir() else []
    return genesis, manifest, blocks


def _settings_snapshot(settings: Any) -> dict[str, Any]:
    """Deep-copy the live settings instance state so a profile run can be
    unwound. ``apply_profile`` setattrs the gate heights; callers embedding
    the runner (the pytest oracle) share the process-wide singleton, so the
    pre-run values must come back or later tests resolve every gate at the
    last profile's pins."""
    return copy.deepcopy(vars(settings))


def _settings_restore(settings: Any, snapshot: dict[str, Any]) -> None:
    """Put back the snapshotted instance state, also dropping attributes the
    run added."""
    vars(settings).clear()
    vars(settings).update(snapshot)


def run_stream(genesis: dict[str, Any], blocks: list[dict[str, Any]], profile: str) -> list[dict[str, Any]]:
    """Replay the real-history stream through the sequential apply path and
    return one output record per tx-bearing block."""
    settings, engine, profiles = _imports()
    snapshot = _settings_snapshot(settings)
    try:
        profiles.apply_profile(settings, profile)
        # The stream replays under the REAL chain id — sealed transactions carry it
        # and apply's chain-isolation check refuses a mismatch.
        chain_id = genesis["source"]["chain_id"]

        engine.reset_chain(chain_id)
        session = engine.open_session(chain_id)
        try:
            engine.seed_genesis(session, chain_id, genesis)
            st = engine.StateTransition()
            outputs = []
            for entry in blocks:
                outputs.append(
                    engine.apply_block(
                        session,
                        st,
                        chain_id,
                        copy.deepcopy(entry["block"]),
                        copy.deepcopy(entry["txs"]),
                    )
                )
            return outputs
        finally:
            session.close()
    finally:
        _settings_restore(settings, snapshot)


def run_case(case: dict[str, Any], profile: str) -> dict[str, Any]:
    """Seed the case's pre-state into a fresh scratch chain and apply its block."""
    settings, engine, profiles = _imports()
    snapshot = _settings_snapshot(settings)
    try:
        profiles.apply_profile(settings, profile)
        case_id = case["case_id"]
        # Cases may carry their own chain id (defaults to a shared scratch id);
        # tx chain_id fields must match it or apply's isolation check refuses.
        chain_id = case.get("chain_id") or "gv-synth"

        engine.reset_chain(chain_id)
        session = engine.open_session(chain_id)
        try:
            for table, rows in (case.get("prestate") or {}).items():
                engine.seed_rows(session, table, rows)
            session.commit()
            st = engine.StateTransition()
            txs = case.get("txs") if "txs" in case else [case["tx"]]
            out = engine.apply_block(
                session,
                st,
                chain_id,
                copy.deepcopy(case["block"]),
                copy.deepcopy(txs),
            )
            return {"case_id": case_id, "profile": profile, "block": out}
        finally:
            session.close()
    finally:
        _settings_restore(settings, snapshot)


def _record(profile: str, cases_dir: Path, expected_dir: Path) -> dict[str, Any]:
    out_dir = expected_dir / profile
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "synthetic").mkdir(exist_ok=True)

    cases = _load_cases(cases_dir)
    genesis, header, blocks = _load_stream(cases_dir)

    summary: dict[str, Any] = {"profile": profile, "cases": {}, "stream": None}
    for case in cases:
        result = run_case(case, profile)
        (out_dir / "synthetic" / f"{case['case_id']}.json").write_text(_canon(result) + "\n")
        txs = result["block"]["txs"]
        summary["cases"][case["case_id"]] = txs[0]["verdict"] if txs else "no-txs"

    if genesis and blocks:
        outputs = run_stream(genesis, blocks, profile)
        stream_out = out_dir / "stream"
        stream_out.mkdir(exist_ok=True)
        for out in outputs:
            (stream_out / f"{out['height']:08d}.json").write_text(_canon(out) + "\n")
        (out_dir / "stream-manifest.json").write_text(
            _canon(
                {
                    "kind": "stream-manifest",
                    "profile": profile,
                    "source": header,
                }
            )
            + "\n"
        )
        summary["stream"] = {
            "blocks": len(outputs),
            "txs": sum(len(o["txs"]) for o in outputs),
            "state_root_mismatches": sum(1 for o in outputs if not o["state_root_match"]),
            "aux_mismatches": sum(1 for o in outputs if o["aux_state_root"]["match"] is False),
        }
    return summary


def _prime(cases_dir: Path, profile: str, max_iters: int = 8) -> dict[str, Any]:
    """Iterate the stream replay, raising bootstrap balances until no
    'Insufficient balance' reject remains.

    The extractor's bootstrap is a *lower bound*: it credits ``recipient`` for
    every sealed tx, but escrow/stake/bridge locks move value to custody rows
    instead — so a recipient counted as funded may never have received the
    units. Rather than reimplement per-type credit semantics, the prime pass
    asks the apply path itself what each account lacked, and tops the
    bootstrap up by the shortfall. The result is a documented minimum replay
    funding; the per-block ``state_root_match`` then measures fidelity.

    Rewrites ``cases/genesis-state.json`` in place (bumps are recorded in each
    account's ``prime_topups`` list for provenance).
    """
    import re

    pattern = re.compile(r"Insufficient balance for (\S+): (\d+) < (\d+)")
    genesis_path = cases_dir / "genesis-state.json"
    genesis = json.loads(genesis_path.read_text())
    _, _, blocks = _load_stream(cases_dir)
    boots = {a["address"].lower(): a for a in genesis.get("bootstrap_accounts", [])}
    iterations = []
    shortfalls: dict[str, int] = {}
    for _ in range(max_iters):
        outputs = run_stream(genesis, blocks, profile)
        shortfalls = {}
        for out in outputs:
            for tx in out["txs"]:
                m = pattern.match(tx.get("reason", ""))
                if m and tx["verdict"] == "rejected":
                    addr, have, need = m.group(1).lower(), int(m.group(2)), int(m.group(3))
                    shortfalls[addr] = max(shortfalls.get(addr, 0), need - have)
        if not shortfalls:
            break
        iterations.append(dict(sorted(shortfalls.items())))
        for addr, gap in shortfalls.items():
            boot = boots.get(addr)
            if boot is None:
                boot = {"address": addr, "balance": 0, "nonce": 0, "prime_topups": []}
                genesis.setdefault("bootstrap_accounts", []).append(boot)
                boots[addr] = boot
            boot["balance"] = int(boot["balance"]) + gap
            boot.setdefault("prime_topups", []).append(gap)
        genesis_path.write_text(json.dumps(genesis, sort_keys=True, indent=1) + "\n")
    return {
        "iterations": len(iterations),
        "converged": not shortfalls,
        "topups": iterations,
    }


def _diff_obj(path: str, expected: Any, actual: Any, diffs: list[dict[str, Any]]) -> None:
    if type(expected) is not type(actual):
        diffs.append({"path": path, "expected": expected, "actual": actual})
        return
    if isinstance(expected, dict):
        for key in sorted(set(expected) | set(actual)):
            if key not in expected:
                diffs.append({"path": f"{path}.{key}", "expected": "<absent>", "actual": actual[key]})
            elif key not in actual:
                diffs.append({"path": f"{path}.{key}", "expected": expected[key], "actual": "<absent>"})
            else:
                _diff_obj(f"{path}.{key}", expected[key], actual[key], diffs)
    elif isinstance(expected, list):
        if len(expected) != len(actual):
            diffs.append({"path": f"{path}.len", "expected": len(expected), "actual": len(actual)})
        for i, (e, a) in enumerate(zip(expected, actual, strict=False)):
            _diff_obj(f"{path}[{i}]", e, a, diffs)
    elif expected != actual:
        diffs.append({"path": path, "expected": expected, "actual": actual})


def _check(profile: str, cases_dir: Path, expected_dir: Path) -> list[dict[str, Any]]:
    out_dir = expected_dir / profile
    diffs: list[dict[str, Any]] = []
    cases = _load_cases(cases_dir)
    genesis, _, blocks = _load_stream(cases_dir)

    for case in cases:
        expected_path = out_dir / "synthetic" / f"{case['case_id']}.json"
        result = run_case(case, profile)
        if not expected_path.exists():
            diffs.append({"path": case["case_id"], "expected": "<recorded>", "actual": "<no expected file>"})
            continue
        expected = json.loads(expected_path.read_text())
        _diff_obj(case["case_id"], expected, result, diffs)

    if genesis and blocks:
        outputs = run_stream(genesis, blocks, profile)
        stream_dir = out_dir / "stream"
        for out in outputs:
            expected_path = stream_dir / f"{out['height']:08d}.json"
            label = f"stream/{out['height']}"
            if not expected_path.exists():
                diffs.append({"path": label, "expected": "<recorded>", "actual": "<no expected file>"})
                continue
            _diff_obj(label, json.loads(expected_path.read_text()), out, diffs)
    return diffs


def _profile_diff(a: str, b: str, expected_dir: Path) -> dict[str, Any]:
    report: dict[str, Any] = {"a": a, "b": b, "cases": {}}
    dir_a, dir_b = expected_dir / a, expected_dir / b
    names = sorted(p.stem for p in (dir_a / "synthetic").glob("*.json"))
    for name in names:
        ea = json.loads((dir_a / "synthetic" / f"{name}.json").read_text())
        eb_path = dir_b / "synthetic" / f"{name}.json"
        if not eb_path.exists():
            report["cases"][name] = [{"path": name, "expected": "recorded", "actual": "missing"}]
            continue
        diffs: list[dict[str, Any]] = []
        _diff_obj(name, ea, json.loads(eb_path.read_text()), diffs)
        # The profile name itself is recorded in each file — not a divergence.
        diffs = [d for d in diffs if not d["path"].endswith(".profile")]
        report["cases"][name] = diffs
    return report


def _coverage(cases_dir: Path, expected_dir: Path) -> dict[str, Any]:
    cases = _load_cases(cases_dir)
    genesis, manifest, blocks = _load_stream(cases_dir)
    by_gate: dict[str, list[str]] = {}
    for case in cases:
        by_gate.setdefault(case.get("gate", "unlabelled"), []).append(case["case_id"])
    return {
        "synthetic_cases": len(cases),
        "by_gate": {g: sorted(ids) for g, ids in sorted(by_gate.items())},
        "real_stream": None
        if manifest is None
        else {
            "tx_bearing_blocks": manifest.get("tx_bearing_blocks"),
            "transactions": manifest.get("transactions"),
            "empty_blocks": manifest.get("empty_blocks"),
            "tip_height": manifest.get("tip_height"),
        },
        "profiles_recorded": sorted(p.name for p in expected_dir.iterdir() if p.is_dir()),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cases-dir", type=Path, default=CASES_DIR)
    ap.add_argument("--expected-dir", type=Path, default=EXPECTED_DIR)
    sub = ap.add_subparsers(dest="command", required=True)
    for cmd in ("record", "check"):
        p = sub.add_parser(cmd)
        p.add_argument("--profile", required=True, choices=["deployed", "gates0", "gates1"])
    pprime = sub.add_parser(
        "prime", help="iterate the stream, topping up bootstrap balances until no insufficiency rejects remain"
    )
    pprime.add_argument("--profile", default="deployed", choices=["deployed", "gates0", "gates1"])
    pdiff = sub.add_parser("diff")
    pdiff.add_argument("a")
    pdiff.add_argument("b")
    sub.add_parser("coverage")
    sub.add_parser("code-commit")
    sub.add_parser("dump-cases", help="regenerate cases/synthetic/*.json from synthetic_cases.cases()")
    args = ap.parse_args(argv)

    workdir = Path(tempfile.mkdtemp(prefix="golden-vectors-"))
    atexit.register(shutil.rmtree, workdir, True)
    _chain_env(workdir)

    if args.command == "code-commit":
        print(subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip())
        return 0
    if args.command == "dump-cases":
        from golden import synthetic_cases

        syn_dir = args.cases_dir / "synthetic"
        syn_dir.mkdir(parents=True, exist_ok=True)
        for case in synthetic_cases.cases():
            (syn_dir / f"{case['case_id']}.json").write_text(json.dumps(case, sort_keys=True, indent=1) + "\n")
        print(json.dumps({"written": len(synthetic_cases.cases())}))
        return 0
    if args.command == "coverage":
        print(json.dumps(_coverage(args.cases_dir, args.expected_dir), indent=1, sort_keys=True))
        return 0
    if args.command == "diff":
        print(json.dumps(_profile_diff(args.a, args.b, args.expected_dir), indent=1, sort_keys=True))
        return 0
    if args.command == "record":
        summary = _record(args.profile, args.cases_dir, args.expected_dir)
        print(json.dumps(summary, indent=1, sort_keys=True))
        return 0
    if args.command == "prime":
        print(json.dumps(_prime(args.cases_dir, args.profile), indent=1, sort_keys=True))
        return 0
    diffs = _check(args.profile, args.cases_dir, args.expected_dir)
    if diffs:
        print(json.dumps({"profile": args.profile, "mismatches": len(diffs), "diffs": diffs}, indent=1, sort_keys=True))
        return 1
    print(json.dumps({"profile": args.profile, "mismatches": 0}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
