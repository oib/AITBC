# enterprise_integration

> **Unmounted:** the `partners` router is imported but never include_router'd in coordinator_api/main.py — these routes 404. Deliberately unmounted per the comment at main.py:920-923 (DB-backed, no webhook delivery yet).

Enterprise integration — partner onboarding and B2B connectors.

## Domain Models

- None (stub)

## Routes

- POST /partners/register
- GET /partners/{partner_id}
- POST /partners/webhooks
- GET /partners/webhooks
- DELETE /partners/webhooks/{webhook_id}
- GET /partners/analytics/usage

## Services

- None (stub)
