# Advanced Rl Context

**Description:** Advanced reinforcement learning for marketplace optimization

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
| `app/domain/agent_performance.py` | `ReinforcementLearningConfig` |

> **Note:** These imports cross the context boundary into the shared `app/domain/` layer. See [P2 audit](../../docs/releases/v0.5.12/p2_cross_context_import_audit.md) for details.
