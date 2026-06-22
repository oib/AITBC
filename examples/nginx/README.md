# AITBC Nginx Examples

Role-specific nginx configurations for AITBC nodes. Each role has a
**container config** (routes to backend services) and a **host proxy
config** (SSL termination + reverse proxy to container).

## Files

### Container configs (run inside the AITBC container)

| File | Role | What it exposes |
|---|---|---|
| `nginx-hub.conf.example` | `BLOCKCHAIN_MODE=hub` | Agent registry, API gateway, blockchain RPC (WS+HTTP), agent coordinator WS, coordinator API, wallet exchange, explorer, website |
| `nginx-shop.conf.example` | `MARKET_ROLE=shop` | Ollama, Whisper, FFmpeg, PeerTube Pruner, explorer |
| `nginx-customer.conf.example` | `MARKET_ROLE=customer` | Explorer, health check |

### Host proxy configs (run on the host machine, SSL termination)

| File | Role | Pairs with |
|---|---|---|
| `nginx-hub-proxy.conf.example` | `BLOCKCHAIN_MODE=hub` | `nginx-hub.conf` |
| `nginx-shop-proxy.conf.example` | `MARKET_ROLE=shop` | `nginx-shop.conf` |
| `nginx-customer-proxy.conf.example` | `MARKET_ROLE=customer` | `nginx-customer.conf` |

## Architecture

```
Internet → Host nginx (SSL termination, nginx-<role>-proxy.conf)
         → Container nginx (role config, nginx-<role>.conf)
            → Backend services (127.0.0.1:8xxx)
```

The **host proxy** terminates SSL and forwards to the container's nginx
on port 80. The **container nginx** routes to individual backend services
on localhost ports.

### Important: nginx is for external traffic only

Nginx exposes services to the **public internet**. Internal service-to-service
communication within a node happens on `localhost` directly and never goes
through nginx. For example:

- `gpu_worker.py` connects to `http://localhost:8203` (coordinator-api) to
  poll for jobs — this does NOT need to be exposed via nginx
- `blockchain-explorer` queries `http://localhost:8202` (blockchain-rpc)
  locally — no nginx needed
- `subscription_client.py` connects to the **hub's** public `/rpc/subscribe`
  (outbound from follower) — the follower's own RPC does not need to be public

This is why `/c/` (coordinator-api) and `/rpc/` (blockchain-rpc) are NOT in
the shop or customer configs, even though those services run locally. They
are only exposed publicly on the **hub** (where external followers and
clients need to reach them).

## Choosing the right config

Check your node's role:

```bash
grep -E "BLOCKCHAIN_MODE|MARKET_ROLE" /etc/aitbc/node.env
```

| `BLOCKCHAIN_MODE` | `MARKET_ROLE` | Container config | Host proxy config |
|---|---|---|---|
| `hub` | customer | `nginx-hub.conf` | `nginx-hub-proxy.conf` |
| `hub` | shop | `nginx-hub.conf` + `nginx-shop.conf` | `nginx-hub-proxy.conf` + `nginx-shop-proxy.conf` |
| `follower` | customer | `nginx-customer.conf` | `nginx-customer-proxy.conf` |
| `follower` | shop | `nginx-shop.conf` | `nginx-shop-proxy.conf` |

> **Hub + Shop combo:** If your hub also provides GPU services, combine the
> hub and shop configs into one server block — include both the hub locations
> and the shop GPU service locations in both the container config and the
> host proxy.

## Setup

1. Install the container config (inside the container):

```bash
sudo cp /opt/aitbc/examples/nginx/nginx-shop.conf.example /etc/nginx/sites-available/aitbc
sudo ln -sf /etc/nginx/sites-available/aitbc /etc/nginx/sites-enabled/aitbc
sudo sed -i 's/YOUR_DOMAIN/shop.example.com/g' /etc/nginx/sites-available/aitbc
sudo sed -i 's/CONTAINER_GATEWAY_IP/10.0.0.1/g' /etc/nginx/sites-available/aitbc
```

2. Install the host proxy config (on the host machine):

```bash
sudo cp /opt/aitbc/examples/nginx/nginx-shop-proxy.conf.example /etc/nginx/sites-available/aitbc-proxy
sudo ln -sf /etc/nginx/sites-available/aitbc-proxy /etc/nginx/sites-enabled/aitbc-proxy
sudo sed -i 's/YOUR_DOMAIN/shop.example.com/g' /etc/nginx/sites-available/aitbc-proxy
sudo sed -i 's/CONTAINER_IP/10.1.223.136/g' /etc/nginx/sites-available/aitbc-proxy
```

3. Enable SSL:

```bash
sudo certbot --nginx -d shop.example.com
```

4. Test and reload:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

## Port reference

| Service | Port | Exposed via nginx | Notes |
|---|---|---|---|
| Agent Registry | 8204 | Hub only | Machine-readable API |
| API Gateway | 8201 | Hub only | Aggregated API |
| Blockchain RPC | 8202 | Hub only | Followers connect here for /rpc/subscribe |
| Coordinator API | 8203 | Hub only | Shop uses it internally via localhost only |
| Agent Coordinator | 8107 | Hub only | WebSocket agent messaging |
| Wallet Service | 8108 | Hub only | Exchange API |
| Blockchain Explorer | 8100 | All roles | Read-only chain viewer |
| Ollama | 11434 | Shop only | AI inference |
| Whisper | 8080 | Shop only | Speech recognition |
| FFmpeg | 9000 | Shop only | Video transcoding |
| PeerTube Pruner | 9500 | Shop only | PeerTube maintenance |

> **Note:** Services like Coordinator API (8203) and Blockchain RPC (8202)
> run on all roles but are only exposed via nginx on the hub. On shop and
> customer nodes, they are used internally via `localhost` and do not need
> public exposure.
