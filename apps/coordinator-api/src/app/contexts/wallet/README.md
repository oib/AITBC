# Wallet Context

**Description:** Multi-chain wallet management

## Structure

| Component | Path |
|---|---|
| `services` | `services/` |

## Domain Dependencies

| Domain Module | Imported Symbols |
|---|---|
| `app/domain/wallet.py` | `AgentWallet`, `TokenBalance`, `TransactionStatus`, `WalletTransaction` |

> **Note:** These imports cross the context boundary into the shared `app/domain/` layer. See [P2 audit](../../docs/releases/v0.5.12/p2_cross_context_import_audit.md) for details.
