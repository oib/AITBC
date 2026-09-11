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
| `/agent/blockchain.env` | Public blockchain config | `/etc/aitbc/blockchain.env` |
| `/agent/genesis.json` | Chain genesis block | `/etc/aitbc/genesis.json` |
| `/rpc/network-info` | Network discovery and join instructions | `aitbc-blockchain-rpc.service` |
| `/agent/openapi.json` | API specification | `aitbc-blockchain-rpc.service` |

`blockchain-secrets.env` is deliberately **not** published (V23-58). It holds live
credentials, and no node needs it to follow the chain.

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
# Test public bootstrap
curl -s https://hub.aitbc.bubuit.net/agent/blockchain.env
curl -s https://hub.aitbc.bubuit.net/agent/genesis.json

# Test network discovery
curl -s https://hub.aitbc.bubuit.net/rpc/network-info | jq .

# Test health check
curl -s https://hub.aitbc.bubuit.net/health

# Must return 404 -- publishing this would leak cluster credentials (V23-58)
curl -s -o /dev/null -w '%{http_code}\n' https://hub.aitbc.bubuit.net/agent/blockchain-secrets.env

# Check CORS headers
curl -I https://hub.aitbc.bubuit.net/agent/blockchain.env
```

## Security Notes

1. **CORS**: All `/agent/` and `/rpc/` endpoints have `Access-Control-Allow-Origin: *` for agent access
2. **Static files**: No sensitive data in JSON files (only public network info)
3. **Env files**: Served from `/etc/aitbc/` with proper permissions
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
