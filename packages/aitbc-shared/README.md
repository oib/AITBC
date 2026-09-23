# AITBC Shared Models

Shared ORM models for AITBC applications.

This package provides common SQLModel definitions used across multiple AITBC services to avoid duplicate model definitions and SQLAlchemy metadata conflicts.

## Models

### Market
- `MarketOffer` - GPU/compute resource offerings
- `MarketBid` - Bids on market offers

### Payments
- `JobPayment` - Payment records for jobs
- `PaymentEscrow` - Escrow records for holding payments

## Installation

```bash
pip install -e packages/aitbc-shared
```

## Usage

```python
from aitbc_shared import MarketBid, MarketOffer, JobPayment, PaymentEscrow
```
