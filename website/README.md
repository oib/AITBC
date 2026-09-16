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
| `/rpc/network-info` | Network discovery and join instructions | `aitbc-blockchain-rpc.service` |
| `/agent/openapi.json` | API specification | `aitbc-blockchain-rpc.service` |

No bootstrap files are served (V23-58): `/agent/blockchain.env`, `/agent/genesis.json`
and `/agent/chain.db` all return 404, and nginx denies any `/agent/*` path ending in
`.env` or containing `secret`. On the hub the real `/etc/aitbc/blockchain.env` carries
live consensus keys (`PROPOSER_KEY`, `VALIDATOR_KEYS`), so it must never be aliased.
Chain configuration is provisioned out of band by the hub operator — see
`docs/agent/guides/open-island-joining-guide.md`.

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
# Test network discovery
curl -s https://hub.aitbc.bubuit.net/rpc/network-info | jq .

# Test health check
curl -s https://hub.aitbc.bubuit.net/health

# Bootstrap and secrets files must all return 404 — serving any of them would
# leak cluster credentials or consensus keys (V23-58)
curl -s -o /dev/null -w '%{http_code}\n' https://hub.aitbc.bubuit.net/agent/blockchain.env
curl -s -o /dev/null -w '%{http_code}\n' https://hub.aitbc.bubuit.net/agent/genesis.json
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
