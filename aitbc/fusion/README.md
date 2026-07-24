# aitbc.fusion — Multi-Modal Fusion shared types ✅ COMPLETE

This package provides the shared data types used by the multi-modal fusion
capability in `apps/coordinator-api/contexts/multimodal` and future fusion
consumers.

## Types

- `FusionStrategy` — supported fusion strategies (ensemble, attention,
  transformer, cross-modal, graph neural, NAS).
- `FusionInput` — a single modality payload with optional metadata.
- `FusionConfig` — runtime hyper-parameters for a fusion run.
- `FusionOutput` — structured fusion result with weights and quality scores.

## Status

- Shared types implemented and exported.
- Concrete fusion engine, SQLModel persistence, and REST/health routers live
  in `apps/coordinator-api/contexts/multimodal` and are wired in the
  coordinator-api service.
