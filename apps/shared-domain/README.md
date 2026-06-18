# shared-domain

## Status

**shared library**

## Description

Poetry package providing shared domain models (SQLModel-based) for AITBC microservices. Used as a dependency by apps (e.g., `agent-management`). Installed via `poetry add ../../shared-domain`, not deployed as a standalone service.

Depends on the root `aitbc` package (`{path = "../../../"}`) and `sqlmodel`.

## Node Type

n/a

## GPU Required

no

## Service

No systemd service file — imported as a library by other apps.

## Core Service

no

## Source

`src/` directory with 1 Python file(s)

---
*Last updated: 2026-06-17*
