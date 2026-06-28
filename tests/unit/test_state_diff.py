from __future__ import annotations

from aitbc.sync.state_diff import (
    AccountChange,
    StateDiff,
    apply_state_diff,
    compute_state_diff,
    decode_state_diff,
    encode_state_diff,
)


def test_compute_state_diff_no_changes():
    """Identical snapshots -> empty diff."""
    accounts = {"addr1": (100, 5), "addr2": (200, 3)}
    diff = compute_state_diff(accounts, accounts, 10, 20, "root_a", "root_b")
    assert diff.changes == []
    assert diff.from_height == 10
    assert diff.to_height == 20


def test_compute_state_diff_new_account():
    """Account in new but not old."""
    old = {"addr1": (100, 5)}
    new = {"addr1": (100, 5), "addr2": (200, 3)}
    diff = compute_state_diff(old, new, 10, 20, "root_a", "root_b")
    assert len(diff.changes) == 1
    assert diff.changes[0].address == "addr2"
    assert diff.changes[0].is_new is True
    assert diff.changes[0].new_balance == 200
    assert diff.changes[0].new_nonce == 3


def test_compute_state_diff_deleted_account():
    """Account in old but not new."""
    old = {"addr1": (100, 5), "addr2": (200, 3)}
    new = {"addr1": (100, 5)}
    diff = compute_state_diff(old, new, 10, 20, "root_a", "root_b")
    assert len(diff.changes) == 1
    assert diff.changes[0].address == "addr2"
    assert diff.changes[0].is_deleted is True


def test_compute_state_diff_balance_change():
    old = {"addr1": (100, 5)}
    new = {"addr1": (150, 5)}
    diff = compute_state_diff(old, new, 10, 20, "root_a", "root_b")
    assert len(diff.changes) == 1
    assert diff.changes[0].old_balance == 100
    assert diff.changes[0].new_balance == 150


def test_compute_state_diff_nonce_change():
    old = {"addr1": (100, 5)}
    new = {"addr1": (100, 6)}
    diff = compute_state_diff(old, new, 10, 20, "root_a", "root_b")
    assert len(diff.changes) == 1
    assert diff.changes[0].old_nonce == 5
    assert diff.changes[0].new_nonce == 6


def test_encode_decode_roundtrip():
    diff = StateDiff(
        from_height=10,
        to_height=20,
        changes=[
            AccountChange(address="addr1", old_balance=100, new_balance=150, old_nonce=5, new_nonce=6),
            AccountChange(address="addr2", old_balance=0, new_balance=200, old_nonce=0, new_nonce=3, is_new=True),
        ],
        from_state_root="root_a",
        to_state_root="root_b",
    )
    encoded = encode_state_diff(diff)
    decoded = decode_state_diff(encoded)
    assert decoded.from_height == 10
    assert decoded.to_height == 20
    assert decoded.from_state_root == "root_a"
    assert decoded.to_state_root == "root_b"
    assert len(decoded.changes) == 2
    assert decoded.changes[0].address == "addr1"
    assert decoded.changes[0].new_balance == 150
    assert decoded.changes[1].is_new is True


def test_apply_state_diff_creates_new():
    diff = StateDiff(
        from_height=10,
        to_height=20,
        changes=[AccountChange(address="addr1", old_balance=0, new_balance=100, old_nonce=0, new_nonce=1, is_new=True)],
        from_state_root="root_a",
        to_state_root="root_b",
    )
    account_map: dict = {}
    changed = apply_state_diff(diff, account_map)
    assert "addr1" in account_map
    assert account_map["addr1"]["balance"] == 100
    assert account_map["addr1"]["nonce"] == 1
    assert changed == ["addr1"]


def test_apply_state_diff_updates_existing():
    diff = StateDiff(
        from_height=10,
        to_height=20,
        changes=[AccountChange(address="addr1", old_balance=100, new_balance=150, old_nonce=5, new_nonce=6)],
        from_state_root="root_a",
        to_state_root="root_b",
    )
    account_map = {"addr1": {"balance": 100, "nonce": 5}}
    changed = apply_state_diff(diff, account_map)
    assert account_map["addr1"]["balance"] == 150
    assert account_map["addr1"]["nonce"] == 6
    assert changed == ["addr1"]


def test_apply_state_diff_handles_deletion():
    diff = StateDiff(
        from_height=10,
        to_height=20,
        changes=[AccountChange(address="addr1", old_balance=100, new_balance=0, old_nonce=5, new_nonce=0, is_deleted=True)],
        from_state_root="root_a",
        to_state_root="root_b",
    )
    account_map = {"addr1": {"balance": 100, "nonce": 5}}
    changed = apply_state_diff(diff, account_map)
    assert "addr1" not in account_map
    assert changed == ["addr1"]


def test_is_too_large_false():
    """Small diff, large state -> False."""
    diff = StateDiff(
        from_height=10,
        to_height=20,
        changes=[AccountChange(address="addr1", old_balance=100, new_balance=150, old_nonce=5, new_nonce=6)],
        from_state_root="root_a",
        to_state_root="root_b",
    )
    # diff size ~300 bytes, full state ~10000 bytes -> 300 < 5000
    assert diff.is_too_large(10000, threshold=0.5) is False


def test_is_too_large_true():
    """Diff > 50% of state -> True."""
    # Create a large diff
    changes = [
        AccountChange(address=f"addr{i:04d}", old_balance=100, new_balance=200, old_nonce=5, new_nonce=6) for i in range(100)
    ]
    diff = StateDiff(
        from_height=10,
        to_height=20,
        changes=changes,
        from_state_root="root_a",
        to_state_root="root_b",
    )
    # diff size ~10200 bytes, full state ~10000 bytes -> 10200 > 5000
    assert diff.is_too_large(10000, threshold=0.5) is True


def test_is_too_large_zero_full_state():
    """full_state_size=0 -> False (no fallback when state is empty)."""
    diff = StateDiff(
        from_height=10,
        to_height=20,
        changes=[],
        from_state_root="root_a",
        to_state_root="root_b",
    )
    assert diff.is_too_large(0) is False
