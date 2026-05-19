# AITBC Agent-First Website Deployment

This directory contains an **agent-first website** that provides machine-readable discovery endpoints for autonomous agents.

## Quick Start

### 1. Serve Directly from Repository

The website is designed to be served directly from this repository location:

```bash
# Using Python (development)
cd /opt/aitbc/website
python3 -m http.server 8080

# Using nginx (production) - see nginx-example.conf
sudo cp nginx-example.conf /etc/nginx/sites-available/aitbc-agent
sudo ln -s /etc/nginx/sites-available/aitbc-agent /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 2. Configure Node-Specific Settings

Edit the JSON files to match your node's role:

**For aitbc (Mainnet Hub):**
- `agent/discovery.json` - Already configured for mainnet
- `agent/islands.json` - Shows ait-mainnet-island only
- `agent/chains.json` - Shows ait-mainnet only
- Remove `agent/join/ait-testnet.json` if present

**For aitbc1 (Testnet Hub):**
- `agent/discovery.json` - Update to testnet configuration
- `agent/islands.json` - Update to show ait-testnet-island
- `agent/chains.json` - Update to show ait-testnet
- Remove `agent/join/ait-mainnet.json`

### 3. Enable Live API (Optional but Recommended)

The live API provides real-time data from the blockchain RPC:

```bash
# Install systemd service
sudo cp systemd-example.service /etc/systemd/system/aitbc-agent-live-api.service

# Edit to match your node configuration
sudo systemctl edit aitbc-agent-live-api.service

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable aitbc-agent-live-api
sudo systemctl start aitbc-agent-live-api
```

## Directory Structure

```
website/
├── index.html              # Agent landing page (human-readable)
├── DEPLOYMENT.md           # This file
├── nginx-example.conf      # Example nginx configuration
├── systemd-example.service # Example systemd service
├── agent/                  # Machine-readable endpoints
│   ├── index.html          # Agent API documentation
│   ├── discovery.json      # Network discovery (static)
│   ├── islands.json      # Island config (static)
│   ├── chains.json       # Chain config (static)
│   ├── openapi.json      # API specification
│   ├── live_api.py       # Live API service (dynamic)
│   ├── health            # Health check
│   └── join/             # Join instructions
│       ├── ait-mainnet.json
│       └── ait-testnet.json
└── assets/               # Static assets (minimal)
```

## Endpoints

### Static Endpoints (Fast, Cached)

| Endpoint | Description | Cache |
|----------|-------------|-------|
| `/agent/discovery.json` | Network topology | 60s |
| `/agent/islands.json` | Island configuration | 30s |
| `/agent/chains.json` | Chain configuration | 60s |
| `/agent/join/*.json` | Join instructions | 1h |

### Live Endpoints (Real-Time, Requires live_api.py)

| Endpoint | Description | Cache |
|----------|-------------|-------|
| `/agent/live/discovery.json` | Real-time discovery | No cache |
| `/agent/live/islands.json` | Live island data | No cache |
| `/agent/live/chains.json` | Live chain data | No cache |
| `/agent/live/health` | Real-time health | No cache |

### RPC Endpoints (Blockchain Access)

| Endpoint | Description |
|----------|-------------|
| `/rpc/head` | Current block height |
| `/rpc/info` | Chain information |
| `/rpc/islands` | Island memberships |

## Node Configuration

### Mainnet Hub (aitbc)

```json
// agent/discovery.json
"this_node": {
  "node_id": "aitbc",
  "role": "hub",
  "chains": ["ait-mainnet"],
  "island_memberships": ["ait-mainnet-island"]
}
```

### Testnet Hub (aitbc1)

```json
// agent/discovery.json
"this_node": {
  "node_id": "aitbc1",
  "role": "hub",
  "chains": ["ait-testnet"],
  "island_memberships": ["ait-testnet-island"]
}
```

## Testing

```bash
# Test static endpoint
curl -s http://localhost/agent/discovery.json | jq .

# Test live endpoint (if live_api.py is running)
curl -s http://localhost/agent/live/islands.json | jq .

# Test RPC endpoint
curl -s http://localhost/rpc/head | jq .

# Check CORS headers
curl -I http://localhost/agent/discovery.json
```

## Security Notes

1. **CORS**: All `/agent/` and `/rpc/` endpoints have `Access-Control-Allow-Origin: *` for agent access
2. **Static files**: No sensitive data in JSON files (only public network info)
3. **Live API**: Runs on localhost only (127.0.0.1:8080), proxied by nginx
4. **No auth**: Discovery endpoints are public by design

## Troubleshooting

**Live API not responding:**
```bash
# Check service status
sudo systemctl status aitbc-agent-live-api

# Check logs
sudo journalctl -u aitbc-agent-live-api -f

# Test directly
curl http://127.0.0.1:8080/agent/live/health
```

**Nginx config errors:**
```bash
# Test configuration
sudo nginx -t

# Check error logs
sudo tail -f /var/log/nginx/error.log
```

**JSON files not updating:**
- Static files are cached - edit directly in `/opt/aitbc/website/agent/`
- For live data, ensure `live_api.py` is running
- Check file permissions: `sudo chown -R www-data:www-data /opt/aitbc/website/`

## Git Workflow

Since the website is served directly from the repo:

```bash
# Edit files
cd /opt/aitbc/website
vim agent/discovery.json

# Test locally
python3 -m http.server 8080

# Commit changes
git add .
git commit -m "Update discovery for mainnet hub"
git push

# Changes are live immediately (no deploy needed)
```

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Autonomous    │────▶│  Nginx (80/443) │────▶│  Static JSON    │
│   Agent         │     │                 │     │  (discovery)    │
└─────────────────┘     │  ┌───────────┐  │     └─────────────────┘
                        │  │ /agent/*  │  │
                        │  │ /rpc/*    │  │     ┌─────────────────┐
                        │  └─────┬─────┘  │────▶│  Live API       │
                        │        │         │     │  (port 8080)    │
                        │        └────┬────┘     └─────┬───────────┘
                        │             │                │
                        └─────────────┘                │
                                                       ▼
                                              ┌─────────────────┐
                                              │  Blockchain RPC │
                                              │  (port 8006)    │
                                              └─────────────────┘
```

## Support

- Repository: https://github.com/oib/AITBC
- Documentation: `/agent/index.html` (served at `http://your-node/agent/`)
