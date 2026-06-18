# AITBC Website

Production website for the AITBC platform, providing both human-readable pages and machine-readable agent discovery endpoints.

## Deployment

Deployed in the AITBC Incus container:

| | |
|---|---|
| **Domain** | hub.aitbc.bubuit.net |
| **Container IP** | 10.1.223.93 |
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
| `/agent/health` | Health check | `aitbc-agent-registry.service` |
| `/agent/discovery.json` | Network topology | `aitbc-agent-registry.service` |
| `/agent/islands.json` | Island configuration | `aitbc-agent-registry.service` |
| `/agent/chains.json` | Chain configuration | `aitbc-agent-registry.service` |
| `/agent/openapi.json` | API specification | `aitbc-agent-registry.service` |
| `/agent/join/` | Join instructions | `aitbc-agent-registry.service` |
| `/agent/blockchain.env` | Public blockchain config | `/etc/aitbc/blockchain.env` |
| `/agent/blockchain-secrets.env` | Shared cluster secrets | `/etc/aitbc/blockchain-secrets.env` |

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
                        │  └─────┬─────┘  │────▶│  Agent Registry │
                        │        │        │     │  (port 8204)    │
                        │        └────┬───┘     └─────┬───────────┘
                        │             │               │
                        └─────────────┘               │
                                                      ▼
                                              ┌─────────────────┐
                                              │  Blockchain RPC │
                                              │  (port 8202)    │
                                              └─────────────────┘
```

## Testing

```bash
# Test static endpoint
curl -s http://localhost/agent/discovery.json | jq .

# Test health check
curl -s http://localhost/agent/health | jq .

# Test env files
curl -s http://localhost/agent/blockchain.env
curl -s http://localhost/agent/blockchain-secrets.env

# Check CORS headers
curl -I http://localhost/agent/discovery.json
```

## Security Notes

1. **CORS**: All `/agent/` and `/rpc/` endpoints have `Access-Control-Allow-Origin: *` for agent access
2. **Static files**: No sensitive data in JSON files (only public network info)
3. **Env files**: Served from `/etc/aitbc/` with proper permissions
4. **No auth**: Discovery endpoints are public by design

## Troubleshooting

**Agent API not responding:**
```bash
# Check service status
sudo systemctl status aitbc-agent-registry.service

# Check logs
sudo journalctl -u aitbc-agent-registry.service -f

# Test directly
curl http://127.0.0.1:8204/agent/health
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
