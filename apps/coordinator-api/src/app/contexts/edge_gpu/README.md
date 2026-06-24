# Edge Gpu Context

**Description:** Edge GPU compute service

## Structure

| Component | Path |
|---|---|
| `routers` | `routers/` |
| `services` | `services/` |

## Domain Dependencies

| Domain Module | Imported Symbols |
|---|---|
| `app/domain/gpu_marketplace.py` | `ConsumerGPUProfile`, `EdgeGPUMetrics`, `GPUArchitecture` |

> **Note:** These imports cross the context boundary into the shared `app/domain/` layer. See [P2 audit](../../docs/releases/v0.5.12/p2_cross_context_import_audit.md) for details.
