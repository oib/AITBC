# multimodal

Multimodal AI — fusion, modality optimization, and RL across modalities.

## Domain Models

- None (stub)

## Routes

Only `multi_modal_rl.py` (`/v1/multi-modal-rl/*`) is mounted. The two
`_health.py` routers are imported in `routers/__init__.py` but never
`include_router`'d in main.py — their rows below 404.

From `modality_optimization_health.py` — **unmounted, 404**:

- GET /health
- GET /health/deep

From `multi_modal_rl.py` (mounted at `/v1/multi-modal-rl`):

- POST /jobs
- GET /jobs/{job_id}
- GET /jobs/{job_id}/result
- POST /jobs/{job_id}/cancel
- GET /jobs
- GET /health

From `multimodal_health.py` — **unmounted, 404**:

- GET /health
- GET /health/deep

## Services

- multimodal_agent.py
