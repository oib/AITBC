#!/usr/bin/env python3
"""unpause-precheck.py — read-only GO/NO-GO sweep before the F5 bridge-lock unpause.

BC2-UNPAUSE-1 (#354). The operator's F5 line flips ``BRIDGE_LOCKS_PAUSED``
to ``false`` fleet-wide; this tool is the read that must print GO first.
It proves, without sending a transaction or touching a key:

- the post-cut verifier ran green (``--post-cut-report`` consumes a saved
  ``post-cut-verify.py --output json`` run — the soak-end gate);
- the F4 funding landed (both post-soak accounts carry a balance);
- every file that carries ``BRIDGE_LOCKS_PAUSED`` still reads ``true``
  (the edit has not partially landed);
- ``BRIDGE_CONTRACT_ADDRESS`` is set in the bridge monitor's env file and
  equals the redeployed contract the operator names;
- the named contract is really on Sepolia — ``eth_getCode`` non-empty,
  ``owner()`` equals the expected Safe, ``getThreshold()`` meets the
  expected threshold (plain JSON-RPC reads, no key);
- the fleet's heads agree (validators on one tip).

Read layers mirror ``post-cut-verify.py``: HTTP GET/POST against each
node's rpc listener, ``eth_*`` JSON-RPC reads against the Sepolia endpoint,
and a host shell (``ssh <host>`` or local when no ``ssh`` key is in the
manifest) only for anchored ``^NAME=`` env greps — the two names this
tool reads (``BRIDGE_LOCKS_PAUSED``, ``BRIDGE_CONTRACT_ADDRESS``) are
public knobs, never secrets. Nothing here opens a wallet or keystore and
nothing is written anywhere.

Manifest (JSON)::

    {
      "expected": {
        "chain_id": "bc-2",
        "f4_accounts": ["0x40c7…", "0x356d…"],
        "pause_files": {"hub": ["blockchain.env", "bootstrap.env"],
                        "hub1": ["blockchain.env"], "node0": ["blockchain.env"],
                        "node1": ["blockchain.env"], "node2": ["blockchain.env"]},
        "monitor_env": {"host": "hub", "file": "aitbc-bridge-monitor.env"}
      },
      "hosts": {"hub": {"ssh": "hub", "rpc": "http://hub:8303",
                        "env_dir": "/etc/aitbc"}, …},
      "sepolia": {"rpc": "https://…", "contract": "0x…",
                  "safe": "0x…", "threshold": 2}
    }

A host without ``ssh`` runs its greps locally (rehearsal harness style).

Usage:
    unpause-precheck.py --manifest fleet.json \
        --post-cut-report postcut.json [--output table|json]

Exit codes: 0 = GO (every STOP check passed), 1 = NO-GO, 2 = run error.
"""

from __future__ import annotations
import importlib.util
from pathlib import Path

import argparse
import json
import shlex
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field

# Selector constants for the two read-only Sepolia calls.
OWNER_SELECTOR = "0x8da5cb5b"  # owner()
GETTHRESHOLD_SELECTOR = "0xe75235b8"  # getThreshold()


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
    report: list | None = None
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


def real_http_post(url: str, body: dict, timeout: int = 8) -> tuple[int, dict]:
    req = urllib.request.Request(  # nosec B310
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "aitbc-ops/1.0"},
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


# Shared host-HTTP transport: ops_http.py sits next to this file and is
# loaded by location because tests load this script via
# spec_from_file_location (no package import is possible). Names are
# re-bound so every existing caller — including run-postcut.py's
# ``pcv.`` attribute access — keeps working.
_spec = importlib.util.spec_from_file_location("aitbc_ops_http", Path(__file__).resolve().with_name("ops_http.py"))
_ops_http = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ops_http)

sh = _ops_http.sh
hget = _ops_http.hget


def eth_rpc(ctx: Ctx, method: str, params: list) -> str | None:
    """One JSON-RPC call against the manifest's Sepolia endpoint; returns
    the hex ``result`` or None on any transport/rpc error."""
    spec = ctx.manifest.get("sepolia") or {}
    url = spec.get("rpc")
    if not url:
        return None
    code, body = ctx.http_post(
        url.rstrip("/"),
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
    )
    if code != 200 or not isinstance(body, dict) or body.get("error"):
        return None
    return body.get("result")


def _grep_anchor(ctx: Ctx, hspec: dict, env_dir: str, fname: str, name: str) -> str | None:
    """Anchored ``^NAME=`` read in one env file; returns the raw value or
    None when absent/unreadable. Only the two public names this tool is
    built for may be read — anything else is refused outright."""
    if name not in ("BRIDGE_LOCKS_PAUSED", "BRIDGE_CONTRACT_ADDRESS"):
        raise ValueError(f"unpause-precheck may not read {name}")
    out = sh(ctx, hspec, f"grep -h '^{name}=' {shlex.quote(env_dir)}/{shlex.quote(fname)} 2>/dev/null")
    if not out:
        return None
    line = out.splitlines()[0].strip()
    if "=" not in line:
        return None
    val = line.split("=", 1)[1].strip()
    if len(val) > 1 and val[0] == val[-1] and val[0] in "'\"":
        val = val[1:-1]
    return val


# --- checks ----------------------------------------------------------------


def check_postcut_report(ctx: Ctx) -> list[Result]:
    if ctx.report is None:
        return [
            Result(
                "postcut-verify",
                "fleet",
                "STOP",
                False,
                "saved --output json run, zero FAIL",
                "no --post-cut-report given",
            )
        ]
    fails = [r for r in ctx.report if r.get("ok") is False]
    return [
        Result(
            "postcut-verify",
            "fleet",
            "STOP",
            not fails,
            "zero FAIL rows in saved report",
            f"{len(ctx.report)} rows, {len(fails)} FAIL",
            "; ".join(f"{r.get('check')}@{r.get('host')}" for r in fails[:4]),
        )
    ]


def check_heads_agree(ctx: Ctx) -> list[Result]:
    heads: dict[str, int] = {}
    hashes: dict[str, str] = {}
    for name, h in ctx.manifest["hosts"].items():
        code, body = hget(ctx, h, "/rpc/head")
        blk = body.get("block") or body
        height = blk.get("height")
        bhash = blk.get("hash") or blk.get("block_hash")
        if code != 200 or height is None:
            return [Result("heads-agree", name, "STOP", False, "/rpc/head 200 + height", f"code={code}")]
        heads[name] = int(height)
        hashes[name] = str(bhash)
    spread = max(heads.values()) - min(heads.values())
    same_tip = spread <= 1
    return [
        Result(
            "heads-agree",
            "fleet",
            "STOP",
            same_tip,
            "all hosts within 1 height",
            f"spread={spread} heads={heads}",
        )
    ]


def check_f4_balances(ctx: Ctx) -> list[Result]:
    rows: list[Result] = []
    hub = ctx.manifest["hosts"].get("hub") or next(iter(ctx.manifest["hosts"].values()))
    for addr in ctx.manifest["expected"].get("f4_accounts") or []:
        code, body = hget(ctx, hub, f"/rpc/account/{addr}")
        acct = body.get("account") or body
        raw = acct.get("balance", acct.get("balance_units"))
        try:
            balance = int(str(raw))
        except (TypeError, ValueError):
            balance = -1
        short = f"{addr[:6]}…{addr[-4:]}" if len(addr) > 10 else addr
        rows.append(
            Result(
                "f4-balance",
                "hub",
                "STOP",
                code == 200 and balance > 0,
                "balance > 0",
                f"{short} balance={raw if code == 200 else f'code={code}'}",
            )
        )
    if not rows:
        rows.append(Result("f4-balance", "hub", "STOP", False, "expected.f4_accounts in manifest", "absent"))
    return rows


def check_pause_flag(ctx: Ctx) -> list[Result]:
    """Every carrier file must still read ``true`` — the operator's edit
    has not partially landed. A file that went missing is INVESTIGATE, a
    carrier reading ``false`` early is STOP."""
    rows: list[Result] = []
    files: dict = ctx.manifest["expected"].get("pause_files") or {}
    for name, h in ctx.manifest["hosts"].items():
        env_dir = h.get("env_dir")
        flist = files.get(name)
        if not env_dir or flist is None:
            rows.append(Result("pause-flag", name, "STOP", None, "env_dir + pause_files entry", "absent"))
            continue
        bad, missing = [], []
        for fname in flist:
            val = _grep_anchor(ctx, h, env_dir, fname, "BRIDGE_LOCKS_PAUSED")
            if val is None:
                missing.append(fname)
            elif val.lower() != "true":
                bad.append(f"{fname}={val}")
        rows.append(
            Result(
                "pause-flag",
                name,
                "STOP",
                not bad and not missing,
                f"{len(flist)} file(s) still =true",
                f"early-false={bad or 'none'} absent={missing or 'none'}",
            )
        )
    return rows


def check_contract_env(ctx: Ctx) -> list[Result]:
    mon = ctx.manifest["expected"].get("monitor_env") or {}
    hname = mon.get("host", "hub")
    h = ctx.manifest["hosts"].get(hname)
    want = (ctx.manifest.get("sepolia") or {}).get("contract", "")
    if not h or not h.get("env_dir") or not mon.get("file"):
        return [Result("contract-env", hname, "STOP", False, "monitor_env + host env_dir", "absent")]
    val = _grep_anchor(ctx, h, h["env_dir"], mon["file"], "BRIDGE_CONTRACT_ADDRESS")
    ok = val is not None and want and val.lower() == want.lower()
    return [
        Result(
            "contract-env",
            hname,
            "STOP",
            ok,
            f"{mon['file']} == named contract",
            f"{'matches' if ok else val or 'unset'}",
        )
    ]


def check_sepolia(ctx: Ctx) -> list[Result]:
    spec = ctx.manifest.get("sepolia") or {}
    contract, safe = spec.get("contract", ""), (spec.get("safe") or "").lower()
    threshold = spec.get("threshold", 2)
    if not spec.get("rpc") or not contract:
        return [Result("sepolia", "sepolia", "STOP", False, "sepolia.rpc + contract in manifest", "absent")]

    rows: list[Result] = []
    code_hex = eth_rpc(ctx, "eth_getCode", [contract, "latest"])
    rows.append(
        Result(
            "sepolia-code",
            "sepolia",
            "STOP",
            bool(code_hex) and code_hex != "0x",
            "eth_getCode non-empty",
            f"{len(code_hex) - 2 if code_hex else 0} bytes" if code_hex else "no result",
        )
    )
    owner_hex = eth_rpc(ctx, "eth_call", [{"to": contract, "data": OWNER_SELECTOR}, "latest"])
    owner = f"0x{owner_hex[-40:]}" if owner_hex and len(owner_hex) >= 42 else None
    rows.append(
        Result(
            "sepolia-owner",
            "sepolia",
            "STOP",
            owner is not None and owner.lower() == safe,
            f"owner() == {safe[:8]}…",
            owner or "no result",
        )
    )
    th_hex = eth_rpc(ctx, "eth_call", [{"to": safe, "data": GETTHRESHOLD_SELECTOR}, "latest"]) if safe else None
    th = int(th_hex, 16) if th_hex else None
    rows.append(
        Result(
            "sepolia-threshold",
            "sepolia",
            "STOP",
            th is not None and th >= threshold,
            f"getThreshold() >= {threshold}",
            str(th),
        )
    )
    return rows


def run(ctx: Ctx) -> list[Result]:
    rows: list[Result] = []
    rows += check_postcut_report(ctx)
    rows += check_heads_agree(ctx)
    rows += check_f4_balances(ctx)
    rows += check_pause_flag(ctx)
    rows += check_contract_env(ctx)
    rows += check_sepolia(ctx)
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", required=True)
    ap.add_argument(
        "--post-cut-report",
        default=None,
        help="saved `post-cut-verify.py --output json` run — the soak-end gate evidence (required for GO)",
    )
    ap.add_argument("--output", choices=["table", "json"], default="table")
    args = ap.parse_args(argv)

    try:
        manifest = json.loads(open(args.manifest).read())
    except (OSError, json.JSONDecodeError) as e:
        print(f"manifest unreadable: {e}", file=sys.stderr)
        return 2
    report = None
    if args.post_cut_report:
        try:
            report = json.loads(open(args.post_cut_report).read())
        except (OSError, json.JSONDecodeError) as e:
            print(f"post-cut report unreadable: {e}", file=sys.stderr)
            return 2

    ctx = Ctx(
        manifest=manifest,
        http_get=real_http_get,
        http_post=real_http_post,
        host_sh=real_host_sh,
        report=report,
    )
    rows = run(ctx)

    if args.output == "json":
        print(json.dumps([r.__dict__ for r in rows], indent=2))
    else:
        for r in rows:
            print(r.line())
    stop_fails = [r for r in rows if r.ok is False and r.severity == "STOP"]
    verdict = "GO" if not stop_fails else "NO-GO"
    if args.output != "json":
        fails = [r for r in rows if r.ok is False]
        skips = sum(1 for r in rows if r.ok is None)
        print(f"--- {verdict}: {len(rows) - len(fails) - skips} PASS, {len(fails)} FAIL, {skips} SKIP")
    return 0 if verdict == "GO" else 1


if __name__ == "__main__":
    sys.exit(main())
