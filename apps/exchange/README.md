# exchange

## Status

**active**

## Description

AITBC Trade Exchange service — order matching, price discovery, treasury balance, marketplace, and bridge endpoints. Uses FastAPI with SQLite (TEXT-stored Decimal columns for exact monetary arithmetic).

## Node Type

shop

## GPU Required

no

## Service

1 systemd service: `aitbc-exchange.service` (port 8106)

## Core Service

no

## Source

`simple_exchange/` — stdlib HTTP server with handler mixins:
- `simple_exchange/server.py` — entry point
- `simple_exchange/db.py` — SQLite schema (TEXT monetary columns) + auto-migration
- `simple_exchange/handlers/exchange.py` — trading, order matching (B1/B2/B3 fixed)
- `simple_exchange/handlers/marketplace.py` — marketplace offers/orders
- `simple_exchange/handlers/bridge.py` — bridge price/status/deposit/withdraw
- `simple_exchange/handlers/wallet.py` — wallet balance/connect

## Tests

`tests/test_simple_exchange_b1_b2_b3.py` — 14 tests covering Decimal arithmetic, schema migration, order matching atomicity, and connection cleanup.

## Database

SQLite at `/var/lib/aitbc/data/exchange/exchange.db` (configurable via `EXCHANGE_DATABASE_URL`).

---

*Last updated: 2026-07-05*
