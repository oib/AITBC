# Explorer read-API rate limit — nginx limit_req

Status: **applied on hub 6 Nov 2026** — `explorer_api` zone live; verified
429s on burst through `https://hub.aitbc.bubuit.net/explorer-api/`.
Closes the nginx layer of PI-EX-001 (#1176) and is part of the
PI-API-001 (#1177) hub-side rollout.

## What it covers

The generic `location /explorer-api/` proxies every explorer read route —
blocks, transaction search, analytics, alerts, advanced search — to
`blockchain_explorer`. Before this change only the three
`/api/messages*` exact locations had `limit_req` (the `messaging_rpc`
zone); the rest of the surface had no nginx-layer throttle.

```nginx
# http context, deployed as /etc/nginx/conf.d/aitbc-explorer-limits.conf:
limit_req_zone $binary_remote_addr zone=explorer_api:10m rate=10r/s;

# inside the server block:
location /explorer-api/ {
    limit_req zone=explorer_api burst=50 nodelay;
    limit_req_status 429;
    proxy_pass http://blockchain_explorer/;
    # ...unchanged proxy headers...
}
```

## Keying

`$binary_remote_addr` is evaluated **after** nginx realip resolution:
the vhost trusts the edge (`set_real_ip_from` + `real_ip_header
X-Real-IP`, recursive) so the bucket is the real client asserted by the
trusted edge — not a client-supplied `X-Forwarded-For`/`X-Real-IP` value.
End-to-end spoof-resistance also depends on the edge vhost setting
`X-Real-IP` correctly (#1193).

## Rate rationale

`rate=10r/s` per client IP with `burst=50 nodelay`: generous for normal
explorer browsing (a page fires a handful of API reads) while bounding an
anonymous flood to ~36k req/h per IP. The application-side clamps from
PI-EX-001 (`limit` ≤ 200, `offset` ≤ 10000, `days` ≤ 365) remain the
correctness bound; this zone is the availability bound. Revisit if
legitimate NAT'd browsing trips 429s.

## Related

- `docs/ops/messaging-explorer-nginx.md` — the messaging_rpc exact-match
  locations that remain on their own zone.
- `docs/ops/messaging-nginx-limits.md` — the `/rpc/messaging/*` surface.
- `examples/nginx/nginx-aitbc.conf.example` — reference vhost.
