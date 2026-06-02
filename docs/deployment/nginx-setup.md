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
/api/      → localhost:8200 (API Gateway)
/rpc/      → localhost:8202 (Blockchain RPC)
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

# Test Agent Registry
curl http://localhost/agent/health

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
ss -lntup | grep 8200
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
