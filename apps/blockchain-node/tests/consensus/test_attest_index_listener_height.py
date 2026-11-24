"""#2869: a gossip ``attest_response`` with ``"height": Infinity`` used to
kill the observation-index listener — ``int(float("inf"))`` raises
OverflowError (an ArithmeticError), which the ``(TypeError, ValueError)``
catch did not cover, so the exception escaped the ``async for`` and the
task died. Sibling listeners already guard ArithmeticError per message.
"""

from __future__ import annotations

import math

from aitbc_chain.consensus.remote_attestation_listener import _ListenerMixin

CHAIN = "test-chain"
VALIDATOR = "0x" + "ab" * 20


def _listener() -> _ListenerMixin:
    listener = _ListenerMixin.__new__(_ListenerMixin)
    listener._chain_id = CHAIN
    return listener


def _response(height) -> dict:
    return {
        "chain_id": CHAIN,
        "height": height,
        "hash": "0x" + "cd" * 32,
        "validator": VALIDATOR,
    }


def test_infinite_height_dropped_not_crash():
    assert _listener()._parse_index_response(_response(math.inf), set()) is None
    assert _listener()._parse_index_response(_response(-math.inf), set()) is None


def test_nan_and_garbage_height_dropped():
    assert _listener()._parse_index_response(_response(math.nan), set()) is None
    assert _listener()._parse_index_response(_response("not-a-number"), set()) is None
    assert _listener()._parse_index_response(_response({"x": 1}), set()) is None


def test_valid_height_parses():
    parsed = _listener()._parse_index_response(_response(1234), set())
    assert parsed is not None
    height, block_hash, validator, canon = parsed
    assert height == 1234
    assert block_hash == "0x" + "cd" * 32
    assert validator == VALIDATOR


def test_wrong_chain_and_missing_fields_dropped():
    listener = _listener()
    assert listener._parse_index_response({**_response(1), "chain_id": "other"}, set()) is None
    assert listener._parse_index_response({"chain_id": CHAIN, "height": 1}, set()) is None
    assert listener._parse_index_response("not-a-dict", set()) is None
