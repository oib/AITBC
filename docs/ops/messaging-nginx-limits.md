# Rate-limiting the messaging RPC surface — nginx limit

Status: **applied on hub 16 Oct 2026** (zone + both `/rpc/messaging/`-family
locations, deployed as `/etc/nginx/conf.d/aitbc-messaging-limits.conf`;
explorer-api side applied the same day — see the companion document).
This document records the MSG-FIX-1 F4 verification findings and the
nginx-layer limit now live for the messaging read endpoints.

Follower exposure resolved 16 Oct (FOLLOWER-RPC-5 / FOLLOWER-RPC-6):
node0, node1, node2 and hub1 all bind `127.0.0.1:8202`, so nginx is the
only ingress on every host — the `0.0.0.0`-bind bypass caveat below no
longer applies anywhere in the fleet.

## What is already in place

Every messaging read endpoint carries an in-app per-client rate limit:

- `aitbc_chain/rpc/messaging.py` and `aitbc_chain/rpc/routers/messaging.py`
  decorate each handler with `@rate_limit(rate=200, per=60)` — 200
  requests per 60 s keyed on the client IP.
- `aitbc/rate_limiting.py::_client_ip_for_rate_limit` resolves the key as:
  1. `X-Real-IP` header (first entry), if present;
  2. else the **rightmost** entry of `X-Forwarded-For`;
  3. else the ASGI peer (`request.client.host`).

Rightmost-XFF is the correct choice: it is the value the nearest trusted
proxy appended, so entries a client prepended further left cannot move
their key. The hub's nginx sets `proxy_set_header X-Real-IP $remote_addr`
and `X-Forwarded-For $proxy_add_x_forwarded_for`, so behind nginx both
inputs are trustworthy.

## Public-exposure caveat (verified live, 15 Oct 2026)

The in-app limiter is only trustworthy when requests arrive **through
nginx** (or when the socket is loopback-only). Verified fleet state
(after FOLLOWER-RPC-5, 16 Oct 2026):

| host | RPC socket | XFF/X-Real-IP trustworthy? |
|---|---|---|
| hub (proposer, customer-facing) | `127.0.0.1:8202` | yes — nginx-only path; nginx overwrites `X-Real-IP` and appends XFF |
| node0, node1, node2 | `127.0.0.1:8202` | yes — every request enters via the follower's own nginx on `:80`, which overwrites `X-Real-IP`/`X-Forwarded-For`; direct `:8202` is refused |
| hub1 | `127.0.0.1:8202` | yes — every request enters via its nginx on `:80` (FOLLOWER-RPC-6, 16 Oct; bind set in `node.env`; direct `:8202` refused, verified from `192.168.100.1`) |

Concretely, on a `0.0.0.0` bind:

- A client can send `X-Real-IP: <fresh value>` per request and never trip
  the 200/60s bucket — the first-header preference makes this the cheapest
  spoof.
- Without `X-Real-IP`, a spoofed XFF rightmost entry does the same.
- Uvicorn runs with `--proxy-headers`, so even the `request.client.host`
  fallback trusts a spoofed XFF.

As of 16 Oct no `0.0.0.0` bind remains on `:8202` anywhere in the fleet,
so this caveat is closed. It is kept here as the reasoning behind the
bind change. The durable fixes, in preference order:

1. **Bind loopback where nginx fronts the service**
   (`RPC_BIND_HOST=127.0.0.1` in the env file the rpc unit reads —
   `blockchain.env` on the followers, which overrides the unit's
   `Environment=` value) and let nginx be the only ingress. On hub and on
   node0/node1/node2 this is now the live state: their nginx on `:80`
   proxies `/rpc/` (including `/rpc/gossip/ws` with Upgrade headers) to
   `127.0.0.1:8202`, and peer gossip URLs were repointed from
   `ws://<lan-ip>:8202/...` to `ws://<lan-ip>/...` beforehand so no peer
   link was lost.
2. **Firewall `:8202`** so only localhost (and explicitly peered services)
   can connect.
3. If a follower must expose the RPC directly, deploy the nginx limit
   below on the public path **and** treat the in-app limiter as best-effort
   there.

Companion document: [messaging-explorer-nginx.md](messaging-explorer-nginx.md)
applies the same zone to the MSG-4 explorer proxies
(`/explorer-api/api/messages*`).

## nginx limit (applied on hub 16 Oct 2026)

Two zones keyed on `$binary_remote_addr`, applied to the messaging read
locations. Rates are above the in-app limit (200/60s ≈ 3.33 r/s) so nginx
absorbs burst floods while the app limiter remains the normal control:

```nginx
# http context (e.g. /etc/nginx/conf.d/messaging-limits.conf or the
# server http block — not inside a location):
limit_req_zone $binary_remote_addr zone=messaging_rpc:10m rate=5r/s;

# inside the server block:
location /rpc/messaging/ {
    limit_req zone=messaging_rpc burst=20 nodelay;
    limit_req_status 429;
    proxy_pass http://127.0.0.1:8202;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}

location /rpc/contracts/messaging/ {
    limit_req zone=messaging_rpc burst=20 nodelay;
    limit_req_status 429;
    proxy_pass http://127.0.0.1:8202;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

Notes:

- One shared zone for both prefixes keeps the 10 MB zone small
  (`$binary_remote_addr` is ~64 B/state; ~160k clients fit).
- `burst=20 nodelay` allows page-load bursts (the forum UI fires several
  messaging calls at once) while `nodelay` rejects rather than queues
  sustained abuse.
- Where the live config already proxies these prefixes inside a larger
  `location /rpc/` block, add the two `limit_req` lines to that block or
  split the prefixes out — a `location` can only match one, and the more
  specific prefix wins.
- `proxy_set_header X-Real-IP $remote_addr` **must** stay — it is what
  makes the in-app limiter's first-preference header trustworthy.

## What the apply changed on a live node

Applying this limit required `nginx -t` + `systemctl reload nginx`
(operator-named). It changes no consensus, state, or RPC behaviour: only
requests beyond `rate=5r/s + burst=20` on the two messaging prefixes get
`429` earlier, at the edge. The in-app 200/60s limiter continues to apply
underneath.
