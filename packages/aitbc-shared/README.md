# AITBC Shared Models

Shared ORM models for AITBC applications.

This package provides common SQLModel definitions used across multiple AITBC services to avoid duplicate model definitions and SQLAlchemy metadata conflicts.

## Models

### Marketplace
- `MarketplaceOffer` - GPU/compute resource offerings
- `MarketplaceBid` - Bids on marketplace offers

### Payments
- `JobPayment` - Payment records for jobs
- `PaymentEscrow` - Escrow records for holding payments

## Installation

```bash
pip install -e packages/aitbc-shared
```

## Usage

```python
from aitbc_shared import MarketplaceBid, MarketplaceOffer, JobPayment, PaymentEscrow
```