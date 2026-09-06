"""Unit tests for gossip topic classification.

These tests do not require Redis or an active node; they guard the topic
matching logic that the public websocket handler uses to decide whether a
topic requires validator authentication.
"""
from __future__ import annotations

import pytest

from aitbc_chain.gossip.gossip_auth import is_public_topic, is_restricted_topic


@pytest.mark.parametrize(
    ("topic", "expected"),
    [
        ("blocks", True),
        ("blocks.ait-hub.aitbc.bubuit.net", True),
        ("pbft.prepare.ait-hub.aitbc.bubuit.net", True),
        ("pbft.pre_prepare.ait-hub.aitbc.bubuit.net", True),
        ("pbft.commit.ait-hub.aitbc.bubuit.net", True),
        ("pbft", True),
        ("consensus.attest_request.ait-hub.aitbc.bubuit.net", True),
        ("consensus.attest_response.ait-hub.aitbc.bubuit.net", True),
        ("consensus", True),
        ("transactions", False),
        ("transactions.ait-hub.aitbc.bubuit.net", False),
        ("status", False),
        ("mempool", False),
        ("mempool.pending", False),
        ("random", False),
    ],
)
def test_is_restricted_topic(topic: str, expected: bool) -> None:
    assert is_restricted_topic(topic) is expected


@pytest.mark.parametrize(
    ("topic", "expected"),
    [
        ("transactions", True),
        ("transactions.ait-hub.aitbc.bubuit.net", True),
        ("status", True),
        ("status.health", True),
        ("mempool", True),
        ("mempool.pending", True),
        ("blocks", False),
        ("blocks.ait-hub.aitbc.bubuit.net", False),
        ("pbft.prepare", False),
        ("pbft.pre_prepare", False),
        ("consensus.attest", False),
        ("random", False),
    ],
)
def test_is_public_topic(topic: str, expected: bool) -> None:
    assert is_public_topic(topic) is expected
