"""Unit tests for the RESET-ROLLBACK-1 scratch rollback driver.

These run without node2 or systemd: path-guard reuse, manifest/checksum
compare, the 'nothing sealed' assertion, prior-run detection, env
isolation, and the pinned default spawn command line.
"""

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "reset-harness"))

import rehearsal  # noqa: E402
import rollback  # noqa: E402


def _inst(tmp_path: Path) -> rehearsal.Instance:
    return rehearsal.Instance(
        idx=0,
        name="bc2-i0",
        role="proposer",
        p2p_port=18400,
        rpc_port=18402,
        sync_port=18404,
        dir=tmp_path / "i0",
    )


def test_default_spawn_command_line_pinned(tmp_path):
    """The rehearsal's spawn line must not change — repo_root defaults to
    the module's own REPO_ROOT so existing callers are untouched."""
    inst = _inst(tmp_path)
    default = rehearsal._prelude(inst)
    explicit = rehearsal._prelude(inst, repo_root=rehearsal.REPO_ROOT)
    assert default == explicit
    assert f"PYTHONPATH={rehearsal.REPO_ROOT}:{rehearsal.REPO_ROOT}/apps/blockchain-node/src" in default
    assert f". {inst.dir}/instance.env" in default


def test_repo_root_override_retargets_pythonpath(tmp_path):
    inst = _inst(tmp_path)
    prelude = rehearsal._prelude(inst, repo_root=Path("/scratch/old-tree"))
    assert "PYTHONPATH=/scratch/old-tree:/scratch/old-tree/apps/blockchain-node/src" in prelude


def test_scratch_root_guard_reused():
    """rollback.py must refuse live prefixes through the same guard."""
    with pytest.raises(SystemExit):
        rollback.scratch_root("/var/lib/aitbc/bc2-rollback")
    with pytest.raises(SystemExit):
        rollback.scratch_root("relative/path")


def test_assert_nothing_sealed(tmp_path):
    db = tmp_path / "chain.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE block (height INTEGER, hash TEXT, state_root TEXT)")
    conn.execute("INSERT INTO block VALUES (0, '0xgen', '0xroot')")
    conn.commit()
    conn.close()
    assert rollback._assert_nothing_sealed(db) == 0

    conn = sqlite3.connect(str(db))
    conn.execute("INSERT INTO block VALUES (1, '0xone', '0xroot1')")
    conn.commit()
    conn.close()
    with pytest.raises(SystemExit):
        rollback._assert_nothing_sealed(db)


def test_detect_prior_run():
    before = {
        "ActiveEnterTimestamp": "Mon 2026-10-20 06:00:00 CEST",
        "ExecMainStartTimestamp": "Mon 2026-10-20 06:00:01 CEST",
        "MainPID": "100",
    }
    same = dict(before)
    assert rollback._detect_prior_run(before, same) is False
    newer = dict(before, ActiveEnterTimestamp="Mon 2026-10-20 07:00:00 CEST", MainPID="200")
    assert rollback._detect_prior_run(before, newer) is True


def test_manifest_write_and_verify(tmp_path):
    old_dir = tmp_path / "bc2rb-old-dir" / "data" / rollback.OLD_CHAIN_ID
    old_dir.mkdir(parents=True)
    (old_dir / "chain.db").write_bytes(b"chain-bytes")
    svc = tmp_path / "svc" / "coordinator"
    svc.mkdir(parents=True)
    (svc / "coordinator.db").write_bytes(b"svc-bytes")

    manifest = {"files": rollback._manifest_files(tmp_path)}
    rollback._write_manifest(tmp_path, manifest)
    assert rollback._verify_manifest(tmp_path) == []

    (old_dir / "chain.db").write_bytes(b"tampered")
    diffs = rollback._verify_manifest(tmp_path)
    assert diffs == ["sha256 changed bc2rb-old-dir/data/ait-hub.aitbc.bubuit.net/chain.db"]

    (old_dir / "chain.db").unlink()
    diffs = rollback._verify_manifest(tmp_path)
    assert diffs == ["missing bc2rb-old-dir/data/ait-hub.aitbc.bubuit.net/chain.db"]


def test_old_env_isolation(tmp_path):
    inst = rollback._old_instance(tmp_path, "bc2rb-old")
    env = rollback._old_env(tmp_path, inst)
    assert "AITBC_CHAIN_ENV_FILE=''" in env
    assert "GOSSIP_MESH_PEER_URLS=''" in env
    assert "ENABLE_BLOCK_PRODUCTION='false'" in env
    assert f"CHAIN_ID='{rollback.OLD_CHAIN_ID}'" in env
    assert "/etc/aitbc" not in env
    # no URL may point off-loopback
    for token in env.split():
        if "://" in token:
            assert "127.0.0.1" in token


def test_old_instance_ports_distinct(tmp_path):
    a = rollback._old_instance(tmp_path, "bc2rb-old")
    b = rollback._old_instance(tmp_path, "bc2rb-old2", slot=1)
    assert a.p2p_port != b.p2p_port
    assert {a.name, b.name} == {"bc2rb-old", "bc2rb-old2"}
    for inst in (a, b):
        assert inst.dir.is_relative_to(tmp_path)


def test_cut_env_swap_roundtrip(tmp_path):
    inst = rollback._old_instance(tmp_path, "bc2rb-old")
    rollback._write_old_env(tmp_path, inst)
    env_file = inst.dir / "instance.env"
    original = env_file.read_bytes()
    saved = rollback._cut_env_swap(inst)
    flipped = env_file.read_text()
    assert "CHAIN_ID='bc-2'" in flipped
    assert rollback.OLD_CHAIN_ID not in flipped
    assert saved == original
