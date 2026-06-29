"""Island registry for multi-island node support.

Parses the ISLAND_REGISTRY config string and provides lookup of
island_id → chain_id → hub_url mappings.
"""

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

    The hub_url may contain colons (e.g. ``http://host:port``). The parser
    splits on the first two colons to extract ``island_id`` and ``chain_id``,
    then intelligently separates the URL from the optional island_name by
    detecting the URL protocol prefix and port.
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
            # Split on first 2 colons: island_id, chain_id, rest
            parts = entry.split(":", 2)
            if len(parts) < 3:
                raise ValueError(f"Invalid island registry entry (expected 'island_id:chain_id:hub_url'): {entry}")
            island_id = parts[0].strip()
            chain_id = parts[1].strip()
            rest = parts[2].strip()
            if not island_id or not chain_id or not rest:
                raise ValueError(f"Invalid island registry entry (empty fields): {entry}")
            # Normalize URL with protocol prefix
            if not rest.startswith("http://") and not rest.startswith("https://"):
                rest = f"http://{rest}"
            # Determine protocol prefix
            protocol = "https://" if rest.startswith("https://") else "http://"
            after_protocol = rest[len(protocol) :]
            # after_protocol is "host:port[:island_name]" or "host[:island_name]"
            sub_parts = after_protocol.split(":")
            if len(sub_parts) <= 1:
                # Just host, no port, no island_name
                hub_url = rest
                island_name = island_id
            elif len(sub_parts) == 2:
                if sub_parts[1].strip().isdigit():
                    # host:port — no island_name
                    hub_url = rest
                    island_name = island_id
                else:
                    # host:island_name (no port)
                    hub_url = f"{protocol}{sub_parts[0].strip()}"
                    island_name = sub_parts[1].strip()
            else:
                # 3+ parts: host:port:island_name[:...]
                hub_url = f"{protocol}{sub_parts[0].strip()}:{sub_parts[1].strip()}"
                island_name = ":".join(sub_parts[2:]).strip()
            if not island_name:
                island_name = island_id
            if not hub_url:
                raise ValueError(f"Invalid island registry entry (empty hub_url): {entry}")
            result[island_id] = IslandRegistryEntry(
                island_id=island_id,
                chain_id=chain_id,
                hub_url=hub_url,
                island_name=island_name,
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
