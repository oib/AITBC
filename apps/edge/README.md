# edge

## Status

**active**

## Description

Edge computing service for offloading compute tasks from the hub to local nodes. Handles task distribution, result collection, and edge-local caching.

## Node Type

island

## GPU Required

**Optional**

## Service

1 systemd service(s): aitbc-edge.service

## Core Service

no

## Source

`src/` directory with 25 Python file(s)

---
*Last updated: 2026-06-17*

## Database migrations

```bash
cd apps/edge && PYTHONPATH=src ../../venv/bin/python -m alembic upgrade head
```

The target database is resolved through `aitbc_edge.config.settings` — the same source the
running service uses, so the two cannot disagree — and **printed to stderr before anything
runs**. Check that line before letting a migration proceed.

**The override variable is `URL`, not `DATABASE_URL`.** `DatabaseConfig` is a `BaseSettings`
with no `env_prefix`, so its `url` field maps to the bare name; `DATABASE_URL` is silently
ignored and the deployed database is used instead. To run against a copy:

```bash
URL=sqlite:///path/to/copy.db PYTHONPATH=src ../../venv/bin/python -m alembic upgrade head
```
