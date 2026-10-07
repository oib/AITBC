"""Round-trip coverage for the replay-guard fields on bridge admin request models.

Regression coverage for c0797723f5: ``ValidatorRegisterRequest`` and
``BlockHeaderRequest`` must carry ``issued_at``, ``nonce``,
``target_chain_id`` and ``target_node_id`` through
``model_dump(exclude_none=True)`` — the exact dict handed to the admin
signature check (``rpc/bridge.py`` ``verify_admin_signature`` at the
register and block-header handlers). On the parent commit the models lack
the fields, pydantic drops them silently, and the positive tests here fail.
"""

from __future__ import annotations

import asyncio
import types

import pytest

from aitbc_chain.rpc.routers import bridge as bridge_router

GUARD = {
    "issued_at": "2026-10-07T12:00:00+00:00",
    "nonce": "ab12cd34ef56",
    "target_chain_id": "ait-hub.aitbc.bubuit.net",
    "target_node_id": "hub",
}

REG_BODY = {
    "chain_id": "ait-hub.aitbc.bubuit.net",
    "address": "0x2ad555a9e5208a6438b24fbda4bc83c4c2453e64",
    "public_key": "0x04deadbeef",
    "signature": "0xsig",
    "epoch": 1,
    "admin_address": "0xd80372cbf66c96299a171accbc98bdd608923cef",
    "admin_signature": "0xadminsig",
    **GUARD,
}

HDR_BODY = {
    "chain_id": "ait-hub.aitbc.bubuit.net",
    "height": 42,
    "hash": "0xabc",
    "proposer": "0x02b8f2c61db1",
    "state_root": "0xdef",
    "signature": "0xpsig",
    "admin_address": "0xd80372cbf66c96299a171accbc98bdd608923cef",
    "admin_signature": "0xadminsig",
    **GUARD,
}


def _stub_request() -> types.SimpleNamespace:
    return types.SimpleNamespace(client=types.SimpleNamespace(host="127.0.0.1"))


def test_register_request_dump_keeps_guard_fields() -> None:
    dumped = bridge_router.ValidatorRegisterRequest(**REG_BODY).model_dump(exclude_none=True)
    for field, value in GUARD.items():
        assert dumped.get(field) == value


def test_block_header_request_dump_keeps_guard_fields() -> None:
    dumped = bridge_router.BlockHeaderRequest(**HDR_BODY).model_dump(exclude_none=True)
    for field, value in GUARD.items():
        assert dumped.get(field) == value


def test_guard_fields_optional_on_register() -> None:
    body = {k: v for k, v in REG_BODY.items() if k not in GUARD}
    dumped = bridge_router.ValidatorRegisterRequest(**body).model_dump(exclude_none=True)
    for field in GUARD:
        assert field not in dumped


def test_guard_fields_optional_on_block_header() -> None:
    body = {k: v for k, v in HDR_BODY.items() if k not in GUARD}
    dumped = bridge_router.BlockHeaderRequest(**body).model_dump(exclude_none=True)
    for field in GUARD:
        assert field not in dumped


def test_register_route_forwards_guard_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """The dict the route hands to ``register_validator`` is what the
    signature check sees — prove the guard fields cross that boundary."""
    captured: dict = {}

    async def _fake_register(request, data):
        captured.update(data)
        return {"success": True}

    monkeypatch.setattr(bridge_router, "register_validator", _fake_register)
    monkeypatch.setattr(bridge_router, "_validate_chain_id", lambda _cid: None)
    reg = bridge_router.ValidatorRegisterRequest(**REG_BODY)
    asyncio.run(bridge_router.register_validator_route.__wrapped__(_stub_request(), reg))
    for field, value in GUARD.items():
        assert captured.get(field) == value


def test_block_header_route_forwards_guard_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    async def _fake_store(request, data):
        captured.update(data)
        return {"success": True}

    monkeypatch.setattr(bridge_router, "store_block_header", _fake_store)
    monkeypatch.setattr(bridge_router, "_validate_chain_id", lambda _cid: None)
    hdr = bridge_router.BlockHeaderRequest(**HDR_BODY)
    asyncio.run(bridge_router.store_block_header_route.__wrapped__(_stub_request(), hdr))
    for field, value in GUARD.items():
        assert captured.get(field) == value
