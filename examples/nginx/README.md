# AITBC Nginx Examples

Role-specific nginx configurations for AITBC nodes.

## Files

| File | Role | What it exposes |
|---|---|---|
| `nginx-hub.conf.example` | `BLOCKCHAIN_MODE=hub` | Agent registry, API gateway, blockchain RPC (WS+HTTP), agent coordinator WS, coordinator API, wallet exchange, explorer, website |
| `nginx-shop.conf.example` | `MARKET_ROLE=shop` | Ollama, Whisper, FFmpeg, PeerTube Pruner, explorer |
| `nginx-follower.conf.example` | `BLOCKCHAIN_MODE=follower, MARKET_ROLE=customer` | Explorer only |
| `nginx-customer.conf.example` | `MARKET_ROLE=customer` (no nginx needed) | Health check only (optional) |
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

## Choosing the right config

Check your node's role:

```bash
grep -E "BLOCKCHAIN_MODE|MARKET_ROLE" /etc/aitbc/node.env
```

| `BLOCKCHAIN_MODE` | `MARKET_ROLE` | Config to use |
|---|---|---|
| `hub` | customer | `nginx-hub.conf` |
| `hub` | shop | `nginx-hub.conf` + `nginx-shop.conf` (combine both) |
| `follower` | customer | `nginx-follower.conf` |
| `follower` | shop | `nginx-shop.conf` (includes explorer) |

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

| Service | Port | Config |
|---|---|---|
| Agent Registry | 8204 | Hub |
| API Gateway | 8201 | Hub |
| Blockchain RPC | 8202 | Hub |
| Coordinator API | 8203 | Hub |
| Agent Coordinator | 8107 | Hub |
| Wallet Service | 8108 | Hub |
| Blockchain Explorer | 8100 | All roles |
| Ollama | 11434 | Shop |
| Whisper | 8080 | Shop |
| FFmpeg | 9000 | Shop |
| PeerTube Pruner | 9500 | Shop |
