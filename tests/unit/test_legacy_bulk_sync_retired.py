"""#899: the stripped-block import scripts are retired.

bulk_sync.sh and fast_bulk_sync.sh rebuilt each block as six header
fields and posted that to /rpc/importBlock — transactions, signature,
state root dropped — with ports defaulting to 8006 while the RPC listens
on 8202. The node's own validated bulk sync (sync_bulk.py / `aitbc
network force-sync`) is the import path; the shell duplicates are gone
and stay gone.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_stripped_block_scripts_are_gone():
    for name in ("bulk_sync.sh", "fast_bulk_sync.sh"):
        assert not (REPO / "scripts" / "sync" / name).exists(), f"{name} is back"


def test_the_validated_import_path_still_exists():
    assert (REPO / "apps" / "blockchain-node" / "src" / "aitbc_chain" / "sync_bulk.py").is_file()
