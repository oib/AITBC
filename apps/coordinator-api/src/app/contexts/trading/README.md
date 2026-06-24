# Trading Context

**Description:** Trading marketplace — AMM, order matching, negotiations

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
| `app/domain/trading.py` | `TradeMatch`, `TradeNegotiation`, `TradeRequest`, `TradeType` |
| `app/domain/amm.py` | `LiquidityPool`, `SwapTransaction` |

> **Note:** These imports cross the context boundary into the shared `app/domain/` layer. See [P2 audit](../../docs/releases/v0.5.12/p2_cross_context_import_audit.md) for details.
