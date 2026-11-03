"""Unit tests for the RESET-ROLLBACK-1 scratch rollback driver.

These run without node2 or systemd: path-guard reuse, manifest/checksum
compare, the 'nothing sealed' assertion, prior-run detection, env
isolation, and the pinned default spawn command line.
"""

import os
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


def test_unit_fields_parses_keyed_output(tmp_path, monkeypatch):
    """systemctl --value order is not the requested order — the parse must
    be keyed so evidence labels are true (observed on node2: MainPID first)."""
    out = "MainPID=574372\nExecMainStartTimestamp=Tue 2026-10-20 07:46:07 CEST\nActiveEnterTimestamp=Tue 2026-10-20 07:43:24 CEST\n"

    class R:
        stdout = out

    monkeypatch.setattr(rollback.subprocess, "run", lambda *a, **k: R())
    fields = rollback._unit_fields("bc2rb-old")
    assert fields["ActiveEnterTimestamp"].endswith("07:43:24 CEST")
    assert fields["ExecMainStartTimestamp"].endswith("07:46:07 CEST")
    assert fields["MainPID"] == "574372"


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


# ---------- #856: claim-before-teardown + atomic claim ----------


class _UnitsFree:
    """subprocess.run stub: no bc2 units live."""

    stdout = ""

    def __init__(self, *a, **k):
        pass


def _no_units(monkeypatch):
    monkeypatch.setattr(rehearsal.subprocess, "run", lambda *a, **k: _UnitsFree())


def test_refused_claim_writes_no_lock(tmp_path, monkeypatch):
    """#856: the unit check runs before the lock write — a run refused for
    live bc2 units must not leave its claim behind for another rehearsal."""
    monkeypatch.setattr(
        rehearsal.subprocess,
        "run",
        lambda *a, **k: type("R", (), {"stdout": "bc2-i0.service loaded active running\n"})(),
    )
    root = tmp_path / "scratch"
    with pytest.raises(SystemExit):
        rehearsal._claim_rehearsal(root)
    assert not (root / ".lock").exists()


def test_claim_then_reclaim_by_holder_is_reentrant(tmp_path, monkeypatch):
    """`run` claims up front, then phase_stage claims again internally —
    the second claim by the SAME pid must pass, not refuse."""
    _no_units(monkeypatch)
    root = tmp_path / "scratch"
    rehearsal._claim_rehearsal(root)
    rehearsal._claim_rehearsal(root)  # must not raise
    assert (root / ".lock").read_text().strip() == str(os.getpid())


def test_stale_lock_is_taken_over_atomically(tmp_path, monkeypatch):
    _no_units(monkeypatch)
    root = tmp_path / "scratch"
    root.mkdir()
    (root / ".lock").write_text("999999999")  # dead pid
    rehearsal._claim_rehearsal(root)
    assert (root / ".lock").read_text().strip() == str(os.getpid())


def test_live_lock_still_refuses(tmp_path, monkeypatch):
    _no_units(monkeypatch)
    root = tmp_path / "scratch"
    root.mkdir()
    (root / ".lock").write_text(str(os.getpid() if os.getpid() != 1 else os.getpid() + 1))
    # lock holds a live pid that is NOT ours: patch getpid so it looks foreign
    monkeypatch.setattr(os, "getpid", lambda: 424242)
    with pytest.raises(SystemExit):
        rehearsal._claim_rehearsal(root)


def test_takeover_race_loser_refuses(tmp_path, monkeypatch):
    """After os.replace, verify our pid landed; if the winner wrote last,
    the loser must refuse rather than proceed."""
    _no_units(monkeypatch)
    root = tmp_path / "scratch"
    root.mkdir()
    (root / ".lock").write_text("999999999")
    real_replace = os.replace

    def _winner_last(src, dst):
        real_replace(src, dst)
        Path(dst).write_text("31337")  # another racer overwrote us

    monkeypatch.setattr(rehearsal.os, "replace", _winner_last)
    with pytest.raises(SystemExit):
        rehearsal._claim_rehearsal(root)


def test_run_phase_does_not_teardown_when_claim_refused(tmp_path, monkeypatch):
    """The done_when scenario: `run` on a root whose lock is held must NOT
    call phase_teardown — that tore the other rehearsal's root down."""
    monkeypatch.setattr(rollback, "_claim_rehearsal", lambda root: (_ for _ in ()).throw(SystemExit(1)))
    calls = []
    monkeypatch.setattr(rollback, "phase_teardown", lambda root: calls.append(root))
    monkeypatch.setattr(
        sys,
        "argv",
        ["rollback.py", "--scratch", str(tmp_path / "scratch"), "run"],
    )
    with pytest.raises(SystemExit):
        rollback.main()
    assert calls == []
