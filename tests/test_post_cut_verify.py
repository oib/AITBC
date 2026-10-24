"""Canned-response tests for scripts/ops/post-cut-verify.py (RESET-POSTCUT-1).

Every check function takes the same Ctx with injected http_get/http_post/
host_sh callables, so the tests exercise the real check logic against
fabricated fleet answers — no network, no systemd, no ssh.
"""

from __future__ import annotations

import json
import urllib.parse
from pathlib import Path

import pytest


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


def _canned_block(url: str, b0: dict, bad_block: int | None):
    if url.endswith("/rpc/blocks/0"):
        return 200, b0
    hgt = int(url.rsplit("/", 1)[1])
    atts = ["a", "b"] if hgt != bad_block else ["a"]
    return 200, {"proposer": VALS[hgt % 4], "block_metadata": json.dumps({"attestations": atts})}


def http_get_factory(
    head_h: int = 5,
    head_hash: str = "0xhead",
    block0: dict | None = None,
    bad_block: int | None = None,
    probe_503: bool = True,
):
    b0 = block0 or {"hash": "0xg", "state_root": "0xsr", "chain_id": CID}
    table = {
        "/rpc/proposer": (200, {"proposer_id": VALS[0], "chain_id": CID, "supported_chains": [CID]}),
        "/rpc/head": (200, {"height": head_h, "hash": head_hash}),
        "/rpc/state/snapshot": (
            200,
            {"accounts": [{"address": "0xT", "balance": "100"}, {"address": "0xS", "balance": "20"}]},
        ),
        "/rpc/bridge/pending": (200, {"pending": []}),
        "/rpc/mempool": (200, {"transactions": []}),
        "/api/v1/alerts": (200, {"data": {"alerts": []}}),
    }

    def get(url: str, timeout: int = 5):
        if "/rpc/blocks/" in url:
            return _canned_block(url, b0, bad_block)
        for suffix, ans in table.items():
            if url.endswith(suffix):
                return ans
        # Reject, don't 404: a check hitting an unmapped route is a bug in
        # the check or the fixture — the 23 Oct `/rpc/blocks` typo slid
        # through because checks turn any non-200 into a SKIP row, and
        # no test noticed the row never ran.
        raise AssertionError(f"fixture fake: unmapped GET {url}")

    return get


def _grep_answer(env_ok: bool, cmd: str) -> str:
    if "CHAIN_ID" in cmd:
        return f"CHAIN_ID={CID}\n" if env_ok else "CHAIN_ID=old-1\nCHAIN_ID=bc-2\n"
    for ename, want in (("BRIDGE_LOCKS_PAUSED", "true"), ("STATE_TRANSITION_V2_HEIGHT", "1")):
        if ename in cmd:
            return f"{ename}={want}\n"
    return ""


def _is_active(cmd: str, unit_active: bool, timer_active: bool) -> str:
    if ".timer" in cmd:
        return "active\n" if timer_active else "inactive\n"
    return "active\n" if unit_active else "inactive\n"


def host_sh_factory(
    env_ok: bool = True,
    stray: bool = False,
    stray_size: int | None = None,
    unit_active: bool = True,
    timer_active: bool = True,
    store_count: int = 3,
):
    handlers = [
        ("grep -h", lambda c: _grep_answer(env_ok, c)),
        ("sha256sum", lambda c: "ab" * 32 + "  /d/bc-2/genesis.json\n"),
        (
            "find",
            lambda c: (
                "0 /d/bc-2/chain.db\n" + (f"{stray_size or 0} /d/old/chain.db\n" if stray else "")
                if "-printf" in c
                else "/d/bc-2/chain.db\n" + ("/d/old/chain.db\n" if stray else "")
            ),
        ),
        (
            "journalctl",
            lambda c: "Successfully created genesis block from genesis.json\nInitializing databases for chains: ['bc-2']\n",
        ),
        ("sqlite3", lambda c: f"{store_count}\n"),
        ("[ -f", lambda c: f"{store_count}\n"),  # guarded probe: [ -f db ] && sqlite3 -readonly … → file exists → count
    ]

    def sh(ssh, cmd):
        if "is-active" in cmd:
            return _is_active(cmd, unit_active, timer_active)
        if "ActiveEnterTimestamp" in cmd:
            return "2000000000\n"
        for prefix, fn in handlers:
            if cmd.startswith(prefix):
                return fn(cmd)
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
    # default is off — a POST on a live endpoint needs the operator's line
    assert statuses(rows)["bridge-paused-probe"] is None
    assert "operator's line" in [r for r in rows if r.check == "bridge-paused-probe"][0].found
    c2 = ctx(tmp_path, probe=True)
    assert statuses(pcv.check_bridge(c2))["bridge-paused-probe"] is True
    c3 = ctx(tmp_path, probe=True, http_post=lambda u, b, timeout=5: (200, {}))
    assert statuses(pcv.check_bridge(c3))["bridge-paused-probe"] is False


def test_env_pins(tmp_path):
    c = ctx(tmp_path)
    rows = pcv.check_env(c, "hub", c.manifest["hosts"]["hub"])
    assert rows[0].ok is True
    c2 = ctx(tmp_path, host_sh=host_sh_factory(env_ok=False))
    rows = pcv.check_env(c2, "hub", c2.manifest["hosts"]["hub"])
    assert rows[0].ok is False
    assert "CHAIN_ID" in rows[0].found


def test_env_denied_name(tmp_path):
    # the script must not be pointable at a non-allow-listed env name —
    # a denied name is never grepped and marks the check failed
    c = ctx(tmp_path)
    m = c.manifest
    m["expected"]["env"]["PROPOSER_KEY"] = "whatever"
    called = []

    def spy_sh(ssh, cmd):
        called.append(cmd)
        return host_sh_factory()(ssh, cmd)

    c.host_sh = spy_sh
    rows = pcv.check_env(c, "hub", m["hosts"]["hub"])
    assert rows[0].ok is False
    assert "PROPOSER_KEY" in rows[0].found
    assert not any("PROPOSER_KEY" in cmd for cmd in called)


def test_stray_dbs(tmp_path):
    c = ctx(tmp_path, host_sh=host_sh_factory(stray=True, stray_size=4096))
    rows = pcv.check_no_stray_dbs(c, "hub", c.manifest["hosts"]["hub"])
    assert rows[0].ok is False
    c2 = ctx(tmp_path)
    assert pcv.check_no_stray_dbs(c2, "hub", c2.manifest["hosts"]["hub"])[0].ok is True


def test_stray_dbs_zero_byte_warns_not_fails(tmp_path):
    """Zero-byte strays (sqlite auto-create accidents) warn; gate stays green."""
    c = ctx(tmp_path, host_sh=host_sh_factory(stray=True, stray_size=0))
    rows = pcv.check_no_stray_dbs(c, "hub", c.manifest["hosts"]["hub"])
    assert rows[0].ok is True
    assert rows[0].severity == "INVESTIGATE"
    assert "/d/old/chain.db" in rows[0].found


def test_stray_dbs_nonempty_still_fails(tmp_path):
    """A stray chain.db with real content is a possible divergent chain — STOP."""
    c = ctx(tmp_path, host_sh=host_sh_factory(stray=True, stray_size=4096))
    rows = pcv.check_no_stray_dbs(c, "hub", c.manifest["hosts"]["hub"])
    assert rows[0].ok is False
    assert rows[0].severity == "STOP"


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


def test_expected_inactive_units(tmp_path):
    # OBS-PRECHECK-1: manifest expected_inactive entries that stay down pass;
    # one that reports active fails the units-expected-inactive row.
    c = ctx(tmp_path)
    m = c.manifest
    m["hosts"]["hub"]["expected_inactive"] = {"oneshot.svc": "rests inactive", "held.svc": "held for F5"}

    def down_sh(ssh, cmd):
        if "is-active" in cmd and any(u in cmd for u in ("oneshot.svc", "held.svc")):
            return "inactive\n"
        return host_sh_factory()(ssh, cmd)

    c2 = ctx(tmp_path, host_sh=down_sh)
    c2.manifest["hosts"]["hub"]["expected_inactive"] = m["hosts"]["hub"]["expected_inactive"]
    rows = pcv.check_units(c2, "hub", c2.manifest["hosts"]["hub"])
    ei = [r for r in rows if r.check == "units-expected-inactive"][0]
    assert ei.ok is True

    def up_sh(ssh, cmd):
        if "is-active" in cmd and "held.svc" in cmd:
            return "active\n"
        return down_sh(ssh, cmd)

    c3 = ctx(tmp_path, host_sh=up_sh)
    c3.manifest["hosts"]["hub"]["expected_inactive"] = m["hosts"]["hub"]["expected_inactive"]
    ei3 = [r for r in pcv.check_units(c3, "hub", c3.manifest["hosts"]["hub"]) if r.check == "units-expected-inactive"][0]
    assert ei3.ok is False and "held.svc" in ei3.found


def test_stores_probe_is_guarded_readonly(tmp_path):
    # OBS-PRECHECK-1: the stores probe must never invoke sqlite3 on a path
    # that might not exist — sqlite3 auto-creates a zero-byte file. The
    # command carries a [ -f ] existence guard plus -readonly + mode=ro.
    seen = []

    def spy_sh(ssh, cmd):
        seen.append(cmd)
        if "sqlite3" in cmd:
            assert cmd.startswith("[ -f"), f"unguarded probe: {cmd}"
            assert "-readonly" in cmd and "mode=ro" in cmd
            return "3\n"  # file exists → table count
        return host_sh_factory()(ssh, cmd)

    c = ctx(tmp_path, host_sh=spy_sh)
    rows = pcv.check_stores(c, "hub", c.manifest["hosts"]["hub"])
    assert rows[0].ok is True
    assert any("sqlite3" in cmd for cmd in seen)

    # missing file: the [ -f ] guard short-circuits to empty output → -1 row,
    # sqlite3 never runs — nothing is created on the measured host.
    c2 = ctx(tmp_path, host_sh=lambda ssh, cmd: "" if "sqlite3" in cmd or "[ -f" in cmd else host_sh_factory()(ssh, cmd))
    rows2 = pcv.check_stores(c2, "hub", c2.manifest["hosts"]["hub"])
    assert rows2[0].ok is False and "-1" in rows2[0].found


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
    c2 = ctx(tmp_path, host_sh=host_sh_factory(stray=True, stray_size=4096), window_start_epoch=1)
    assert pcv.worst(pcv.run(c2)) == 1
    c3 = ctx(tmp_path, host_sh=host_sh_factory(stray=True, stray_size=0), window_start_epoch=1)
    assert pcv.worst(pcv.run(c3)) == 0  # zero-byte stray warns; gate stays green


# --- SOAK-GATE-WINDOW-1: windowed validator coverage + head progression --
#
# The 23 Oct hub series is the failure shape this row exists for: hub
# (`0xAa`) was dark 07:28-09:42 — 10 proposals against ~34 expected and a
# ~135-block silent run — while the other three validators rotated through
# the window. The gate must fail hub's coverage row on that series and
# pass a healthy rotation.


BASE_HEAD = 5
WINDOW_HEAD = 141  # baseline 5 + 136 blocks, mirroring the outage window


def _series(proposers: list[str], base: int = BASE_HEAD) -> list[dict]:
    return [{"height": base + i + 1, "proposer": p} for i, p in enumerate(proposers)]


def _outage_series() -> list[dict]:
    """The 23 Oct shape: hub proposes its first 10, then goes dark for the
    remaining ~126 blocks while hub1/node1/node2 rotate."""
    props = [VALS[0]] * 10 + [VALS[1 + (i % 3)] for i in range(126)]
    return _series(props)


def _blocks_get(blocks: list[dict], head_h: int = WINDOW_HEAD):
    base_get = http_get_factory(head_h=head_h)

    def get(url: str, timeout: int = 5):
        if "/rpc/blocks-range?" in url:
            q = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).items()}
            start, end = int(q["start"]), int(q["end"])
            sliced = [b for b in blocks if start <= b["height"] <= end]
            return 200, {"success": True, "blocks": sliced, "count": len(sliced)}
        return base_get(url, timeout)

    return get


def _gate_ctx(tmp_path: Path, blocks: list[dict], head_h: int = WINDOW_HEAD, heads=None, window_start=None) -> pcv.Ctx:
    m = manifest(tmp_path)
    m["expected"]["baseline_head_height"] = BASE_HEAD
    if window_start is not None:
        m["expected"]["window_start"] = window_start
    c = ctx(tmp_path, manifest_over={"expected": m["expected"]}, http_get=_blocks_get(blocks, head_h))
    c.heads = heads if heads is not None else {"hub": {"height": head_h, "hash": "0xhead"}}
    return c


def test_head_progression(tmp_path):
    c = _gate_ctx(tmp_path, _outage_series())
    row = pcv.check_head_progression(c)[0]
    assert row.ok is True
    stalled = _gate_ctx(tmp_path, [], head_h=BASE_HEAD, heads={"hub": {"height": BASE_HEAD, "hash": "0xsame"}})
    assert pcv.check_head_progression(stalled)[0].ok is False
    unconfigured = ctx(tmp_path)
    unconfigured.heads = {"hub": {"height": 9, "hash": "0xh"}}
    assert pcv.check_head_progression(unconfigured)[0].ok is None


def test_validator_coverage_outage_fails(tmp_path):
    """The 23 Oct hub series fails BOTH coverage thresholds on hub."""
    c = _gate_ctx(tmp_path, _outage_series())
    rows = {r.host: r for r in pcv.check_validator_coverage(c)}
    hub_row = rows[VALS[0][:8]]
    assert hub_row.ok is False
    # 126-block silent run (> 40 floor) and 10 proposals (< 0.4x34 floor)
    assert "silent=126" in hub_row.found
    assert "proposals=10/136" in hub_row.found
    for v in VALS[1:]:
        assert rows[v[:8]].ok is True, rows[v[:8]].line()


def test_validator_coverage_healthy_passes(tmp_path):
    """A rotating 4-validator window passes every coverage row."""
    c = _gate_ctx(tmp_path, _series([VALS[i % 4] for i in range(136)]))
    for r in pcv.check_validator_coverage(c):
        assert r.ok is True, r.line()


def test_validator_coverage_window_start_narrows(tmp_path):
    """expected.window_start overrides baseline_head_height for the
    coverage window — the same series then shows a smaller denominator."""
    series = _series([VALS[i % 4] for i in range(136)])
    c = _gate_ctx(tmp_path, series, window_start=100)
    for r in pcv.check_validator_coverage(c):
        assert r.ok is True, r.line()
        assert "/41" in r.found  # heights 101..141, not the full 136
    # And without the key the check falls back to baseline_head_height:
    c2 = _gate_ctx(tmp_path, series)
    assert "/136" in pcv.check_validator_coverage(c2)[0].found


def test_fake_rejects_unknown_route():
    """The fixture contract itself: an unmapped URL must raise, not 404 —
    checks turn non-200 into SKIP rows that silently hide a wrong path."""
    get = http_get_factory()
    with pytest.raises(AssertionError, match="unmapped"):
        get("http://h/rpc/blocks?start=1&end=5")


def _alerts_ctx(tmp_path: Path, firing: list[str], heads=None, mode: str = "split") -> pcv.Ctx:
    m = manifest(tmp_path)
    m["prom_url"] = "http://p"
    m["expected"]["v9_alert_mode"] = mode
    c = pcv.Ctx(
        manifest=m,
        http_get=lambda u, timeout=5: (
            200,
            {"data": {"alerts": [{"state": "firing", "labels": {"alertname": a}} for a in firing]}},
        ),
        http_post=None,
        host_sh=host_sh_factory(),
    )
    if heads is not None:
        c.heads = heads
    return c


UNIFORM = {"hub": {"height": 10, "hash": "0xsame"}, "node1": {"height": 10, "hash": "0xsame"}}
DIVERGENT = {"hub": {"height": 10, "hash": "0xa"}, "node1": {"height": 11, "hash": "0xb"}}
V9_PAIR = ["V9AttestationRefusal", "V9ShadowRejection"]


def test_v9_split_alone_uniform_is_noise(tmp_path):
    row = pcv.check_alerts(_alerts_ctx(tmp_path, V9_PAIR, heads=UNIFORM))[0]
    assert row.ok is True
    assert "flag_v9" not in row.detail


def test_v9_split_flags_on_degradation(tmp_path):
    row = pcv.check_alerts(_alerts_ctx(tmp_path, V9_PAIR + ["AttestationArrivalDegraded"], heads=UNIFORM))[0]
    assert row.ok is False
    assert "flag_v9" in row.detail


def test_v9_split_flags_on_divergent_heads(tmp_path):
    row = pcv.check_alerts(_alerts_ctx(tmp_path, V9_PAIR, heads=DIVERGENT))[0]
    assert row.ok is False
    assert "flag_v9" in row.detail


def test_v9_surface_always_flags(tmp_path):
    row = pcv.check_alerts(_alerts_ctx(tmp_path, V9_PAIR, heads=UNIFORM, mode="surface"))[0]
    assert row.ok is False


def test_v9_noise_always_expected(tmp_path):
    row = pcv.check_alerts(_alerts_ctx(tmp_path, V9_PAIR, heads=DIVERGENT, mode="noise"))[0]
    assert row.ok is True


def test_journal_evidence_aged_out(tmp_path):
    """genesis-created may age out of journal retention; init bc2 stays required."""

    def sh(ssh, cmd):
        return "Initializing databases for chains: ['bc-2']\n" if cmd.startswith("journalctl") else host_sh_factory()(ssh, cmd)

    c = ctx(tmp_path, host_sh=sh)
    assert pcv.check_journal(c, "hub", c.manifest["hosts"]["hub"])[0].ok is True


def test_result_line_public(tmp_path):
    c = ctx(tmp_path)
    rows = pcv.run(c)
    for r in rows:
        line = r.line()
        assert "PRIVATE" not in line and "KEY" not in line.upper() or "peer_keys" in line


# --- LATE-23OCT: bounded retries on transport failures (node1 ssh-curl) --


def _retry_manifest(tmp_path: Path, attempts: int | None = None) -> dict:
    m = manifest(tmp_path)
    m["expected"]["http_retry_backoff_s"] = 0
    if attempts is not None:
        m["expected"]["http_attempts"] = attempts
    return m


def test_http_get_retries_transport_failure(tmp_path):
    """-1 (no HTTP answer) retries until a real answer arrives."""
    calls = {"n": 0}
    good = http_get_factory()

    def flaky(url: str, timeout: int = 5):
        calls["n"] += 1
        if calls["n"] <= 2:
            return -1, {"error": "ssh: connection timed out"}
        return good(url, timeout)

    c = pcv.Ctx(
        manifest=_retry_manifest(tmp_path),
        http_get=flaky,
        http_post=lambda u, b, timeout=5: (503, {}),
        host_sh=host_sh_factory(),
    )
    rows = pcv.check_heads(c)
    assert all(r.ok for r in rows)
    assert calls["n"] > 1  # retried, then served


def test_http_get_no_retry_on_definitive_code(tmp_path):
    """A real HTTP status (even an error) is returned on the first try."""
    calls = {"n": 0}

    def gone(url: str, timeout: int = 5):
        calls["n"] += 1
        return 404, {}

    c = pcv.Ctx(
        manifest=_retry_manifest(tmp_path),
        http_get=gone,
        http_post=lambda u, b, timeout=5: (503, {}),
        host_sh=host_sh_factory(),
    )
    pcv.check_heads(c)
    assert calls["n"] == 2  # one call per host, zero retries


def test_http_get_retry_exhaustion_still_reports(tmp_path):
    """Persistent -1 exhausts attempts and still yields a failing row."""
    calls = {"n": 0}

    def dead(url: str, timeout: int = 5):
        calls["n"] += 1
        return -1, {"error": "timeout"}

    m = _retry_manifest(tmp_path, attempts=3)
    c = pcv.Ctx(
        manifest=m,
        http_get=dead,
        http_post=lambda u, b, timeout=5: (503, {}),
        host_sh=host_sh_factory(),
    )
    rows = [r for r in pcv.check_heads(c) if r.check == "head-equality"]
    assert rows and rows[0].ok is False
    assert calls["n"] == 2 * 3  # 2 hosts x 3 attempts


def test_http_get_attempts_one_disables_retry(tmp_path):
    calls = {"n": 0}

    def dead(url: str, timeout: int = 5):
        calls["n"] += 1
        return -1, {"error": "timeout"}

    m = _retry_manifest(tmp_path, attempts=1)
    c = pcv.Ctx(
        manifest=m,
        http_get=dead,
        http_post=lambda u, b, timeout=5: (503, {}),
        host_sh=host_sh_factory(),
    )
    pcv.check_heads(c)
    assert calls["n"] == 2  # 2 hosts, no retries


def test_check_overrides_skip(tmp_path):
    c = ctx(tmp_path)
    h = dict(c.manifest["hosts"]["hub"])
    h["check_overrides"] = {"journal-evidence": {"skip": True, "reason": "journal rotated"}}
    rows = pcv._apply_overrides(h, pcv.check_journal(c, "hub", h))
    assert len(rows) == 1 and rows[0].ok is None and "journal rotated" in rows[0].found


def test_check_overrides_untouched(tmp_path):
    c = ctx(tmp_path)
    h = dict(c.manifest["hosts"]["hub"])
    h["check_overrides"] = {"other-check": {"skip": True}}
    rows = pcv._apply_overrides(h, pcv.check_journal(c, "hub", h))
    assert rows[0].check == "journal-evidence" and rows[0].ok is not None


# --- rpc_via_ssh / prom_via_ssh: loopback-only remote endpoints read through
# ssh <alias> curl instead of a local tunnel (dead-forward manifest fix, 24 Oct)


def _ssh_manifest(tmp_path: Path, **host_extra) -> dict:
    m = manifest(tmp_path)
    hub = dict(m["hosts"]["hub"])
    hub.update({"rpc": "http://127.0.0.1:8202", "ssh": "hub", "rpc_via_ssh": True})
    hub.update(host_extra)
    m["hosts"] = {"hub": hub}
    return m


def _curl_sh(canned: dict, calls: list, code: int = 200):
    base = host_sh_factory()

    def sh(ssh, cmd):
        calls.append(cmd)
        if cmd.startswith("curl"):
            return json.dumps(canned) + f"\n{code}"
        return base(ssh, cmd)

    return sh


def test_rpc_via_ssh_routes_through_host_sh(tmp_path):
    calls = []
    c = ctx(
        tmp_path,
        manifest_over=_ssh_manifest(tmp_path),
        http_get=lambda u, timeout=5: (_ for _ in ()).throw(AssertionError(f"direct GET {u}")),
        host_sh=_curl_sh({"height": 7, "hash": "0xs"}, calls),
    )
    rows = pcv.check_heads(c)
    assert rows[0].ok is True and rows[0].found == "200"
    assert any("curl" in cmd and "127.0.0.1:8202/rpc/head" in cmd for cmd in calls)


def test_rpc_via_ssh_missing_alias_fails(tmp_path):
    m = _ssh_manifest(tmp_path)
    del m["hosts"]["hub"]["ssh"]
    c = ctx(
        tmp_path,
        manifest_over=m,
        http_get=lambda u, timeout=5: (_ for _ in ()).throw(AssertionError(f"direct GET {u}")),
        host_sh=host_sh_factory(),
    )
    rows = pcv.check_heads(c)
    assert rows[0].ok is False and rows[0].found == "-1"


def test_rpc_via_ssh_retries_on_dead_leg(tmp_path):
    calls = []
    c = ctx(
        tmp_path,
        manifest_over=_ssh_manifest(tmp_path),
        http_get=lambda u, timeout=5: (-1, {"error": "must not be used"}),
        host_sh=lambda ssh, cmd: calls.append(cmd) or "",
    )
    rows = pcv.check_heads(c)
    assert rows[0].ok is False
    assert len([c2 for c2 in calls if c2.startswith("curl")]) == 3  # default http_attempts


def test_bridge_probe_post_via_ssh(tmp_path):
    calls = []

    def sh(ssh, cmd):
        calls.append(cmd)
        if cmd.startswith("curl") and "-X POST" in cmd:
            return json.dumps({"detail": "paused"}) + "\n503"
        if cmd.startswith("curl"):
            return json.dumps({"pending": []}) + "\n200"
        return host_sh_factory()(ssh, cmd)

    c = ctx(
        tmp_path,
        manifest_over=_ssh_manifest(tmp_path),
        http_get=lambda u, timeout=5: (_ for _ in ()).throw(AssertionError(f"direct GET {u}")),
        http_post=lambda u, b, timeout=5: (_ for _ in ()).throw(AssertionError(f"direct POST {u}")),
        host_sh=sh,
        probe=True,
    )
    rows = pcv.check_bridge(c)
    assert statuses(rows)["bridge-paused-probe"] is True
    assert any("-X POST" in cmd and "/rpc/bridge/lock" in cmd for cmd in calls)


def test_prom_via_ssh(tmp_path):
    calls = []
    m = manifest(tmp_path)
    m["prom_url"] = "http://127.0.0.1:9090"
    m["prom_via_ssh"] = "hub"
    c = ctx(
        tmp_path,
        manifest_over=m,
        http_get=lambda u, timeout=5: (_ for _ in ()).throw(AssertionError(f"direct GET {u}")),
        host_sh=_curl_sh({"data": {"alerts": []}}, calls),
    )
    rows = pcv.check_alerts(c)
    assert rows[0].ok is True
    assert any("127.0.0.1:9090/api/v1/alerts" in cmd for cmd in calls)


def test_ssh_curl_parse_edges(tmp_path):
    c = ctx(tmp_path)
    # 200 with empty body -> (200, {}) — the -w code is the only line needed
    c.host_sh = lambda ssh, cmd: "\n200"
    assert pcv._ssh_curl(c, "hub", ["http://x"]) == (200, {})
    # body whose last line is numeric — the status is still the final line
    c.host_sh = lambda ssh, cmd: "42\n200"
    assert pcv._ssh_curl(c, "hub", ["http://x"])[0] == 200
    # non-JSON error body -> (code, {})
    c.host_sh = lambda ssh, cmd: "bad gateway\n503"
    assert pcv._ssh_curl(c, "hub", ["http://x"]) == (503, {})
    # no output at all -> -1 transport failure
    c.host_sh = lambda ssh, cmd: ""
    assert pcv._ssh_curl(c, "hub", ["http://x"])[0] == -1


def test_hpost_non_ssh_single_call(tmp_path):
    calls = {"n": 0}

    def post(url, body, timeout=5):
        calls["n"] += 1
        return 503, {"detail": "paused"}

    c = ctx(tmp_path, probe=True, http_post=post)
    rows = pcv.check_bridge(c)
    assert statuses(rows)["bridge-paused-probe"] is True and calls["n"] == 1


def test_prom_via_ssh_nonstring_fails_clear(tmp_path):
    m = manifest(tmp_path)
    m["prom_url"] = "http://127.0.0.1:9090"
    m["prom_via_ssh"] = True  # boolean by analogy with rpc_via_ssh — must fail clearly
    c = ctx(tmp_path, manifest_over=m)
    rows = pcv.check_alerts(c)
    assert rows[0].ok is False and "prom_via_ssh" in rows[0].expected
