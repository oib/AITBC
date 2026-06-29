from __future__ import annotations

import pytest

from aitbc.network import IslandRegistry, IslandRegistryEntry


def test_empty_registry():
    registry = IslandRegistry(registry_str="")
    assert registry.get_all_entries() == []
    assert registry.get_entry("any-island") is None


def test_single_entry():
    registry = IslandRegistry(registry_str="island-1:ait-hub:http://hub-a:8006")
    entry = registry.get_entry("island-1")
    assert entry is not None
    assert entry.island_id == "island-1"
    assert entry.chain_id == "ait-hub"
    assert entry.hub_url == "http://hub-a:8006"
    assert entry.island_name == "island-1"  # defaults to island_id


def test_multiple_entries():
    registry = IslandRegistry(registry_str="island-1:ait-hub:http://hub-a:8006,island-2:ait-island1:http://hub-b:8006")
    entries = registry.get_all_entries()
    assert len(entries) == 2
    assert registry.get_entry("island-1") is not None
    assert registry.get_entry("island-2") is not None


def test_entry_with_name():
    registry = IslandRegistry(registry_str="island-1:ait-hub:http://hub-a:8006:Main Hub")
    entry = registry.get_entry("island-1")
    assert entry is not None
    assert entry.island_name == "Main Hub"


def test_entry_without_name_defaults_to_island_id():
    registry = IslandRegistry(registry_str="island-1:ait-hub:http://hub-a:8006")
    entry = registry.get_entry("island-1")
    assert entry is not None
    assert entry.island_name == "island-1"


def test_get_entry():
    registry = IslandRegistry(registry_str="island-1:ait-hub:http://hub-a:8006")
    assert registry.get_entry("island-1") is not None
    assert isinstance(registry.get_entry("island-1"), IslandRegistryEntry)


def test_get_chain_for_island():
    registry = IslandRegistry(registry_str="island-1:ait-hub:http://hub-a:8006")
    assert registry.get_chain_for_island("island-1") == "ait-hub"


def test_get_hub_for_island():
    registry = IslandRegistry(registry_str="island-1:ait-hub:http://hub-a:8006")
    assert registry.get_hub_for_island("island-1") == "http://hub-a:8006"


def test_unknown_island_returns_none():
    registry = IslandRegistry(registry_str="island-1:ait-hub:http://hub-a:8006")
    assert registry.get_entry("unknown") is None
    assert registry.get_chain_for_island("unknown") is None
    assert registry.get_hub_for_island("unknown") is None


def test_malformed_entry_raises():
    with pytest.raises(ValueError, match="Invalid island registry entry"):
        IslandRegistry(registry_str="island-1:ait-hub")


def test_empty_fields_raises():
    with pytest.raises(ValueError, match="empty fields"):
        IslandRegistry(registry_str=":ait-hub:http://hub-a:8006")


def test_url_normalized():
    registry = IslandRegistry(registry_str="island-1:ait-hub:hub-a:8006")
    entry = registry.get_entry("island-1")
    assert entry is not None
    assert entry.hub_url == "http://hub-a:8006"


def test_url_with_https_preserved():
    registry = IslandRegistry(registry_str="island-1:ait-hub:https://hub-a:8006")
    entry = registry.get_entry("island-1")
    assert entry is not None
    assert entry.hub_url == "https://hub-a:8006"


def test_whitespace_stripped():
    registry = IslandRegistry(registry_str="  island-1 :  ait-hub :  http://hub-a:8006  ")
    entry = registry.get_entry("island-1")
    assert entry is not None
    assert entry.chain_id == "ait-hub"
    assert entry.hub_url == "http://hub-a:8006"


def test_empty_entries_skipped():
    registry = IslandRegistry(registry_str="island-1:ait-hub:http://hub-a:8006,, ,island-2:ait-island1:http://hub-b:8006")
    assert len(registry.get_all_entries()) == 2


def test_get_all_entries_returns_list():
    registry = IslandRegistry(registry_str="island-1:ait-hub:http://hub-a:8006,island-2:ait-island1:http://hub-b:8006")
    entries = registry.get_all_entries()
    assert isinstance(entries, list)
    assert all(isinstance(e, IslandRegistryEntry) for e in entries)
