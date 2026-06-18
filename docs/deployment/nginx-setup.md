# How to Configure Nginx for AITBC

## Overview

Nginx provides SSL termination, security headers, and load balancing for AITBC public services. This guide covers installation and configuration.

## Installation

### Install Nginx

```bash
# Debian/Ubuntu
sudo apt update
sudo apt install nginx

# Verify installation
nginx -v
```

## Configuration

### Copy AITBC Nginx Configuration

```bash
# Copy the AITBC nginx configuration
sudo cp /opt/aitbc/deployment/nginx-aitbc.conf /etc/nginx/sites-available/aitbc

# Edit server_name to match your hostname
sudo vim /etc/nginx/sites-available/aitbc
# Change server_name from "_" to your actual hostname (e.g., aitbc3.aitbc.bubuit.net)

# Enable the site
sudo ln -s /etc/nginx/sites-available/aitbc /etc/nginx/sites-enabled/aitbc

# Remove default site (optional)
sudo rm /etc/nginx/sites-enabled/default
```

### Test Configuration

```bash
# Test nginx configuration
sudo nginx -t
```

### Restart Nginx

```bash
# Restart nginx
sudo systemctl restart nginx

# Enable nginx to start on boot
sudo systemctl enable nginx
```

## SSL Configuration (Optional)

### Generate Self-Signed Certificate (Testing)

```bash
# Create SSL directory
sudo mkdir -p /etc/nginx/ssl

# Generate self-signed certificate
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/nginx/ssl/aitbc.key \
  -out /etc/nginx/ssl/aitbc.crt

# Update nginx configuration to use SSL
# Uncomment the HTTPS server block in /etc/nginx/sites-available/aitbc
# Update ssl_certificate and ssl_certificate_key paths
```

### Use Let's Encrypt (Production)

```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal is configured automatically
```

## Routing Configuration

The nginx configuration routes requests as follows:

```
/api/      → localhost:8201 (API Gateway)
/rpc/      → localhost:8202 (Blockchain RPC, bundled in blockchain-node)
/c/        → localhost:8203 (Coordinator API - failover)
```

## Verification

### Test HTTP Access

```bash
# Test API Gateway
curl http://localhost/api/health

# Test Blockchain RPC
curl http://localhost/rpc/health

# Test Coordinator API
curl http://localhost/c/health

# Test nginx health
curl http://localhost/health

# Test network discovery endpoint
curl http://localhost/rpc/network-info
```

### Test HTTPS Access (After SSL Configuration)

```bash
# Test API Gateway
curl https://localhost/api/health

# Test Blockchain RPC
curl https://localhost/rpc/health

# Test Coordinator API
curl https://localhost/c/health
```

## Firewall Configuration

Ensure nginx ports are allowed through the firewall:

```bash
# Update firehol configuration
sudo vim /etc/firehol/firehol.conf

# Add to interface4 any world section:
server "http https" accept

# Restart firehol
sudo firehol restart
```

## Critical: HTTP→HTTPS Redirect Must Preserve POST Method

> **⚠️ Required for marketplace and blockchain RPC POST endpoints to work correctly.**

### The Problem

If nginx redirects HTTP to HTTPS using `301 Moved Permanently`, HTTP clients (including Python `requests`, curl without `-L`, and browsers) will **downgrade POST to GET** on redirect (RFC 7231 compliant behavior). This breaks all blockchain RPC POST submissions:

- `POST /rpc/transactions/marketplace` → redirected → becomes `GET` → nginx returns **405 Method Not Allowed**
- Marketplace offers, bids, and coin requests submitted over HTTP will silently fail

### The Fix: Use 308 Instead of 301

In your nginx HTTP server block, use `308 Permanent Redirect` which explicitly preserves the request method and body:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # ❌ WRONG — downgrades POST to GET on redirect
    # return 301 https://$host$request_uri;

    # ✅ CORRECT — preserves POST method and body
    return 308 https://$host$request_uri;
}
```

### Verification

```bash
# Check what redirect code your nginx returns for POST
curl -sv -X POST http://your-domain.com/rpc/transactions/marketplace \
  -H "Content-Type: application/json" -d '{}' 2>&1 | grep "< HTTP"

# Expected with 308: HTTP/1.1 308 Permanent Redirect  ✅
# Broken with 301:   HTTP/1.1 301 Moved Permanently   ❌ (POST becomes GET)
```

### Client-Side Workaround

If you cannot change the nginx config, ensure all AITBC CLI and service clients use `https://` URLs directly (skip HTTP entirely). The AITBC CLI reads `HUB_DISCOVERY_URL` from `/etc/aitbc/blockchain.env` — confirm it does not need an HTTP fallback:

```bash
grep HUB_DISCOVERY_URL /etc/aitbc/blockchain.env
# Should be: HUB_DISCOVERY_URL=hub.aitbc.bubuit.net
# CLI prepends https:// automatically
```

---

## Troubleshooting

### Nginx Won't Start

```bash
# Check configuration syntax
sudo nginx -t

# Check error logs
sudo tail -f /var/log/nginx/error.log

# Check if port 80/443 is already in use
sudo ss -lntup | grep ':80'
sudo ss -lntup | grep ':443'
```

### Service Not Accessible

```bash
# Check if nginx is running
sudo systemctl status nginx

# Check if backend service is running
sudo systemctl status aitbc-api-gateway
sudo systemctl status aitbc-blockchain-node
sudo systemctl status aitbc-coordinator-api

# Check service binding
ss -lntup | grep 8201
ss -lntup | grep 8202
ss -lntup | grep 8203
```

### 502 Bad Gateway

This typically means nginx cannot connect to the backend service:

```bash
# Check backend service status
sudo systemctl status <service-name>

# Check backend service is listening on correct port
ss -lntup | grep <port>

# Check nginx error logs
sudo tail -f /var/log/nginx/error.log
```

## Related Documentation

- [Incus Port Forwarding](incus-port-forwarding.md) - Container port configuration
- [Firehol Configuration](firehol-configuration.md) - Firewall configuration
- [Service Ports Reference](../reference/SERVICE_PORTS.md) - Complete port configuration
