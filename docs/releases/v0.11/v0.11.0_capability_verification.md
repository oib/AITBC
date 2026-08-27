# v0.11.0 Core Capability Verification

This document records the completion status of the Phase 2/3 core capabilities
referenced in the v0.11.0 plan.

## Global Multi-Region Edge Nodes — ✅ COMPLETE

- `apps/edge` service registers edge nodes with a `region` field on startup.
- Island memberships now support an optional `region` field stored in
  `extra_data` and exposed via `POST /api/v1/islands/join` and
  `GET /api/v1/islands/by-region/{region}`.
- `apps/edge` already provides health reporting, blockchain registration,
  and island/bridge/serve/database/metrics routers.

## Dynamic GPU Priority Queuing — ✅ COMPLETE

- `apps/gpu` now persists a `gpu_job_queue` table with `priority` ordering.
- New endpoints:
  - `POST /v1/gpu/queue` — enqueue a job with priority.
  - `GET /v1/gpu/queue/{gpu_id}` — list jobs for a GPU ordered by priority.
  - `POST /v1/gpu/queue/{gpu_id}/next` — pop the highest-priority queued job.
  - `POST /v1/gpu/queue/{job_id}/complete` — mark a running job completed.
- `EdgeGPUService` exposes `queue_job`, `list_queued_jobs`,
  `get_next_queued_job`, and `complete_job`.

## Multi-Modal Fusion — ✅ COMPLETE

- Shared fusion types landed in `aitbc/fusion/` (`FusionInput`, `FusionOutput`,
  `FusionConfig`, `FusionStrategy`).
- `apps/coordinator-api/contexts/multimodal` contains the SQLModel
  `FusionModel`, `MultiModalFusionEngine`, neural modules, and health router,
  all wired into `coordinator-api`.

## Verification Commands

```bash
cd /opt/aitbc
./venv/bin/python -m ruff check .
./venv/bin/python -m mypy --show-error-codes aitbc/fusion apps/edge/src/aitbc_edge apps/gpu/src/gpu_service
./venv/bin/python -m pytest tests/unit -q -o addopts=""
```
