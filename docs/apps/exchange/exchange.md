# Exchange

## Status

✅ Operational

## Overview

AITBC Trade Exchange — order matching, price discovery, treasury balance, marketplace offers/orders, and ETH→AIT bridge endpoints. FastAPI app over a SQLite store (monetary columns stored as TEXT/Decimal for exact arithmetic). Runs as the `aitbc-exchange` systemd unit on port 8106 (`User=aitbc`, loopback by default).

## Quick Start (End Users)

### Prerequisites

- Python 3.13+
- The repo virtualenv (`/opt/aitbc/venv`) — there is **no** `requirements.txt` under `apps/exchange`; dependencies come from the repo environment, with `PYTHONPATH=/opt/aitbc` so `aitbc.*` and `apps.*` imports resolve
- SQLite (built-in; no external database server)
- Access to the blockchain RPC endpoint (`BLOCKCHAIN_RPC_URL`, default `http://localhost:8202`)

### Configuration

Environment is read from the process environment; `apps/exchange/simple_exchange/.env.example` documents the bridge variables and is meant to be copied to `/etc/aitbc/aitbc-exchange.env` on a deployed node (the systemd unit also loads `/etc/aitbc/blockchain.env`, `/etc/aitbc/node.env`, and `/etc/aitbc/%N.env`).

Key variables:

- `EXCHANGE_API_KEY` — required for write endpoints (`POST`/`DELETE`); a missing key fails auth rather than allowing writes
- `EXCHANGE_DATABASE_URL` — SQLite location (default `/var/lib/aitbc/data/exchange/exchange.db`)
- `BLOCKCHAIN_RPC_URL` — blockchain RPC base URL
- `EXCHANGE_HOST` — bind host (systemd sets `127.0.0.1`)
- Bridge: `BRIDGE_ETH_ADDRESS`, `BRIDGE_CONTRACT_ADDRESS`, `BRIDGE_FEE_RATE`, `BRIDGE_DEPOSIT_ENABLED`, `BRIDGE_WITHDRAW_ENABLED`, `BRIDGE_CUSTODIAN_MODE`, `BRIDGE_MULTISIG_*`, `BRIDGE_SAFE_ADDRESS`, `ETH_NETWORK`, `MIN_ETH_DEPOSIT`

### Running the Service

```bash
# Via systemd (production path)
systemctl start aitbc-exchange.service

# Manually, from the repo root
cd /opt/aitbc
PYTHONPATH=/opt/aitbc venv/bin/python -m apps.exchange.simple_exchange.server --host 127.0.0.1 --port 8106
```

`server.py` accepts `--host` (default `0.0.0.0`) and `--port` (default `8106`). There is no `deploy_real_exchange.sh` — the systemd unit is the production launcher.

## Developer Guide

### Project Structure

```
apps/exchange/
├── aitbc-exchange.service    # systemd unit (port 8106)
├── exchange_wrapper.sh       # wrapper script
├── README.md
├── simple_exchange/
│   ├── server.py             # CLI entry point (argparse → uvicorn)
│   ├── main.py               # FastAPI app; adapts requests onto ExchangeAPIHandler
│   ├── config.py             # Bridge/runtime config from env (no secrets)
│   ├── db.py                 # SQLite schema + auto-migration (TEXT money columns)
│   ├── .env.example          # bridge env template
│   └── handlers/
│       ├── base.py           # dispatch, X-Api-Key auth, shared helpers
│       ├── exchange.py       # orders, orderbook, treasury, price, history
│       ├── marketplace.py    # marketplace offers/orders/book
│       ├── bridge.py         # bridge price/status/deposit/withdraw/estimate
│       └── wallet.py         # wallet balance/connect
└── tests/
    ├── test_simple_exchange_b1_b2_b3.py
    ├── test_bridge_withdraw.py
    ├── test_http_contract.py
    └── test_main.py
```

### Testing

```bash
cd /opt/aitbc
pytest apps/exchange/tests/
```

## API Reference

The service dispatches to `ExchangeAPIHandler` (stdlib-style handler under the FastAPI wrapper). Write operations require the `X-Api-Key` header matching `EXCHANGE_API_KEY`.

### Trading

```http
GET  /api/orders/orderbook          # order book (buys/sells)
POST /api/orders                    # place order — {"order_type": "BUY"|"SELL", "amount": "...", "price": "...", "user_address": "0x..."}
GET  /api/trades/recent             # recent trades
GET  /api/total-supply              # total supply
GET  /api/treasury-balance          # treasury balance (auth)
GET  /v1/exchange/history           # exchange history
GET  /exchange/price.json           # current price JSON
```

### Marketplace

```http
GET    /v1/marketplace/offers
POST   /v1/marketplace/offers
GET    /v1/marketplace/offers/{offer_id}
DELETE /v1/marketplace/offers/{offer_id}
POST   /v1/marketplace/offers/{offer_id}/book
GET    /v1/marketplace/orders
DELETE /v1/marketplace/orders/{order_id}
```

### Bridge (ETH → AIT)

```http
GET  /v1/bridge/price
GET  /v1/bridge/status            # and /v1/bridge/status/{id}
GET  /v1/bridge/deposits          # and /v1/bridge/deposit/{id}
POST /v1/bridge/deposit
POST /v1/bridge/withdraw          # disabled by default (BRIDGE_WITHDRAW_ENABLED=false)
POST /v1/bridge/estimate
GET  /v1/cross-chain/rates        # also /cross-chain/rates
```

Deposits run in trusted-custodian mode by default (`BRIDGE_CUSTODIAN_MODE=true`); withdrawals are disabled unless `BRIDGE_WITHDRAW_ENABLED` is set.

### Wallet

```http
GET  /api/wallet/balance?address=0x...   # balance via the wallet service (port 8108)
POST /api/wallet/connect                 # verify a wallet address exists (body: {"address": "0x..."})
```

### Health

```http
GET /health                       # also /api/health
GET /metrics
```

## Removed content

Earlier versions of this page described a different codebase that is not in
the repo: a multi-pair order-management API (`/api/v1/orders`, `/api/v1/ticker`,
`/api/v1/crosschain/transfer`), a `requirements.txt` at `apps/exchange/`, a
`deploy_real_exchange.sh` launcher, an `index.html`/`styles.css` web
interface, and PostgreSQL/Redis requirements (`DATABASE_URL`, `REDIS_URL`).
The shipped service is `apps/exchange/simple_exchange` with the routes listed
above; database is SQLite, and there is no bundled web UI.

## Troubleshooting

**Order not matched**: check order book depth (`GET /api/orders/orderbook`) and that `amount`/`price` are positive decimal strings.

**Deposit issues**: verify `BRIDGE_ETH_ADDRESS`/`BRIDGE_CONTRACT_ADDRESS` and that `BRIDGE_DEPOSIT_ENABLED=true`; withdrawals require `BRIDGE_WITHDRAW_ENABLED=true`.

**401 on writes**: set `X-Api-Key` to the configured `EXCHANGE_API_KEY`.

**Database errors**: check `EXCHANGE_DATABASE_URL` path is writable by the `aitbc` user.

## Security Notes

- `EXCHANGE_API_KEY` gates all write endpoints — set it before exposing the service
- The unit binds `127.0.0.1` by default; only widen `EXCHANGE_HOST` deliberately
- Monetary values are Decimal-as-TEXT; keep it that way in schema changes
