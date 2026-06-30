# v0.6.3 — Agent A Tasks (Shared Core)

**Last Updated**: 2026-06-30
**Version**: 1.0

## Scope

Create generic sync source resolution and island registry parsing utilities. These are blockchain-agnostic and reusable.

**Working directory**: `/opt/aitbc/aitbc/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/ && ./venv/bin/python -m ruff check aitbc/ && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Create `SyncSourceResolver` — parse chain_sync_sources, resolve hub URL per chain | 🔴 P0 | `aitbc/sync/source_resolver.py` (new), `aitbc/sync/__init__.py` (update) | ✅ |
| A2 | Create `IslandRegistry` — parse island_registry config, map island_id → chain_id → hub_url | High | `aitbc/network/island_registry.py` (new), `aitbc/network/__init__.py` (update) | ✅ |
| A3 | Unit tests for A1-A4 + verify mypy/ruff/pytest clean | High | `tests/unit/test_sync_source_resolver.py`, `tests/unit/test_island_registry.py`, `tests/unit/test_subscription_manager.py` | ✅ |
| A4 | Create `SubscriptionManager` — generic multi-hub subscription tracking, per-(chain_id, hub_url) lifecycle | 🔴 P0 | `aitbc/network/subscription_manager.py` (new), `aitbc/network/__init__.py` (update) | ✅ |

## Detailed Instructions

### A1: SyncSourceResolver

Create `aitbc/sync/source_resolver.py`:

```python
from __future__ import annotations


class SyncSourceResolver:
    """Resolves sync source URLs per chain_id.

    Parses the CHAIN_SYNC_SOURCES config string (format:
    "chain_id:url,chain_id:url,...") and provides per-chain hub URL
    resolution with fallback to a default URL.
    """

    def __init__(self, sync_sources: str = "", default_url: str | None = None) -> None:
        """Initialize with config string and default fallback URL.

        Args:
            sync_sources: Comma-separated "chain_id:url" pairs.
            default_url: Fallback URL for chains not in the mapping.
        """
        self._sources: dict[str, str] = self._parse_sync_sources(sync_sources)
        self._default_url = default_url

    @staticmethod
    def _parse_sync_sources(sync_sources: str) -> dict[str, str]:
        """Parse the sync sources config string.

        Format: "chain_id:url,chain_id:url,..."
        Returns dict mapping chain_id → url.
        Raises ValueError for malformed entries.
        """
        if not sync_sources or not sync_sources.strip():
            return {}
        result: dict[str, str] = {}
        for entry in sync_sources.split(","):
            entry = entry.strip()
            if not entry:
                continue
            if ":" not in entry:
                raise ValueError(f"Invalid sync source entry (expected 'chain_id:url'): {entry}")
            # Split on first colon only (URL may contain colons)
            chain_id, url = entry.split(":", 1)
            chain_id = chain_id.strip()
            url = url.strip()
            if not chain_id or not url:
                raise ValueError(f"Invalid sync source entry (empty chain_id or url): {entry}")
            if not url.startswith("http://") and not url.startswith("https://"):
                url = f"http://{url}"
            result[chain_id] = url
        return result

    def get_sync_source(self, chain_id: str) -> str | None:
        """Resolve sync source URL for a given chain_id.

        1. Check the per-chain mapping
        2. Fall back to default_url
        """
        if chain_id in self._sources:
            return self._sources[chain_id]
        return self._default_url

    def get_all_sources(self) -> dict[str, str]:
        """Return all configured sync sources (chain_id → url)."""
        return dict(self._sources)

    def has_per_chain_sources(self) -> bool:
        """Return True if per-chain sources are configured (non-empty mapping)."""
        return bool(self._sources)
```

Export from `aitbc/sync/__init__.py` as `SyncSourceResolver` (add to existing exports).

### A2: IslandRegistry

Create `aitbc/network/island_registry.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class IslandRegistryEntry:
    """A single island registry entry mapping island_id to chain and hub."""
    island_id: str
    chain_id: str
    hub_url: str
    island_name: str = ""


class IslandRegistry:
    """Parses the ISLAND_REGISTRY config string and provides lookup.

    Format: "island_id:chain_id:hub_url,island_id:chain_id:hub_url,..."
    Optional 4th field: island_name (defaults to island_id).
    """

    def __init__(self, registry_str: str = "") -> None:
        self._entries: dict[str, IslandRegistryEntry] = self._parse_registry(registry_str)

    @staticmethod
    def _parse_registry(registry_str: str) -> dict[str, IslandRegistryEntry]:
        if not registry_str or not registry_str.strip():
            return {}
        result: dict[str, IslandRegistryEntry] = {}
        for entry in registry_str.split(","):
            entry = entry.strip()
            if not entry:
                continue
            parts = entry.split(":")
            if len(parts) < 3:
                raise ValueError(f"Invalid island registry entry (expected 'island_id:chain_id:hub_url'): {entry}")
            island_id = parts[0].strip()
            chain_id = parts[1].strip()
            hub_url = parts[2].strip()
            island_name = parts[3].strip() if len(parts) > 3 else island_id
            if not island_id or not chain_id or not hub_url:
                raise ValueError(f"Invalid island registry entry (empty fields): {entry}")
            if not hub_url.startswith("http://") and not hub_url.startswith("https://"):
                hub_url = f"http://{hub_url}"
            result[island_id] = IslandRegistryEntry(
                island_id=island_id, chain_id=chain_id, hub_url=hub_url, island_name=island_name,
            )
        return result

    def get_entry(self, island_id: str) -> IslandRegistryEntry | None:
        return self._entries.get(island_id)

    def get_all_entries(self) -> list[IslandRegistryEntry]:
        return list(self._entries.values())

    def get_chain_for_island(self, island_id: str) -> str | None:
        entry = self._entries.get(island_id)
        return entry.chain_id if entry else None

    def get_hub_for_island(self, island_id: str) -> str | None:
        entry = self._entries.get(island_id)
        return entry.hub_url if entry else None
```

Export from `aitbc/network/__init__.py` as `IslandRegistry`, `IslandRegistryEntry` (check existing exports first — add to them).

### A3: Unit tests

**`tests/unit/test_sync_source_resolver.py`**:
- `test_empty_sources_uses_default` — empty string, default URL returned
- `test_single_source` — one chain mapped
- `test_multiple_sources` — multiple chains mapped
- `test_chain_not_in_sources_falls_back` — unknown chain uses default
- `test_no_default_returns_none` — unknown chain, no default → None
- `test_url_normalized_with_http_prefix` — URL without http:// gets prefix
- `test_malformed_entry_raises` — entry without colon raises ValueError
- `test_empty_chain_id_raises` — entry with empty chain_id raises
- `test_has_per_chain_sources` — True when sources configured, False when empty
- `test_get_all_sources` — returns copy of sources dict

**`tests/unit/test_island_registry.py`**:
- `test_empty_registry` — empty string → no entries
- `test_single_entry` — one island parsed correctly
- `test_multiple_entries` — multiple islands
- `test_entry_with_name` — 4th field as island name
- `test_entry_without_name_defaults_to_island_id` — 3 fields, name = island_id
- `test_get_entry` — lookup by island_id
- `test_get_chain_for_island` — chain_id lookup
- `test_get_hub_for_island` — hub_url lookup
- `test_unknown_island_returns_none` — lookup miss
- `test_malformed_entry_raises` — entry with < 3 parts raises ValueError
- `test_url_normalized` — hub_url gets http:// prefix

### A4: SubscriptionManager

Create `aitbc/network/subscription_manager.py`:

```python
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class SubscriptionClientProtocol(Protocol):
    """Interface contract for subscription clients (implemented by Agent B)."""
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    @property
    def chain_id(self) -> str: ...
    @property
    def hub_url(self) -> str: ...
    @property
    def is_connected(self) -> bool: ...


@dataclass
class SubscriptionEntry:
    """Tracks a single subscription client instance."""
    client: SubscriptionClientProtocol
    task: asyncio.Task[None] | None = None
    restart_count: int = 0
    last_error: str = ""


class SubscriptionManager:
    """Manages multiple subscription clients, one per (chain_id, hub_url) pair.

    Provides lifecycle management: add/remove subscriptions, start/stop all,
    per-subscription restart on failure with configurable backoff.
    """

    def __init__(
        self,
        max_restarts: int = 3,
        restart_delay: float = 5.0,
    ) -> None:
        """Initialize the subscription manager.

        Args:
            max_restarts: Max restart attempts per subscription before giving up.
            restart_delay: Seconds to wait before restarting a failed subscription.
        """
        self._subscriptions: dict[str, SubscriptionEntry] = {}
        self._max_restarts = max_restarts
        self._restart_delay = restart_delay
        self._running = False

    def add_subscription(self, chain_id: str, client: SubscriptionClientProtocol) -> None:
        """Register a subscription client for a chain_id.

        Raises ValueError if a subscription for this chain_id already exists.
        """
        if chain_id in self._subscriptions:
            raise ValueError(f"Subscription for chain_id '{chain_id}' already exists")
        self._subscriptions[chain_id] = SubscriptionEntry(client=client)
        logger.info("Added subscription for chain %s (hub: %s)", chain_id, client.hub_url)

    def remove_subscription(self, chain_id: str) -> SubscriptionEntry | None:
        """Remove and return a subscription entry. Stops the task if running."""
        entry = self._subscriptions.pop(chain_id, None)
        if entry and entry.task and not entry.task.done():
            entry.task.cancel()
        return entry

    def get_subscription(self, chain_id: str) -> SubscriptionEntry | None:
        """Get the subscription entry for a chain_id."""
        return self._subscriptions.get(chain_id)

    def get_all_chains(self) -> list[str]:
        """Return all chain_ids with active subscriptions."""
        return list(self._subscriptions.keys())

    async def start_all(self) -> None:
        """Start all registered subscriptions as background tasks."""
        self._running = True
        for chain_id, entry in self._subscriptions.items():
            if entry.task is None or entry.task.done():
                entry.task = asyncio.create_task(
                    self._run_subscription(chain_id), name=f"subscription_{chain_id}",
                )

    async def _run_subscription(self, chain_id: str) -> None:
        """Run a subscription with restart-on-failure logic."""
        entry = self._subscriptions[chain_id]
        while self._running and entry.restart_count <= self._max_restarts:
            try:
                await entry.client.start()
                break  # Normal exit
            except asyncio.CancelledError:
                break
            except Exception as e:
                entry.restart_count += 1
                entry.last_error = str(e)
                logger.warning(
                    "Subscription for chain %s failed (attempt %d/%d): %s",
                    chain_id, entry.restart_count, self._max_restarts, e,
                )
                if entry.restart_count <= self._max_restarts:
                    await asyncio.sleep(self._restart_delay)
                else:
                    logger.error(
                        "Subscription for chain %s exhausted restarts (%d). Giving up.",
                        chain_id, entry.restart_count,
                    )

    async def stop_all(self) -> None:
        """Stop all subscriptions and cancel tasks."""
        self._running = False
        for entry in self._subscriptions.values():
            if entry.task and not entry.task.done():
                entry.task.cancel()
        for entry in self._subscriptions.values():
            if entry.task:
                try:
                    await entry.task
                except asyncio.CancelledError:
                    pass
```

Export from `aitbc/network/__init__.py` as `SubscriptionManager`, `SubscriptionEntry`, `SubscriptionClientProtocol` (add to existing exports).

**`tests/unit/test_subscription_manager.py`**:
- `test_add_subscription` — add one client
- `test_add_duplicate_raises` — adding same chain_id twice raises ValueError
- `test_remove_subscription` — remove and verify task cancelled
- `test_remove_nonexistent_returns_none` — remove miss returns None
- `test_get_subscription` — lookup by chain_id
- `test_get_all_chains` — list of chain_ids
- `test_start_all_starts_tasks` — all clients get tasks
- `test_restart_on_failure` — client fails, gets restarted up to max_restarts
- `test_max_restarts_exhausted` — client fails beyond max, task ends
- `test_stop_all_cancels_tasks` — stop_all cancels all running tasks

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.6.3 — Multi-Island Node Support
**Agent**: Agent A (Shared Core)
