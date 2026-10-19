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
