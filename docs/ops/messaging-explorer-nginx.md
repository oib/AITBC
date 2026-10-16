# Rate-limiting the explorer messaging read surface — nginx limit

Status: **applied on hub 16 Oct 2026** — the three exact-match locations and
the shared `messaging_rpc` zone are live; verified `429` on burst across both
surfaces. Companion to
`docs/ops/messaging-nginx-limits.md`, which covers the `/rpc/messaging/*`
locations — this document covers the MSG-4 read proxies.

## What MSG-4 adds

`apps/blockchain-explorer` gains three read-only routes that proxy the chain
RPC's messaging index through the existing `/explorer-api/` location:

- `GET /api/messages/state`
- `GET /api/messages/topics?limit&offset`
- `GET /api/messages?topic&limit&offset&cursor`

Bounds mirror upstream (`limit` clamps to 1..100, `offset` rejects >500;
cursors are validated upstream). `website/messages.html` consumes them.

## Current exposure

`/explorer-api/` proxies to `blockchain_explorer` with no `limit_req` and no
in-app rate limiter on the new routes — the upstream RPC keeps its own
200 req/60 s per-client limiter, so a flood through the explorer still
terminates at the chain layer. The unprotected segment is explorer itself:
an unbounded client fans requests into one upstream connection pool.

## Config (applied on hub 16 Oct 2026)

Reuse the zone defined in `docs/ops/messaging-nginx-limits.md` rather than
introducing a second one — the same client abusing either surface is the
same `$binary_remote_addr` key:

```nginx
# http context, deployed as /etc/nginx/conf.d/aitbc-messaging-limits.conf:
# limit_req_zone $binary_remote_addr zone=messaging_rpc:10m rate=5r/s;

# inside the server block, BEFORE the generic /explorer-api/ location
# (longest-prefix wins, so order in the file does not matter, but keep it
# adjacent for readability):
location = /explorer-api/api/messages { limit_req zone=messaging_rpc burst=20 nodelay; limit_req_status 429;
    proxy_pass http://blockchain_explorer;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    add_header Access-Control-Allow-Origin * always;
    add_header Access-Control-Allow-Methods "GET, POST, OPTIONS" always;
    add_header Access-Control-Allow-Headers "Content-Type, Accept" always;
}
location = /explorer-api/api/messages/topics { limit_req zone=messaging_rpc burst=20 nodelay; limit_req_status 429;
    proxy_pass http://blockchain_explorer;
    # same headers as above
}
location = /explorer-api/api/messages/state { limit_req zone=messaging_rpc burst=20 nodelay; limit_req_status 429;
    proxy_pass http://blockchain_explorer;
    # same headers as above
}
```

Exact-match `location =` is deliberate: the rest of `/explorer-api/` keeps
its existing, wider allowance — only the new unbounded-read routes take the
messaging zone.

A shared `limit_req` zone across both surfaces means a client at 200/60 s on
`/rpc/messaging/` has already exhausted budget for `/explorer-api/api/messages/`
— that is intended: one abusive key, one bucket.
