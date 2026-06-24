# Cross Chain Context

**Description:** Cross-chain bridge and multi-chain transaction support

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
| `app/domain/cross_chain_bridge.py` | `BridgeRequest`, `BridgeTransaction` |
| `app/domain/multi_chain_transaction.py` | `TransactionType` |

> **Note:** These imports cross the context boundary into the shared `app/domain/` layer. See [P2 audit](../../docs/releases/v0.5.12/p2_cross_context_import_audit.md) for details.
