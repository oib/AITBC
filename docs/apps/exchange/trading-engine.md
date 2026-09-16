# Trading Engine

## Status

✅ Operational

## Overview

Trading service for automated and manual trading strategies — offer discovery, trade requests/matches/agreements, inter-chain trades, escrow settlement, and exchange-compatible payment endpoints. FastAPI app in `apps/trading` (package `trading_service`), running as the `aitbc-trading` systemd unit on port 8104 (`User=aitbc`, loopback via `TRADING_BIND_HOST`).

## Quick Start (End Users)

### Prerequisites

- Python 3.13+
- The repo virtualenv (`/opt/aitbc/venv`) — there is no `requirements.txt` under `apps/trading`; dependencies come from the repo environment
- SQLite by default (`DATABASE_URL` → `{DATA_DIR}/data/trading_service.db`); PostgreSQL is supported (`DB_TYPE=postgresql` for Alembic migrations; the unit declares `After=postgresql.service`)
- Redis for gossip broadcast + offer lease tracking (`REDIS_URL`, default `redis://localhost:6379`)
- Access to the blockchain RPC (`BLOCKCHAIN_RPC_URL`)

### Configuration

Environment variables read by `trading_service/config.py` and the systemd unit:

- `TRADING_API_KEY` — API key required on most routers (`X-Api-Key` header)
- `TRADING_BIND_HOST` / `TRADING_BIND_PORT` — bind address (defaults `127.0.0.1:8104`)
- `DATABASE_URL` — SQLAlchemy async URL (SQLite default; `postgresql+asyncpg://` for Postgres)
- `REDIS_URL` — gossip broadcast and lease tracker
- `BLOCKCHAIN_RPC_URL`, `BRIDGE_RPC_URL` — chain RPC endpoints

### Running the Service

```bash
# Via systemd (production path)
systemctl start aitbc-trading.service

# Manually (module entry point; there is no top-level main.py)
cd /opt/aitbc
PYTHONPATH=/opt/aitbc:/opt/aitbc/apps/trading/src venv/bin/python -m trading_service.main
```

## Developer Guide

### Project Structure

```
apps/trading/
├── aitbc-trading.service     # systemd unit
├── aitbc-trading-wrapper.py
├── alembic/                  # DB migrations (env.py, versions/)
├── alembic.ini
├── pyproject.toml
├── examples/
├── scripts/
├── src/trading_service/
│   ├── main.py               # FastAPI app + uvicorn entry
│   ├── config.py             # settings (env-driven)
│   ├── dependencies.py       # require_trading_api_key, webhook signature
│   ├── storage.py            # async engine (DATABASE_URL)
│   ├── domain/               # trading, inter_chain, exchange_payment, base
│   ├── routers/              # system, legacy_trading, transactions,
│   │                         #   exchange_compat, inter_chain, offers,
│   │                         #   subscriptions, settlement
│   └── services/             # trading_service, offer_search_service,
│                             #   gossip_client, lease_tracker
└── tests/
```

### Testing

```bash
cd /opt/aitbc
pytest apps/trading/tests/
```

## API Reference

All routes below are real. Most routers are gated by `require_trading_api_key` (`X-Api-Key` header matching `TRADING_API_KEY`); `/v1/exchange/confirm-payment/{payment_id}` uses a webhook signature instead.

### System (unauthenticated)

```http
GET /health | /ready | /live | /metrics
GET /v1/trading/status
```

### Trading (legacy request/match model)

```http
GET  /v1/trading/requests            GET  /v1/trading/matches        GET  /v1/trading/agreements
POST /v1/trading/requests            POST /v1/trading/matches        POST /v1/trading/agreements
GET  /v1/trading/requests/{id}                                            GET /v1/trading/analytics
```

### Inter-chain trades

```http
GET  /v1/trading/chains                       POST /v1/trading/inter-chain/create
POST /v1/trading/chains/register              GET  /v1/trading/inter-chain
GET  /v1/trading/chains/{id}/health           GET  /v1/trading/inter-chain/history
                                              POST /v1/trading/inter-chain/match-all
GET  /v1/trading/inter-chain/{trade_id}
GET  /v1/trading/inter-chain/{trade_id}/status
POST /v1/trading/inter-chain/{trade_id}/match
```

### Settlement

```http
POST /v1/trading/trades/{trade_id}/lock-escrow
POST /v1/trading/trades/{trade_id}/settle
GET  /v1/trading/trades/{trade_id}/settlement-status
```

### Offers (discovery / subscriptions)

```http
POST /v1/trading/offers/discover
POST /v1/trading/offers/sync            GET /v1/trading/offers/sync-status
GET  /v1/trading/offers/cache           GET /v1/trading/offers/search
POST /v1/trading/offers/subscribe       POST /v1/trading/offers/heartbeat
GET  /v1/trading/offers/subscription-status
```

### Exchange-compatible payments

```http
POST /v1/exchange/create-payment                GET /v1/exchange/rates
GET  /v1/exchange/payment-status/{payment_id}   GET /v1/exchange/market-stats
POST /v1/exchange/confirm-payment/{payment_id}  # webhook signature, not X-Api-Key
GET  /v1/exchange/wallet/balance                GET /v1/exchange/wallet/info
```

### Transactions / blocks / receipts

```http
POST /v1/transactions                GET /v1/blocks
GET  /v1/transactions                GET /v1/blocks/{block_id}
GET  /v1/transactions/{tx_hash}      GET /v1/receipts
GET  /v1/explorer/blocks             GET /v1/explorer/receipts
GET  /v1/explorer/transactions/{tx_hash}
GET  /api/v1/blocks                  (legacy alias)
```

## Removed content

Earlier versions of this page described a generic matching/risk/settlement
engine under `apps/trading-engine` with `main.py` at the app root, a
`requirements.txt`, and `/api/v1/trading/orders|trades|risk|settlement`
routes plus margin/liquidation parameters. That layout and API do not exist;
the shipped service is `apps/trading` with the `/v1/trading/*` and
`/v1/exchange/*` surface above.

## Troubleshooting

**401 on API calls**: set `X-Api-Key` to the configured `TRADING_API_KEY`.

**Trades not settling**: check escrow state via `/v1/trading/trades/{trade_id}/settlement-status` and confirm the blockchain RPC is reachable.

**Offer search empty**: the offer search index (`offer_search_index_url`, default `http://localhost:7700`) and Redis lease tracker must be reachable; check `/v1/trading/offers/sync-status`.

## Security Notes

- `TRADING_API_KEY` gates the trading/offer/settlement routers — set it before exposing the service
- The unit binds `127.0.0.1` by default; only widen `TRADING_BIND_HOST` deliberately
- `POST /v1/exchange/confirm-payment/{id}` authenticates by webhook signature, not the API key
