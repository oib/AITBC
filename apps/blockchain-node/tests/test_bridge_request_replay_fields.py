"""Replay-guard fields must survive the bridge request models.

The admin replay guard (issued_at/nonce/target_chain_id/target_node_id)
verifies a signature over the *dumped* request dict. If the Pydantic
models drop those fields, the verifier sees a payload different from the
one the caller signed and freshness can never pass — the endpoint is
dead on the release path. These tests pin the fields through
``model_dump(exclude_none=True)`` for both admin-gated models.
"""

from __future__ import annotations

from aitbc_chain.rpc.routers.bridge import BlockHeaderRequest, ValidatorRegisterRequest

_REPLAY_FIELDS = ("issued_at", "nonce", "target_chain_id", "target_node_id")

_REGISTER_PAYLOAD = {
    "chain_id": "ait-test",
    "address": "0x" + "ab" * 20,
    "public_key": "0x" + "cd" * 32,
    "signature": "0x" + "ef" * 65,
    "epoch": 1,
    "admin_address": "0x" + "12" * 20,
    "admin_signature": "0x" + "34" * 65,
    "issued_at": "2026-10-07T12:00:00+00:00",
    "nonce": "deadbeef" * 4,
    "target_chain_id": "ait-test",
    "target_node_id": "hub",
}

_HEADER_PAYLOAD = {
    "chain_id": "ait-test",
    "height": 7,
    "hash": "0x" + "ab" * 32,
    "parent_hash": "0x" + "cd" * 32,
    "proposer": "0x" + "ef" * 20,
    "state_root": "0x" + "12" * 32,
    "bridge_state_root": "0x" + "34" * 32,
    "signature": "0x" + "56" * 65,
    "issued_at": "2026-10-07T12:00:00+00:00",
    "nonce": "deadbeef" * 4,
    "target_chain_id": "ait-test",
    "target_node_id": "hub",
}


def _assert_fields_survive(model, payload: dict) -> None:
    req = model(**payload)
    dumped = req.model_dump(exclude_none=True)
    for field in _REPLAY_FIELDS:
        assert field in dumped, f"{model.__name__} dropped {field} — replay guard can never pass"
        assert dumped[field] == payload[field]


def test_validator_register_request_keeps_replay_fields() -> None:
    _assert_fields_survive(ValidatorRegisterRequest, _REGISTER_PAYLOAD)


def test_block_header_request_keeps_replay_fields() -> None:
    _assert_fields_survive(BlockHeaderRequest, _HEADER_PAYLOAD)


def test_replay_fields_optional_when_absent() -> None:
    # omitting the fields must still parse — the server-side guard is what
    # fails closed on missing values, not the model.
    minimal = {k: v for k, v in _REGISTER_PAYLOAD.items() if k not in _REPLAY_FIELDS}
    req = ValidatorRegisterRequest(**minimal)
    dumped = req.model_dump(exclude_none=True)
    for field in _REPLAY_FIELDS:
        assert field not in dumped
