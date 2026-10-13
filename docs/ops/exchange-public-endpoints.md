# Exchange read-only public endpoints (ETH-11)

The exchange service (`simple_exchange`, loopback `127.0.0.1:8106` on the
hub) holds an order book and trade tape used by the public exchange page.
Exactly **two** paths are exposed publicly; everything else the service
serves (`POST /api/orders`, `/api/wallet/balance`, …) stays loopback-only.

## Public surface

| public path (GET only) | upstream | cache | rate |
|---|---|---|---|
| `/exchange-api/orderbook` | `exchange_service/api/orders/orderbook` | 10 s nginx cache, stale-on-error | 60 req/min/IP, burst 10, then 429 |
| `/exchange-api/trades` | `exchange_service/api/trades/recent` | same | same |

- Both locations are `location =` **exact matches** with
  `limit_except GET { deny all; }` — no prefix pass-through, no POST.
- `limit_req_zone` and `proxy_cache_path` live at http level in
  `/etc/nginx/conf.d/aitbc-exchange-api.conf` (reference snippet at the
  bottom of `examples/nginx/nginx-aitbc.conf.example`).
- Cache keys are `$scheme$host$uri` — cookies and auth headers are not
  part of the key; `Set-Cookie` is stripped on the way out. Responses
  carry `Cache-Control: public, max-age=10` and `X-Cache-Status`
  (HIT/MISS) for verification.
- The page (`website/exchange.html` + `website/exchange-book.js`) is
  fetch-only: no POST, no wallet connect, no signing. It renders all
  server strings via `textContent`.

## Why exact-match aliases instead of a prefix

`/api/` on the exchange service is an authenticated/sensitive surface.
A prefix location (`/exchange-api/` → `/api/`) would have published the
whole API. Exact matches publish two handlers and nothing else.

## Verification checklist (post-deploy)

```bash
curl -sI https://hub.aitbc.bubuit.net/exchange-api/orderbook | grep -E 'HTTP|X-Cache'   # 200, MISS→HIT
curl -s https://hub.aitbc.bubuit.net/exchange-api/wallet    # 404 (never routed)
curl -s -X POST https://hub.aitbc.bubuit.net/exchange-api/orderbook  # 405/403
```

Rollback: remove the two `location =` blocks + the conf.d file,
`nginx -t`, `systemctl reload nginx`.
