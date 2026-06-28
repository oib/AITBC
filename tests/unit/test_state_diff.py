"""Unit tests for aitbc.sync.state_diff (A3)."""

import json

from aitbc.network.compression import compress_json
from aitbc.sync.state_diff import (
    AccountChange,
    StateDiff,
    compute_state_diff,
)


class TestComputeStateDiff:
    def test_compute_state_diff_no_changes(self) -> None:
        """Identical states → empty diff."""
        old = {"addr1": (100, 0), "addr2": (200, 0)}
        new = {"addr1": (100, 0), "addr2": (200, 0)}
        diff = compute_state_diff(old, new, 10, 20, chain_id="chain1")
        assert diff.is_empty()
        assert diff.changes == []
        assert diff.new_accounts == []
        assert diff.removed_accounts == []

    def test_compute_state_diff_balance_change(self) -> None:
        """One account balance changed."""
        old = {"addr1": (100, 0), "addr2": (200, 0)}
        new = {"addr1": (150, 0), "addr2": (200, 0)}
        diff = compute_state_diff(old, new, 10, 20, chain_id="chain1")
        assert len(diff.changes) == 1
        assert diff.changes[0].address == "addr1"
        assert diff.changes[0].old_balance == 100
        assert diff.changes[0].new_balance == 150
        assert diff.changes[0].balance_changed
        assert not diff.changes[0].nonce_changed

    def test_compute_state_diff_nonce_change(self) -> None:
        """One account nonce changed."""
        old = {"addr1": (100, 0)}
        new = {"addr1": (100, 1)}
        diff = compute_state_diff(old, new, 10, 20, chain_id="chain1")
        assert len(diff.changes) == 1
        assert diff.changes[0].nonce_changed
        assert not diff.changes[0].balance_changed

    def test_compute_state_diff_new_account(self) -> None:
        """Account added in new state."""
        old = {"addr1": (100, 0)}
        new = {"addr1": (100, 0), "addr2": (200, 0)}
        diff = compute_state_diff(old, new, 10, 20, chain_id="chain1")
        assert len(diff.new_accounts) == 1
        assert diff.new_accounts[0]["address"] == "addr2"
        assert diff.new_accounts[0]["balance"] == 200
        # new_accounts is derived from changes with is_new=True
        assert any(c.is_new for c in diff.changes)

    def test_compute_state_diff_removed_account(self) -> None:
        """Account removed in new state."""
        old = {"addr1": (100, 0), "addr2": (200, 0)}
        new = {"addr1": (100, 0)}
        diff = compute_state_diff(old, new, 10, 20, chain_id="chain1")
        assert len(diff.removed_accounts) == 1
        assert diff.removed_accounts == ["addr2"]

    def test_compute_state_diff_mixed(self) -> None:
        """Mix of changes, new, and removed."""
        old = {"a": (100, 0), "b": (200, 0), "c": (300, 0)}
        new = {"a": (150, 0), "b": (200, 0), "d": (400, 0)}
        diff = compute_state_diff(old, new, 10, 20, chain_id="chain1")
        # a changed (not new, not deleted), d is new, c is deleted
        assert len(diff.changes) == 3  # a changed, c deleted, d new
        modified = [c for c in diff.changes if not c.is_new and not c.is_deleted]
        assert len(modified) == 1
        assert modified[0].address == "a"
        assert len(diff.new_accounts) == 1  # d added
        assert diff.new_accounts[0]["address"] == "d"
        assert len(diff.removed_accounts) == 1  # c removed
        assert diff.removed_accounts == ["c"]

    def test_compute_state_diff_metadata(self) -> None:
        """Diff carries from/to heights, chain_id, state roots."""
        old = {"a": (100, 0)}
        new = {"a": (200, 0)}
        diff = compute_state_diff(
            old,
            new,
            from_height=10,
            to_height=20,
            chain_id="mychain",
            state_root_before="root_before",
            state_root_after="root_after",
        )
        assert diff.from_height == 10
        assert diff.to_height == 20
        assert diff.chain_id == "mychain"
        assert diff.state_root_before == "root_before"
        assert diff.state_root_after == "root_after"


class TestSizeRatio:
    def test_size_ratio(self) -> None:
        """30 changed out of 100 → 0.3."""
        old = {f"addr{i}": (100, 0) for i in range(100)}
        new = dict(old)
        # Change 30 accounts
        for i in range(30):
            new[f"addr{i}"] = (200, 0)
        diff = compute_state_diff(old, new, 10, 20, chain_id="chain1")
        assert diff.size_ratio(100) == 0.3

    def test_size_ratio_empty_diff(self) -> None:
        """Empty diff → 0.0."""
        old = {"a": (100, 0)}
        new = {"a": (100, 0)}
        diff = compute_state_diff(old, new, 10, 20, chain_id="chain1")
        assert diff.size_ratio(100) == 0.0

    def test_size_ratio_zero_total(self) -> None:
        """Zero total accounts with empty diff → 0.0."""
        diff = StateDiff(from_height=10, to_height=20, chain_id="c")
        assert diff.size_ratio(0) == 0.0

    def test_size_ratio_zero_total_with_changes(self) -> None:
        """Zero total accounts with changes → 1.0 (edge case)."""
        diff = StateDiff(
            from_height=10,
            to_height=20,
            chain_id="c",
            changes=[AccountChange("a", 0, 100, 0, 0)],
        )
        assert diff.size_ratio(0) == 1.0


class TestEncodeDecode:
    def test_encode_decode_round_trip(self) -> None:
        """Serialize + deserialize = original."""
        original = StateDiff(
            from_height=10,
            to_height=20,
            chain_id="chain1",
            changes=[
                AccountChange("addr1", 100, 150, 0, 1),
                AccountChange("addr2", 0, 200, 0, 0, is_new=True),
                AccountChange("addr3", 300, 0, 0, 0, is_deleted=True),
            ],
            state_root_before="root_before",
            state_root_after="root_after",
        )
        encoded = original.encode()
        decoded = StateDiff.decode(encoded)
        assert decoded.from_height == 10
        assert decoded.to_height == 20
        assert decoded.chain_id == "chain1"
        assert len(decoded.changes) == 3
        # Check the modified account
        modified = [c for c in decoded.changes if not c.is_new and not c.is_deleted]
        assert len(modified) == 1
        assert modified[0].address == "addr1"
        assert modified[0].new_balance == 150
        # Check new_accounts (derived from is_new changes)
        assert len(decoded.new_accounts) == 1
        assert decoded.new_accounts[0]["address"] == "addr2"
        # Check removed_accounts (derived from is_deleted changes)
        assert decoded.removed_accounts == ["addr3"]
        assert decoded.state_root_before == "root_before"
        assert decoded.state_root_after == "root_after"

    def test_encode_decode_empty_diff(self) -> None:
        """Empty diff round-trips correctly."""
        original = StateDiff(from_height=0, to_height=10, chain_id="c")
        encoded = original.encode()
        decoded = StateDiff.decode(encoded)
        assert decoded.is_empty()

    def test_compressed_size_smaller(self) -> None:
        """Encoded diff is smaller than raw JSON."""
        changes = [AccountChange(f"addr{i}", 100, 200, 0, 1) for i in range(50)]
        diff = StateDiff(
            from_height=10,
            to_height=20,
            chain_id="chain1",
            changes=changes,
        )
        encoded = diff.encode()
        raw = json.dumps(diff.to_dict(), separators=(",", ":")).encode("utf-8")
        assert len(encoded) < len(raw)

    def test_encode_uses_gzip(self) -> None:
        """Encode produces gzip-compressed bytes (starts with gzip magic)."""
        diff = StateDiff(from_height=0, to_height=1, chain_id="c")
        encoded = diff.encode()
        # gzip magic bytes: 0x1f 0x8b
        assert encoded[:2] == b"\x1f\x8b"

    def test_encode_matches_compress_json(self) -> None:
        """encode() output matches compress_json(to_dict())."""
        diff = StateDiff(
            from_height=10,
            to_height=20,
            chain_id="c",
            changes=[AccountChange("a", 1, 2, 0, 0)],
        )
        assert diff.encode() == compress_json(diff.to_dict())


class TestAccountChange:
    def test_balance_changed(self) -> None:
        change = AccountChange("a", 100, 200, 0, 0)
        assert change.balance_changed
        assert not change.nonce_changed

    def test_nonce_changed(self) -> None:
        change = AccountChange("a", 100, 100, 0, 1)
        assert not change.balance_changed
        assert change.nonce_changed

    def test_no_change(self) -> None:
        change = AccountChange("a", 100, 100, 0, 0)
        assert not change.balance_changed
        assert not change.nonce_changed

    def test_to_dict_from_dict_round_trip(self) -> None:
        change = AccountChange("a", 100, 200, 0, 1)
        restored = AccountChange.from_dict(change.to_dict())
        assert restored == change
