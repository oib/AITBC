# AITBC Website

Production website for the AITBC platform, providing both human-readable pages and machine-readable agent discovery endpoints.

## Deployment

Deployed in the AITBC Incus container:

| | |
|---|---|
| **Domain** | hub.aitbc.bubuit.net |
| **Nginx Config** | `/etc/nginx/sites-enabled/aitbc` |

## File Structure

```
website/
├── index.html              # Homepage — platform overview
├── explorer.html           # Blockchain explorer UI (NEW)
├── exchange.html           # ETH-AIT Bridge and token pricing
├── favicon.svg             # Site favicon (symlink to AITBC.svg)
├── AITBC.svg               # Logo
├── style.css               # Main stylesheet
├── exchange-price.json     # Price data for exchange page
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
| `/rpc/subscribe/ws` | WebSocket for real-time updates |

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
curl -s https://hub.aitbc.bubuit.net/agent/bootstrap.env
curl -s https://hub.aitbc.bubuit.net/agent/genesis.json | jq .
curl -s -X POST https://hub.aitbc.bubuit.net/rpc/join \
  -H 'Content-Type: application/json' -d '{"node_id":"test-node-1"}'

# Test network discovery
curl -s https://hub.aitbc.bubuit.net/rpc/network-info | jq .

# Test health check
curl -s https://hub.aitbc.bubuit.net/health

# Real env and secrets files must still return 404 — serving them would leak
# cluster credentials or consensus keys (V23-58)
curl -s -o /dev/null -w '%{http_code}\n' https://hub.aitbc.bubuit.net/agent/blockchain.env
curl -s -o /dev/null -w '%{http_code}\n' https://hub.aitbc.bubuit.net/agent/blockchain-secrets.env
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
