"""Per-chain port allocation with conflict detection.

Parses the CHAIN_PORT_OFFSETS config string and resolves ports as
base + offset. Detects conflicts (two chains with same port pair).
"""

from __future__ import annotations


class PortAllocationError(Exception):
    """Raised when port allocation fails (conflict or exhaustion)."""


class PortAllocator:
    """Allocates per-chain RPC and P2P ports from base ports + offsets.

    Parses the CHAIN_PORT_OFFSETS config string (format:
    "chain_id:offset,chain_id:offset,...") and resolves ports as
    base + offset. Detects conflicts (two chains with same port pair).

    When no offsets are configured, all chains share the base ports
    (backward compat with single-chain config — only one chain uses
    the ports).
    """

    def __init__(
        self,
        base_rpc_port: int = 8202,
        base_p2p_port: int = 8200,
        port_offsets: str = "",
    ) -> None:
        """Initialize with base ports and optional per-chain offsets.

        Args:
            base_rpc_port: Base RPC port (default 8202).
            base_p2p_port: Base P2P port (default 8200).
            port_offsets: Comma-separated "chain_id:offset" pairs.
                Offset is added to both base ports for that chain.

        Raises:
            ValueError: If port_offsets is malformed.
            PortAllocationError: If two configured chains resolve to the same port pair.
        """
        self._base_rpc_port = base_rpc_port
        self._base_p2p_port = base_p2p_port
        self._offsets: dict[str, int] = self._parse_offsets(port_offsets)
        self._allocated: dict[str, tuple[int, int]] = {}
        self._validate_no_conflicts()

    @staticmethod
    def _parse_offsets(port_offsets: str) -> dict[str, int]:
        """Parse the port offsets config string.

        Format: "chain_id:offset,chain_id:offset,..."
        Returns dict mapping chain_id → offset.
        Raises ValueError for malformed entries.
        """
        if not port_offsets or not port_offsets.strip():
            return {}
        result: dict[str, int] = {}
        for entry in port_offsets.split(","):
            entry = entry.strip()
            if not entry:
                continue
            if ":" not in entry:
                raise ValueError(f"Invalid port offset entry (expected 'chain_id:offset'): {entry}")
            chain_id, offset_str = entry.split(":", 1)
            chain_id = chain_id.strip()
            offset_str = offset_str.strip()
            if not chain_id or not offset_str:
                raise ValueError(f"Invalid port offset entry (empty fields): {entry}")
            try:
                offset = int(offset_str)
            except ValueError:
                raise ValueError(f"Invalid port offset (not an integer): {offset_str}") from None
            if offset < 0:
                raise ValueError(f"Invalid port offset (negative): {offset}")
            result[chain_id] = offset
        return result

    def _validate_no_conflicts(self) -> None:
        """Check that no two chains resolve to the same port pair."""
        seen: dict[tuple[int, int], str] = {}
        for chain_id, offset in self._offsets.items():
            ports = (self._base_rpc_port + offset, self._base_p2p_port + offset)
            if ports in seen:
                raise PortAllocationError(
                    f"Port conflict: chains '{seen[ports]}' and '{chain_id}' both resolve to RPC {ports[0]}, P2P {ports[1]}"
                )
            seen[ports] = chain_id

    def get_ports(self, chain_id: str) -> tuple[int, int]:
        """Resolve (rpc_port, p2p_port) for a chain.

        Unconfigured chains get offset 0 (base ports).
        Tracks allocation to detect runtime conflicts.

        Raises:
            PortAllocationError: If this chain's ports conflict with an already-allocated chain.
        """
        offset = self._offsets.get(chain_id, 0)
        ports = (self._base_rpc_port + offset, self._base_p2p_port + offset)
        if chain_id in self._allocated:
            return self._allocated[chain_id]
        # Check runtime conflict (e.g. two unconfigured chains both get base ports)
        for other_chain, other_ports in self._allocated.items():
            if other_ports == ports and other_chain != chain_id:
                raise PortAllocationError(
                    f"Port conflict: chains '{other_chain}' and '{chain_id}' both resolve to RPC {ports[0]}, P2P {ports[1]}"
                )
        self._allocated[chain_id] = ports
        return ports

    def get_all_allocations(self) -> dict[str, tuple[int, int]]:
        """Return all allocated ports (chain_id → (rpc, p2p))."""
        return dict(self._allocated)

    def has_per_chain_offsets(self) -> bool:
        """Return True if per-chain offsets are configured."""
        return bool(self._offsets)
