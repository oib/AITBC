# Log Utils

Structured logging, middleware, and formatting utilities for the AITBC platform. Replaced `aitbc/logging` to avoid shadowing Python's stdlib `logging` module.

## State

Active. Required by all services that use AITBC's logging infrastructure.

## Contents

- `__init__.py` — Public exports: `StructuredLogFormatter`, `configure_structured_logging`, etc.
- `logging.py` — Core structured logging implementation.
- `middleware.py` — Logging middleware for FastAPI/ASGI applications.
- `structured.py` — JSON structured log formatter.

## History

Renamed from `aitbc/logging/` in v0.4.24 to fix stdlib shadowing (`import logging.handlers` was resolving to `aitbc/logging/__init__.py`).

---
*Last updated: 2026-06-18*
