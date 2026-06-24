# Marketplace Context

**Description:** GPU marketplace — offers, bookings, reviews, resource matching

## Structure

| Component | Path |
|---|---|
| `domain` | `domain/` |
| `routers` | `routers/` |
| `services` | `services/` |
| `storage` | `storage/` |

## Domain Dependencies

| Domain Module | Imported Symbols |
|---|---|
| `app/domain/global_marketplace.py` | `GlobalMarketplaceOffer` |
| `app/domain/gpu_marketplace.py` | `GPUBooking`, `GPURegistry`, `GPUReview` |
| `app/domain/multi_chain_transaction.py` | `TransactionPriority` |
| `app/domain/agent.py` | `Miner` |

> **Note:** These imports cross the context boundary into the shared `app/domain/` layer. See [P2 audit](../../docs/releases/v0.5.12/p2_cross_context_import_audit.md) for details.
