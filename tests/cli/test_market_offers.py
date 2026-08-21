"""Tests for the market offers CLI helpers."""

import pytest

from aitbc_cli.commands.market.offers import _sort_offers


class TestSortOffers:
    """Test deterministic sorting of marketplace offers."""

    @pytest.fixture
    def offers(self):
        return [
            {
                "plugin_id": "low-rated",
                "avg_rating": 0.0,
                "rating_count": 0,
                "price": 0.001,
                "status": "active",
                "capacity": 1,
            },
            {
                "plugin_id": "mid-rated",
                "avg_rating": 4.2,
                "rating_count": 8,
                "price": 0.0015,
                "status": "active",
                "capacity": 2,
            },
            {
                "plugin_id": "top-rated",
                "avg_rating": 4.5,
                "rating_count": 12,
                "price": 0.002,
                "status": "active",
                "capacity": 1,
            },
        ]

    def test_sort_reputation_desc(self, offers):
        sorted_offers = _sort_offers(offers, "reputation")
        assert [o["plugin_id"] for o in sorted_offers] == ["top-rated", "mid-rated", "low-rated"]

    def test_sort_price_asc(self, offers):
        sorted_offers = _sort_offers(offers, "price")
        assert [o["plugin_id"] for o in sorted_offers] == ["low-rated", "mid-rated", "top-rated"]

    def test_sort_availability_prefers_active(self, offers):
        offers[0]["status"] = "inactive"
        sorted_offers = _sort_offers(offers, "availability")
        # active ones first, then by capacity desc
        assert sorted_offers[0]["plugin_id"] != "low-rated"
        assert sorted_offers[-1]["plugin_id"] == "low-rated"

    def test_sort_default_is_reputation(self, offers):
        sorted_offers = _sort_offers(offers, "default")
        assert [o["plugin_id"] for o in sorted_offers] == ["top-rated", "mid-rated", "low-rated"]
