"""#2553: GET /v1/market/offer?provider=<id> filters the merged catalog server-side.

The shop dashboard used to fetch one server page and filter by node_id
client-side, so a shop's own offers could be pushed out by the page cap.
The provider filter now runs before the cap inside list_software_services.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from market_service.domain.market import SoftwareService  # noqa: E402
from market_service.main import app  # noqa: E402
from market_service.storage import get_session_context  # noqa: E402


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.asyncio
async def test_provider_filter_keeps_only_matching_offers(client):
    suffix = uuid.uuid4().hex[:8]
    shop_a = f"shop-a-{suffix}"
    shop_b = f"shop-b-{suffix}"
    async with get_session_context() as session:
        session.add(
            SoftwareService(
                plugin_id=f"pf-a-{suffix}",
                service_type="inference",
                model="m",
                node_id=shop_a,
                provider_address="0xaaa",
                status="active",
            )
        )
        session.add(
            SoftwareService(
                plugin_id=f"pf-b-{suffix}",
                service_type="inference",
                model="m",
                node_id=shop_b,
                provider_address="0xbbb",
                status="active",
            )
        )
        await session.commit()

    resp = client.get("/v1/market/offer", params={"provider": shop_a})
    assert resp.status_code == 200
    offers = resp.json()["offers"]
    ours = [o for o in offers if o.get("plugin_id") == f"pf-a-{suffix}"]
    assert ours, "the shop's own offer must survive the provider filter"
    assert all(
        o.get("node_id") == shop_a or shop_a in str(o.get("provider_address") or "")
        for o in offers
        if o.get("plugin_id", "").startswith("pf-")
    )
    assert not any(o.get("plugin_id") == f"pf-b-{suffix}" for o in offers)

    # Unfiltered listing still returns both.
    both = client.get("/v1/market/offer").json()["offers"]
    ids = {o.get("plugin_id") for o in both}
    assert f"pf-a-{suffix}" in ids and f"pf-b-{suffix}" in ids
