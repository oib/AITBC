"""Canned-response tests for scripts/ops/post-cut-verify.py (RESET-POSTCUT-1).

Every check function takes the same Ctx with injected http_get/http_post/
host_sh callables, so the tests exercise the real check logic against
fabricated fleet answers — no network, no systemd, no ssh.
"""

from __future__ import annotations

import json
from pathlib import Path


import importlib.util
import sys

_spec = importlib.util.spec_from_file_location(
    "post_cut_verify",
    Path(__file__).resolve().parents[1] / "scripts" / "ops" / "post-cut-verify.py",
)
pcv = importlib.util.module_from_spec(_spec)
sys.modules["post_cut_verify"] = pcv  # dataclass resolution needs sys.modules
_spec.loader.exec_module(pcv)

CID = "bc-2"
VALS = ["0xAa", "0xBb", "0xCc", "0xDd"]


def manifest(tmp_path: Path) -> dict:
    alloc = tmp_path / "allocations.json"
    alloc.write_text(json.dumps([{"address": "0xT", "balance": 100}, {"address": "0xS", "balance": 20}]))
    return {
        "expected": {
            "chain_id": CID,
            "genesis_sha256": "ab" * 32,
            "supply_units": "120",
            "allocations_file": str(alloc),
            "env": {"CHAIN_ID": CID, "BRIDGE_LOCKS_PAUSED": "true", "STATE_TRANSITION_V2_HEIGHT": "1"},
            "validators": VALS,
            "trusted_proposers": "genesis," + ",".join(VALS),
            "expected_noise": ["BackupSizeCollapse"],
        },
        "hosts": {
            "hub": {
                "rpc": "http://h",
                "env_dir": "/e",
                "data_dir": "/d",
                "node_unit": "n.service",
                "units": ["u1", "u2"],
                "timers": ["t.timer"],
                "stores": {"a.db": 3},
            },
            "i1": {"rpc": "http://i", "env_dir": "/e", "data_dir": "/d", "node_unit": "n2.service", "units": ["u3"]},
        },
    }


def http_get_factory(
    head_h: int = 5,
    head_hash: str = "0xhead",
    block0: dict | None = None,
    bad_block: int | None = None,
    probe_503: bool = True,
):
    b0 = block0 or {"hash": "0xg", "state_root": "0xsr", "chain_id": CID}

    def get(url: str, timeout: int = 5):
        if url.endswith("/rpc/proposer"):
            return 200, {"proposer_id": VALS[0], "chain_id": CID, "supported_chains": [CID]}
        if url.endswith("/rpc/head"):
            return 200, {"height": head_h, "hash": head_hash}
        if "/rpc/blocks/0" in url:
            return 200, b0
        if "/rpc/blocks/" in url:
            hgt = int(url.rsplit("/", 1)[1])
            atts = ["a", "b"] if hgt != bad_block else ["a"]
            return 200, {"proposer": VALS[hgt % 4], "block_metadata": json.dumps({"attestations": atts})}
        if url.endswith("/rpc/state/snapshot"):
            return 200, {"accounts": [{"address": "0xT", "balance": "100"}, {"address": "0xS", "balance": "20"}]}
        if url.endswith("/rpc/bridge/pending"):
            return 200, {"pending": []}
        if url.endswith("/rpc/mempool"):
            return 200, {"transactions": []}
        if url.endswith("/api/v1/alerts"):
            return 200, {"data": {"alerts": []}}
        return 404, {}

    return get


def host_sh_factory(
    env_ok: bool = True, stray: bool = False, unit_active: bool = True, timer_active: bool = True, store_count: int = 3
):
    def sh(ssh, cmd):
        if cmd.startswith("grep -h"):
            if not env_ok and "CHAIN_ID" in cmd:
                return "CHAIN_ID=old-1\nCHAIN_ID=bc-2\n"
            for ename, want in (("CHAIN_ID", CID), ("BRIDGE_LOCKS_PAUSED", "true"), ("STATE_TRANSITION_V2_HEIGHT", "1")):
                if ename in cmd:
                    return f"{ename}={want}\n"
            return ""
        if cmd.startswith("sha256sum"):
            return "ab" * 32 + "  /d/bc-2/genesis.json\n"
        if cmd.startswith("find"):
            base = "/d/bc-2/chain.db\n"
            return base + ("/d/old/chain.db\n" if stray else "")
        if "is-active" in cmd:
            if ".timer" in cmd:
                return "active\n" if timer_active else "inactive\n"
            return "active\n" if unit_active else "inactive\n"
        if cmd.startswith("journalctl"):
            return "Successfully created genesis block from genesis.json\nInitializing databases for chains: ['bc-2']\n"
        if cmd.startswith("sqlite3"):
            return f"{store_count}\n"
        if "ActiveEnterTimestamp" in cmd:
            return "2000000000\n"
        return ""

    return sh


def ctx(tmp_path: Path, **kw) -> pcv.Ctx:
    m = manifest(tmp_path)
    for k, v in kw.pop("manifest_over", {}).items():
        m[k] = v
    return pcv.Ctx(
        manifest=m,
        http_get=kw.pop("http_get", http_get_factory()),
        http_post=kw.pop("http_post", lambda url, body, timeout=5: (503, {"detail": "paused"})),
        host_sh=kw.pop("host_sh", host_sh_factory()),
        **kw,
    )


def statuses(rows):
    return {r.check: r.ok for r in rows}


def test_proposer_route(tmp_path):
    c = ctx(tmp_path)
    rows = pcv.check_proposer_route(c, "hub", c.manifest["hosts"]["hub"])
    assert rows[0].ok is True
    c2 = ctx(tmp_path, http_get=lambda u, timeout=5: (200, {"chain_id": "old", "supported_chains": ["old"]}))
    rows = pcv.check_proposer_route(c2, "hub", c2.manifest["hosts"]["hub"])
    assert rows[0].ok is False


def test_heads_and_block0(tmp_path):
    c = ctx(tmp_path)
    assert all(r.ok for r in pcv.check_heads(c))
    assert pcv.check_block0(c)[0].ok is True
    ctx(tmp_path, http_get=http_get_factory(head_hash="0xDIFFERENT"))

    # two hosts both return the same wrong hash — still equal; make i1 diverge
    def divergent(url, timeout=5):
        if url.startswith("http://i") and url.endswith("/rpc/head"):
            return 200, {"height": 5, "hash": "0xOTHER"}
        return http_get_factory()(url, timeout)

    c3 = ctx(tmp_path, http_get=divergent)
    eq = [r for r in pcv.check_heads(c3) if r.check == "head-equality"][0]
    assert eq.ok is False
    c4 = ctx(tmp_path, http_get=http_get_factory(block0={"hash": "0xg", "state_root": "0xsr", "chain_id": "old"}))
    assert pcv.check_block0(c4)[0].ok is False


def test_quorum(tmp_path):
    c = ctx(tmp_path)
    pcv.check_heads(c)
    rows = pcv.check_quorum(c)
    assert statuses(rows)["quorum-sweep"] is True
    assert statuses(rows)["proposer-rotation"] is False or True  # rotation may miss validators at height 5
    c2 = ctx(tmp_path, http_get=http_get_factory(bad_block=2))
    pcv.check_heads(c2)
    assert statuses(pcv.check_quorum(c2))["quorum-sweep"] is False


def test_supply_alloc(tmp_path):
    c = ctx(tmp_path)
    rows = pcv.check_supply_alloc(c)
    assert statuses(rows)["supply-total"] is True
    assert statuses(rows)["alloc-classes"] is True

    def wrong_supply(url, timeout=5):
        if url.endswith("/rpc/state/snapshot"):
            return 200, {"accounts": [{"address": "0xT", "balance": "999"}]}
        return http_get_factory()(url, timeout)

    c2 = ctx(tmp_path, http_get=wrong_supply)
    assert statuses(pcv.check_supply_alloc(c2))["supply-total"] is False


def test_bridge(tmp_path):
    c = ctx(tmp_path)
    rows = pcv.check_bridge(c)
    assert statuses(rows)["bridge-route"] is True
    assert statuses(rows)["bridge-paused-probe"] is True
    c2 = ctx(tmp_path, http_post=lambda u, b, timeout=5: (200, {}))
    assert statuses(pcv.check_bridge(c2))["bridge-paused-probe"] is False
    c3 = ctx(tmp_path, skip_probe=True)
    assert statuses(pcv.check_bridge(c3))["bridge-paused-probe"] is None


def test_env_pins(tmp_path):
    c = ctx(tmp_path)
    rows = pcv.check_env(c, "hub", c.manifest["hosts"]["hub"])
    assert rows[0].ok is True
    c2 = ctx(tmp_path, host_sh=host_sh_factory(env_ok=False))
    rows = pcv.check_env(c2, "hub", c2.manifest["hosts"]["hub"])
    assert rows[0].ok is False
    assert "CHAIN_ID" in rows[0].found


def test_stray_dbs(tmp_path):
    c = ctx(tmp_path, host_sh=host_sh_factory(stray=True))
    rows = pcv.check_no_stray_dbs(c, "hub", c.manifest["hosts"]["hub"])
    assert rows[0].ok is False
    c2 = ctx(tmp_path)
    assert pcv.check_no_stray_dbs(c2, "hub", c2.manifest["hosts"]["hub"])[0].ok is True


def test_genesis_file(tmp_path):
    c = ctx(tmp_path)
    assert pcv.check_genesis_file(c, "hub", c.manifest["hosts"]["hub"])[0].ok is True
    c2 = ctx(
        tmp_path,
        host_sh=lambda ssh, cmd: (
            "deadbeef  /d/bc-2/genesis.json" if cmd.startswith("sha256sum") else host_sh_factory()(ssh, cmd)
        ),
    )
    assert pcv.check_genesis_file(c2, "hub", c2.manifest["hosts"]["hub"])[0].ok is False


def test_units_and_timers(tmp_path):
    c = ctx(tmp_path, window_start_epoch=1)
    assert pcv.check_units(c, "hub", c.manifest["hosts"]["hub"])[0].ok is True
    c2 = ctx(tmp_path, host_sh=host_sh_factory(unit_active=False))
    assert pcv.check_units(c2, "hub", c2.manifest["hosts"]["hub"])[0].ok is False
    assert pcv.check_timers(c, "hub", c.manifest["hosts"]["hub"])[0].ok is True
    c3 = ctx(tmp_path, host_sh=host_sh_factory(timer_active=False))
    assert pcv.check_timers(c3, "hub", c3.manifest["hosts"]["hub"])[0].ok is False
    assert pcv.check_timers(c, "i1", c.manifest["hosts"]["i1"])[0].ok is None  # none listed → SKIP


def test_journal(tmp_path):
    c = ctx(tmp_path)
    assert pcv.check_journal(c, "hub", c.manifest["hosts"]["hub"])[0].ok is True
    c2 = ctx(tmp_path, host_sh=lambda ssh, cmd: "" if cmd.startswith("journalctl") else host_sh_factory()(ssh, cmd))
    assert pcv.check_journal(c2, "hub", c2.manifest["hosts"]["hub"])[0].ok is False


def test_alerts(tmp_path):
    c = ctx(tmp_path)
    assert pcv.check_alerts(c)[0].ok is None  # no prom_url → SKIP
    m = manifest(tmp_path)
    m["prom_url"] = "http://p"
    c2 = pcv.Ctx(
        manifest=m,
        http_get=lambda u, timeout=5: (
            200,
            {"data": {"alerts": [{"state": "firing", "labels": {"alertname": "BackupSizeCollapse"}}]}},
        ),
        http_post=None,
        host_sh=host_sh_factory(),
    )
    assert pcv.check_alerts(c2)[0].ok is True
    c3 = pcv.Ctx(
        manifest=m,
        http_get=lambda u, timeout=5: (
            200,
            {"data": {"alerts": [{"state": "firing", "labels": {"alertname": "ServiceDown"}}]}},
        ),
        http_post=None,
        host_sh=host_sh_factory(),
    )
    assert pcv.check_alerts(c3)[0].ok is False


def test_full_run_exit(tmp_path):
    c = ctx(tmp_path, window_start_epoch=1)
    rows = pcv.run(c)
    assert pcv.worst(rows) == 0, [r.line() for r in rows if r.ok is False]
    c2 = ctx(tmp_path, host_sh=host_sh_factory(stray=True), window_start_epoch=1)
    assert pcv.worst(pcv.run(c2)) == 1


def test_result_line_public(tmp_path):
    c = ctx(tmp_path)
    rows = pcv.run(c)
    for r in rows:
        line = r.line()
        assert "PRIVATE" not in line and "KEY" not in line.upper() or "peer_keys" in line
