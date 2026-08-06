"""Regression tests for the v0.5.10 x3600 balance migration (OPS-03, OPS-08).

The migration rewrites every balance on a chain and cannot be undone except by restoring
the backup it takes during the run. Two defects made that dangerous:

OPS-03  recalculate_state_root hashed a concatenated "address:balance:nonce;" string with
        sha256 and wrote the result as the genesis state root. The node computes a Merkle
        Patricia Trie root, so the two values could never agree -- and the script printed
        the root and reported success either way. The mismatch only surfaced when a node
        was started, after the balances had already been rewritten.

OPS-08  --chain-id and --data-path defaulted to the production chain and /var/lib/aitbc/
        data, and nothing was confirmed, so running the script with no arguments rewrote
        production balances.
"""

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "scripts" / "migration" / "scale_balances_3600x.py"
NODE_SRC = REPO_ROOT / "apps" / "blockchain-node" / "src"

CHAIN_ID = "test-chain"
ACCOUNTS = [
    ("0x1111111111111111111111111111111111111111", 3_600_000, 0),
    ("0x2222222222222222222222222222222222222222", 7_200_000, 5),
    ("0x3333333333333333333333333333333333333333", 123_456_789, 42),
]


@pytest.fixture(scope="module")
def migration():
    spec = importlib.util.spec_from_file_location("scale_balances_3600x", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def chain_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "chain.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE account (chain_id TEXT, address TEXT, balance INTEGER, nonce INTEGER)")
    conn.execute("CREATE TABLE block (chain_id TEXT, height INTEGER, state_root TEXT)")
    conn.executemany(
        "INSERT INTO account (chain_id, address, balance, nonce) VALUES (?, ?, ?, ?)",
        [(CHAIN_ID, address, balance, nonce) for address, balance, nonce in ACCOUNTS],
    )
    conn.execute(
        "INSERT INTO block (chain_id, height, state_root) VALUES (?, ?, ?)",
        (CHAIN_ID, 0, "0xstale"),
    )
    conn.commit()
    conn.close()
    return db_path


def node_state_root() -> str:
    """The root the node itself computes, via the same trie compute_state_root_full uses."""
    if str(NODE_SRC) not in sys.path:
        sys.path.insert(0, str(NODE_SRC))
    from aitbc_chain.state.merkle_patricia_trie import StateManager

    state_manager = StateManager()
    for address, balance, nonce in ACCOUNTS:
        state_manager.update_account(address, balance, nonce)
    return "0x" + state_manager.get_root().hex()


class TestStateRoot:
    def test_matches_the_root_the_node_computes(self, migration, chain_db):
        """The equality that makes the migrated chain startable."""
        assert migration.recalculate_state_root(chain_db, CHAIN_ID) == node_state_root()

    def test_writes_the_root_to_the_genesis_block(self, migration, chain_db):
        migration.recalculate_state_root(chain_db, CHAIN_ID)

        conn = sqlite3.connect(str(chain_db))
        stored = conn.execute("SELECT state_root FROM block WHERE height = 0 AND chain_id = ?", (CHAIN_ID,)).fetchone()[0]
        conn.close()

        assert stored == node_state_root()

    def test_is_hex_encoded_with_an_0x_prefix(self, migration, chain_db):
        """The node compares against an "0x"-prefixed string; the prefix is part of the format."""
        state_root = migration.recalculate_state_root(chain_db, CHAIN_ID)

        assert state_root.startswith("0x")
        assert len(state_root) == 66
        bytes.fromhex(state_root[2:])

    def test_reflects_the_scaled_balances(self, migration, chain_db):
        """A different set of balances must produce a different root."""
        before = migration.recalculate_state_root(chain_db, CHAIN_ID)

        conn = sqlite3.connect(str(chain_db))
        conn.execute("UPDATE account SET balance = balance * 3600 WHERE chain_id = ?", (CHAIN_ID,))
        conn.commit()
        conn.close()

        assert migration.recalculate_state_root(chain_db, CHAIN_ID) != before

    def test_reports_failure_when_there_are_no_accounts(self, migration, tmp_path):
        """It must return None rather than a root over an empty account set."""
        db_path = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE account (chain_id TEXT, address TEXT, balance INTEGER, nonce INTEGER)")
        conn.execute("CREATE TABLE block (chain_id TEXT, height INTEGER, state_root TEXT)")
        conn.commit()
        conn.close()

        assert migration.recalculate_state_root(db_path, CHAIN_ID) is None

    def test_reports_failure_when_there_is_no_genesis_block(self, migration, tmp_path):
        db_path = tmp_path / "no_genesis.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE account (chain_id TEXT, address TEXT, balance INTEGER, nonce INTEGER)")
        conn.execute("CREATE TABLE block (chain_id TEXT, height INTEGER, state_root TEXT)")
        conn.execute(
            "INSERT INTO account (chain_id, address, balance, nonce) VALUES (?, ?, ?, ?)",
            (CHAIN_ID, ACCOUNTS[0][0], ACCOUNTS[0][1], ACCOUNTS[0][2]),
        )
        conn.commit()
        conn.close()

        assert migration.recalculate_state_root(db_path, CHAIN_ID) is None


class TestInvocationSafety:
    def test_both_targeting_flags_are_required(self):
        """Running bare must not fall back to a chain id or data path at all."""
        source = MIGRATION.read_text()

        assert 'default="ait-hub.aitbc.bubuit.net"' not in source
        assert 'default="/var/lib/aitbc/data"' not in source
        assert source.count("required=True") >= 2

    def test_refuses_to_run_unattended_without_the_override(self, migration, monkeypatch):
        monkeypatch.delenv("CONFIRM_BALANCE_MIGRATION", raising=False)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)

        assert migration.confirm_migration(CHAIN_ID, Path("/var/lib/aitbc/data")) is False

    def test_the_override_allows_automation(self, migration, monkeypatch):
        monkeypatch.setenv("CONFIRM_BALANCE_MIGRATION", "yes")

        assert migration.confirm_migration(CHAIN_ID, Path("/var/lib/aitbc/data")) is True

    def test_the_override_must_be_exactly_yes(self, migration, monkeypatch):
        monkeypatch.setenv("CONFIRM_BALANCE_MIGRATION", "true")
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)

        assert migration.confirm_migration(CHAIN_ID, Path("/var/lib/aitbc/data")) is False

    def test_interactive_confirmation_requires_the_chain_id(self, migration, monkeypatch):
        """Pressing enter, or typing anything else, must abort."""
        monkeypatch.delenv("CONFIRM_BALANCE_MIGRATION", raising=False)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)

        monkeypatch.setattr("builtins.input", lambda *_: "")
        assert migration.confirm_migration(CHAIN_ID, Path("/data")) is False

        monkeypatch.setattr("builtins.input", lambda *_: "yes")
        assert migration.confirm_migration(CHAIN_ID, Path("/data")) is False

        monkeypatch.setattr("builtins.input", lambda *_: "some-other-chain")
        assert migration.confirm_migration(CHAIN_ID, Path("/data")) is False

        monkeypatch.setattr("builtins.input", lambda *_: CHAIN_ID)
        assert migration.confirm_migration(CHAIN_ID, Path("/data")) is True
