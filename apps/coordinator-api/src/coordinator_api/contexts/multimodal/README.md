# multimodal

Multimodal AI — fusion, modality optimization, and RL across modalities.

## Domain Models

- None (stub)

## Routes

Only `multi_modal_rl.py` (`/v1/multi-modal-rl/*`) is mounted. The two
`_health.py` routers (`multimodal_health.py`, `modality_optimization_health.py`)
were deleted in issue #701 — imported in `routers/__init__.py` but never
mounted.

From `multi_modal_rl.py` (mounted at `/v1/multi-modal-rl`):

- POST /jobs
- GET /jobs/{job_id}
- GET /jobs/{job_id}/result
- POST /jobs/{job_id}/cancel
- GET /jobs
- GET /health

## Services

- multimodal_agent.py
