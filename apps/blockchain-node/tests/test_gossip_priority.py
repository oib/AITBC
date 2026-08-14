"""Integration tests for v0.6.2 gossip priority queue and message batching."""

from __future__ import annotations


from aitbc_chain.gossip.broker import (
    _decode_batch,
    _encode_batch,
    _encode_message,
)


class TestGossipPriority:
    """Test gossip message prioritization."""


class TestMessageBatching:
    """Test gossip message batching."""

    def test_message_batching_encode_decode(self):
        """Test that batch encode/decode roundtrips correctly."""
        messages = [
            {"type": "block", "height": 1},
            {"type": "block", "height": 2},
            {"type": "tx", "hash": "abc"},
        ]
        encoded = _encode_batch(messages)
        decoded = _decode_batch(encoded)
        assert len(decoded) == 3
        assert decoded[0]["type"] == "block"
        assert decoded[0]["height"] == 1
        assert decoded[1]["height"] == 2
        assert decoded[2]["type"] == "tx"

    def test_batch_backward_compat_single_message(self):
        """Test that _decode_batch handles single (non-batched) messages."""
        # Encode a single message (not as a list)
        single = _encode_message({"type": "block", "height": 1})
        decoded = _decode_batch(single)
        # Should be wrapped in a list
        assert isinstance(decoded, list)
        assert len(decoded) == 1
        assert decoded[0]["type"] == "block"
