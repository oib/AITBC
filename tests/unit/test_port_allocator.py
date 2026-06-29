from __future__ import annotations

import pytest

from aitbc.network import PortAllocationError, PortAllocator


def test_empty_offsets_returns_base_ports():
    allocator = PortAllocator(base_rpc_port=8006, base_p2p_port=8007, port_offsets="")
    rpc, p2p = allocator.get_ports("chain-a")
    assert rpc == 8006
    assert p2p == 8007


def test_single_offset():
    allocator = PortAllocator(base_rpc_port=8006, base_p2p_port=8007, port_offsets="chain-a:10")
    rpc, p2p = allocator.get_ports("chain-a")
    assert rpc == 8016
    assert p2p == 8017


def test_multiple_offsets():
    allocator = PortAllocator(
        base_rpc_port=8006,
        base_p2p_port=8007,
        port_offsets="chain-a:0,chain-b:10,chain-c:20",
    )
    assert allocator.get_ports("chain-a") == (8006, 8007)
    assert allocator.get_ports("chain-b") == (8016, 8017)
    assert allocator.get_ports("chain-c") == (8026, 8027)


def test_chain_not_in_offsets_gets_base():
    allocator = PortAllocator(base_rpc_port=8006, base_p2p_port=8007, port_offsets="chain-a:10")
    # chain-b not in offsets → gets base ports
    assert allocator.get_ports("chain-b") == (8006, 8007)


def test_malformed_entry_raises():
    with pytest.raises(ValueError, match="expected 'chain_id:offset'"):
        PortAllocator(port_offsets="chain-a")


def test_non_integer_offset_raises():
    with pytest.raises(ValueError, match="not an integer"):
        PortAllocator(port_offsets="chain-a:abc")


def test_negative_offset_raises():
    with pytest.raises(ValueError, match="negative"):
        PortAllocator(port_offsets="chain-a:-1")


def test_empty_fields_raises():
    with pytest.raises(ValueError, match="empty fields"):
        PortAllocator(port_offsets=":10")


def test_empty_offset_value_raises():
    with pytest.raises(ValueError, match="empty fields"):
        PortAllocator(port_offsets="chain-a:")


def test_conflict_detection_at_init():
    with pytest.raises(PortAllocationError, match="Port conflict"):
        PortAllocator(
            base_rpc_port=8006,
            base_p2p_port=8007,
            port_offsets="chain-a:10,chain-b:10",
        )


def test_runtime_conflict_detection():
    """Two unconfigured chains both get base ports → second raises."""
    allocator = PortAllocator(base_rpc_port=8006, base_p2p_port=8007, port_offsets="")
    allocator.get_ports("chain-a")  # Gets base ports
    with pytest.raises(PortAllocationError, match="Port conflict"):
        allocator.get_ports("chain-b")  # Also gets base ports → conflict


def test_get_all_allocations():
    allocator = PortAllocator(
        base_rpc_port=8006,
        base_p2p_port=8007,
        port_offsets="chain-a:0,chain-b:10",
    )
    allocator.get_ports("chain-a")
    allocator.get_ports("chain-b")
    allocations = allocator.get_all_allocations()
    assert allocations == {"chain-a": (8006, 8007), "chain-b": (8016, 8017)}


def test_get_all_allocations_returns_copy():
    allocator = PortAllocator(port_offsets="chain-a:10")
    allocator.get_ports("chain-a")
    allocations = allocator.get_all_allocations()
    allocations["chain-z"] = (9999, 9999)
    # Original should be unchanged
    assert "chain-z" not in allocator.get_all_allocations()


def test_has_per_chain_offsets_true():
    allocator = PortAllocator(port_offsets="chain-a:10")
    assert allocator.has_per_chain_offsets() is True


def test_has_per_chain_offsets_false():
    allocator = PortAllocator(port_offsets="")
    assert allocator.has_per_chain_offsets() is False


def test_get_ports_idempotent():
    allocator = PortAllocator(port_offsets="chain-a:10")
    first = allocator.get_ports("chain-a")
    second = allocator.get_ports("chain-a")
    assert first == second == (8016, 8017)


def test_whitespace_stripped():
    allocator = PortAllocator(base_rpc_port=8006, base_p2p_port=8007, port_offsets="  chain-a :  10  ")
    assert allocator.get_ports("chain-a") == (8016, 8017)


def test_empty_entries_skipped():
    allocator = PortAllocator(
        base_rpc_port=8006,
        base_p2p_port=8007,
        port_offsets="chain-a:10,, ,chain-b:20",
    )
    assert allocator.get_ports("chain-a") == (8016, 8017)
    assert allocator.get_ports("chain-b") == (8026, 8027)


def test_custom_base_ports():
    allocator = PortAllocator(base_rpc_port=9000, base_p2p_port=9001, port_offsets="chain-a:5")
    assert allocator.get_ports("chain-a") == (9005, 9006)


def test_large_offset():
    allocator = PortAllocator(base_rpc_port=8006, base_p2p_port=8007, port_offsets="chain-a:1000")
    assert allocator.get_ports("chain-a") == (9006, 9007)


def test_zero_offset_explicit():
    allocator = PortAllocator(base_rpc_port=8006, base_p2p_port=8007, port_offsets="chain-a:0,chain-b:10")
    assert allocator.get_ports("chain-a") == (8006, 8007)
    assert allocator.get_ports("chain-b") == (8016, 8017)
