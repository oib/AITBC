# v0.6.4 — Agent A Tasks (Shared Core)

**Last Updated**: 2026-06-30
**Version**: 1.0

## Scope

Create reusable port allocation and chain config parsing utilities. These are blockchain-agnostic and will be consumed by Agent B's MultiChainManager and config integration.

**Working directory**: `/opt/aitbc/aitbc/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/network/port_allocator.py aitbc/utils/chain_config.py aitbc/network/__init__.py aitbc/utils/__init__.py && ./venv/bin/python -m ruff check aitbc/network/port_allocator.py aitbc/utils/chain_config.py aitbc/network/__init__.py aitbc/utils/__init__.py tests/unit/test_port_allocator.py tests/unit/test_chain_config.py && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Create `PortAllocator` — per-chain port allocation with conflict detection | 🔴 P0 | `aitbc/network/port_allocator.py` (new), `aitbc/network/__init__.py` (update) | ✅ |
| A2 | Create `ChainConfigParser` — parse "key:value,key:value" strings into typed dict | High | `aitbc/utils/chain_config.py` (new), `aitbc/utils/__init__.py` (update) | ✅ |
| A3 | Unit tests for A1-A2 + verify mypy/ruff/pytest clean | High | `tests/unit/test_port_allocator.py`, `tests/unit/test_chain_config.py` | ✅ |

## Detailed Instructions

### A1: PortAllocator

Create `aitbc/network/port_allocator.py`:

```python
from __future__ import annotations


class PortAllocationError(Exception):
    """Raised when port allocation fails (conflict or exhaustion)."""


class PortAllocator:
    """Allocates per-chain RPC and P2P ports from base ports + offsets.

    Parses the CHAIN_PORT_OFFSETS config string (format:
    "chain_id:offset,chain_id:offset,...") and resolves ports as
    base + offset. Detects conflicts (two chains with same port).

    When no offsets are configured, all chains share the base ports
    (backward compat with single-chain config).
    """

    def __init__(
        self,
        base_rpc_port: int = 8006,
        base_p2p_port: int = 8007,
        port_offsets: str = "",
    ) -> None:
        """Initialize with base ports and optional per-chain offsets.

        Args:
            base_rpc_port: Base RPC port (default 8006).
            base_p2p_port: Base P2P port (default 8007).
            port_offsets: Comma-separated "chain_id:offset" pairs.
                Offset is added to both base ports for that chain.
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
        """Validate that no two chains have the same port allocation."""
        seen_ports: set[int] = set()
        for chain_id, offset in self._offsets.items():
            rpc_port = self._base_rpc_port + offset
            p2p_port = self._base_p2p_port + offset
            if rpc_port in seen_ports or p2p_port in seen_ports:
                raise PortAllocationError(
                    f"Port conflict for chain '{chain_id}': RPC {rpc_port} or P2P {p2p_port} already allocated"
                )
            seen_ports.add(rpc_port)
            seen_ports.add(p2p_port)

    def get_ports(self, chain_id: str) -> tuple[int, int]:
        """Get RPC and P2P ports for a chain.

        Args:
            chain_id: Chain identifier.

        Returns:
            Tuple of (rpc_port, p2p_port).

        Raises:
            PortAllocationError: If port conflict detected at runtime.
        """
        offset = self._offsets.get(chain_id, 0)
        rpc_port = self._base_rpc_port + offset
        p2p_port = self._base_p2p_port + offset

        # Runtime conflict detection for unconfigured chains
        if chain_id in self._allocated:
            return self._allocated[chain_id]

        if rpc_port in {p for _, p in self._allocated.values()}:
            raise PortAllocationError(
                f"Port conflict for chain '{chain_id}': P2P port {p2p_port} already allocated to another chain"
            )
        if p2p_port in {p for _, p in self._allocated.values()}:
            raise PortAllocationError(
                f"Port conflict for chain '{chain_id}': P2P port {p2p_port} already allocated to another chain"
            )

        self._allocated[chain_id] = (rpc_port, p2p_port)
        return (rpc_port, p2p_port)

    def get_all_allocations(self) -> dict[str, tuple[int, int]]:
        """Get all port allocations (copy to prevent mutation)."""
        return self._allocated.copy()

    def has_per_chain_offsets(self) -> bool:
        """Return True if per-chain offsets are configured."""
        return bool(self._offsets)
```

Export from `aitbc/network/__init__.py` as `PortAllocator` (add to existing exports — check if `aitbc/network/__init__.py` exists first; if not, create it).

### A2: ChainConfigParser

Create `aitbc/utils/chain_config.py`:

```python
from __future__ import annotations


class ChainConfigParseError(Exception):
    """Raised when chain config string parsing fails."""


class ChainConfigParser:
    """Parses chain config strings into typed dictionaries.

    Config format: "key1:value1,key2:value2,..."
    Known keys: block_time_seconds (int), max_txs_per_block (int),
    block_generation_mode (str), etc.
    """

    KNOWN_KEYS: dict[str, type] = {
        "block_time_seconds": int,
        "max_txs_per_block": int,
        "block_generation_mode": str,
        "proposer_mode": str,
        "validator_mode": str,
    }

    @classmethod
    def parse(cls, config_str: str) -> dict[str, int | str]:
        """Parse a single chain config string.

        Args:
            config_str: Config string in "key:value,key:value" format.

        Returns:
            Dict mapping keys to typed values.

        Raises:
            ChainConfigParseError: If parsing fails.
        """
        if not config_str or not config_str.strip():
            return {}

        result: dict[str, int | str] = {}
        for entry in config_str.split(","):
            entry = entry.strip()
            if not entry:
                continue
            if ":" not in entry:
                raise ChainConfigParseError(
                    f"Invalid config entry (expected 'key:value'): {entry}"
                )
            key, value = entry.split(":", 1)
            key = key.strip()
            value = value.strip()
            if not key or not value:
                raise ChainConfigParseError(
                    f"Invalid config entry (empty fields): {entry}"
                )
            if key not in cls.KNOWN_KEYS:
                raise ChainConfigParseError(
                    f"Unknown chain config key '{key}'. Known keys: {sorted(cls.KNOWN_KEYS.keys())}"
                )
            expected_type = cls.KNOWN_KEYS[key]
            if expected_type is int:
                try:
                    result[key] = int(value)
                except ValueError:
                    raise ChainConfigParseError(f"Invalid int value for key '{key}': '{value}'") from None
            else:
                result[key] = value
        return result

    @classmethod
    def parse_multiple(cls, configs: dict[str, str]) -> dict[str, dict[str, int | str]]:
        """Parse multiple chain config strings at once.

        Args:
            configs: Dict mapping chain_id → config string.

        Returns:
            Dict mapping chain_id → typed config dict.
        """
        result: dict[str, dict[str, int | str]] = {}
        for chain_id, config_str in configs.items():
            if not config_str or not config_str.strip():
                continue
            result[chain_id] = cls.parse(config_str)
        return result
```

Export from `aitbc/utils/__init__.py` as `ChainConfigParser` (add to existing exports — check if `aitbc/utils/__init__.py` exists first; if not, create it).

### A3: Unit tests

**`tests/unit/test_port_allocator.py`**:
- `test_empty_offsets_returns_base_ports` — no offsets, chain gets base ports
- `test_single_offset` — one chain with offset 10
- `test_multiple_offsets` — multiple chains with different offsets
- `test_chain_not_in_offsets_gets_base` — unconfigured chain gets offset 0
- `test_malformed_entry_raises` — entry without colon raises ValueError
- `test_non_integer_offset_raises` — offset "abc" raises ValueError
- `test_negative_offset_raises` — offset -1 raises ValueError
- `test_empty_fields_raises` — empty chain_id or offset raises ValueError
- `test_conflict_detection_at_init` — two chains with same offset raises PortAllocationError
- `test_runtime_conflict_detection` — two unconfigured chains both get base ports → second raises
- `test_get_all_allocations` — returns copy of allocations dict
- `test_has_per_chain_offsets` — True when offsets configured, False when empty
- `test_get_ports_idempotent` — calling get_ports twice returns same result
- `test_whitespace_stripped` — whitespace in entries is stripped

**`tests/unit/test_chain_config.py`**:
- `test_empty_string_returns_empty_dict` — empty string → {}
- `test_single_int_entry` — "block_time_seconds:2" → {"block_time_seconds": 2}
- `test_multiple_entries` — "block_time_seconds:2,max_txs_per_block:500"
- `test_string_entry` — "block_generation_mode:hybrid"
- `test_malformed_entry_raises` — entry without colon raises ValueError
- `test_empty_key_raises` — ":value" raises ValueError
- `test_empty_value_raises` — "key:" raises ValueError
- `test_unknown_key_raises` — "unknown_key:value" raises ValueError
- `test_non_int_value_for_int_key_raises` — "block_time_seconds:abc" raises ValueError
- `test_whitespace_stripped` — " block_time_seconds : 2 " works
- `test_empty_entries_skipped` — "block_time_seconds:2,, ,max_txs_per_block:500"
- `test_parse_multiple` — dict of config strings → dict of typed dicts
- `test_parse_multiple_skips_empty` — empty config strings skipped
- `test_known_keys_listed_in_error` — unknown key error lists known keys

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.6.4 — Multi-Chain Per Island
**Agent**: Agent A (Shared Core)
