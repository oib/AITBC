from __future__ import annotations

from aitbc_shared import MarketBid

from ..storage.schema import MARKET_BID_TABLE

# Configure MarketBid to use the correct table name
MarketBid.with_table_name(MARKET_BID_TABLE)
