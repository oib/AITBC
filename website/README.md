# AITBC Website

Production website for the AITBC platform, providing both human-readable pages and machine-readable agent discovery endpoints.

## Deployment

Deployed in the AITBC Incus container:

| | |
|---|---|
| **Domain** | hub.example.net |
| **Nginx Config** | `/etc/nginx/sites-enabled/aitbc` |

## File Structure

```
website/
├── index.html              # Homepage — platform overview + self-serve join form
├── explorer.html           # Blockchain explorer UI
├── blocks.html / block.html / tx.html / search.html  # Explorer detail pages
├── marketplace.html        # Market offers browser
├── exchange.html           # ETH-AIT bridge and token pricing
├── bridges.html            # Bridge transfer listing
├── customer-dashboard.html # Customer dashboard (public view + auth token)
├── shop-dashboard.html     # Shop dashboard (public view + miner key)
├── config.js               # Shared chain_id + explorer API base
├── dashboard.js            # Shared dashboard logic (credential + fetch layer)
├── favicon.svg             # Site favicon (symlink to AITBC.svg)
├── AITBC.svg               # Logo
├── style.css               # Main stylesheet
├── vendor/                 # Vendored third-party assets
└── DEPLOYMENT.md           # Deployment documentation (legacy)
```

## Agent-First Endpoints

The website provides machine-readable discovery endpoints for autonomous agents through the main AITBC infrastructure.

### Static Endpoints (Fast, Cached)

| Endpoint | Description | Source |
|----------|-------------|--------|
| `/health` | Blockchain RPC health | `aitbc-blockchain-rpc.service` |
| `/agent/bootstrap.env` | Sanitized public follower config | `/etc/aitbc/bootstrap.env` (rendered by `scripts/ops/render-bootstrap-env.sh`) |
| `/agent/genesis.json` | Chain genesis block | `/var/lib/aitbc/data/<chain>/genesis.json` |
| `/rpc/join` | Self-serve peer-key issuance (POST, node-bound) | `aitbc-blockchain-rpc.service` |
| `/rpc/network-info` | Network discovery and join instructions | `aitbc-blockchain-rpc.service` |
| `/agent/openapi.json` | API specification | `aitbc-blockchain-rpc.service` |

`/agent/bootstrap.env` is a sanitized allowlist-rendered file — the node's real
`/etc/aitbc/blockchain.env` carries live consensus keys (`PROPOSER_KEY`,
`VALIDATOR_KEYS`) and is never served. nginx still denies every `/agent/*` path
ending in `.env` or containing `secret`; the two public files above are served
through exact-match `location =` blocks, which take precedence over that regex
(V23-58). Peer keys issued by `/rpc/join` are bound to a single `node_id` —
see `docs/ops/peer-keys.md`.

### RPC Endpoints (Blockchain Access)

| Endpoint | Description |
|----------|-------------|
| `/rpc/head` | Current block height |
| `/rpc/info` | Chain information |
| `/rpc/islands` | Island memberships |
| `/rpc/account/{addr}` | Account balance/nonce |
| `/rpc/bridge/transfers` | Bridge transfer listing |
| `/rpc/subscribe/ws` | WebSocket for real-time updates |

### Page Data Endpoints (what the site's JS actually calls)

All anonymous-safe — no credential needed:

| Endpoint | Backend | Used by |
|----------|---------|---------|
| `/explorer-api/api/**` | blockchain-explorer :8100 | explorer, blocks, tx, search, marketplace stats + reputation |
| `/v1/market/offer`, `/v1/market/status`, `/v1/market/jobs`, `/v1/market/analytics` | market :8102 | marketplace + both dashboards |
| `/v1/market/gpu/list` | coordinator :8203 (public in security matrix) | shop dashboard GPU table |
| `/v1/exchange/history`, `/exchange/price.json` | exchange :8106 | exchange page |
| `/v1/bridge/status`, `POST /v1/bridge/deposit`, `/v1/bridge/deposit/{tx_hash}` | wallet :8108 | exchange deposit flow + tracking |
| `/v1/bridge/deposit/by-recipient/{addr}` | wallet :8108 | exchange track-by-address (non-enumerable; the `/v1/bridge/deposits` index is loopback-only) |
| `/c/health` | coordinator :8203 | marketplace health check |

Credential-gated (used only when the operator pastes a credential into the
dashboard field — auto-detected: `eyJ…` → `Authorization: Bearer`,
otherwise `X-Api-Key` miner key):

| Endpoint | Required role | Used by |
|----------|---------------|---------|
| `/v1/jobs` | client/admin JWT | customer dashboard "your account" view |
| `/v1/monitoring/metrics` | any credential | shop dashboard network metrics |
| `POST /v1/miners/{id}/jobs`, `POST /v1/miners/{id}/earnings` | miner key | shop dashboard miner panels |

Aliases: `/dashboard/` → `customer-dashboard.html`, `/shop/` → `shop-dashboard.html`.

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Autonomous    │────▶│  Nginx (80/443) │────▶│  Static HTML    │
│   Agent         │     │                 │     │  (index.html)   │
└─────────────────┘     │  ┌───────────┐  │     └─────────────────┘
                        │  │ /agent/*  │  │
                        │  │ /rpc/*    │  │     ┌─────────────────┐
                        │  └─────┬─────┘  │────▶│  Blockchain RPC │
                        │        │        │     │  (port 8202)    │
                        │        └────┬───┘     └─────────────────┘
                        │             │
                        └─────────────┘
```

## Testing

```bash
# Test public bootstrap + join
curl -s https://hub.example.net/agent/bootstrap.env
curl -s https://hub.example.net/agent/genesis.json | jq .
curl -s -X POST https://hub.example.net/rpc/join \
  -H 'Content-Type: application/json' -d '{"node_id":"test-node-1"}'

# Test network discovery
curl -s https://hub.example.net/rpc/network-info | jq .

# Test health check
curl -s https://hub.example.net/health

# Test the endpoints the site's pages call
curl -s https://hub.example.net/v1/market/jobs?limit=5 | jq .
curl -s https://hub.example.net/v1/market/gpu/list | jq .
curl -s https://hub.example.net/v1/bridge/deposit/by-recipient/0xYourAitAddress | jq .
curl -s https://hub.example.net/dashboard/ -o /dev/null -w '%{http_code}\n'
curl -s https://hub.example.net/shop/ -o /dev/null -w '%{http_code}\n'

# Gated routes still answer 401/403 to anonymous callers
curl -s -o /dev/null -w '%{http_code}\n' https://hub.example.net/v1/jobs
curl -s -o /dev/null -w '%{http_code}\n' https://hub.example.net/v1/bridge/deposits

# Real env and secrets files must still return 404 — serving them would leak
# cluster credentials or consensus keys (V23-58)
curl -s -o /dev/null -w '%{http_code}\n' https://hub.example.net/agent/blockchain.env
curl -s -o /dev/null -w '%{http_code}\n' https://hub.example.net/agent/blockchain-secrets.env
```

## Security Notes

1. **CORS**: `/agent/` and `/rpc/` endpoints have `Access-Control-Allow-Origin: *` for agent access
2. **Static files**: No sensitive data in JSON files (only public network info)
3. **Env files**: Never served — `/etc/aitbc/` env files hold live credentials and consensus keys
4. **No auth**: Discovery endpoints are public by design

## Troubleshooting

**Blockchain RPC / agent endpoints not responding:**
```bash
# Check service status
sudo systemctl status aitbc-blockchain-rpc.service

# Check logs
sudo journalctl -u aitbc-blockchain-rpc.service -f

# Test directly
curl http://127.0.0.1:8202/health
```

**Nginx config errors:**
```bash
# Test configuration
sudo nginx -t

# Check error logs
sudo tail -f /var/log/nginx/error.log

# Reload after changes
sudo systemctl reload nginx
```

## Git Workflow

Since the website is served directly from the repo:

```bash
# Edit files
cd /opt/aitbc/website

# Commit changes
git add .
git commit -m "Update website"
git push

# Changes are live immediately (no deploy needed)
```

## Support

- Repository: https://github.com/oib/AITBC
- Documentation: Agent API documentation is served through the main AITBC infrastructure
