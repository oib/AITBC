"""Unit tests for aitbc.network.compression (A4)."""

import json

import pytest

from aitbc.network.compression import (
    compress,
    compress_json,
    compression_ratio,
    decompress,
    decompress_json,
)


class TestCompressDecompressBytes:
    def test_gzip_round_trip(self) -> None:
        original = b"hello world " * 100
        compressed = compress(original, algorithm="gzip")
        assert isinstance(compressed, bytes)
        assert decompress(compressed, algorithm="gzip") == original

    def test_zlib_round_trip(self) -> None:
        original = b"hello world " * 100
        compressed = compress(original, algorithm="zlib")
        assert isinstance(compressed, bytes)
        assert decompress(compressed, algorithm="zlib") == original

    def test_compress_string_input(self) -> None:
        original = "hello world " * 100
        compressed = compress(original, algorithm="gzip")
        assert decompress(compressed, algorithm="gzip") == original.encode("utf-8")

    def test_unknown_algorithm_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown compression algorithm"):
            compress(b"data", algorithm="bogus")

    def test_decompress_unknown_algorithm_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown compression algorithm"):
            decompress(b"data", algorithm="bogus")


class TestCompressJson:
    def test_compress_json_round_trip(self) -> None:
        obj = {"height": 42, "hash": "0xabc", "transactions": [{"sender": "0x1", "amount": 100}]}
        compressed = compress_json(obj, algorithm="gzip")
        assert isinstance(compressed, bytes)
        result = decompress_json(compressed, algorithm="gzip")
        assert result == obj

    def test_compress_json_uses_compact_separators(self) -> None:
        obj = {"a": 1, "b": 2}
        compressed = compress_json(obj, algorithm="gzip")
        # Decompress to check the raw JSON has no spaces
        import gzip

        raw = gzip.decompress(compressed)
        assert b'"a":1' in raw  # no space after colon
        assert b'"b":2' in raw

    def test_compress_json_zlib_round_trip(self) -> None:
        obj = {"data": [1, 2, 3, "test"]}
        compressed = compress_json(obj, algorithm="zlib")
        result = decompress_json(compressed, algorithm="zlib")
        assert result == obj


class TestCompressionRatio:
    def test_ratio_calculation(self) -> None:
        original = b"hello world " * 100
        compressed = compress(original, algorithm="gzip")
        ratio = compression_ratio(original, compressed)
        # Should be a positive percentage (compressed is smaller)
        assert ratio > 0.0
        assert ratio <= 100.0

    def test_ratio_empty_original(self) -> None:
        assert compression_ratio(b"", b"") == 0.0

    def test_ratio_typical_block_json(self) -> None:
        # Simulate a typical block payload
        block = {
            "height": 1000,
            "hash": "0x" + "a" * 64,
            "parent_hash": "0x" + "b" * 64,
            "state_root": "0x" + "c" * 64,
            "transactions": [
                {
                    "sender": "0x" + "1" * 40,
                    "recipient": "0x" + "2" * 40,
                    "amount": 1000000,
                    "fee": 1000,
                    "nonce": 42,
                    "signature": "0x" + "d" * 130,
                }
                for _ in range(50)
            ],
        }
        raw = json.dumps(block).encode("utf-8")
        compressed = compress(raw, algorithm="gzip")
        ratio = compression_ratio(raw, compressed)
        # Should achieve >50% compression for this repetitive JSON
        assert ratio > 50.0, f"Compression ratio {ratio:.1f}% should be >50%"


class TestZstdFallback:
    def test_zstd_not_available_raises_clear_error(self) -> None:
        # If zstd is not installed, should raise ValueError with clear message
        # If it IS installed, the round-trip should work
        from aitbc.network.compression import _ZSTD_AVAILABLE

        if _ZSTD_AVAILABLE:
            original = b"hello world " * 100
            compressed = compress(original, algorithm="zstd")
            assert decompress(compressed, algorithm="zstd") == original
        else:
            with pytest.raises(ValueError, match="zstandard.*not installed"):
                compress(b"data", algorithm="zstd")
