# Trading

## 7. Trading

### Trade Requests

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Create Request | Create a new trade request | [docs/architecture/6_trade-exchange.md](../architecture/6_trade-exchange.md) | ✅ | v0.8.0 |
| List Requests | List trade requests with filters | [docs/architecture/6_trade-exchange.md](../architecture/6_trade-exchange.md) | ✅ | v0.8.0 |
| Get Request | Get a specific trade request by ID | [docs/architecture/6_trade-exchange.md](../architecture/6_trade-exchange.md) | ✅ | v0.8.0 |

### Trade Matches & Agreements

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Create Match | Create a new trade match | [docs/architecture/6_trade-exchange.md](../architecture/6_trade-exchange.md) | ✅ | v0.8.0 |
| List Matches | List trade matches with filters | [docs/architecture/6_trade-exchange.md](../architecture/6_trade-exchange.md) | ✅ | v0.8.0 |
| Create Agreement | Create a trade agreement | [docs/architecture/6_trade-exchange.md](../architecture/6_trade-exchange.md) | ✅ | v0.8.0 |
| List Agreements | List trade agreements with filters | [docs/architecture/6_trade-exchange.md](../architecture/6_trade-exchange.md) | ✅ | v0.8.0 |

### Inter-Chain Trading

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Create Inter-Chain Trade | Create trade between source and destination chains | [docs/releases/v0.8/v0.8.0_change.log](releases/v0.8/v0.8.0_change.log) | ✅ | v0.8.0 |
| Match Trade | Attempt to match a trade | [docs/releases/v0.8/v0.8.0_change.log](releases/v0.8/v0.8.0_change.log) | ✅ | v0.8.0 |
| Match All Trades | Match all pending trades | [docs/releases/v0.8/v0.8.0_change.log](releases/v0.8/v0.8.0_change.log) | ✅ | v0.8.0 |
| Inter-Chain Trade History | View cross-chain trade history | [docs/releases/v0.8/v0.8.0_change.log](releases/v0.8/v0.8.0_change.log) | ✅ | v0.8.0 |

### Offer Sync

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Discover Offers | Discover offers across chains (polling) | [docs/releases/v0.8/v0.8.1_change.log](releases/v0.8/v0.8.1_change.log) | ✅ | v0.8.1 |
| Sync Offers | Sync offers from other chains (polling) | [docs/releases/v0.8/v0.8.1_change.log](releases/v0.8/v0.8.1_change.log) | ✅ | v0.8.1 |
| Sync Status | Get offer sync status | [docs/releases/v0.8/v0.8.1_change.log](releases/v0.8/v0.8.1_change.log) | ✅ | v0.8.1 |
| Offer Cache | Get cached offers | [docs/releases/v0.8/v0.8.2_change.log](releases/v0.8/v0.8.2_change.log) | ✅ | v0.8.2 |
| Search Offers | Search offers with filters | [docs/releases/v0.8/v0.8.2_change.log](releases/v0.8/v0.8.2_change.log) | ✅ | v0.8.2 |

### Offer Subscription

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Subscribe to Offers | Subscribe to real-time offer updates via gossip | [docs/releases/v0.8/v0.8.2_change.log](releases/v0.8/v0.8.2_change.log) | ✅ | v0.8.2 |
| Heartbeat | Extend subscription lease via heartbeat | [docs/releases/v0.8/v0.8.2_change.log](releases/v0.8/v0.8.2_change.log) | ✅ | v0.8.2 |
| Subscription Status | Get subscription status | [docs/releases/v0.8/v0.8.2_change.log](releases/v0.8/v0.8.2_change.log) | ✅ | v0.8.2 |
| Polling Fallback | Automatic fallback to polling when gossip is silent | [docs/releases/v0.8/v0.8.2_change.log](releases/v0.8/v0.8.2_change.log) | ✅ | v0.10.1 |
| Lease Tracker | Redis-based lease tracking for subscription auth | [docs/releases/v0.8/v0.8.2_change.log](releases/v0.8/v0.8.2_change.log) | ✅ | v0.10.1 |

### Atomic Settlement (Trading)

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Lock Escrow | Lock escrow funds for atomic settlement | [docs/releases/v0.9/v0.9.0_change.log](releases/v0.9/v0.9.0_change.log) | ⚠️ | v0.9.0 |
| Settle Trade | Execute atomic cross-chain settlement | [docs/releases/v0.9/v0.9.0_change.log](releases/v0.9/v0.9.0_change.log) | ⚠️ | v0.9.0 |
| Settlement Status | Get settlement status for a trade | [docs/releases/v0.9/v0.9.0_change.log](releases/v0.9/v0.9.0_change.log) | ⚠️ | v0.9.0 |

### Chain Management (Trading)

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| List Chains | List registered trading chains | [docs/releases/v0.8/v0.8.0_change.log](releases/v0.8/v0.8.0_change.log) | ✅ | v0.8.0 |
| Register Chain | Register a new chain for trading | [docs/releases/v0.8/v0.8.0_change.log](releases/v0.8/v0.8.0_change.log) | ✅ | v0.8.0 |
| Chain Health | Check chain health | [docs/releases/v0.8/v0.8.0_change.log](releases/v0.8/v0.8.0_change.log) | ✅ | v0.8.0 |

### Exchange Integration

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Create Payment | Create exchange payment | [docs/features/create-payment.md](./create-payment.md) | ✅ | — |
| Payment Status | Get payment status | [docs/features/payment-status.md](./payment-status.md) | ✅ | — |
| Exchange Rates | Get exchange rates | [docs/features/exchange-rates.md](./exchange-rates.md) | ✅ | — |
| Market Stats | Get market statistics | [docs/features/market-stats.md](./market-stats.md) | ✅ | — |
| Wallet Balance/Info | Get exchange wallet balance and info | [docs/features/wallet-balance-info.md](./wallet-balance-info.md) | ✅ | — |

---
