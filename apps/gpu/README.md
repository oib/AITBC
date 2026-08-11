# gpu

## Status

**active**

## Description

GPU marketplace and resource management service. Tracks GPU availability, allocates GPU resources to jobs, and manages GPU profiles for different workload types.

## Node Type

hub, island

## GPU Required

**Yes**

## Service

1 systemd service(s): aitbc-gpu.service

## Core Service

no

## Source

`src/` directory with 9 Python file(s)

---
*Last updated: 2026-06-17*

## Database migrations

```bash
cd apps/gpu && PYTHONPATH=src ../../venv/bin/python -m alembic upgrade head
```

The target database is resolved from `DATABASE_URL`, defaulting to
`sqlite:////var/lib/aitbc/data/gpu_service.db`, and **printed to stderr before anything
runs** — check that line before letting a migration proceed. To run against a copy:

```bash
DATABASE_URL=sqlite:///path/to/copy.db PYTHONPATH=src ../../venv/bin/python -m alembic upgrade head
```

Note that `apps/edge` resolves its URL differently (through its settings object, from `URL`);
the two are not interchangeable, which is why both echo the target.
