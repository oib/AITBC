# Advanced Auction Types

## Overview

The marketplace now supports three advanced auction types in addition to standard bidding.

## Auction Types

### Dutch Auction
- **Description:** Price decreases over time until a bid is accepted
- **Configuration:**
  - `start_price`: Initial high price
  - `decrement_rate`: Price decrease per interval
  - `decrement_interval`: Time between decrements (seconds)
  - `reserve_price`: Minimum acceptable price
- **Use Case:** Quick resource liquidation

### Sealed-Bid Auction
- **Description:** Bids are encrypted until reveal time
- **Configuration:**
  - `reveal_timestamp`: When bids are revealed
  - `reserve_price`: Minimum acceptable price
- **Use Case:** Private competitive bidding

### Reverse Auction
- **Description:** Providers compete to offer lowest price
- **Configuration:**
  - `reserve_price`: Maximum acceptable price
- **Use Case:** Cost optimization for buyers

## Usage Example

```python
from app.contexts.marketplace.services.marketplace import MarketplaceService

service = MarketplaceService(session)

# Create Dutch auction
auction = service.create_auction(
    resource_id="gpu-789",
    auction_type="dutch",
    start_price=1.0,
    decrement_rate=0.05,
    decrement_interval=60,
    reserve_price=0.30,
    duration_hours=4
)

# Submit bid
bid = service.submit_auction_bid(
    auction_id=auction.auction_id,
    provider="provider-123",
    price=0.45
)

# Update Dutch price
current_price = service.update_dutch_price(auction.auction_id)
```
