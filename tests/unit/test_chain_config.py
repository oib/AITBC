from __future__ import annotations

import pytest

from aitbc.utils.chain_config import ChainConfigParser


def test_empty_string_returns_empty_dict():
    assert ChainConfigParser.parse("") == {}


def test_whitespace_only_returns_empty_dict():
    assert ChainConfigParser.parse("   ") == {}


def test_single_int_entry():
    result = ChainConfigParser.parse("block_time_seconds:2")
    assert result == {"block_time_seconds": 2}
    assert isinstance(result["block_time_seconds"], int)


def test_multiple_entries():
    result = ChainConfigParser.parse("block_time_seconds:2,max_txs_per_block:500")
    assert result == {"block_time_seconds": 2, "max_txs_per_block": 500}


def test_string_entry():
    result = ChainConfigParser.parse("block_generation_mode:hybrid")
    assert result == {"block_generation_mode": "hybrid"}
    assert isinstance(result["block_generation_mode"], str)


def test_malformed_entry_raises():
    with pytest.raises(ValueError, match="expected 'key:value'"):
        ChainConfigParser.parse("block_time_seconds")


def test_empty_key_raises():
    with pytest.raises(ValueError, match="empty key or value"):
        ChainConfigParser.parse(":2")


def test_empty_value_raises():
    with pytest.raises(ValueError, match="empty key or value"):
        ChainConfigParser.parse("block_time_seconds:")


def test_unknown_key_raises():
    with pytest.raises(ValueError, match="Unknown chain config key"):
        ChainConfigParser.parse("unknown_key:value")


def test_non_int_value_for_int_key_raises():
    with pytest.raises(ValueError, match="Invalid int value for key"):
        ChainConfigParser.parse("block_time_seconds:abc")


def test_whitespace_stripped():
    result = ChainConfigParser.parse("  block_time_seconds :  2  ")
    assert result == {"block_time_seconds": 2}


def test_empty_entries_skipped():
    result = ChainConfigParser.parse("block_time_seconds:2,, ,max_txs_per_block:500")
    assert result == {"block_time_seconds": 2, "max_txs_per_block": 500}


def test_parse_multiple():
    configs = {
        "chain-a": "block_time_seconds:2,max_txs_per_block:500",
        "chain-b": "block_time_seconds:5",
    }
    result = ChainConfigParser.parse_multiple(configs)
    assert result == {
        "chain-a": {"block_time_seconds": 2, "max_txs_per_block": 500},
        "chain-b": {"block_time_seconds": 5},
    }


def test_parse_multiple_skips_empty():
    configs = {
        "chain-a": "block_time_seconds:2",
        "chain-b": "",
        "chain-c": "   ",
    }
    result = ChainConfigParser.parse_multiple(configs)
    assert result == {"chain-a": {"block_time_seconds": 2}}


def test_parse_multiple_empty_dict():
    assert ChainConfigParser.parse_multiple({}) == {}


def test_known_keys_listed_in_error():
    with pytest.raises(ValueError) as exc_info:
        ChainConfigParser.parse("bad_key:1")
    msg = str(exc_info.value)
    assert "block_time_seconds" in msg
    assert "max_txs_per_block" in msg


def test_all_int_keys_parsed_as_int():
    result = ChainConfigParser.parse(
        "block_time_seconds:10,max_txs_per_block:1000,max_block_size_bytes:2000000,max_empty_block_interval:120"
    )
    assert all(isinstance(v, int) for v in result.values())


def test_string_key_parsed_as_str():
    result = ChainConfigParser.parse("block_generation_mode:mempool-only")
    assert isinstance(result["block_generation_mode"], str)


def test_value_with_colon_for_string_key():
    """String values may contain colons (e.g. URLs)."""
    result = ChainConfigParser.parse("block_generation_mode:a:b")
    assert result == {"block_generation_mode": "a:b"}
