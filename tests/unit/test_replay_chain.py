"""Tests for scripts/ops/replay-chain.py — checkpoint mode and stub capping.

The module itself is stdlib-only (aitbc_chain imports are lazy, inside the
functions that need them); the state-root proof tests skip when aitbc_chain
is not importable.
"""

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ops" / "replay-chain.py"

CHAIN = "replay-test"
TIP = 9


@pytest.fixture(scope="module")
def replay_chain():
    spec = importlib.util.spec_from_file_location("replay_chain", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["replay_chain"] = module
    spec.loader.exec_module(module)
    return module


def _block_row(height: int, hash_: str, parent: str = "0x00", state_root: str = "0x00") -> tuple:
    return (CHAIN, height, hash_, parent, "0xproposer", "2026-01-01T00:00:00+00:00", 0, state_root, None, None, "sig")


def _make_db(path: Path, blocks: list[tuple], accounts: list[tuple] | None = None) -> Path:
    """Minimal chain.db carrying exactly the columns replay-chain queries."""
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute(
        "CREATE TABLE block (chain_id TEXT, height INTEGER, hash TEXT, parent_hash TEXT, "
        "proposer TEXT, timestamp TEXT, tx_count INTEGER, state_root TEXT, "
        "bridge_state_root TEXT, block_metadata TEXT, signature TEXT)"
    )
    db.execute(
        'CREATE TABLE "transaction" (id INTEGER PRIMARY KEY, chain_id TEXT, block_height INTEGER, '
        "sender TEXT, recipient TEXT, payload TEXT, envelope TEXT, created_at TEXT)"
    )
    db.execute("CREATE TABLE account (chain_id TEXT, address TEXT, balance INTEGER, nonce INTEGER)")
    db.executemany("INSERT INTO block VALUES (?,?,?,?,?,?,?,?,?,?,?)", blocks)
    for addr, balance, nonce in accounts or []:
        db.execute("INSERT INTO account VALUES (?,?,?,?)", (CHAIN, addr, balance, nonce))
    db.commit()
    db.close()
    return path


@pytest.fixture()
def snapshot_db(tmp_path):
    blocks = [_block_row(h, f"0x{h:064x}", f"0x{h - 1:064x}" if h else "0x00") for h in range(TIP + 1)]
    return _make_db(tmp_path / "snapshot.db", blocks)


def _state_root_for(accounts: dict[str, tuple[int, int]]) -> str:
    """Real MPT root — the same value a production checkpoint would record."""
    from aitbc_chain.base_models import Account
    from aitbc_chain.state.merkle_patricia_trie import StateManager

    objs = {addr: Account(chain_id=CHAIN, address=addr, balance=bal, nonce=nonce) for addr, (bal, nonce) in accounts.items()}
    return "0x" + StateManager().compute_state_root(objs).hex()


class TestParseArgs:
    def test_checkpoint_makes_genesis_optional(self, replay_chain, tmp_path):
        snap = tmp_path / "snap.db"
        ckpt = tmp_path / "ckpt.db"
        snap.touch()
        ckpt.touch()
        args = replay_chain._parse_args(["--snapshot", str(snap), "--checkpoint", str(ckpt), "--chain-id", CHAIN])
        assert args.checkpoint == str(ckpt.resolve())
        assert args.genesis is None

    def test_genesis_required_without_checkpoint(self, replay_chain, tmp_path):
        snap = tmp_path / "snap.db"
        snap.touch()
        with pytest.raises(SystemExit) as exc:
            replay_chain._parse_args(["--snapshot", str(snap), "--chain-id", CHAIN])
        assert exc.value.code == 2

    def test_genesis_defaulted_beside_snapshot(self, replay_chain, tmp_path):
        snap = tmp_path / "snap.db"
        snap.touch()
        (tmp_path / "genesis.json").write_text("{}")
        args = replay_chain._parse_args(["--snapshot", str(snap), "--chain-id", CHAIN])
        assert args.genesis == str(tmp_path / "genesis.json")

    def test_missing_checkpoint_file_rejected(self, replay_chain, tmp_path):
        snap = tmp_path / "snap.db"
        snap.touch()
        with pytest.raises(SystemExit) as exc:
            replay_chain._parse_args(["--snapshot", str(snap), "--checkpoint", str(tmp_path / "gone.db"), "--chain-id", CHAIN])
        assert exc.value.code == 2

    def test_checkpoint_same_as_snapshot_rejected(self, replay_chain, tmp_path):
        snap = tmp_path / "snap.db"
        snap.touch()
        with pytest.raises(SystemExit) as exc:
            replay_chain._parse_args(["--snapshot", str(snap), "--checkpoint", str(snap), "--chain-id", CHAIN])
        assert exc.value.code == 2

    def test_genesis_ignored_with_checkpoint(self, replay_chain, tmp_path, capsys):
        snap = tmp_path / "snap.db"
        ckpt = tmp_path / "ckpt.db"
        snap.touch()
        ckpt.touch()
        gen = tmp_path / "g.json"
        gen.write_text("{}")
        args = replay_chain._parse_args(
            ["--snapshot", str(snap), "--checkpoint", str(ckpt), "--genesis", str(gen), "--chain-id", CHAIN]
        )
        assert args.genesis is None
        assert "--genesis ignored" in capsys.readouterr().err

    def test_chain_id_required(self, replay_chain, tmp_path, monkeypatch):
        monkeypatch.delenv("CHAIN_ID", raising=False)
        snap = tmp_path / "snap.db"
        snap.touch()
        with pytest.raises(SystemExit) as exc:
            replay_chain._parse_args(["--snapshot", str(snap)])
        assert exc.value.code == 2


class TestSnapshotCap:
    """The stub's served head is what stops a --to-height import."""

    def test_head_reports_real_tip_without_cap(self, replay_chain, snapshot_db):
        src = replay_chain._SnapshotSource(str(snapshot_db), CHAIN)
        assert src.head()["height"] == TIP

    def test_head_and_range_capped(self, replay_chain, snapshot_db):
        src = replay_chain._SnapshotSource(str(snapshot_db), CHAIN, cap_height=5)
        assert src.head()["height"] == 5
        assert src.head()["hash"] == f"0x{5:064x}"
        assert src.tip_height() == TIP  # real tip still visible for messaging
        assert [b["height"] for b in src.blocks_range(3, 99)["blocks"]] == [3, 4, 5]
        assert src.blocks_range(7, 9)["blocks"] == []

    def test_cap_above_tip_is_noop(self, replay_chain, snapshot_db):
        src = replay_chain._SnapshotSource(str(snapshot_db), CHAIN, cap_height=TIP + 100)
        assert src.head()["height"] == TIP


class TestCheckpointHead:
    def test_no_blocks_returns_none(self, replay_chain, tmp_path):
        path = _make_db(tmp_path / "empty.db", [])
        assert replay_chain._read_checkpoint_head(str(path), CHAIN) is None

    def test_wrong_chain_returns_none(self, replay_chain, tmp_path):
        blocks = [_block_row(h, f"0x{h:064x}") for h in range(3)]
        path = _make_db(tmp_path / "other.db", blocks)
        db = sqlite3.connect(path)
        db.execute("UPDATE block SET chain_id = 'other-chain'")
        db.commit()
        db.close()
        assert replay_chain._read_checkpoint_head(str(path), CHAIN) is None

    def test_reads_head_and_account_count(self, replay_chain, tmp_path):
        blocks = [_block_row(h, f"0x{h:064x}", state_root=f"0x{h:032x}root") for h in range(4)]
        path = _make_db(tmp_path / "ckpt.db", blocks, accounts=[("0xA", 100, 1), ("0xB", 50, 0)])
        ckpt = replay_chain._read_checkpoint_head(str(path), CHAIN)
        assert ckpt is not None
        assert ckpt.height == 3
        assert ckpt.hash == f"0x{3:064x}"
        assert ckpt.state_root == f"0x{3:032x}root"
        assert ckpt.accounts == 2


class TestValidateCheckpoint:
    """Proof failures that never reach the aitbc_chain-dependent root check."""

    def test_tip_at_or_above_end_fails(self, replay_chain, snapshot_db, tmp_path, capsys):
        ckpt_db = _make_db(tmp_path / "ckpt.db", [_block_row(TIP, f"0x{TIP:064x}")], accounts=[("0xA", 1, 0)])
        src = replay_chain._SnapshotSource(str(snapshot_db), CHAIN)
        assert replay_chain._validate_checkpoint(str(ckpt_db), CHAIN, src, end=TIP) is None
        assert "nothing to replay" in capsys.readouterr().err

    def test_lineage_mismatch_fails(self, replay_chain, snapshot_db, tmp_path, capsys):
        ckpt_db = _make_db(tmp_path / "ckpt.db", [_block_row(4, "0xdeadbeef")], accounts=[("0xA", 1, 0)])
        src = replay_chain._SnapshotSource(str(snapshot_db), CHAIN)
        assert replay_chain._validate_checkpoint(str(ckpt_db), CHAIN, src, end=TIP) is None
        assert "not on this chain" in capsys.readouterr().err

    def test_forked_next_block_fails(self, replay_chain, snapshot_db, tmp_path, capsys):
        # Checkpoint head matches snapshot at C, but snapshot's C+1 names a
        # different parent — the checkpoint sits on a pruned fork.
        blocks = [_block_row(h, f"0x{h:064x}") for h in range(TIP + 1)]
        snap = _make_db(tmp_path / "snap2.db", blocks)
        db = sqlite3.connect(snap)
        db.execute("UPDATE block SET parent_hash = '0xforked' WHERE height = 5")
        db.commit()
        db.close()
        ckpt_db = _make_db(tmp_path / "ckpt.db", [_block_row(4, f"0x{4:064x}")], accounts=[("0xA", 1, 0)])
        src = replay_chain._SnapshotSource(str(snap), CHAIN)
        assert replay_chain._validate_checkpoint(str(ckpt_db), CHAIN, src, end=TIP) is None
        assert "different fork" in capsys.readouterr().err

    def test_missing_state_root_fails(self, replay_chain, snapshot_db, tmp_path, capsys):
        ckpt_db = _make_db(tmp_path / "ckpt.db", [_block_row(4, f"0x{4:064x}", state_root=None)], accounts=[("0xA", 1, 0)])
        src = replay_chain._SnapshotSource(str(snapshot_db), CHAIN)
        assert replay_chain._validate_checkpoint(str(ckpt_db), CHAIN, src, end=TIP) is None
        assert "no recorded state_root" in capsys.readouterr().err

    def test_no_accounts_fails(self, replay_chain, snapshot_db, tmp_path, capsys):
        ckpt_db = _make_db(tmp_path / "ckpt.db", [_block_row(4, f"0x{4:064x}")], accounts=[])
        src = replay_chain._SnapshotSource(str(snapshot_db), CHAIN)
        assert replay_chain._validate_checkpoint(str(ckpt_db), CHAIN, src, end=TIP) is None
        assert "not state-bearing" in capsys.readouterr().err


class TestCheckpointStateRoot:
    """The state-bearing proof — needs the real MPT from aitbc_chain."""

    @pytest.fixture(autouse=True)
    def _require_aitbc(self):
        pytest.importorskip("aitbc_chain")

    def _checkpoint_db(self, tmp_path, height, accounts, recorded_root):
        blocks = [_block_row(h, f"0x{h:064x}", state_root=recorded_root) for h in range(height + 1)]
        return _make_db(tmp_path / "ckpt.db", blocks, accounts=[(a, b, n) for a, (b, n) in accounts.items()])

    def test_recomputes_root_over_account_table(self, replay_chain, tmp_path):
        accounts = {"0xAAA": (1000, 2), "0xBBB": (500, 0), "0xCCC": (7, 11)}
        root = _state_root_for(accounts)
        path = self._checkpoint_db(tmp_path, 4, accounts, root)
        assert replay_chain._checkpoint_state_root(str(path), CHAIN) == root

    def test_empty_accounts_returns_none(self, replay_chain, tmp_path):
        path = self._checkpoint_db(tmp_path, 4, {}, "0x00")
        assert replay_chain._checkpoint_state_root(str(path), CHAIN) is None

    def test_validate_happy_path(self, replay_chain, tmp_path, capsys):
        accounts = {"0xAAA": (1000, 2), "0xBBB": (500, 0)}
        root = _state_root_for(accounts)
        ckpt_path = self._checkpoint_db(tmp_path, 4, accounts, root)
        # Snapshot: same lineage (hash 0x4 at height 4), C+1 parented on it.
        blocks = [_block_row(h, f"0x{h:064x}", f"0x{h - 1:064x}" if h else "0x00") for h in range(TIP + 1)]
        snap = _make_db(tmp_path / "snap.db", blocks)
        src = replay_chain._SnapshotSource(str(snap), CHAIN)
        ckpt = replay_chain._validate_checkpoint(str(ckpt_path), CHAIN, src, end=TIP)
        assert ckpt is not None
        assert ckpt.height == 4
        assert "checkpoint verified" in capsys.readouterr().out

    def test_validate_root_mismatch_fails(self, replay_chain, tmp_path, capsys):
        accounts = {"0xAAA": (1000, 2)}
        wrong_root = _state_root_for({"0xAAA": (9999, 2)})  # recorded root of a different state
        ckpt_path = self._checkpoint_db(tmp_path, 4, accounts, wrong_root)
        blocks = [_block_row(h, f"0x{h:064x}", f"0x{h - 1:064x}" if h else "0x00") for h in range(TIP + 1)]
        snap = _make_db(tmp_path / "snap.db", blocks)
        src = replay_chain._SnapshotSource(str(snap), CHAIN)
        assert replay_chain._validate_checkpoint(str(ckpt_path), CHAIN, src, end=TIP) is None
        err = capsys.readouterr().err
        assert "does not reproduce the recorded state root" in err
        assert wrong_root in err


class TestCopyCheckpoint:
    def test_copy_lands_at_chain_db_path(self, replay_chain, tmp_path):
        ckpt = _make_db(tmp_path / "ckpt.db", [_block_row(4, f"0x{4:064x}")])
        workdir = tmp_path / "work"
        target = replay_chain._copy_checkpoint(str(ckpt), workdir, CHAIN)
        assert target == workdir / "data" / CHAIN / "chain.db"
        assert target.exists()
        rows = sqlite3.connect(target).execute("SELECT COUNT(*) FROM block").fetchone()[0]
        assert rows == 1
        # Source untouched (read-only contract).
        rows = sqlite3.connect(ckpt).execute("SELECT COUNT(*) FROM block").fetchone()[0]
        assert rows == 1


class TestCompareState:
    """Wholesale non-history comparison — the checkpoint-to-checkpoint layer."""

    def _replayed_target(self, tmp_path, blocks, accounts):
        db_path = tmp_path / "replayed.db"
        _make_db(db_path, blocks, accounts)
        return db_path

    def test_identical_state_passes(self, replay_chain, tmp_path):
        blocks = [_block_row(h, f"0x{h:064x}") for h in range(TIP + 1)]
        accounts = [("0xA", 100, 1), ("0xB", 50, 0)]
        compare = _make_db(tmp_path / "ckpt-b.db", blocks, accounts)
        target = self._replayed_target(tmp_path / "r", blocks, accounts)
        assert replay_chain._compare_state(str(compare), target, CHAIN, TIP) is True

    def test_tip_mismatch_refused(self, replay_chain, tmp_path, capsys):
        blocks = [_block_row(h, f"0x{h:064x}") for h in range(TIP + 1)]
        compare = _make_db(tmp_path / "ckpt-b.db", blocks)
        target = self._replayed_target(tmp_path / "r", blocks, [])
        assert replay_chain._compare_state(str(compare), target, CHAIN, end=TIP - 1) is False
        assert "!= replay end" in capsys.readouterr().err

    def test_account_divergence_reported(self, replay_chain, tmp_path, capsys):
        blocks = [_block_row(h, f"0x{h:064x}") for h in range(TIP + 1)]
        compare = _make_db(tmp_path / "ckpt-b.db", blocks, accounts=[("0xA", 100, 1)])
        target = self._replayed_target(tmp_path / "r", blocks, accounts=[("0xA", 101, 1)])
        assert replay_chain._compare_state(str(compare), target, CHAIN, TIP) is False
        err = capsys.readouterr()
        assert "account: DIVERGED" in err.out

    def test_history_tables_not_compared(self, replay_chain, tmp_path):
        # Block/tx rows differ but are covered by _verify's hash+root check —
        # wholesale state compare must not flag them.
        cmp_blocks = [_block_row(h, f"0x{h:064x}") for h in range(TIP + 1)]
        tgt_blocks = [_block_row(h, f"0xother{h}") for h in range(TIP + 1)]
        accounts = [("0xA", 100, 1)]
        compare = _make_db(tmp_path / "ckpt-b.db", cmp_blocks, accounts)
        target = self._replayed_target(tmp_path / "r", tgt_blocks, accounts)
        assert replay_chain._compare_state(str(compare), target, CHAIN, TIP) is True

    def test_aux_table_divergence_caught(self, replay_chain, tmp_path, capsys):
        blocks = [_block_row(h, f"0x{h:064x}") for h in range(TIP + 1)]
        accounts = [("0xA", 100, 1)]
        escrow_ddl = "CREATE TABLE escrow (chain_id TEXT, job_id TEXT, amount INTEGER)"
        for name in ("ckpt-b.db", "r/replayed.db"):
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            _make_db(path, blocks, accounts)
            db = sqlite3.connect(path)
            db.execute(escrow_ddl)
            db.commit()
            db.close()
        db = sqlite3.connect(tmp_path / "ckpt-b.db")
        db.execute("INSERT INTO escrow VALUES (?, ?, ?)", (CHAIN, "job1", 700))
        db.commit()
        db.close()
        db = sqlite3.connect(tmp_path / "r" / "replayed.db")
        db.execute("INSERT INTO escrow VALUES (?, ?, ?)", (CHAIN, "job1", 701))
        db.commit()
        db.close()
        assert replay_chain._compare_state(str(tmp_path / "ckpt-b.db"), tmp_path / "r" / "replayed.db", CHAIN, TIP) is False
        assert "escrow: DIVERGED" in capsys.readouterr().out

    def test_volatile_columns_ignored(self, replay_chain, tmp_path):
        blocks = [_block_row(h, f"0x{h:064x}") for h in range(TIP + 1)]
        accounts = [("0xA", 100, 1)]
        compare = _make_db(tmp_path / "ckpt-b.db", blocks, accounts)
        target = self._replayed_target(tmp_path / "r", blocks, accounts)
        # transaction rows carry created_at — a volatile column — but the
        # table itself is history (excluded); prove volatile dropping on the
        # account table shape instead via a table that keeps a *_at column.
        for path in (compare, target):
            db = sqlite3.connect(path)
            db.execute("CREATE TABLE stake (chain_id TEXT, address TEXT, amount INTEGER, updated_at TEXT)")
            db.commit()
            db.close()
        for path, ts in ((compare, "2026-09-01T00:00:00"), (target, "2026-10-05T00:00:00")):
            db = sqlite3.connect(path)
            db.execute("INSERT INTO stake VALUES (?, ?, ?, ?)", (CHAIN, "0xA", 5, ts))
            db.commit()
            db.close()
        assert replay_chain._compare_state(str(compare), target, CHAIN, TIP) is True
