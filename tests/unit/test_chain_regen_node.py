"""Pins for scripts/utils/chain_regen_node.py (CHAIN-REGEN-NODE-UNGUARDED-RESET-1, #933).

The script hard-coded live paths and deleted the shared mempool.db on a bare
``reset --yes``. It is now scratch-gated like the other legacy reset tools:
``AITBC_RESET_SCRATCH`` must claim the data root, the chain id must not be
live, ``reset`` requires a verified ``backup`` manifest, and the delete set is
the target chain's own files only. The path roots are env-overridable
(``CHAIN_REGEN_*``) so the tests run the real functions against tmp dirs.
"""

import importlib.util
import json
import socket
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "utils" / "chain_regen_node.py"
CHAIN_ID = "tst-regen"
SERVICE = "definitely-not-a-real-unit.service"


def _load(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]):
    """Exec the script module fresh with the CHAIN_REGEN_*/AITBC_RESET_SCRATCH env set."""
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    name = f"chain_regen_node_{id(env)}"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _scratch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "scratch-root"
    (root / "data" / CHAIN_ID).mkdir(parents=True)
    (root / "etc").mkdir()
    (root / "systemd").mkdir()
    env = {
        "AITBC_RESET_SCRATCH": str(root),
        "CHAIN_REGEN_REPO_DIR": str(REPO_ROOT),
        "CHAIN_REGEN_DATA_ROOT": str(root / "data"),
        "CHAIN_REGEN_ENV_DIR": str(root / "etc"),
        "CHAIN_REGEN_SYSTEMD_DIR": str(root / "systemd"),
        "CHAIN_REGEN_BACKUP_ROOT": str(root / "backups"),
    }
    return root, _load(monkeypatch, env)


def _seed_chain_tree(root: Path) -> None:
    chain = root / "data" / CHAIN_ID
    (chain / "chain.db").write_bytes(b"not really sqlite")
    (chain / "genesis.json").write_text("{}")
    (chain / "mempool.db").write_bytes(b"chain mempool")
    other = root / "data" / "tst-other"
    other.mkdir()
    (other / "chain.db").write_bytes(b"other chain")
    (root / "data" / "mempool.db").write_bytes(b"shared mempool")
    (root / "data" / "mempool.db-wal").write_bytes(b"shared wal")


def test_reset_removes_only_the_target_chains_files(tmp_path, monkeypatch):
    root, mod = _scratch(tmp_path, monkeypatch)
    _seed_chain_tree(root)

    backup_root = root / "backups"
    mod.backup(CHAIN_ID, SERVICE, backup_root, "20260101T000000Z")
    manifest_path = backup_root / "20260101T000000Z" / socket.gethostname() / CHAIN_ID / "manifest.json"
    assert manifest_path.exists()

    result = mod.reset(CHAIN_ID, SERVICE, yes=True, force=True, backup_manifest=manifest_path)
    removed = {Path(p).name for p in result["removed"]}

    chain = root / "data" / CHAIN_ID
    assert not (chain / "chain.db").exists()
    assert not (chain / "mempool.db").exists()
    # The shared mempool and every other chain's files survive.
    assert (root / "data" / "mempool.db").exists()
    assert (root / "data" / "mempool.db-wal").exists()
    assert (root / "data" / "tst-other" / "chain.db").exists()
    assert removed == {"chain.db", "mempool.db"}
    # genesis.json was never in the delete set.
    assert (chain / "genesis.json").exists()


def test_reset_refuses_without_scratch_marker(tmp_path, monkeypatch):
    root = tmp_path / "scratch-root"
    root.mkdir()
    env = {
        "CHAIN_REGEN_REPO_DIR": str(REPO_ROOT),
        "CHAIN_REGEN_DATA_ROOT": str(root / "data"),
        "CHAIN_REGEN_ENV_DIR": str(root / "etc"),
        "CHAIN_REGEN_SYSTEMD_DIR": str(root / "systemd"),
    }
    for key in ("AITBC_RESET_SCRATCH",):
        monkeypatch.delenv(key, raising=False)
    mod = _load(monkeypatch, env)
    with pytest.raises(SystemExit, match="reset-guard"):
        mod.reset(CHAIN_ID, SERVICE, yes=True, force=True, backup_manifest=root / "none.json")


def test_reset_refuses_manifest_for_another_chain(tmp_path, monkeypatch):
    root, mod = _scratch(tmp_path, monkeypatch)
    _seed_chain_tree(root)
    mod.backup(CHAIN_ID, SERVICE, root / "backups", "20260101T000000Z")
    manifest_path = root / "backups" / "20260101T000000Z" / socket.gethostname() / CHAIN_ID / "manifest.json"
    doc = json.loads(manifest_path.read_text())
    doc["chain_id"] = "tst-other"
    bad = root / "bad-manifest.json"
    bad.write_text(json.dumps(doc))
    with pytest.raises(SystemExit, match="chain_id"):
        mod.reset(CHAIN_ID, SERVICE, yes=True, force=True, backup_manifest=bad)
    # Nothing was deleted.
    assert (root / "data" / CHAIN_ID / "chain.db").exists()


def test_reset_refuses_missing_manifest(tmp_path, monkeypatch):
    _root, mod = _scratch(tmp_path, monkeypatch)
    with pytest.raises(SystemExit, match="manifest not found"):
        mod.reset(CHAIN_ID, SERVICE, yes=True, force=True, backup_manifest=tmp_path / "nope.json")


def test_set_role_refuses_without_scratch(tmp_path, monkeypatch):
    root = tmp_path / "scratch-root"
    root.mkdir()
    monkeypatch.delenv("AITBC_RESET_SCRATCH", raising=False)
    mod = _load(
        monkeypatch,
        {
            "CHAIN_REGEN_REPO_DIR": str(REPO_ROOT),
            "CHAIN_REGEN_DATA_ROOT": str(root / "data"),
            "CHAIN_REGEN_SYSTEMD_DIR": str(root / "systemd"),
        },
    )
    with pytest.raises(SystemExit, match="reset-guard"):
        mod.set_role(CHAIN_ID, SERVICE, "leader")
