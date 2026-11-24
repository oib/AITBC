"""#2856 AUDIT-MONEY-45: SoftwareService price/price_unit validated on register.

``price`` feeds the #2608 listed-price floor and metered billing — NaN,
negative, or oversized values persisted silently and disabled the floor for
that offer. ``price_unit`` selects the billing formula. Registration now runs
the same ``_money_decimal`` bound offers/bids/job-payments use, plus the
known-unit vocabulary.
"""

from __future__ import annotations

import time
from uuid import uuid4

import pytest
from market_service.services.market_service import MarketService
from market_service.storage import get_session_context

pytestmark = pytest.mark.asyncio

_TEST_PRIVATE_KEY = "0x" + "33" * 32


def _signed_data(**fields) -> dict:
    """POST /v1/market/offer body carrying a valid provider signature."""
    from aitbc.crypto.crypto import derive_ethereum_address, sign_transaction_data
    from aitbc.market.offer_registration import offer_body_hash, registration_message
    from aitbc.utils.chain_id import resolve_chain_id
    from market_service.config import settings

    provider = derive_ethereum_address(_TEST_PRIVATE_KEY)
    issued_at = int(time.time())
    chain_id = settings.default_chain_id or resolve_chain_id()
    body = {
        **fields,
        "provider_address": provider,
        "chain_id": chain_id,
        "issued_at": issued_at,
    }
    body["signature"] = sign_transaction_data(
        registration_message("register", fields["plugin_id"], provider, chain_id, issued_at, offer_body_hash(body)),
        _TEST_PRIVATE_KEY,
    )
    return body


async def _register(**fields) -> dict:
    async with get_session_context() as session:
        return await MarketService(session).register_software_service(_signed_data(**fields))


@pytest.mark.parametrize("bad_price", ["NaN", "Infinity", -1, "-0.5", 1e30, "not-a-number"])
async def test_invalid_price_rejected(bad_price) -> None:
    plugin_id = f"p2856-{uuid4().hex[:10]}"
    with pytest.raises(ValueError):
        await _register(plugin_id=plugin_id, service_type="inference", model="m", price=bad_price)


async def test_unknown_price_unit_rejected() -> None:
    plugin_id = f"p2856-{uuid4().hex[:10]}"
    with pytest.raises(ValueError, match="price_unit"):
        await _register(
            plugin_id=plugin_id,
            service_type="inference",
            model="m",
            price="0.01",
            price_unit="per_furlong",
        )


async def test_valid_price_and_unit_accepted() -> None:
    plugin_id = f"p2856-{uuid4().hex[:10]}"
    out = await _register(
        plugin_id=plugin_id,
        service_type="inference",
        model="m",
        price="0.0125",
        price_unit="per_1k_tokens",
    )
    assert out["plugin_id"] == plugin_id


async def test_update_with_invalid_price_rejected_and_row_unchanged() -> None:
    """The update path shares the same validation — a bad price must not
    land on an existing row."""
    plugin_id = f"p2856-{uuid4().hex[:10]}"
    await _register(plugin_id=plugin_id, service_type="inference", model="m", price="0.01", price_unit="per_day")
    with pytest.raises(ValueError):
        await _register(plugin_id=plugin_id, service_type="inference", model="m", price="NaN")

    from market_service.domain.market import SoftwareService
    from sqlalchemy import select

    async with get_session_context() as session:
        row = (await session.execute(select(SoftwareService).where(SoftwareService.plugin_id == plugin_id))).scalars().one()
        assert str(row.price) == "0.01000000"
        assert row.price_unit == "per_day"
