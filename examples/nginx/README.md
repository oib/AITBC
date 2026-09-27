# nginx configuration examples

Two layers of nginx, two kinds of examples:

```
Internet → EDGE HOST :443 (TLS terminator, plain pass-through)
         → CONTAINER :80 (routing, auth, real-ip restore)
         → services (uvicorn, etc.)
```

## Which file do I need?

| File | Layer | Role |
|---|---|---|
| `nginx-aitbc.conf.example` | container | inner vhost — full route map, real-ip rules, per-service upstreams |
| `nginx-hub-proxy.conf.example` | edge host | `BLOCKCHAIN_MODE=hub` (proposer; also serves agent/coordinator/market APIs) |
| `nginx-shop-proxy.conf.example` | edge host | `MARKET_ROLE=shop` (GPU provider: ollama/whisper/ffmpeg/hermes) |
| `nginx-customer-proxy.conf.example` | edge host | `MARKET_ROLE=customer` follower |

`setup.sh` / `update.sh` pick the proxy example automatically from the role
configured in `aitbc-frontend.env` (`FRONTEND_NGINX_MODE`).

## Edge (host) proxy rules

1. **TLS terminates here** — the container receives plain HTTP. Deploy certs
   with `certbot --nginx -d YOUR_DOMAIN`.
2. **Extended timeouts on long-lived paths** — the default
   `proxy_read_timeout` (~60 s) tears down idle WebSocket/SSE connections.
   `3600s` on `/rpc/subscribe/ws`, `/rpc/gossip/ws`, `/agent/` (hub) and the
   shop's `/ollama/` + `/api/` (600 s) is verified live.
3. **Forward the real client IP** — `X-Real-IP` + `X-Forwarded-For`. Inside
   the container, `set_real_ip_from <edge bridge IP>` + `real_ip_header
   X-Forwarded-For` restores it for logs and per-IP rate limits. The
   container must trust ONLY its own edge's bridge IP.
4. **The edge is a dumb pipe** — route auth, exposure decisions and static
   files live in the container's nginx. Do not duplicate per-path routing at
   the edge except for timeout/streaming overrides.
5. **`Connection $connection_upgrade`, not `"upgrade"`** — the examples use
   the mapped variable so plain requests do not get a spurious
   `Connection: upgrade` header. Add the map once per edge host in
   `/etc/nginx/conf.d/websocket-upgrade.conf` (snippet is in each example's
   header comment).

## Sanitization

These examples are scrubbed for the public repo: replace `YOUR_DOMAIN` and
`CONTAINER_IP` when deploying. Do not commit real hostnames, IPs, tokens or
certificate paths.
