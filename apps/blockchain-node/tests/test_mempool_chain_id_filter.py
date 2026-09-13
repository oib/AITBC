"""``/mempool`` must report the node's own chain when no chain_id is given.

The endpoint used to coerce an unspecified ``chain_id`` to ``""`` before
calling ``get_pending_transactions``, which defeated that method's
``if chain_id is None: chain_id = settings.chain_id`` default. ``""`` is not an
all-chains sentinel — both backends filter on it literally, and no entry
carries it — so a mempool holding transactions reported ``count: 0``.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import aitbc_chain.mempool as mempool_mod
from aitbc_chain.config import settings as aitbc_settings
from aitbc_chain.mempool import InMemoryMempool
from aitbc_chain.metrics import metrics_registry
from aitbc_chain.rpc.routers.core import router as core_router

CHAIN = "ait-test.example"
OTHER_CHAIN = "ait-other.example"


@pytest.fixture
def client(monkeypatch):
    """A client over a mempool holding one tx on the node's configured chain."""
    metrics_registry.reset()
    monkeypatch.setattr(aitbc_settings, "chain_id", CHAIN)

    pool = InMemoryMempool()
    pool.add({"from": "0xabc", "to": "0xdef", "amount": 1, "fee": 0, "nonce": 0}, chain_id=CHAIN)
    monkeypatch.setattr(mempool_mod, "_MEMPOOL", pool)

    app = FastAPI()
    app.include_router(core_router)
    yield TestClient(app)
    metrics_registry.reset()


def test_omitted_chain_id_reports_the_nodes_own_chain(client):
    body = client.get("/mempool").json()
    assert body["count"] == 1, "an omitted chain_id must fall back to settings.chain_id"
    assert body["transactions"][0]["from"] == "0xabc"


def test_empty_chain_id_param_is_treated_as_omitted(client):
    # ?chain_id= arrives as "", which must not be filtered on literally.
    assert client.get("/mempool?chain_id=").json()["count"] == 1


def test_explicit_chain_id_still_filters(client):
    assert client.get(f"/mempool?chain_id={CHAIN}").json()["count"] == 1
    assert client.get(f"/mempool?chain_id={OTHER_CHAIN}").json()["count"] == 0
