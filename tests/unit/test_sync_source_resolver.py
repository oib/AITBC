from __future__ import annotations

import pytest

from aitbc.sync import SyncSourceResolver


def test_empty_sources_uses_default():
    resolver = SyncSourceResolver(sync_sources="", default_url="http://hub-a:8006")
    assert resolver.get_sync_source("ait-hub") == "http://hub-a:8006"


def test_single_source():
    resolver = SyncSourceResolver(sync_sources="ait-hub:http://hub-a:8006")
    assert resolver.get_sync_source("ait-hub") == "http://hub-a:8006"


def test_multiple_sources():
    resolver = SyncSourceResolver(sync_sources="ait-hub:http://hub-a:8006,ait-island1:http://hub-b:8006")
    assert resolver.get_sync_source("ait-hub") == "http://hub-a:8006"
    assert resolver.get_sync_source("ait-island1") == "http://hub-b:8006"


def test_chain_not_in_sources_falls_back():
    resolver = SyncSourceResolver(
        sync_sources="ait-hub:http://hub-a:8006",
        default_url="http://fallback:8006",
    )
    assert resolver.get_sync_source("ait-island1") == "http://fallback:8006"


def test_no_default_returns_none():
    resolver = SyncSourceResolver(sync_sources="ait-hub:http://hub-a:8006")
    assert resolver.get_sync_source("ait-island1") is None


def test_url_normalized_with_http_prefix():
    resolver = SyncSourceResolver(sync_sources="ait-hub:hub-a:8006")
    assert resolver.get_sync_source("ait-hub") == "http://hub-a:8006"


def test_url_with_https_preserved():
    resolver = SyncSourceResolver(sync_sources="ait-hub:https://hub-a:8006")
    assert resolver.get_sync_source("ait-hub") == "https://hub-a:8006"


def test_malformed_entry_raises():
    with pytest.raises(ValueError, match="Invalid sync source entry"):
        SyncSourceResolver(sync_sources="ait-hub-no-colon")


def test_empty_chain_id_raises():
    with pytest.raises(ValueError, match="empty chain_id or url"):
        SyncSourceResolver(sync_sources=":http://hub-a:8006")


def test_empty_url_raises():
    with pytest.raises(ValueError, match="empty chain_id or url"):
        SyncSourceResolver(sync_sources="ait-hub:")


def test_has_per_chain_sources_true():
    resolver = SyncSourceResolver(sync_sources="ait-hub:http://hub-a:8006")
    assert resolver.has_per_chain_sources() is True


def test_has_per_chain_sources_false():
    resolver = SyncSourceResolver(sync_sources="")
    assert resolver.has_per_chain_sources() is False


def test_get_all_sources():
    resolver = SyncSourceResolver(sync_sources="ait-hub:http://hub-a:8006,ait-island1:http://hub-b:8006")
    sources = resolver.get_all_sources()
    assert sources == {
        "ait-hub": "http://hub-a:8006",
        "ait-island1": "http://hub-b:8006",
    }


def test_get_all_sources_returns_copy():
    resolver = SyncSourceResolver(sync_sources="ait-hub:http://hub-a:8006")
    sources = resolver.get_all_sources()
    sources["ait-hub"] = "modified"
    # Original should be unchanged
    assert resolver.get_sync_source("ait-hub") == "http://hub-a:8006"


def test_whitespace_stripped():
    resolver = SyncSourceResolver(sync_sources="  ait-hub :  http://hub-a:8006  ,  ait-island1 : http://hub-b:8006  ")
    assert resolver.get_sync_source("ait-hub") == "http://hub-a:8006"
    assert resolver.get_sync_source("ait-island1") == "http://hub-b:8006"


def test_empty_entries_skipped():
    resolver = SyncSourceResolver(sync_sources="ait-hub:http://hub-a:8006,, ,ait-island1:http://hub-b:8006")
    assert resolver.has_per_chain_sources() is True
    assert resolver.get_sync_source("ait-hub") == "http://hub-a:8006"
    assert resolver.get_sync_source("ait-island1") == "http://hub-b:8006"


def test_url_with_port_and_colon():
    """URLs with colons (e.g. host:port) should split on first colon only."""
    resolver = SyncSourceResolver(sync_sources="ait-hub:http://hub-a:8006")
    assert resolver.get_sync_source("ait-hub") == "http://hub-a:8006"
