"""#1524: LIKE-metacharacter escaping on user-supplied search strings.

Search values stay parameter-bound (no SQL injection), but unescaped ``%``
and ``_`` acted as wildcards — ``model=%`` matched every GPU. These tests
pin literal-match semantics on the hardened coordinator-api sites:

* ``market_gpu`` ``GET /v1/market/gpu/list?model=``
* ``agent_router`` ``GET /v1/agents/workflows?tags=`` (JSON-string column —
  ``.contains([tag])`` also bound a list to a VARCHAR LIKE and could never
  match; now a literal JSON-element match)
* ``ResourceMatcher.advanced_search`` model/capabilities filters
* ``BountyService.search_bounties``
* ``AgentIdentityCore.search_identities``
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from aitbc.auth import create_access_token
from coordinator_api.agent_identity.core import AgentIdentityCore
from coordinator_api.contexts.agent_coordination.domain.agent import AIAgentWorkflow
from coordinator_api.contexts.agent_identity.domain.agent_identity import AgentIdentity
from coordinator_api.contexts.bounty.domain.bounty import Bounty
from coordinator_api.contexts.bounty.services.bounty_service import BountyService
from coordinator_api.contexts.market.domain.gpu_market import GPURegistry
from coordinator_api.contexts.market.services.resource_matcher import ResourceMatcher
from coordinator_api.utils.sql_like import escape_like, like_contains

ADMIN = "admin-like-escape"


def _admin_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(ADMIN, 'admin')}"}


class TestLikeHelpers:
    def test_escape_like_escapes_all_metacharacters(self):
        assert escape_like("a%b_c\\d") == "a\\%b\\_c\\\\d"

    def test_like_contains_wraps_and_escapes(self):
        assert like_contains("50%") == "%50\\%%"
        assert like_contains("plain") == "%plain%"


class TestGpuModelFilter:
    def _seed(self, db_session: Session) -> None:
        db_session.add(GPURegistry(id="gpu-a", miner_id="m1", model="rtx4090"))
        db_session.add(GPURegistry(id="gpu-b", miner_id="m1", model="100%"))
        db_session.commit()

    def test_percent_is_literal_not_wildcard(self, client: TestClient, db_session: Session) -> None:
        self._seed(db_session)
        resp = client.get("/v1/market/gpu/list", params={"model": "%"})
        assert resp.status_code == 200
        models = {g["model"] for g in resp.json()}
        assert models == {"100%"}

    def test_normal_substring_still_matches(self, client: TestClient, db_session: Session) -> None:
        self._seed(db_session)
        resp = client.get("/v1/market/gpu/list", params={"model": "rtx"})
        assert resp.status_code == 200
        assert {g["model"] for g in resp.json()} == {"rtx4090"}


class TestWorkflowTagFilter:
    def _seed(self, db_session: Session) -> None:
        for name, tags in (("alpha-wf", ["alpha"]), ("pct-wf", ["%"]), ("under-wf", ["a_b"])):
            db_session.add(
                AIAgentWorkflow(
                    owner_id=ADMIN,
                    name=name,
                    description="",
                    steps={"s": {"action": "noop"}},
                    is_public=True,
                    tags=json.dumps(tags),
                )
            )
        db_session.commit()

    def _names(self, client: TestClient, tag: str) -> set[str]:
        resp = client.get("/v1/agents/workflows", params={"tags": tag}, headers=_admin_headers())
        assert resp.status_code == 200
        return {w["name"] for w in resp.json()}

    def test_tag_match_is_exact_json_element(self, client: TestClient, db_session: Session) -> None:
        self._seed(db_session)
        assert self._names(client, "alpha") == {"alpha-wf"}

    def test_percent_tag_is_literal(self, client: TestClient, db_session: Session) -> None:
        self._seed(db_session)
        assert self._names(client, "%") == {"pct-wf"}

    def test_underscore_tag_is_literal(self, client: TestClient, db_session: Session) -> None:
        self._seed(db_session)
        assert self._names(client, "a_b") == {"under-wf"}


class TestResourceMatcherFilters:
    def _seed(self, db_session: Session) -> None:
        db_session.add(GPURegistry(id="gpu-a", miner_id="m1", model="rtx4090", capabilities=["a100"]))
        db_session.add(GPURegistry(id="gpu-b", miner_id="m1", model="h100", capabilities=["%"]))
        db_session.commit()

    def test_model_wildcard_is_literal(self, db_session: Session) -> None:
        self._seed(db_session)
        matcher = ResourceMatcher(db_session)
        results = matcher.advanced_search({"model": "%"}, user_id=None)
        assert results == []
        results = matcher.advanced_search({"model": "rtx"}, user_id=None)
        assert [r["gpu_id"] for r in results] == ["gpu-a"]

    def test_capability_wildcard_is_literal(self, db_session: Session) -> None:
        self._seed(db_session)
        matcher = ResourceMatcher(db_session)
        results = matcher.advanced_search({"capabilities": ["%"]}, user_id=None)
        assert [r["gpu_id"] for r in results] == ["gpu-b"]
        results = matcher.advanced_search({"capabilities": ["zzz"]}, user_id=None)
        assert results == []
        results = matcher.advanced_search({"capabilities": ["a100"]}, user_id=None)
        assert [r["gpu_id"] for r in results] == ["gpu-a"]


class TestBountySearch:
    def _seed(self, db_session: Session) -> None:
        for bounty_id, title in (("b-1", "train a model"), ("b-2", "100% uptime")):
            db_session.add(
                Bounty(
                    bounty_id=bounty_id,
                    title=title,
                    description="desc",
                    reward_amount=Decimal("10"),
                    creator_id="c1",
                    deadline=datetime.now(UTC) + timedelta(days=1),
                )
            )
        db_session.commit()

    @pytest.mark.asyncio
    async def test_percent_is_literal(self, db_session: Session) -> None:
        self._seed(db_session)
        service = BountyService(db_session)
        results = await service.search_bounties("%")
        assert [b.bounty_id for b in results] == ["b-2"]
        results = await service.search_bounties("model")
        assert [b.bounty_id for b in results] == ["b-1"]


class TestIdentitySearch:
    def _seed(self, db_session: Session) -> None:
        for agent_id, name in (("agent-a", "alice"), ("agent-b", "100%")):
            db_session.add(AgentIdentity(agent_id=agent_id, owner_address="0x" + "1" * 40, display_name=name))
        db_session.commit()

    @pytest.mark.asyncio
    async def test_percent_is_literal(self, db_session: Session) -> None:
        self._seed(db_session)
        core = AgentIdentityCore(db_session)
        results = await core.search_identities(query="%")
        assert [i.agent_id for i in results] == ["agent-b"]
        results = await core.search_identities(query="alice")
        assert [i.agent_id for i in results] == ["agent-a"]
