"""The island swarm key is served, never minted.

`get_island_swarm_key` used to create a key when the directory was empty, using
the island id straight from the request body. A request naming no island did
not fail -- it minted a second island and handed the caller a key nobody else
holds. There is only one island, so any id but the provisioned one is wrong.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_MODULE = (
    Path(__file__).resolve().parents[2]
    / "apps/coordinator-api/src/coordinator_api/contexts/ipfs/services/island_ipfs_access.py"
)

_spec = importlib.util.spec_from_file_location("island_ipfs_access_under_test", _MODULE)
assert _spec and _spec.loader
island_ipfs_access = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = island_ipfs_access
_spec.loader.exec_module(island_ipfs_access)

ISLAND = "ait-hub.aitbc.bubuit.net-island"
KEY = "/key/swarm/psk/1.0.0/\n/base16/\n" + "ab" * 32 + "\n"


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path))
    return tmp_path


def _provision(data_dir: Path, island_id: str = ISLAND) -> Path:
    key_dir = data_dir / "ipfs-island" / island_id
    key_dir.mkdir(parents=True)
    key_file = key_dir / "swarm.key"
    key_file.write_text(KEY)
    return key_file


def test_returns_the_provisioned_key(data_dir):
    _provision(data_dir)
    assert island_ipfs_access.get_island_swarm_key(ISLAND) == KEY


def test_unknown_island_is_refused_and_creates_nothing(data_dir):
    _provision(data_dir)
    with pytest.raises(PermissionError):
        island_ipfs_access.get_island_swarm_key("ait-hub-island")
    # The old behaviour left a directory and a key behind.
    assert [p.name for p in (data_dir / "ipfs-island").iterdir()] == [ISLAND]


def test_island_id_cannot_escape_the_data_dir(data_dir):
    for island_id in ("../../etc", "a/b", "..", ".", ""):
        with pytest.raises(PermissionError):
            island_ipfs_access.get_island_swarm_key(island_id)
