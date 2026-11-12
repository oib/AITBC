"""NaN/Infinity fuzz pins for the market money paths (#1676-class, dict bodies).

``POST /v1/market/offers/{id}/book`` and ``POST /v1/market/offers`` take plain
``dict`` bodies, so pydantic never sees the fields — literal ``NaN`` /
``Infinity`` JSON floats arrive as Python floats and ``Decimal(str(nan))``
yields ``Decimal("NaN")``, which used to persist on the bid/offer row and
reach the on-chain escrow payload. The service now rejects non-finite money
fields with ``ValueError`` (-> HTTP 400 via the route's existing mapping)
before the offer CAS claim.
"""

import sys
from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from market_service.domain.market import Bid
from market_service.services.market_service import MarketService, _money_decimal
from market_service.storage import get_session_context


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with get_session_context() as s:
        yield s


async def _bookable_offer(svc: MarketService, **overrides):
    data = {
        "provider": "0xProviderAddr",
        "price": "5",
        "capacity": 1,
        "gpu_model": "RTX4090",
        "chain_id": "ait-testchain",
        "status": "available",
    }
    data.update(overrides)
    return await svc.create_offer(data)


class TestBookOfferNonFinite:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), "NaN", "Infinity", 1e308, -1, 1e18, "1e30"])
    async def test_non_finite_price_rejected_before_bid(self, session, bad):
        svc = MarketService(session)
        offer = await _bookable_offer(svc)
        with pytest.raises(ValueError):
            await svc.book_offer(offer.id, {"wallet": "0xBuyer", "price": bad})
        bids = list((await session.execute(select(Bid).where(Bid.offer_id == offer.id))).scalars())
        assert bids == []
        await session.refresh(offer)
        # The CAS claim must not have fired — the offer stays bookable.
        assert offer.status == "available"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad", [float("nan"), "NaN", float("inf")])
    async def test_non_finite_amount_rejected(self, session, bad):
        """``amount`` feeds the on-chain escrow payload even when ``price`` is fine."""
        svc = MarketService(session)
        offer = await _bookable_offer(svc)
        with pytest.raises(ValueError):
            await svc.book_offer(offer.id, {"wallet": "0xBuyer", "price": "5", "amount": bad})

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), "nan"])
    async def test_non_finite_duration_rejected(self, session, bad):
        svc = MarketService(session)
        offer = await _bookable_offer(svc)
        with pytest.raises(ValueError):
            await svc.book_offer(offer.id, {"wallet": "0xBuyer", "duration_hours": bad})

    @pytest.mark.asyncio
    async def test_valid_booking_still_works(self, session):
        svc = MarketService(session)
        offer = await _bookable_offer(svc)
        result = await svc.book_offer(offer.id, {"wallet": "0xBuyer", "price": "7.5", "duration_hours": 2})
        assert result["bid_id"]
        bid = await session.get(Bid, result["bid_id"])
        assert bid is not None
        assert bid.price == Decimal("7.5")


class TestCreateOfferNonFinite:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("field", ["price", "price_per_hour"])
    @pytest.mark.parametrize("bad", [float("nan"), "NaN", float("inf"), "-Infinity", -0.5, 1e18])
    async def test_non_finite_offer_price_rejected(self, session, field, bad):
        """A NaN price on the offer row would poison every later booking that
        defaults to it and every avg(price) aggregate."""
        svc = MarketService(session)
        with pytest.raises(ValueError):
            await svc.create_offer(
                {
                    "provider": "0xP",
                    "capacity": 1,
                    "status": "available",
                    field: bad,
                }
            )

    @pytest.mark.asyncio
    async def test_string_and_scientific_prices_accepted(self, session):
        svc = MarketService(session)
        offer = await _bookable_offer(svc, price="1e3")
        await session.refresh(offer)
        assert offer.price is not None


class TestBookRouteRawNaNBody:
    """HTTP-level pin: a literal ``NaN`` JSON float in the dict body must
    answer 400 (service ValueError), never 500 or a stored NaN bid."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient

        from market_service import main as market_main
        from market_service.main import app

        market_main._market_user_key_auth.auth_enabled = True
        market_main._market_user_key_auth.expected_key = "test-market-key"
        market_main._market_operator_key_auth.auth_enabled = True
        market_main._market_operator_key_auth.expected_key = "test-operator-key"
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c

    @pytest.mark.asyncio
    async def test_raw_nan_price_body_is_400_not_500(self, session, client):
        svc = MarketService(session)
        offer = await _bookable_offer(svc)
        body = b'{"wallet":"0xBuyer","price":NaN,"amount":Infinity,"duration_hours":-Infinity}'
        resp = client.post(
            f"/v1/market/offers/{offer.id}/book",
            content=body,
            headers={"Content-Type": "application/json", "X-API-Key": "test-operator-key"},
        )
        assert resp.status_code == 400, f"{resp.status_code}: {resp.text[:300]}"


class TestMoneyDecimalBoundary:
    """V16 round-5 money-edge: the 1e15 ceiling is INCLUSIVE, exponent
    overflow ('1e999') and type-confused inputs must raise ValueError —
    never persist, never 500."""

    @pytest.mark.parametrize(
        "ok",
        [
            "0",
            "0.00000001",
            "999999999999999.99999999",
            "1000000000000000",  # exactly the ceiling — inclusive
            "1e15",
            Decimal("1000000000000000"),
            5,
            5.5,
            "-0",  # negative zero compares equal to zero — non-negative
            "١٢٣",  # Unicode decimal digits parse to a real number (123)
            "1_000",  # Decimal accepts digit underscores — same as float()/int()
        ],
    )
    def test_boundary_and_valid_inputs_accepted(self, ok):
        parsed = _money_decimal(ok, "price")
        assert parsed >= 0
        assert parsed <= Decimal("1000000000000000")

    @pytest.mark.parametrize(
        "bad",
        [
            "1000000000000000.00000001",  # ceiling + epsilon
            "1e999",  # exponent overflow — finite Decimal, way over cap
            Decimal("1e999"),
            1e30,
            float("inf"),
            float("-inf"),
            "NaN",
            "Infinity",
            "-Infinity",
            "-0.00000001",  # genuinely negative
            "-5",
            True,  # bool is not a number here
            False,
            [],
            {},
            b"5",  # bytes stringify to "b'5'" — not a number
            "  ",
            "abc",
            None,
        ],
    )
    def test_over_ceiling_and_type_confused_rejected(self, bad):
        with pytest.raises(ValueError):
            _money_decimal(bad, "price")

    def test_unicode_digits_parse_to_their_value(self):
        """'١٢٣' is a legitimate numeric string — pin the parse so a future
        'fix' that rejects it is a deliberate change, not an accident."""
        assert _money_decimal("١٢٣", "price") == Decimal("123")
