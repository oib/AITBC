# Exchange

## Status

✅ Operational

## Overview

AITBC Trade Exchange — order matching, price discovery, treasury balance, market offers/orders, and ETH→AIT bridge endpoints. FastAPI app over a SQLite store (monetary columns stored as TEXT/Decimal for exact arithmetic). Runs as the `aitbc-exchange` systemd unit on port 8106 (`User=aitbc`, loopback by default).

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
- Settlement (phase 3, all inert unless `EXCHANGE_SETTLEMENT_ENABLED=true`): `AIT_SELL_ESCROW` and `BRIDGE_ETH_ADDRESS` — both **must be EIP-55 checksummed**; placement refuses 503 when the order's side has an unset/malformed destination, and `/readyz` reports `settlement_envs` while they are. `EXCHANGE_FEE_PCT` (default `0` — the treasury leg is skipped when it floors to zero chain units), `EXCHANGE_PRICE_BAND_PCT`, `EXCHANGE_CANCEL_RATIO`, `EXCHANGE_WATCHLIST_*`, `EXCHANGE_TRUSTED_PROXIES`, `EXCHANGE_CHAIN_ID`. The wallet-side settlement monitor additionally reads `EXCHANGE_INTERNAL_URL` (default `http://127.0.0.1:8106`) for its event posts.

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
│       ├── market.py    # market offers/orders/book
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
GET  /api/orders/orderbook          # order book (buys/sells; rows carry node label, expiry, out_of_band)
POST /api/orders                    # place order — signed envelope when enforcement is on (see below)
GET  /api/trades/recent             # recent trades (buyer/seller node labels + fee_ait)
GET  /api/total-supply              # total supply
GET  /api/treasury-balance          # treasury balance (auth)
GET  /v1/exchange/history           # exchange history
GET  /exchange/price.json           # current price JSON
```

### Signed orders & node registry (ETH-11 phase 2)

Enforcement is controlled by `EXCHANGE_REQUIRE_SIGNED_ORDERS` (default **on**;
set to `false`/`0`/`off` to revert to the pre-phase-2 unsigned `POST /api/orders`
behavior — the phase-2 routes then answer 404). When on:

```http
POST /api/orders                  # signed place — {"envelope": {...}, "signature": "0x...", "user_address": "0x..."}
POST /api/orders/{id}/cancel      # signed cancel by the order's owner
POST /api/exchange/nodes/register # claim a seeded registry row — signed register envelope
GET  /api/exchange/nodes          # participants board (label, short address, status, open_orders, watchlisted)
GET  /api/exchange/my-orders?addr=0x...   # one wallet's orders + next expected account_nonce
```

- **Envelope (place)**: `{side: "BUY"|"SELL", pair: "AIT/ETH", amount_ticks: int,
  price_ticks: int, expiry_height: int, account_nonce: int,
  chain_id: "ait-localnet"}` — ticks are ×10⁸ integer minor units.
- **Envelope (cancel)**: `{action: "exchange_cancel", order_id: int,
  expiry_height: int, account_nonce: int, chain_id}` — `order_id` must equal
  the path id.
- **Envelope (register)**: `{action: "exchange_register", address, label,
  account_nonce, chain_id}` — the label is pinned by the registry seed.
- **Signature**: secp256k1 over `keccak256(canonical_json(envelope))` —
  canonical JSON = sorted keys, compact separators; the repo's bare-digest
  convention (no EIP-191 prefix), the same encoding
  `aitbc.crypto.sign_transaction_data` produces. Verified via
  `aitbc.crypto.signature_recovery.verify_signature`.
- **Auth**: while enforcement is on, the signed envelope is the credential —
  `X-Api-Key` is not required on the three signed writes (a per-node wallet
  signature is strictly stronger than a shared write secret, and nodes never
  see the exchange's key). With the flag off, `POST /api/orders` again
  requires `X-Api-Key` exactly as before.
- **account_nonce** is the exchange-scoped per-address counter
  (`order_nonces`), **not** the chain nonce. GET `my-orders` returns the next
  expected value; a stale or skipped nonce answers 409.
- **Price rule** (decided 14 Oct): an order's `price_ticks` must sit inside the
  oracle AIT/ETH rate ± `EXCHANGE_PRICE_BAND_PCT` (default `0.10`). A stale or
  unavailable feed answers **503**, like the bridge quote endpoint.
- **Registration**: only addresses seeded into `node_registry` can register —
  the signed claim flips `seeded → registered` and only `registered` nodes may
  place orders (`403` otherwise). Phase 2 orders stay **unfunded** and
  settlement-free; `funded_state` is recorded for the phase-3 ledger only.
- **Abuse limits** (design §9): `EXCHANGE_MAX_ORDERS_PER_MIN` (20) per IP and
  per address, `EXCHANGE_MAX_OPEN_PER_NODE` (50), `EXCHANGE_MAX_BOOK_ROWS`
  (5000), `EXCHANGE_MIN_ORDER_AIT` (1), `EXCHANGE_READS_PER_MIN` (60) on the
  read endpoints, `EXCHANGE_REGISTER_PER_MIN` (5), and a cancel-ratio
  watchlist surfaced as `watchlisted` on `GET /api/exchange/nodes` —
  flag-and-log only, it never blocks or throttles an order. Watchlist knobs:
  `EXCHANGE_CANCEL_RATIO` (0.9, strictly-greater edge),
  `EXCHANGE_WATCHLIST_MIN_PLACEMENTS` (10 — a single order+cancel is normal),
  `EXCHANGE_WATCHLIST_WINDOW_S` (86400). Per-IP limits trust `X-Real-IP`
  only when the direct peer is in `EXCHANGE_TRUSTED_PROXIES`
  (default `127.0.0.1,::1` — the nginx hop); a raw spoofed header from an
  untrusted peer is ignored. `EXCHANGE_CHAIN_ID` overrides
  the envelope `chain_id` expectation (default `CHAIN_ID` env or
  `ait-localnet`). `EXCHANGE_FEE_PCT` (default `0`) is recorded on each trade
  row as `fee_ait` — the AIT-leg fee knob, decided 14 Oct; phase 2 moves no
  funds.
- **Cancel/fill races** resolve under the same `BEGIN IMMEDIATE` write lock:
  whoever commits first wins; the loser gets `409`.

### Funded settlement (ETH-19 phase 3, dark)

Everything below is inert unless `EXCHANGE_SETTLEMENT_ENABLED=true`; with the
flag off placement never emits a `funding` block and the monitors idle.

**Funding an order.** A placed order answers with a `funding` block:

- **BUY** (`eth_prepay`): `needed_eth`, `tag=EXCHANGE_DEPOSIT:<your address>`,
  `bridge_eth_address`. Send the ETH **on Sepolia** to the bridge wallet with
  that tag as the tx input data — `aitbc exchange order place` prints the
  instruction when it applies.
- **SELL** (`ait_lock`): `escrow`, `payload=sell_quote=<order id>`,
  `required_ait` (amount + fee). Send a chain `TRANSFER` of at least that
  amount to the escrow account with that payload, **from the order owner's
  wallet** — the settlement monitor credits a lock only when the sender
  (canonicalized) equals the order owner; stranger locks get an
  `order_refund`, never credit.

**The watchers.** `aitbc-bridge-monitor` (the live deposit watcher on hub)
intercepts tagged inflows into `eth_deposits` at status `exchange_prepay` —
terminal, outside the payout vocabulary, never minted; tagged deposits bypass
the dust floor since they owe no payout. The wallet-side deposit monitor
carries the same intercept for hosts where it is the live watcher. The
wallet's exchange-settlement monitor then polls `exchange_prepay` rows and
posts `prepaid_credit` to the exchange (registered nodes only), scans escrow
for order locks (`order_funded`), and drives each trade's three legs: AIT to
the buyer, ETH release to the seller's registered payout address, and the
`EXCHANGE_FEE_PCT` treasury leg — skipped entirely when the fee floors to
zero chain units. Lock remainders at or below the sweep fee are logged and
left in escrow rather than refunded. The three ETH release lanes (withdraw,
sell, exchange) share one nonce-fetch→sign→broadcast lock so two lanes can
never grab the same pending nonce.

**Misconfiguration surfaces early.** Placement under the flag refuses 503
when the side's destination env (`BRIDGE_ETH_ADDRESS` for BUY,
`AIT_SELL_ESCROW` for SELL) is unset, empty, malformed, or not EIP-55
checksummed — refused orders burn no `account_nonce` — and `/readyz` reports
a `settlement_envs` failure while either env is missing. `/readyz` also
verifies the bridge monitor's `eth_deposits` table under `bridge_storage`
when bridge deposits/withdrawals are enabled.

**Rollout order.** `EXCHANGE_SETTLEMENT_ENABLED` is read independently by
**three** units — set it in all three env files:

- the **exchange** (`aitbc-exchange.env`) — placement refusal and the
  `funding` instructions,
- the **bridge-monitor service** (`aitbc-bridge-monitor.env`) — routes
  `EXCHANGE_DEPOSIT:`-tagged inflow to the `exchange_prepay` lane
  (`bridge_monitor/main.py`); flag-off takes the normal deposit lane where
  the tag fails recipient parsing, and a below-floor amount dies on
  `MIN_ETH_DEPOSIT` — this omission is what broke D2,
- the **wallet** (`aitbc-wallet.env`) — the settlement monitor plus the
  wallet-side bridge watcher and sell-escrow monitor, which run the same
  tag routing and gates.

Enable it on the **exchange first**, then the wallet and bridge-monitor. The
pairing is fail-safe either way: a
wallet monitor posting to a flag-off exchange gets 503
(`{"error": "exchange settlement disabled"}`) and retries the lock next poll
(it never reads it as "order gone" and never refunds on it), while an enabled
exchange with a flag-off wallet simply emits `funding` instructions nobody
consumes until the monitor comes up. Before this pairing shipped, a flag-off
exchange answered 404 — indistinguishable from a missing order — and the
monitor refunded live locks; keep that ordering rule (exchange first) as the
documented procedure regardless.

Verify all three units see the name before enabling:

```bash
for u in aitbc-exchange aitbc-bridge-monitor aitbc-wallet; do
    aitbc system env-names --service "$u" | grep EXCHANGE_SETTLEMENT_ENABLED
done
```

**Post-incident audit.** Before reopening the book after a crash or restore:

```bash
venv/bin/python scripts/ops/exchange_verify.py --db /var/lib/aitbc/data/exchange/exchange.db \
    --bridge-db /var/lib/aitbc/data/bridge_deposits.db \
    --bridge-address "$BRIDGE_ETH_ADDRESS" \
    --ait-rpc "$BLOCKCHAIN_RPC_URL" --escrow-address "$AIT_SELL_ESCROW"
```

The verifier is read-only (sqlite `mode=ro`, stdlib, no keys): DB-internal
consistency, bridge-deposit cross-checks, Sepolia settlement legs, and the
escrow lock/sweep history on the chain RPC. Exit 1 on any FAIL; WARN marks
unsealed or still-pending rows. `--no-chain` limits it to DB-internal checks.

The exchange service is intentionally absent from the generated OpenAPI
specs (`scripts/extract_openapi_specs.py` skips it — the catch-all FastAPI
adapter cannot produce useful route schemas); this document is the canonical
API reference.

### Market

```http
GET    /v1/market/offers
POST   /v1/market/offers
GET    /v1/market/offers/{offer_id}
DELETE /v1/market/offers/{offer_id}
POST   /v1/market/offers/{offer_id}/book
GET    /v1/market/orders
DELETE /v1/market/orders/{order_id}
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
