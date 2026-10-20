"""Canned-response tests for scripts/ops/unpause-precheck.py (BC2-UNPAUSE-1).

Same injection pattern as test_post_cut_verify.py: every check takes a Ctx
with fake http_get/http_post/host_sh callables — no network, no ssh, no
real env files. The GO/NO-GO verdict is exercised end-to-end through run().
"""

from __future__ import annotations

import json
from pathlib import Path

import importlib.util
import sys

_spec = importlib.util.spec_from_file_location(
    "unpause_precheck",
    Path(__file__).resolve().parents[1] / "scripts" / "ops" / "unpause-precheck.py",
)
upc = importlib.util.module_from_spec(_spec)
sys.modules["unpause_precheck"] = upc  # dataclass resolution needs sys.modules
_spec.loader.exec_module(upc)

CONTRACT = "0xfbDd3Dc5B7A6E82a11b95A1F5A90B4E43fEc92c8"
SAFE = "0xdd32f1234567890abcdef1234567890abcdefaC7"
F4_A, F4_B = "0x40c7" + "0" * 36, "0x356d" + "1" * 36


def manifest() -> dict:
    return {
        "expected": {
            "chain_id": "bc-2",
            "f4_accounts": [F4_A, F4_B],
            "pause_files": {
                "hub": ["blockchain.env", "bootstrap.env"],
                "node0": ["blockchain.env"],
            },
            "monitor_env": {"host": "hub", "file": "aitbc-bridge-monitor.env"},
        },
        "hosts": {
            "hub": {"rpc": "http://h", "env_dir": "/e"},
            "node0": {"rpc": "http://n", "env_dir": "/n"},
        },
        "sepolia": {"rpc": "http://sep", "contract": CONTRACT, "safe": SAFE, "threshold": 2},
    }


def fake_get(url: str, timeout: int = 5):
    if url.endswith("/rpc/head"):
        return 200, {"height": 42, "hash": "0xhead"}
    if url.endswith(f"/rpc/account/{F4_A}"):
        return 200, {"balance": "5000"}
    if url.endswith(f"/rpc/account/{F4_B}"):
        return 200, {"balance": "7000"}
    return 404, {}


def fake_post(url: str, body: dict, timeout: int = 8):
    method = body.get("method")
    if method == "eth_getCode":
        return 200, {"jsonrpc": "2.0", "id": 1, "result": "0x60806040"}
    if method == "eth_call":
        data = body["params"][0]["data"]
        if data == upc.OWNER_SELECTOR:
            return 200, {"jsonrpc": "2.0", "id": 1, "result": "0x" + "0" * 24 + SAFE.lower().removeprefix("0x")}
        if data == upc.GETTHRESHOLD_SELECTOR:
            return 200, {"jsonrpc": "2.0", "id": 1, "result": "0x" + "0" * 63 + "2"}
    return 500, {}


def fake_sh(ssh, cmd, timeout: int = 15):
    # anchored greps only; records nothing secret
    if "BRIDGE_LOCKS_PAUSED" in cmd:
        return "BRIDGE_LOCKS_PAUSED=true\n"
    if "BRIDGE_CONTRACT_ADDRESS" in cmd:
        return f"BRIDGE_CONTRACT_ADDRESS={CONTRACT}\n"
    return None


def ctx(report=None, get=fake_get, post=fake_post, sh_=fake_sh):
    return upc.Ctx(manifest=manifest(), http_get=get, http_post=post, host_sh=sh_, report=report)


GOOD_REPORT = [
    {"check": "block0", "host": "hub", "severity": "STOP", "ok": True, "expected": "", "found": "", "detail": ""},
    {"check": "mempool", "host": "hub", "severity": "NOTE", "ok": None, "expected": "", "found": "", "detail": ""},
]


def test_all_green_is_go():
    rows = upc.run(ctx(report=GOOD_REPORT))
    assert all(r.ok is not False for r in rows), [r.line() for r in rows]


def test_missing_report_is_nogo():
    rows = upc.run(ctx(report=None))
    r = next(r for r in rows if r.check == "postcut-verify")
    assert r.ok is False and r.severity == "STOP"


def test_fail_row_in_report_is_nogo():
    bad = GOOD_REPORT + [
        {"check": "env-pins", "host": "node1", "severity": "STOP", "ok": False, "expected": "", "found": "", "detail": ""}
    ]
    rows = upc.run(ctx(report=bad))
    r = next(r for r in rows if r.check == "postcut-verify")
    assert r.ok is False and "env-pins@node1" in r.detail


def test_heads_spread_fails():
    def get(url, timeout=5):
        if url == "http://n/rpc/head":
            return 200, {"height": 50, "hash": "0xother"}
        return fake_get(url)

    rows = upc.run(ctx(report=GOOD_REPORT, get=get))
    r = next(r for r in rows if r.check == "heads-agree")
    assert r.ok is False


def test_f4_zero_balance_fails():
    def get(url, timeout=5):
        if url.endswith(f"/rpc/account/{F4_B}"):
            return 200, {"balance": "0"}
        return fake_get(url)

    rows = upc.run(ctx(report=GOOD_REPORT, get=get))
    fails = [r for r in rows if r.check == "f4-balance" and r.ok is False]
    assert len(fails) == 1


def test_early_false_flag_fails():
    def sh_(ssh, cmd, timeout=15):
        if "BRIDGE_LOCKS_PAUSED" in cmd and "/n/" in cmd:
            return "BRIDGE_LOCKS_PAUSED=false\n"
        return fake_sh(ssh, cmd)

    rows = upc.run(ctx(report=GOOD_REPORT, sh_=sh_))
    assert any(r.check == "pause-flag" and r.ok is False for r in rows)


def test_missing_flag_file_fails():
    def sh_(ssh, cmd, timeout=15):
        if "BRIDGE_LOCKS_PAUSED" in cmd and "bootstrap.env" in cmd:
            return None
        return fake_sh(ssh, cmd)

    rows = upc.run(ctx(report=GOOD_REPORT, sh_=sh_))
    hub = next(r for r in rows if r.check == "pause-flag" and r.host == "hub")
    assert hub.ok is False and "bootstrap.env" in hub.found


def test_contract_env_mismatch_fails():
    def sh_(ssh, cmd, timeout=15):
        if "BRIDGE_CONTRACT_ADDRESS" in cmd:
            return "BRIDGE_CONTRACT_ADDRESS=0x0000000000000000000000000000000000000001\n"
        return fake_sh(ssh, cmd)

    rows = upc.run(ctx(report=GOOD_REPORT, sh_=sh_))
    r = next(r for r in rows if r.check == "contract-env")
    assert r.ok is False


def test_sepolia_no_code_fails():
    def post(url, body, timeout=8):
        if body.get("method") == "eth_getCode":
            return 200, {"jsonrpc": "2.0", "id": 1, "result": "0x"}
        return fake_post(url, body)

    rows = upc.run(ctx(report=GOOD_REPORT, post=post))
    r = next(r for r in rows if r.check == "sepolia-code")
    assert r.ok is False


def test_sepolia_wrong_owner_fails():
    def post(url, body, timeout=8):
        if body.get("method") == "eth_call" and body["params"][0]["data"] == upc.OWNER_SELECTOR:
            return 200, {"jsonrpc": "2.0", "id": 1, "result": "0x" + "0" * 24 + "1" * 40}
        return fake_post(url, body)

    rows = upc.run(ctx(report=GOOD_REPORT, post=post))
    r = next(r for r in rows if r.check == "sepolia-owner")
    assert r.ok is False


def test_sepolia_threshold_below_fails():
    def post(url, body, timeout=8):
        if body.get("method") == "eth_call" and body["params"][0]["data"] == upc.GETTHRESHOLD_SELECTOR:
            return 200, {"jsonrpc": "2.0", "id": 1, "result": "0x" + "0" * 63 + "1"}
        return fake_post(url, body)

    rows = upc.run(ctx(report=GOOD_REPORT, post=post))
    r = next(r for r in rows if r.check == "sepolia-threshold")
    assert r.ok is False


def test_grep_only_anchored_public_names():
    """The shell layer must never grep anything but the two public names —
    a manifest cannot point the checker at a secret-bearing key."""
    calls = []

    def sh_(ssh, cmd, timeout=15):
        calls.append(cmd)
        return fake_sh(ssh, cmd)

    upc.run(ctx(report=GOOD_REPORT, sh_=sh_))
    greps = [c for c in calls if "grep" in c]
    assert greps, "expected env greps"
    for c in greps:
        assert "^BRIDGE_LOCKS_PAUSED=" in c or "^BRIDGE_CONTRACT_ADDRESS=" in c


def test_other_env_name_refused():
    import pytest

    with pytest.raises(ValueError):
        upc._grep_anchor(ctx(), {"env_dir": "/e"}, "/e", "x.env", "PROPOSER_KEY")


def test_main_exit_codes(tmp_path, monkeypatch, capsys):
    mf = tmp_path / "m.json"
    mf.write_text(json.dumps(manifest()))
    rep = tmp_path / "r.json"
    rep.write_text(json.dumps(GOOD_REPORT))
    monkeypatch.setattr(upc, "real_http_get", fake_get)
    monkeypatch.setattr(upc, "real_http_post", fake_post)
    monkeypatch.setattr(upc, "real_host_sh", fake_sh)
    assert upc.main(["--manifest", str(mf), "--post-cut-report", str(rep)]) == 0
    out = capsys.readouterr().out
    assert "GO" in out and "NO-GO" not in out
    assert upc.main(["--manifest", str(mf)]) == 1  # no report → NO-GO
    assert upc.main(["--manifest", str(tmp_path / "absent.json")]) == 2
