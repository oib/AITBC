from __future__ import annotations

from aitbc_shared import MarketplaceBid, MarketplaceOffer

from ..storage.schema import MARKETPLACE_BID_TABLE

# Configure MarketplaceBid to use the correct table name
MarketplaceBid = MarketplaceBid.with_table_name(MARKETPLACE_BID_TABLE)
