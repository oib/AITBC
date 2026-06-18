# shared-core

## Status

**shared library**

## Description

Poetry package providing shared core utilities for AITBC microservices: `ServiceSettings` (Pydantic base settings), `DatabaseConfig` (SQLAlchemy/SQLModel base), and security helpers. Used as a dependency by apps (e.g., `agent-management`). Installed via `poetry add ../../shared-core`, not deployed as a standalone service.

Depends on the root `aitbc` package (`{path = "../../../"}`).

## Node Type

n/a

## GPU Required

no

## Service

No systemd service file — imported as a library by other apps.

## Core Service

no

## Source

`src/` directory with 6 Python file(s)

---
*Last updated: 2026-06-17*
