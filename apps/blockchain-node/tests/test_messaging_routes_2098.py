"""#2098 regression: canonical ``/rpc/messaging/*`` read routes must await
the shared handlers.

``27dd6a86d8`` stripped ``async``/``await`` from the delegating routes in
``rpc/routers/messaging.py``, but the shared ``messaging_*`` handlers stay
coroutine functions via the ``@_observed`` wrapper. A sync route then
returns an unawaited coroutine; FastAPI validates it against the inferred
``dict[str, Any]`` response model and raises ``ResponseValidationError``
→ every read 503'd fleet-wide (state/topics/messages/dm-keys/...).

Each route is exercised through a real ``TestClient`` with the shared
handler stubbed to an async function — pre-fix the route returns the
coroutine unawaited (500/ResponseValidationError), post-fix it awaits and
returns the payload.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import aitbc_chain.rpc.routers.messaging as messaging_router_mod
from aitbc_chain.rpc.routers.messaging import router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/rpc")
    return TestClient(app, raise_server_exceptions=False)


_ROUTES = [
    # (path, handler attribute, query)
    ("/rpc/messaging/state", "messaging_state", ""),
    ("/rpc/messaging/stats", "messaging_stats", ""),
    ("/rpc/messaging/topics", "messaging_topics", "?limit=5"),
    ("/rpc/messaging/messages", "messaging_messages", "?limit=5"),
    ("/rpc/messaging/messages/search?query=hi", "messaging_search", ""),
    ("/rpc/messaging/reputation/0xabc", "messaging_reputation", ""),
    ("/rpc/messaging/topics/someslug/moderation", "messaging_moderation", ""),
    ("/rpc/messaging/dm-keys/0xabc", "messaging_dm_key", ""),
    ("/rpc/messaging/dm/0xabc", "messaging_dm_inbox", ""),
    ("/rpc/messaging/messages/0xdeadbeef/votes", "messaging_votes", ""),
    ("/rpc/messaging/messages/0xdeadbeef", "messaging_get", ""),
]


@pytest.mark.parametrize("path,handler_attr,_q", _ROUTES)
def test_route_awaits_shared_handler(monkeypatch, path, handler_attr, _q):
    async def _stub(*args, **kwargs):
        return {"success": True, "stub": handler_attr}

    monkeypatch.setattr(messaging_router_mod, handler_attr, _stub)
    r = _client().get(path)
    assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text[:200]}"
    assert r.json()["stub"] == handler_attr
