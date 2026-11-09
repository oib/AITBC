"""Service-layer tests for ipfs/services/island_ipfs_access.py (#1289 residual).

Covers the paid-gated swarm-key path end to end against a scratch chain DB:
subscription lookup, expiry/quota gates, signature verification, swarm-key
file reads, and the path-traversal guard on island_id. AITBC_DATA_DIR is
redirected to tmp_path; verify_signature is monkeypatched at the module
boundary (the crypto itself is covered elsewhere).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from coordinator_api.contexts.ipfs.services import island_ipfs_access as svc
from aitbc.crypto.signature_recovery import canonical_address

CHAIN_ID = "testchain"
ISLAND = "island-a"
MEMBER = "0x" + "ab" * 20


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def chain_db(data_dir: Path) -> Path:
    """Scratch chain DB with block + ipfs_subscription tables."""
    db_dir = data_dir / CHAIN_ID
    db_dir.mkdir(parents=True)
    db = db_dir / "chain.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("CREATE TABLE block (chain_id TEXT, height INTEGER)")
        conn.execute(
            "CREATE TABLE ipfs_subscription (chain_id TEXT, island_id TEXT, member_address TEXT,"
            " expires_at_block INTEGER, quota_bytes INTEGER, used_bytes INTEGER)"
        )
        conn.execute("INSERT INTO block VALUES (?, ?)", (CHAIN_ID, 100))
        conn.execute(
            "INSERT INTO ipfs_subscription VALUES (?, ?, ?, ?, ?, ?)",
            (CHAIN_ID, ISLAND, canonical_address(MEMBER), 200, 1000, 100),
        )
        conn.commit()
    return db


@pytest.fixture
def swarm_key(data_dir: Path) -> Path:
    key_dir = data_dir / "ipfs-island" / ISLAND
    key_dir.mkdir(parents=True)
    key_file = key_dir / "swarm.key"
    key_file.write_text("test-swarm-key-material")
    return key_file


class TestChainDbPath:
    def test_prefers_chain_subdir(self, data_dir: Path, chain_db: Path) -> None:
        assert svc._chain_db_path(CHAIN_ID) == chain_db

    def test_falls_back_to_flat_db(self, data_dir: Path) -> None:
        (data_dir / "chain.db").write_text("")
        assert svc._chain_db_path("other") == data_dir / "chain.db"

    def test_missing_returns_expected_path(self, data_dir: Path) -> None:
        assert svc._chain_db_path("nope") == data_dir / "nope" / "chain.db"


class TestBlockHeight:
    def test_reads_max_height(self, chain_db: Path) -> None:
        assert svc.get_current_block_height(CHAIN_ID) == 100

    def test_missing_db_returns_zero(self, data_dir: Path) -> None:
        assert svc.get_current_block_height("ghost") == 0

    def test_corrupt_db_returns_zero(self, data_dir: Path) -> None:
        bad = data_dir / "bad" / "chain.db"
        bad.parent.mkdir(parents=True)
        bad.write_text("not sqlite")
        assert svc.get_current_block_height("bad") == 0


class TestSubscriptionLookup:
    def test_active_subscription_found(self, chain_db: Path) -> None:
        sub = svc.get_ipfs_subscription(CHAIN_ID, ISLAND, MEMBER)
        assert sub == {"expires_at_block": 200, "quota_bytes": 1000, "used_bytes": 100}

    def test_address_normalized_before_lookup(self, chain_db: Path) -> None:
        # lowercase input must still match the canonical stored row
        sub = svc.get_ipfs_subscription(CHAIN_ID, ISLAND, MEMBER.lower())
        assert sub is not None

    def test_wrong_island_returns_none(self, chain_db: Path) -> None:
        assert svc.get_ipfs_subscription(CHAIN_ID, "island-b", MEMBER) is None

    def test_missing_db_returns_none(self, data_dir: Path) -> None:
        assert svc.get_ipfs_subscription("ghost", ISLAND, MEMBER) is None


class TestSubscriptionActive:
    def test_active_when_unexpired_under_quota(self, chain_db: Path) -> None:
        assert svc.is_ipfs_subscription_active(CHAIN_ID, ISLAND, MEMBER) is True

    def test_expired_at_boundary(self, chain_db: Path) -> None:
        # current height 100; push expiry to exactly 100 -> expired
        with sqlite3.connect(str(chain_db)) as conn:
            conn.execute("UPDATE ipfs_subscription SET expires_at_block = 100 WHERE island_id = ?", (ISLAND,))
        assert svc.is_ipfs_subscription_active(CHAIN_ID, ISLAND, MEMBER) is False

    def test_quota_exhausted(self, chain_db: Path) -> None:
        with sqlite3.connect(str(chain_db)) as conn:
            conn.execute("UPDATE ipfs_subscription SET used_bytes = 1000 WHERE island_id = ?", (ISLAND,))
        assert svc.is_ipfs_subscription_active(CHAIN_ID, ISLAND, MEMBER) is False

    def test_no_subscription_false(self, chain_db: Path) -> None:
        assert svc.is_ipfs_subscription_active(CHAIN_ID, "island-b", MEMBER) is False


class TestSwarmKeyDir:
    @pytest.mark.parametrize("bad", ["", ".", "..", "a/b", "a\\b"])
    def test_rejects_unsafe_island_ids(self, data_dir: Path, bad: str) -> None:
        with pytest.raises(PermissionError, match="Invalid island id"):
            svc._swarm_key_dir(bad)

    def test_accepts_normal_id(self, data_dir: Path) -> None:
        assert svc._swarm_key_dir(ISLAND) == data_dir / "ipfs-island" / ISLAND


class TestIslandSwarmKey:
    def test_reads_existing_key(self, data_dir: Path, swarm_key: Path) -> None:
        assert svc.get_island_swarm_key(ISLAND) == "test-swarm-key-material"

    def test_never_creates_missing_key(self, data_dir: Path) -> None:
        with pytest.raises(PermissionError, match="Unknown island"):
            svc.get_island_swarm_key("island-ghost")
        assert not (data_dir / "ipfs-island" / "island-ghost").exists()

    def test_traversal_island_rejected(self, data_dir: Path) -> None:
        with pytest.raises(PermissionError):
            svc.get_island_swarm_key("../etc")


class TestVerifyMemberSignature:
    def test_empty_inputs_false(self) -> None:
        assert svc.verify_member_signature(ISLAND, "", "n", "sig") is False
        assert svc.verify_member_signature(ISLAND, MEMBER, "n", "") is False

    def test_delegates_to_verify_signature(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = {}

        def fake_verify(msg_hash: bytes, signature: str, address: str) -> bool:
            calls["args"] = (msg_hash, signature, address)
            return True

        monkeypatch.setattr(svc, "verify_signature", fake_verify)
        assert svc.verify_member_signature(ISLAND, MEMBER, "nonce1", "0xsig") is True
        assert calls["args"][1] == "0xsig"
        assert calls["args"][2] == MEMBER

    def test_verify_exception_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(*_a: object) -> bool:
            raise ValueError("bad sig")

        monkeypatch.setattr(svc, "verify_signature", boom)
        assert svc.verify_member_signature(ISLAND, MEMBER, "n", "sig") is False


class TestGetMemberSwarmKey:
    @pytest.fixture(autouse=True)
    def _good_sig(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(svc, "verify_signature", lambda *a: True)

    def test_bad_signature_denied(self, monkeypatch: pytest.MonkeyPatch, chain_db: Path, swarm_key: Path) -> None:
        monkeypatch.setattr(svc, "verify_signature", lambda *a: False)
        with pytest.raises(PermissionError, match="Invalid signature"):
            svc.get_member_swarm_key(CHAIN_ID, ISLAND, MEMBER, "n", "sig")

    def test_no_subscription_denied(self, chain_db: Path, swarm_key: Path) -> None:
        with pytest.raises(PermissionError, match="No active IPFS subscription"):
            svc.get_member_swarm_key(CHAIN_ID, "island-b", MEMBER, "n", "sig")

    def test_success_returns_key_and_multiaddr(self, chain_db: Path, swarm_key: Path) -> None:
        out = svc.get_member_swarm_key(CHAIN_ID, ISLAND, MEMBER, "n", "sig")
        assert out["swarm_key"] == "test-swarm-key-material"
        assert out["island_id"] == ISLAND
        assert out["member_address"] == canonical_address(MEMBER)
        assert "/p2p/" in out["hub_multiaddr_template"]
        assert out["issued_at"].endswith("+00:00")

    def test_unknown_island_denied_after_subscription(self, data_dir: Path, chain_db: Path) -> None:
        # subscription exists for ISLAND but no swarm.key on disk
        with pytest.raises(PermissionError, match="Unknown island"):
            svc.get_member_swarm_key(CHAIN_ID, ISLAND, MEMBER, "n", "sig")
