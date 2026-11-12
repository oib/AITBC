# API Key Management

This guide covers how AITBC service API keys are actually generated, stored,
and revoked — the shared implementation is `aitbc/auth/api_key.py`
(`APIKeyManager`).

## Key generation

Keys are minted by `APIKeyManager.generate_api_key(user_id, permissions=None)`
— `secrets.token_urlsafe(32)` (~43 chars), **not** a custom `aitbc_` prefix:

```python
from aitbc.auth.api_key import get_api_key_manager

result = get_api_key_manager().generate_api_key("svc-name", permissions=["read"])
# result["api_key"] is the plaintext — shown once, never persisted
```

## Key storage

- Plaintext keys are **never persisted**. The store keeps only the SHA-256
  digest of each key.
- Digests live in `API_KEY_STORAGE_PATH` (default
  `/var/lib/aitbc/api_keys.json`, mode `0600`), protected by a
  `<storage>.lock` file lock and written atomically — a truncated write
  cannot erase the store (APIKEY-STORE-ATOMIC-1).
- Each entry records `user_id`, `permissions`, `created_at`, `last_used`,
  and `usage_count`.
- Service-to-service keys used by callers (e.g. `BLOCKCHAIN_RPC_API_KEY`,
  market `api_key`) are **env vars** in `/etc/aitbc/*.env` (mode `0600`),
  loaded via systemd `EnvironmentFile=` — a different mechanism from the
  digest store. The digest store is for keys the *services issue to
  callers*; env keys are the ones services *present*.

## Validation and revocation

```python
mgr = get_api_key_manager()
mgr.validate_api_key(key)   # -> {"status": "success", "valid": True, ...}
mgr.revoke_api_key(key)     # removes the digest; key stops working
```

There is no `update_api_key`/`invalidate_api_key` — rotation is
revoke-old + generate-new. Usage stats (`last_used`, `usage_count`) flush
periodically; treat them as approximate.

## Operational notes

- `APIKeyAuthenticator` (the FastAPI dependency most services use) compares
  the presented `X-Api-Key` header against the service's configured
  `api_key` env value with `hmac.compare_digest` — it does **not** consult
  the digest store. The digest store backs `aitbc.auth` login/API flows.
- When a service's `auth_enabled` setting is false the authenticator is a
  no-op; when `api_key` is unset, gated routes return `501`.
- Rotate env keys by editing the env file and restarting the unit
  (`systemctl restart <unit>`); rotate issued keys via
  `revoke_api_key` + `generate_api_key`.

## Caller-to-object binding model (#1883)

Service API keys authenticate the *caller tier*, not the *object*. Whether a
key may act on a given row depends on which tier it belongs to:

| Key | Tier | Binding rule |
|-----|------|--------------|
| `MARKET_API_KEY` (`X-Api-Key`, market :8102) | **user-facing** — distributed to `aitbc market` CLI users | Party mutations need a wallet signature naming the job party / buyer / offer provider, **or** `MARKET_OPERATOR_API_KEY` (#1893). |
| `MARKET_OPERATOR_API_KEY` | operator/service | Full operator tier: dispute resolution, sweeper flows, unsigned party routes. Must differ from `MARKET_API_KEY`; unset ⇒ operator tier closed. |
| `TRADING_API_KEY` (`X-Trading-Api-Key`, trading :8104) | **service-to-service** — node-local `/etc/aitbc/aitbc-trading.env`, no user distribution path | No per-object principal exists at this tier by design: trades are created by services, `settle` is bound by the HTLC secret in the request body, and `lock-escrow`/`cancel`/`match` act on service-created rows whose sender/recipient come from the stored trade, never the request. |
| `EXCHANGE_API_KEY` (`X-Api-Key`, exchange) | **service/internal** — order placement is bound per-object | `EXCHANGE_REQUIRE_SIGNED_ORDERS` (default on) requires a registered node's secp256k1 signature over the order envelope; the legacy unsigned `user_address` path exists only as an explicit revert flag. |

### Documented residuals

- **Market creation routes** (`POST /v1/market/jobs`, `/v1/market/offers`)
  still accept self-asserted `buyer_address`/`provider_address` under the
  user key. Bounded: payment rows are always created `status="pending"`
  (caller-set escrow state was removed in #815), and every money-moving
  follow-up (cancel/dispute/release/refund/book/offer-cancel) now requires
  the named party's signature or the operator key, so a fabricated row
  cannot move funds. Binding creation to a signature is a follow-up if
  job/offer spam becomes a problem.
- **Exchange address-keyed reads** (`/api/exchange/my-orders?addr=`,
  `/api/wallet/connect`) are tracked under #1895 — authentication of the
  read surface, not object binding.
- **Trading cancel/match** on inter-chain trades remain service-key only;
  there is no user principal at this tier. If trading ever exposes
  user-facing routes, this row's decision must be revisited.

## Public financial-read surfaces (#1885)

Per-address financial metadata reads were audited for enumerable
disclosure. Decision: **intended-public where the data derives from public
chain state; operator-only where it enumerates the ledger index.**

| Surface | Decision | Enforcement |
|---------|----------|-------------|
| `GET /v1/bridge/deposits`, `GET /v1/bridge/withdrawals` (wallet bridge) | operator-only | No app-level auth by design — the enumerable indexes are restricted to loopback in nginx (`examples/nginx/nginx-aitbc.conf.example`, `location ~ ^/v1/bridge/(deposits\|withdrawals)`). Per-tx-hash and per-recipient lookups (`/deposit/{tx_hash}`, `/deposit/by-recipient/{address}`, `/withdraw/{ait_tx_hash}`) stay public: they require already knowing the lookup key, matching the publicness of the underlying chain data. |
| `GET /v1/market/orders?wallet=` (exchange) | intended-public | The unfiltered order list is the public order book and already returns each order's `wallet`; the `wallet=` filter only narrows public data. |
| `GET /api/exchange/my-orders?addr=` | intended-public | Returns the address's orders (public book rows), `next_nonce`, and unfunded-order funding instructions — all reconstructible from public chain/exchange state; the signed-order phase-2 flow needs no secrecy here. |
| `POST /api/wallet/connect` | gated | Requires `EXCHANGE_API_KEY`; only confirms wallet existence via the wallet service. |
| `DELETE /v1/market/orders/{id}?wallet=`, `DELETE /v1/market/offers/{id}?wallet=` | **residual** | API-key + self-asserted `wallet` query param — any key holder can cancel any wallet's order/offer. The simple-exchange market surface has no per-object signature scheme; tracked as a binding follow-up, not a read-disclosure issue. |

## See also

- [Security overview](SECURITY.md) — the consolidated page that replaced the generic checklists
- [Security architecture](2_security-architecture.md) — where keys are checked per route
