# AITBC Nginx Examples

Role-specific nginx configurations for AITBC nodes.

## Files

| File | Role | What it exposes |
|---|---|---|
| `nginx-hub.conf.example` | `BLOCKCHAIN_MODE=hub` | Agent registry, API gateway, blockchain RPC (WS+HTTP), agent coordinator WS, coordinator API, wallet exchange, explorer, website |
| `nginx-shop.conf.example` | `MARKET_ROLE=shop` | Ollama, Whisper, FFmpeg, PeerTube Pruner, explorer |
| `nginx-customer.conf.example` | `MARKET_ROLE=customer` | Explorer, health check |
| `nginx-aitbc-host-reverse-proxy.conf.example` | All roles (host machine) | SSL termination + reverse proxy to container. Includes all role-specific locations — comment out what you don't need |

## Architecture

```
Internet → Host nginx (SSL termination, host-reverse-proxy.conf)
         → Container nginx (role config, e.g. nginx-hub.conf)
            → Backend services (127.0.0.1:8xxx)
```

The **host reverse proxy** terminates SSL and forwards to the container's
nginx on port 80. The **container nginx** routes to individual backend
services on localhost ports.

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
the shop or follower configs, even though those services run locally. They
are only exposed publicly on the **hub** (where external followers and
clients need to reach them).

## Choosing the right config

Check your node's role:

```bash
grep -E "BLOCKCHAIN_MODE|MARKET_ROLE" /etc/aitbc/node.env
```

| `BLOCKCHAIN_MODE` | `MARKET_ROLE` | Config to use |
|---|---|---|
| `hub` | customer | `nginx-hub.conf` |
| `hub` | shop | `nginx-hub.conf` + `nginx-shop.conf` (combine both) |
| `follower` | customer | `nginx-customer.conf` |
| `follower` | shop | `nginx-shop.conf` |

> **Hub + Shop combo:** If your hub also provides GPU services, combine the
> hub and shop configs into one server block — include both the hub locations
> and the shop GPU service locations.

## Setup

1. Copy the role-specific config to the container:

```bash
# On the container:
sudo cp /opt/aitbc/examples/nginx/nginx-hub.conf.example /etc/nginx/sites-available/aitbc
sudo ln -sf /etc/nginx/sites-available/aitbc /etc/nginx/sites-enabled/aitbc
```

2. Replace placeholders:

```bash
sudo sed -i 's/YOUR_DOMAIN/hub.example.com/g' /etc/nginx/sites-available/aitbc
sudo sed -i 's/CONTAINER_GATEWAY_IP/10.0.0.1/g' /etc/nginx/sites-available/aitbc
```

3. Copy the host reverse proxy config to the host machine:

```bash
# On the host:
sudo cp /opt/aitbc/examples/nginx/nginx-aitbc-host-reverse-proxy.conf.example \
        /etc/nginx/sites-available/aitbc-proxy
sudo ln -sf /etc/nginx/sites-available/aitbc-proxy /etc/nginx/sites-enabled/aitbc-proxy
sudo sed -i 's/YOUR_DOMAIN/hub.example.com/g' /etc/nginx/sites-available/aitbc-proxy
sudo sed -i 's/CONTAINER_IP/10.0.0.2/g' /etc/nginx/sites-available/aitbc-proxy
```

4. Comment out role-specific locations in the host proxy that don't apply:

```bash
# On a follower node, comment out the HUB-ONLY and SHOP-ONLY sections:
sudo nano /etc/nginx/sites-available/aitbc-proxy
```

5. Enable SSL:

```bash
sudo certbot --nginx -d hub.example.com
```

6. Test and reload:

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
> follower nodes, they are used internally via `localhost` and do not need
> public exposure.
