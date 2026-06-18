# Middleware

Reusable FastAPI/ASGI middleware for AITBC services: error handling, request tracing, performance logging, validation, and security headers.

## State

Active. Imported by coordinator-api and other FastAPI-based services.

## Contents

- `__init__.py` — Exports: `ErrorHandlerMiddleware`, `PerformanceLoggingMiddleware`, `RequestIDMiddleware`, `RequestValidationMiddleware`.
- `error_handler.py` — Global exception handling and error response formatting.
- `performance.py` — Request timing and performance metrics.
- `request_id.py` — Correlation ID injection for distributed tracing.
- `validation.py` — Request validation middleware.
- `correlation.py` — Correlation context propagation.

---
*Last updated: 2026-06-18*
