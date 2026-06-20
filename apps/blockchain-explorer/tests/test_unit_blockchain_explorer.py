"""Unit tests for blockchain explorer service"""

import pytest
from main import AnalyticsRequest, BlockSearch, TransactionSearch, app


@pytest.mark.unit
def test_app_initialization() -> None:
    """Test that the FastAPI app initializes correctly"""
    assert app is not None
    assert "AITBC Blockchain Explorer" in app.title
    assert app.version >= "2.0.0"


@pytest.mark.unit
def test_transaction_search_model() -> None:
    """Test TransactionSearch model"""
    search = TransactionSearch(
        address="0x1234567890abcdef",
        amount_min=1.0,
        amount_max=100.0,
        tx_type="transfer",
        since="2024-01-01",
        until="2024-12-31",
        limit=50,
        offset=0,
    )
    assert search.address == "0x1234567890abcdef"
    assert search.amount_min == 1.0
    assert search.amount_max == 100.0
    assert search.tx_type == "transfer"
    assert search.limit == 50


@pytest.mark.unit
def test_transaction_search_defaults() -> None:
    """Test TransactionSearch with default values"""
    search = TransactionSearch()
    assert search.address is None
    assert search.amount_min is None
    assert search.amount_max is None
    assert search.tx_type is None
    assert search.limit == 50
    assert search.offset == 0


@pytest.mark.unit
def test_block_search_model() -> None:
    """Test BlockSearch model"""
    search = BlockSearch(validator="0x1234567890abcdef", since="2024-01-01", until="2024-12-31", min_tx=5, limit=50, offset=0)
    assert search.validator == "0x1234567890abcdef"
    assert search.min_tx == 5
    assert search.limit == 50


@pytest.mark.unit
def test_block_search_defaults() -> None:
    """Test BlockSearch with default values"""
    search = BlockSearch()
    assert search.validator is None
    assert search.since is None
    assert search.until is None
    assert search.min_tx is None
    assert search.limit == 50
    assert search.offset == 0


@pytest.mark.unit
def test_analytics_request_model() -> None:
    """Test AnalyticsRequest model"""
    request = AnalyticsRequest(period="24h", granularity="hourly", metrics=["total_transactions", "volume"])
    assert request.period == "24h"
    assert request.granularity == "hourly"
    assert request.metrics == ["total_transactions", "volume"]


@pytest.mark.unit
def test_analytics_request_defaults() -> None:
    """Test AnalyticsRequest with default values"""
    request = AnalyticsRequest()
    assert request.period == "24h"
    assert request.granularity is None
    assert request.metrics == []


@pytest.mark.unit
def test_transaction_search_limit_validation() -> None:
    """Test TransactionSearch limit validation"""
    search = TransactionSearch(limit=1000)
    assert search.limit == 1000


@pytest.mark.unit
def test_transaction_search_offset_validation() -> None:
    """Test TransactionSearch offset validation"""
    search = TransactionSearch(offset=100)
    assert search.offset == 100


@pytest.mark.unit
def test_block_search_limit_validation() -> None:
    """Test BlockSearch limit validation"""
    search = BlockSearch(limit=500)
    assert search.limit == 500
