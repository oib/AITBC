"""Unit tests for scripts/reset-harness/rehearsal.py (RESET-GENESIS-HARNESS-1).

Covers the pure-logic parts: scratch-root safety, the port/instance map, the
per-instance env contract (all gates at 1, no live env-file leak, follower
without proposer keys), allocation totals, authority parameters and bridge
validators. Nothing here spawns processes, touches systemd, or reads a live
env file.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
REHEARSAL = REPO_ROOT / "scripts" / "reset-harness" / "rehearsal.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("rehearsal", REHEARSAL)
    module = importlib.util.module_from_spec(spec)
    sys.modules["rehearsal"] = module
    spec.loader.exec_module(module)
    return module


rh = _load_module()


def _keys() -> dict:
    def k(suffix: str) -> dict:
        return {
            "address": f"0x{suffix * 40}"[:42],
            "private_key": "0x" + "ab" * 32,
            "public_key": "0x" + "04" + "cd" * 64,
        }

    return {
        "proposers": [k(c) for c in ("a1", "b2", "c3", "d4")],
        "executors": [k("e5"), k("f6")],
        "authorities": {
            "bond_slash": k("11"),
            "bridge_release": k("22"),
            "escrow_settlement": k("33"),
        },
        "treasury": k("44"),
        "service_floats": {name: k(f"{i:02x}") for i, name in enumerate(rh.SERVICE_FLOAT_NAMES)},
        "ops_float": k("55"),
    }


# ---------- scratch-root safety ----------


def test_scratch_root_refuses_live_prefixes():
    for bad in ("/var/lib/aitbc/x", "/etc/aitbc/x", "/root/x"):
        with pytest.raises(SystemExit):
            rh.scratch_root(bad)


def test_scratch_root_refuses_relative():
    with pytest.raises(SystemExit):
        rh.scratch_root("tmp/rel")


def test_scratch_root_accepts_tmp(tmp_path):
    assert rh.scratch_root(str(tmp_path / "rehearsal")) == (tmp_path / "rehearsal").resolve()


def test_scratch_root_resolves_symlinks(tmp_path):
    link = tmp_path / "link"
    link.symlink_to("/var/lib/aitbc")
    with pytest.raises(SystemExit):
        rh.scratch_root(str(link / "sub"))


def test_scratch_root_refuses_shallow_roots():
    """GAP-HARNESS-SCRATCH-1: the shared guard's depth rule now applies —
    fewer than three resolved path components is refused."""
    for bad in ("/", "/tmp", "/home", "/var"):
        with pytest.raises(SystemExit):
            rh.scratch_root(bad)


def test_scratch_root_accepts_three_component_tmp():
    assert rh.scratch_root("/tmp/bc2-rehearsal") == Path("/tmp/bc2-rehearsal")


# ---------- instance map ----------


def test_instance_map_roles_and_unique_ports(tmp_path):
    insts = rh.instances(tmp_path)
    assert len(insts) == rh.N_INSTANCES
    assert [i.role for i in insts] == ["proposer"] * 4 + ["follower"]
    ports = [p for i in insts for p in (i.p2p_port, i.rpc_port, i.sync_port)]
    assert len(ports) == len(set(ports)), "port collision in instance map"
    assert all(1024 < p < 65000 for p in ports)


# ---------- env contract ----------


def _parse_env(text: str) -> dict[str, str]:
    out = {}
    for line in text.strip().splitlines():
        key, _, raw = line.partition("=")
        assert raw.startswith("'") and raw.endswith("'"), f"unquoted env value: {line}"
        out[key] = raw[1:-1]
    return out


def test_env_gates_all_at_one(tmp_path):
    env = _parse_env(rh._env_lines(tmp_path, rh.instances(tmp_path)[0], _keys()))
    for name in rh.GATE_ENV:
        assert env[name] == "1", f"{name} must be pinned at 1 on bc-2"


def test_env_matches_gates1_profile_pins(tmp_path):
    """The rehearsal env set must stay in lock-step with the golden gates1 profile."""
    golden = REPO_ROOT / "apps" / "blockchain-node" / "tests" / "golden" / "profiles.py"
    spec = importlib.util.spec_from_file_location("golden_profiles", golden)
    prof = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prof)
    # GATES1_PINS uses pydantic field names (lowercase, int); GATE_ENV uses env names.
    normalized = {k.upper(): str(v) for k, v in prof.GATES1_PINS.items()}
    assert rh.GATE_ENV == normalized


def test_env_no_live_env_file_leak(tmp_path):
    insts = rh.instances(tmp_path)
    for inst in insts:
        env = _parse_env(rh._env_lines(tmp_path, inst, _keys()))
        assert env["AITBC_CHAIN_ENV_FILE"] == "", "ChainSettings must not load /etc/aitbc env"
        assert env["CHAIN_ID"] == "bc-2"
        assert env["SUPPORTED_CHAINS"] == "bc-2"
        assert str(tmp_path) in env["AITBC_DATA_DIR"]
        assert env["REDIS_URL"] != "redis://localhost:6379", "must not touch live redis"
        assert env["BRIDGE_MULTISIG_THRESHOLD"] == "2"


def test_env_fleet_mode_profile(tmp_path):
    """Phase 2: the rehearsal runs the fleet's consensus mode — PBFT off,
    attestation 2, subscription on, fleet timing. GOSSIP_AUTH_ENABLED stays
    unset so the code default (true) applies."""
    env = _parse_env(rh._env_lines(tmp_path, rh.instances(tmp_path)[0], _keys()))
    assert env["PBFT_CONSENSUS_ENABLED"] == "false"
    assert env["MULTI_VALIDATOR_CONSENSUS_ENABLED"] == "true"
    assert env["MULTI_VALIDATOR_MIN_ATTESTATIONS"] == "2"
    assert env["MULTI_VALIDATOR_ATTESTATION_TIMEOUT_SECONDS"] == "15"
    assert env["SUBSCRIPTION_ENABLED"] == "true"
    assert env["MAX_EMPTY_BLOCK_INTERVAL"] == "60"
    assert "GOSSIP_AUTH_ENABLED" not in env, "auth must ride the code default (true)"
    # Deployed-true flags from GATES.md's table; the rest keep code defaults.
    assert env["SIDE_ROOT_SHADOW_ENABLED"] == "true"
    assert env["BRIDGE_LOCK_REQUIRE_REPLAY_GUARD"] == "true"
    assert env["CROSS_CHAIN_REQUIRE_REPLAY_GUARD"] == "true"


def test_env_proposer_has_keys_follower_does_not(tmp_path):
    insts = rh.instances(tmp_path)
    keys = _keys()
    prop = _parse_env(rh._env_lines(tmp_path, insts[0], keys))
    fol = _parse_env(rh._env_lines(tmp_path, insts[4], keys))
    assert prop["ENABLE_BLOCK_PRODUCTION"] == "true"
    assert "VALIDATOR_KEYS" in prop and keys["proposers"][0]["address"] in prop["VALIDATOR_KEYS"]
    assert fol["ENABLE_BLOCK_PRODUCTION"] == "false"
    assert "VALIDATOR_KEYS" not in fol
    assert "PROPOSER_KEY" not in fol


def test_env_mesh_peers_exclude_self(tmp_path):
    insts = rh.instances(tmp_path)
    keys = _keys()
    for inst in insts:
        env = _parse_env(rh._env_lines(tmp_path, inst, keys))
        peers = env["GOSSIP_MESH_PEER_URLS"].split(",")
        assert len(peers) == rh.N_INSTANCES - 1
        assert not any(f":{inst.rpc_port}" in p for p in peers)


def test_env_validator_set_is_all_four_proposers(tmp_path):
    keys = _keys()
    env = _parse_env(rh._env_lines(tmp_path, rh.instances(tmp_path)[0], keys))
    vs = json.loads(env["VALIDATOR_SET"])
    assert len(vs) == 4
    assert {v["address"] for v in vs} == {p["address"] for p in keys["proposers"]}


# ---------- allocation / parameters / validators ----------


def test_allocations_total_and_service_floats():
    allocs = rh._allocations(_keys())
    assert sum(a["balance"] for a in allocs) == rh.EXPECTED_TOTAL_UNITS
    by_amount = {}
    for a in allocs:
        by_amount.setdefault(a["balance"], []).append(a["address"])
    assert rh.TREASURY_UNITS in by_amount and len(by_amount[rh.TREASURY_UNITS]) == 1
    # 11 named floats + 2 executors + 3 authorities = 16 accounts at 1 AIT
    assert len(by_amount[rh.SERVICE_FLOAT_UNITS]) == 16


def test_parameters_cover_five_authority_slots():
    params = rh._parameters(_keys())
    assert set(params) == {
        "bond_slash_authority",
        "bridge_release_authority",
        "escrow_fee_recipient",
        "escrow_settlement_authority",
        "governance_executors",
    }
    assert re.fullmatch(r"0x[0-9a-fA-F]{40}(,0x[0-9a-fA-F]{40})*", params["governance_executors"])


def test_bridge_validators_are_the_four_proposers():
    keys = _keys()
    bv = rh._bridge_validators(keys)
    assert len(bv) == 4
    assert [v["address"] for v in bv] == [p["address"] for p in keys["proposers"]]
    assert all(v["epoch"] == 1 for v in bv)


def test_gate_env_has_no_live_values():
    assert set(rh.GATE_ENV.values()) == {"1"}


def test_live_snapshot_parses_keyed_output(monkeypatch):
    """systemctl --value order is not the requested order (observed on
    node2: MainPID emitted first). The snapshot must parse keyed
    Name=value lines so ActiveEnterTimestamp/MainPID labels stay true."""
    keyed = "MainPID=574372\nActiveEnterTimestamp=Tue 2026-10-20 07:43:24 CEST\n"

    class R:
        stdout = keyed

    monkeypatch.setattr(rh.subprocess, "run", lambda *a, **k: R())
    snap = rh._live_snapshot()
    assert set(snap) == set(rh.LIVE_UNITS)
    for fields in snap.values():
        assert fields["MainPID"] == "574372"
        assert fields["ActiveEnterTimestamp"].endswith("07:43:24 CEST")


# ---------- decided env-set names (RESET-REHEARSAL-4) ----------


def test_env_carries_the_decided_env_set_names(tmp_path):
    """Every name the env-set decides must land in the profile — the six
    additions: paused bridge locks, consensus linger/view-change, and the
    sync pins all five hosts write."""
    env = _parse_env(rh._env_lines(tmp_path, rh.instances(tmp_path)[0], _keys()))
    assert env["BRIDGE_LOCKS_PAUSED"] == "true"
    assert env["ATTESTATION_POST_QUORUM_LINGER_SECONDS"] == "2.0"
    assert env["PBFT_VIEW_CHANGE_TIMEOUT"] == "30"
    assert env["AUTO_SYNC_ENABLED"] == "true"
    assert env["AUTO_SYNC_THRESHOLD"] == "0"
    assert env["STATE_SYNC_MAX_GAP"] == "-1"
    # and the long-standing decided names still hold
    assert env["GOSSIP_MAX_CONCURRENT_CONNECTIONS_PER_IP"] == "256"
    assert env["TRUSTED_PROPOSERS"].startswith("genesis,0x")


def test_env_bridge_admission_rows(tmp_path):
    """Env-set rows :64/:67/:68 — release admission + merkle-proof stay
    fleet-true; supported-chains admits only bc-2."""
    env = _parse_env(rh._env_lines(tmp_path, rh.instances(tmp_path)[0], _keys()))
    assert env["BRIDGE_RELEASE_ENABLED"] == "true"
    assert env["BRIDGE_SUPPORTED_CHAINS"] == "bc-2"
    assert env["BRIDGE_REQUIRE_MERKLE_PROOF"] == "true"


def test_env_documented_deviations_stay_at_defaults(tmp_path):
    """BLOCK_TIME_SECONDS (fleet 60) and PARALLEL_TX_VALIDATION (inert on
    bc-2) are documented deviations — the profile must NOT write them."""
    env = _parse_env(rh._env_lines(tmp_path, rh.instances(tmp_path)[0], _keys()))
    assert "BLOCK_TIME_SECONDS" not in env
    assert "PARALLEL_TX_VALIDATION" not in env


def test_untrusted_env_drops_only_the_named_address():
    keys = _keys()
    victim = keys["proposers"][3]["address"]
    original = f"TRUSTED_PROPOSERS='genesis,{','.join(p['address'] for p in keys['proposers'])}'\n"
    doctored = rh._untrusted_env(original, victim)
    assert victim not in doctored
    assert "genesis" in doctored
    for p in keys["proposers"][:3]:
        assert p["address"] in doctored
    # untouched when the address is absent
    assert rh._untrusted_env(original, "0x" + "ff" * 20) == original


# ---------- pause fence + timing helpers ----------


def test_check_bridge_paused_accepts_503(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        rh,
        "_post_json",
        lambda url, body: (503, {"detail": "Bridge paused: locks unavailable until validator attestation is live"}),
    )
    failures: list[str] = []
    rh._check_bridge_paused(rh.instances(tmp_path), failures)
    assert failures == []


def test_check_bridge_paused_flags_other_codes(tmp_path, monkeypatch):
    for code in (200, 403, 400, 0):
        monkeypatch.setattr(rh, "_post_json", lambda url, body, c=code: (c, {}))
        failures: list[str] = []
        rh._check_bridge_paused(rh.instances(tmp_path), failures)
        assert len(failures) == 1 and str(code) in failures[0]


def test_check_bridge_paused_flags_wrong_detail(tmp_path, monkeypatch):
    """A 503 that is NOT the pause fence (rpc not ready, db error, ...) must
    fail — status alone is not proof of BRIDGE_LOCKS_PAUSED."""
    monkeypatch.setattr(rh, "_post_json", lambda url, body: (503, {"detail": "database unavailable"}))
    failures: list[str] = []
    rh._check_bridge_paused(rh.instances(tmp_path), failures)
    assert len(failures) == 1 and "unexpected detail" in failures[0] and "database unavailable" in failures[0]


def test_parse_systemd_ts_and_span():
    # CEST input is normalized to naive UTC so the block-ts delta shares
    # one instant basis (a naive subtraction used to land ~-7200s).
    ts = rh._parse_systemd_ts("Mon 2026-10-20 07:43:42 CEST")
    assert ts is not None and (ts.year, ts.hour, ts.minute, ts.second) == (2026, 5, 43, 42)
    assert rh._parse_systemd_ts("Mon 2026-10-20 05:43:42 UTC") == ts
    assert rh._parse_systemd_ts("") is None
    assert rh._parse_systemd_ts("n/a") is None
    assert rh._parse_systemd_ts("Mon 2026-10-20 07:43:42 XYZ") is None  # unknown zone: unmeasured, not guessed
    a = rh._parse_systemd_ts("Mon 2026-10-19 19:42:01 CEST")
    b = rh._parse_systemd_ts("Mon 2026-10-19 19:42:03 CEST")
    assert rh._span_seconds([a, b]) == 2.0
    assert rh._span_seconds([a]) == 0.0


def test_parse_iso_ts():
    ts = rh._parse_iso_ts("2026-10-20T05:43:40.784513+00:00")
    assert ts is not None and ts.second == 40
    # an aware non-UTC input converts, a naive input is taken as UTC
    assert rh._parse_iso_ts("2026-10-20T07:43:40+02:00") == ts.replace(microsecond=0)
    assert rh._parse_iso_ts("2026-10-20T05:43:40.784513") == ts
    assert rh._parse_iso_ts("") is None
    assert rh._parse_iso_ts(None) is None
    assert rh._parse_iso_ts("not-a-date") is None


def test_phase_timing_cest_systemd_vs_utc_block(tmp_path, monkeypatch, capsys):
    """The reported delta: a CEST systemd string and a +00:00 block
    timestamp seconds apart must yield a small positive measured delta —
    this is the defect-1 repro (naive zones gave ~-7200s)."""
    insts = rh.instances(tmp_path)
    monkeypatch.setattr(rh, "instances", lambda root: insts)
    monkeypatch.setattr(rh, "_unit_field", lambda name, prop: "Tue 2026-10-20 07:43:42 CEST")
    monkeypatch.setattr(rh, "_block", lambda inst, h: {"timestamp": "2026-10-20T05:43:50+00:00"})
    rh.phase_timing(tmp_path)
    out = capsys.readouterr().out
    assert "block 1: 8.0s" in out and "measured" in out


def test_phase_timing_marks_mismatch_unmeasured(tmp_path, monkeypatch, capsys):
    insts = rh.instances(tmp_path)
    monkeypatch.setattr(rh, "instances", lambda root: insts)
    monkeypatch.setattr(rh, "_unit_field", lambda name, prop: "Tue 2026-10-20 05:50:00 UTC")
    monkeypatch.setattr(rh, "_block", lambda inst, h: {"timestamp": "2026-10-20T05:43:42+00:00"})
    rh.phase_timing(tmp_path)
    out = capsys.readouterr().out
    assert (
        "unmeasured" in out
        and "clock mismatch" in out
        and "block 1: 0" not in out
        and "(measured: journal+block ts)" not in out
    )


# ---------- fault phases (RESET-REHEARSAL-FAULTS-1) ----------


def test_stall_mark_matches_poa_refusal():
    """The stall mark must track poa.py's exact refusal line — both the
    attestation and PBFT counts and the 'need N' quorum tail."""
    assert rh.STALL_MARK.search(
        "Not enough attestations for multi-validator block 42: got 1 attestation(s) and 0 PBFT commit(s), need 2"
    )
    assert rh.STALL_MARK.search(
        "Not enough attestations for multi-validator block 7: got 0 attestation(s) and 0 PBFT commit(s), need 2"
    )
    assert not rh.STALL_MARK.search("Not enough attestations for multi-validator block")
    assert not rh.STALL_MARK.search("sealed block 42")


def test_node_log_reads_only_scratch_log(tmp_path):
    inst = rh.instances(tmp_path)[0]
    assert rh._node_log(inst) == ""
    log = inst.dir / "logs" / "node.log"
    log.parent.mkdir(parents=True)
    log.write_text(
        "line1\nNot enough attestations for multi-validator block 3: got 0 attestation(s) and 0 PBFT commit(s), need 2\n"
    )
    assert rh.STALL_MARK.search(rh._node_log(inst))


def test_corrupt_store_breaks_sqlite_header(tmp_path):
    inst = rh.instances(tmp_path)[0]
    db_dir = inst.dir / "data" / "bc-2"
    db_dir.mkdir(parents=True)
    db = db_dir / "chain.db"
    import sqlite3

    with sqlite3.connect(str(db)) as conn:
        conn.execute("CREATE TABLE t (x)")
    rh._corrupt_store(inst)
    with pytest.raises(sqlite3.DatabaseError):
        sqlite3.connect(str(db)).execute("SELECT * FROM t").fetchall()


def test_corrupt_store_refuses_missing_db(tmp_path):
    with pytest.raises(SystemExit):
        rh._corrupt_store(rh.instances(tmp_path)[0])


def test_wipe_store_keeps_only_genesis(tmp_path):
    root = tmp_path / "rehearsal"
    inst = rh.instances(root)[0]
    src = root / "genesis-build" / "out" / "data" / "bc-2"
    src.mkdir(parents=True)
    (src / "genesis.json").write_text('{"chain_id": "bc-2"}')
    data = inst.dir / "data" / "bc-2"
    data.mkdir(parents=True)
    (data / "chain.db").write_bytes(b"junk")
    (data / "genesis.json").write_text("stale")
    genesis = rh._wipe_store_keep_genesis(root, inst)
    assert genesis.read_text() == '{"chain_id": "bc-2"}', "must restore the genesis phase output, not the stale copy"
    assert [p.name for p in data.iterdir()] == ["genesis.json"]


def test_wipe_store_refuses_without_build_output(tmp_path):
    with pytest.raises(SystemExit):
        rh._wipe_store_keep_genesis(tmp_path, rh.instances(tmp_path)[0])


def test_corrective_tx_signature_verifies():
    """The corrective body must satisfy the same verification the rpc
    admission runs: sign_transaction_data over the canonical unsigned
    fields, recovered against the treasury address."""
    pytest.importorskip("eth_keys")
    pytest.importorskip("eth_utils")
    from aitbc_chain.rpc.utils import verify_transaction_signature

    keys = {**_keys(), "treasury": rh._mint_key()}
    recipient = "0x" + "99" * 20
    tx = rh._corrective_tx(keys, recipient, 7 * rh.UNITS_PER_AIT, 0)
    assert tx["from"] == keys["treasury"]["address"]
    assert tx["to"] == recipient
    assert tx["chain_id"] == "bc-2"
    assert tx["type"] == "TRANSFER"
    assert verify_transaction_signature(tx, tx["signature"], keys["treasury"]["address"])
    # and through the endpoint's own translation — validate_payload mutates
    # an absent/partial payload, so the signed body must carry it complete
    from aitbc_chain.rpc.transactions import TransactionRequest

    req = TransactionRequest.model_validate(tx)
    verified_dict = {
        "from": req.sender,
        "to": req.recipient,
        "amount": req.amount,
        "fee": req.fee,
        "nonce": req.nonce,
        "payload": req.payload,
        "type": req.type,
        "chain_id": tx["chain_id"],
        "signature": req.sig,
    }
    assert verify_transaction_signature(verified_dict, req.sig, req.sender)
    # a signature from a different key must not pass — the corrective is
    # treasury-only on the production path too
    assert not verify_transaction_signature(tx, tx["signature"], "0x" + "11" * 20)


def test_corrective_tx_uses_live_nonce(tmp_path):
    keys = _keys()
    tx = rh._corrective_tx(keys, "0x" + "11" * 20, 1, 9)
    assert tx["nonce"] == 9
    assert "signature" in tx and tx["signature"].startswith("0x")


# ---------- gossip filter + fork/gossip phases ----------


def _load_filter():
    spec = importlib.util.spec_from_file_location(
        "gossip_filter", REPO_ROOT / "scripts" / "reset-harness" / "gossip_filter.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["gossip_filter"] = module
    spec.loader.exec_module(module)
    return module


gf = _load_filter()


def test_filter_gate_transparent_until_armed():
    class Req:
        def __init__(self, path):
            self.path = path

    class Conn:
        @staticmethod
        def respond(status, body):
            return (status, body)

    state = {"deny": ["blocks.bc-2"], "armed": False}
    gate = gf._gate(state)
    # pre-trigger: everything proxies, even the denied topic
    assert gate(Conn(), Req("/rpc/gossip/ws?topic=blocks.bc-2&client_id=x")) is None
    state["armed"] = True
    assert gate(Conn(), Req("/rpc/gossip/ws?topic=blocks.bc-2"))[0] == 503
    assert gate(Conn(), Req("/rpc/gossip/ws?topic=consensus.attest_request.bc-2")) is None
    assert gate(Conn(), Req("/rpc/head"))[0] == 503


def test_filter_topic_gate_denies_listed_only():
    assert gf.topic_denied("blocks.bc-2", ["blocks.bc-2"])
    assert gf.topic_denied(None, ["blocks.bc-2"])  # malformed upgrade refused like websocket.py:104
    assert not gf.topic_denied("consensus.attest_request.bc-2", ["blocks.bc-2"])
    assert not gf.topic_denied("transactions.bc-2", ["blocks.bc-2"])
    assert gf.topic_denied("consensus.attest_response.bc-2", rh.ATTEST_TOPICS)
    assert not gf.topic_denied("blocks.bc-2", rh.ATTEST_TOPICS)


def _write_instance_envs(root: Path) -> None:
    keys = _keys()
    for inst in rh.instances(root):
        (inst.dir / "data").mkdir(parents=True, exist_ok=True)
        (inst.dir / "logs").mkdir(parents=True, exist_ok=True)
        (inst.dir / "instance.env").write_text(rh._env_lines(root, inst, keys))


def test_env_set_rewrites_exactly_one_assignment(tmp_path):
    text = "FOO='1'\nBAR='x,y'\n"
    assert rh._env_set(text, "BAR", "z") == "FOO='1'\nBAR='z'\n"
    with pytest.raises(SystemExit):
        rh._env_set(text, "MISSING", "1")


def test_partition_envs_route_block_plane_through_filter(tmp_path):
    root = tmp_path / "rehearsal"
    _write_instance_envs(root)
    victim = rh.instances(root)[3]
    trigger = root / "filter.trigger"
    specs, envs = rh._partition_envs(root, victim, trigger)
    # 1 shared inbound port + 4 outbound ports, all refusing blocks.* once armed
    assert len(specs) == 5
    assert {s["port"] for s in specs} == set(range(rh.FILTER_PORT_BASE, rh.FILTER_PORT_BASE + 5))
    for s in specs:
        assert s["deny_topics"] == ["blocks.bc-2"]
        assert s["trigger"] == str(trigger)
    inbound = rh.FILTER_PORT_BASE
    victim_env = _parse_env(envs[3])
    peer_env = _parse_env(envs[0])
    # victim: every mesh peer url is a filter port; every http url is dead;
    # its broadcast leg carries the dedicated ACL user
    vports = {int(u.split(":")[2].split("/")[0]) for u in victim_env["GOSSIP_MESH_PEER_URLS"].split(",")}
    assert vports == set(range(rh.FILTER_PORT_BASE + 1, rh.FILTER_PORT_BASE + 5))
    assert victim_env["GOSSIP_BROADCAST_URL"] == rh.VICTIM_REDIS_URL
    for name in (
        "DEFAULT_PEER_RPC_URL",
        "HUB_RPC_URL",
        "HUB_BLOCKCHAIN_RPC_URL",
        "AITBC_SYNC_SOURCE",
        "AITBC_SYNC_IMPORT_URL",
    ):
        assert victim_env[name] == f"http://127.0.0.1:{rh.FILTER_PORT_BASE + 1}"
    # peer: only the victim's entry is rerouted to the shared inbound port
    peer_urls = peer_env["GOSSIP_MESH_PEER_URLS"].split(",")
    assert f"ws://127.0.0.1:{inbound}/rpc/gossip/ws" in peer_urls
    assert not any(f":{victim.rpc_port}" in u for u in peer_urls)
    assert any(f":{rh.instances(root)[1].rpc_port}" in u for u in peer_urls)
    # untouched keys stay byte-identical — including the peer's broadcast url
    assert (
        peer_env["CHAIN_ID"] == "bc-2"
        and peer_env["VALIDATOR_SET"] == _parse_env((rh.instances(root)[0].dir / "instance.env").read_text())["VALIDATOR_SET"]
        and peer_env["GOSSIP_BROADCAST_URL"] == "redis://127.0.0.1:16379"
    )


def test_degrade_envs_attest_only_all_links(tmp_path):
    root = tmp_path / "rehearsal"
    _write_instance_envs(root)
    victim = rh.instances(root)[3]
    trigger = root / "gossip.trigger"
    specs, envs = rh._degrade_envs(root, victim, trigger)
    # shared inbound + one outbound per peer, attest topics denied once armed
    assert len(specs) == 5
    assert all(s["deny_topics"] == rh.ATTEST_TOPICS for s in specs)
    assert all(s["trigger"] == str(trigger) for s in specs)
    victim_env = _parse_env(envs[3])
    assert victim_env["GOSSIP_BROADCAST_URL"] == rh.VICTIM_REDIS_URL
    assert not any("blocks.bc-2" in s for s in victim_env["GOSSIP_MESH_PEER_URLS"].split(","))
    vports = {int(u.split(":")[2].split("/")[0]) for u in victim_env["GOSSIP_MESH_PEER_URLS"].split(",")}
    assert vports == set(range(rh.FILTER_PORT_BASE + 1, rh.FILTER_PORT_BASE + 5))
    # blocks/pulls untouched: sync source still points at i2's real rpc
    assert victim_env["AITBC_SYNC_SOURCE"] == f"http://127.0.0.1:{rh.PORT_BASE + 2}", "degrade must not cut the victim's pulls"
    # peers keep blocks conns to the victim's real port — only the victim
    # entry moves to the attest-refusing inbound port
    peer_urls = _parse_env(envs[0])["GOSSIP_MESH_PEER_URLS"].split(",")
    assert f"ws://127.0.0.1:{rh.FILTER_PORT_BASE}/rpc/gossip/ws" in peer_urls
    assert not any(f":{victim.rpc_port}" in u for u in peer_urls)


def test_acl_narrow_and_restore_commands(monkeypatch):
    calls = []
    monkeypatch.setattr(
        rh.subprocess,
        "run",
        lambda cmd, **kw: calls.append(cmd) or type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
    )
    rh._acl_narrow(["consensus.*", "transactions.*"])
    setuser = calls[0]
    assert setuser[:4] == ["redis-cli", "-p", "16379", "ACL"]
    i = setuser.index("resetchannels")
    assert setuser[i + 1 :] == ["&consensus.*", "&transactions.*"]
    assert calls[1][3:] == ["CLIENT", "KILL", "USER", rh.VICTIM_REDIS_USER]
    calls.clear()
    rh._acl_restore()
    assert "&*" in calls[0] and calls[1][3:] == ["CLIENT", "KILL", "USER", rh.VICTIM_REDIS_USER]
    # the fork keep-list drops only blocks.*; the M6 list only consensus.*
    assert "blocks.*" not in [c for c in rh.ALL_CHANNEL_FAMILIES if not c.startswith("blocks.")]
    assert "consensus.*" not in [c for c in rh.ALL_CHANNEL_FAMILIES if not c.startswith("consensus.")]


def test_rotation_slot_reads_recent_seals(monkeypatch):
    blocks = {h: {"proposer": f"0x{'ab' * 20}" if h % 4 == 2 else "0x" + "cd" * 20} for h in range(10, 19)}
    inst = rh.instances(Path("/nonexistent"))[0]
    monkeypatch.setattr(rh, "_head", lambda i: 18)
    monkeypatch.setattr(rh, "_block", lambda i, h: blocks.get(h))
    assert rh._rotation_slot(inst, "0x" + "AB" * 20) == 2
    assert rh._rotation_slot(inst, "0x" + "00" * 20) is None


def test_attesters_of_reads_metadata_attestations():
    blk = {
        "hash": "0xabc",
        "proposer": "0xP",
        "block_metadata": json.dumps({"attestations": [{"validator": "0xAA"}, {"validator": "0xbb"}]}),
    }
    assert rh._attesters_of(blk) == {"0xaa", "0xbb"}
    assert rh._attesters_of({}) == set()
    assert rh._attesters_of({"block_metadata": "not-json"}) == set()


def test_hash_and_proposer_of_tolerate_nested_shape():
    assert rh._hash_of({"hash": "0x1"}) == "0x1"
    assert rh._hash_of({"block": {"hash": "0x2"}}) == "0x2"
    assert rh._hash_of(None) == ""
    assert rh._proposer_of({"proposer": "0xA"}) == "0xA"
    assert rh._proposer_of({"block": {"proposer": "0xB"}}) == "0xB"


def test_consecutive_from_prom_finds_victim_streak():
    prom = "\n".join(
        [
            "# HELP aitbc_attestation_consecutive_missed Consecutive owed-but-missed blocks.",
            "# TYPE aitbc_attestation_consecutive_missed gauge",
            'aitbc_attestation_consecutive_missed{db="/x/i0/data/bc-2/chain.db",validator="0xAaAa"} 3',
            'aitbc_attestation_consecutive_missed{db="/x/i0/data/bc-2/chain.db",validator="0xBBBB"} 17',
            'aitbc_attestation_consecutive_missed{db="/x/i1/data/bc-2/chain.db",validator="0xBbbb"} 5',
            'aitbc_attestation_scrape_success{db="/x/i0/data/bc-2/chain.db"} 1',
            "",
        ]
    )
    assert rh._consecutive_from_prom(prom, "0xbbbb") == 17  # case-insensitive, max over dbs
    assert rh._consecutive_from_prom(prom, "0xAAAA") == 3
    assert rh._consecutive_from_prom(prom, "0xCCCC") == 0
    assert rh._consecutive_from_prom("", "0xbbbb") == 0
