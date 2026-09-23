# Trade Exchange - AITBC Documentation

Ethereum-to-AITBC exchange: ETH deposit requests, payment tracking, and
wallet-based user accounts on the coordinator API.

> **Note:** An earlier version of this document described a public hosted
> exchange at `aitbc.bubuit.net` with a web frontend, `X-Session-Token`
> headers, and `/api/*` routes. That deployment does not exist — the real
> surface is the coordinator-api exchange router plus the standalone
> exchange/bridge service described below.

## Overview

The AITBC Trade Exchange lets users exchange Ethereum for the network
tokens. The backend is split across two services:

- **coordinator-api** (`:8203`) — `/v1/exchange/*` payment requests and
  `/v1/users|auth|login|logout` account/session routes.
- **exchange service** (`:8106`) — order book, trading pairs, wallet
  balances, and the `/v1/bridge/*` deposit/withdrawal surface.

### Key Features

- Ethereum deposit requests with payment-address tracking
- Wallet-based authentication (nonce + signature → JWT)
- Payment status polling with confirmation counts
- Per-user balance and transaction history

## How It Works

1. **Register/login** — `POST /v1/auth/nonce` returns a nonce; the wallet
   signs it; `POST /v1/login` verifies the signature and returns a JWT.
2. **Create a payment request** — `POST /v1/exchange/create-payment`
   returns a `payment_address` and expiry (1 hour).
3. **Send ETH** to the payment address.
4. **Track confirmation** — `GET /v1/exchange/payment-status/{id}` reports
   `confirmations` and `status` (`pending` → `confirmed`).
5. **Tokens credited** on confirmation (admin confirmation is also
   available via `POST /v1/exchange/confirm-payment/{payment_id}`).

## User Management

Authentication is wallet-signature based — no passwords.

### Authentication Flow

- `POST /v1/auth/nonce` issues a single-use nonce for a wallet address
- `POST /v1/login` consumes the nonce, verifies the wallet signature, and
  returns a JWT access token (auto-registers on first login)
- JWT expiry is configured by `JWT_EXPIRATION_HOURS` /
  `JWT_NO_EXPIRATION`; `POST /v1/logout` adds the token to a revocation
  blocklist until its natural expiry

### User Features

- `GET /v1/users/me` — current user profile
- `GET /v1/users/{user_id}/balance` — wallet balance
- `GET /v1/users/{user_id}/transactions` — transaction history
- `POST /v1/register` — explicit registration

## Exchange API

All routes below live on **coordinator-api** (`:8203`).

### User Management Endpoints

`POST /v1/auth/nonce` — request a wallet-signable login nonce
`POST /v1/register` — register with wallet address
`POST /v1/login` — login via wallet-signed nonce → JWT
`GET /v1/users/me` — get current user profile
`GET /v1/users/{user_id}/balance` — get user wallet balance
`POST /v1/logout` — logout and revoke the token (blocklist)

### Exchange Endpoints

`POST /v1/exchange/create-payment` — create Ethereum deposit request
`GET /v1/exchange/payment-status/{payment_id}` — check confirmation status
`POST /v1/exchange/confirm-payment/{payment_id}` — manual confirm
`GET /v1/exchange/rates` — get current exchange rates
`GET /v1/exchange/market-stats` — market statistics

## Security Features

### Authentication Security

- JWT access tokens (HMAC-signed) with optional expiry
- Token revocation blocklist on logout
- Wallet-signature verification for login (nonce challenge)

### Payment Security

- Payment requests carry an expiry (`ETH_CONFIG["payment_timeout"]`, 1 h)
- Confirmation threshold before crediting
  (`ETH_CONFIG["min_confirmations"]`, 12)

## Configuration

### Exchange Settings

The coordinator-api exchange router uses a hardcoded `ETH_CONFIG` dict in
`apps/coordinator-api/.../infrastructure/routers/exchange.py`
(`exchange_rate` 1000, `min_confirmations` 12, `payment_timeout` 3600) —
no env vars feed it.

The standalone exchange/bridge service (`apps/exchange`, `:8106`) reads:

```bash
BRIDGE_FEE_RATE=0.005          # fee fraction on bridge transfers
BRIDGE_ETH_ADDRESS=0x...       # treasury address receiving ETH deposits
MIN_ETH_DEPOSIT=0.001          # minimum ETH deposit
ETH_NETWORK=sepolia            # ethereum network name
BRIDGE_WITHDRAW_ENABLED=false  # withdrawals off unless explicitly enabled

# Auth / integration
EXCHANGE_API_KEY=<key>
EXCHANGE_WEBHOOK_SECRET=<secret>
EXCHANGE_DATABASE_URL=sqlite:///exchange.db
BLOCKCHAIN_RPC_BASE_URL=http://localhost:8202
```

> The previously documented `ETH_TO_AITBC_RATE`, `MIN_CONFIRMATIONS`,
> `PAYMENT_TIMEOUT`, `MIN_PAYMENT`, `MAX_PAYMENT`, `ETHEREUM_NETWORK`, and
> `ETHEREUM_RPC_*` vars are **not read** by any code.

## API Examples

### Create Payment Request

```bash
curl -X POST http://localhost:8203/v1/exchange/create-payment \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <jwt>" \
  -d '{
    "user_id": "my-user",
    "aitbc_amount": 1000,
    "eth_amount": 0.01
  }'
```

Response:

```json
{
  "payment_id": "pay_123456",
  "user_id": "my-user",
  "aitbc_amount": 1000,
  "eth_amount": 0.01,
  "payment_address": "0x0000...",
  "status": "pending",
  "created_at": 1759155000,
  "expires_at": 1759158600
}
```

### Check Payment Status

```bash
curl -X GET http://localhost:8203/v1/exchange/payment-status/pay_123456 \
  -H "Authorization: Bearer <jwt>"
```

Response:

```json
{
  "payment_id": "pay_123456",
  "user_id": "my-user",
  "aitbc_amount": 1000,
  "eth_amount": 0.01,
  "payment_address": "0x0000...",
  "status": "confirmed",
  "created_at": 1759155000,
  "expires_at": 1759158600,
  "confirmations": 12,
  "tx_hash": "0xabc...",
  "confirmed_at": 1759155900
}
```

## Integration Guide

### Python

```python
import requests

class AITBCExchange:
    def __init__(self, base_url="http://localhost:8203"):
        self.base_url = base_url
        self.token = None

    def login(self, wallet_address, sign_fn):
        nonce = requests.post(
            f"{self.base_url}/v1/auth/nonce",
            json={"wallet_address": wallet_address},
        ).json()["nonce"]
        data = requests.post(
            f"{self.base_url}/v1/login",
            json={
                "wallet_address": wallet_address,
                "nonce": nonce,
                "signature": sign_fn(nonce),
            },
        ).json()
        self.token = data["session_token"]
        return data

    def create_payment(self, aitbc_amount, eth_amount):
        return requests.post(
            f"{self.base_url}/v1/exchange/create-payment",
            json={
                "user_id": "my-user",
                "aitbc_amount": aitbc_amount,
                "eth_amount": eth_amount,
            },
            headers={"Authorization": f"Bearer {self.token}"},
        ).json()
```

## Troubleshooting

### Common Issues

1. **Payment not detected**
   - Confirm the ETH transaction was broadcast and reached the payment
     address
   - Check `GET /v1/exchange/payment-status/{id}` for `confirmations`
     against the 12-confirmation threshold
   - Check the request hasn't expired (`expires_at`, 1 h window)

2. **Session expired**
   - Re-run the nonce + login flow to get a fresh JWT
   - `JWT_NO_EXPIRATION=true` disables expiry (dev only)

3. **401 on login**
   - The nonce is single-use — request a fresh `/v1/auth/nonce` per login
   - The signature must be over the exact nonce string

## Rate Limits

`POST /v1/exchange/create-payment` and `POST /v1/login` are limited to 20
requests per minute per caller via `@rate_limit` (see
`aitbc/rate_limiting.py`). Other routes carry their own per-route limits;
there are no per-plan tiers.
