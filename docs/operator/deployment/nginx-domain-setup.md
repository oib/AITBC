# Nginx Domain Setup for AITBC

## Problem
The admin endpoint at `https://aitbc.bubuit.net/admin` returns 404 because nginx isn't properly routing to the backend services.

## Solution

### 1. Make sure services are running in the container

```bash
# Access the container
incus exec aitbc -- bash

# Inside container, start services
cd /home/oib/aitbc
./start_aitbc.sh

# Check if running
ps aux | grep uvicorn
```

### 2. Update nginx configuration in container

The nginx config needs to be inside the container at `/etc/nginx/sites-available/aitbc`:

```nginx
server {
    listen 80;
    server_name aitbc.bubuit.net;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name aitbc.bubuit.net;
    
    # SSL certs (already configured)
    ssl_certificate /etc/letsencrypt/live/aitbc.bubuit.net/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/aitbc.bubuit.net/privkey.pem;
    
    # API routes - MUST include /v1
    location /api/ {
        proxy_pass http://127.0.0.1:8000/v1/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # Admin routes
    location /admin/ {
        proxy_pass http://127.0.0.1:8000/admin/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # Blockchain RPC
    location /rpc/ {
        proxy_pass http://127.0.0.1:9080/rpc/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # Marketplace UI
    location /Marketplace {
        proxy_pass http://127.0.0.1:3001/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # Trade Exchange
    location /Exchange {
        proxy_pass http://127.0.0.1:3002/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # Health endpoint
    location /health {
        proxy_pass http://127.0.0.1:8000/v1/health;
        proxy_set_header Host $host;
    }
    
    # Default redirect
    location / {
        return 301 /Marketplace;
    }
}
```

### 3. Apply the configuration

```bash
# Copy config to container
incus file push nginx-aitbc.conf aitbc/etc/nginx/sites-available/aitbc

# Enable site
incus exec aitbc -- ln -sf /etc/nginx/sites-available/aitbc /etc/nginx/sites-enabled/

# Test config
incus exec aitbc -- nginx -t

# Reload nginx
incus exec aitbc -- systemctl reload nginx
```

### 4. Verify services are running

```bash
# Check each service
curl -k https://aitbc.bubuit.net/api/health
curl -k https://aitbc.bubuit.net/admin/stats -H "X-Api-Key: ${ADMIN_API_KEY}"
curl -k https://aitbc.bubuit.net/rpc/head
```

## Quick Fix

If you need immediate access, you can access the API directly:

- **API**: https://aitbc.bubuit.net/api/health
- **Admin**: https://aitbc.bubuit.net/admin/stats (with API key)
- **Marketplace**: https://aitbc.bubuit.net/Marketplace
- **Exchange**: https://aitbc.bubuit.net/Exchange

The issue is likely that:
1. Services aren't running in the container
2. Nginx config isn't properly routing /admin to the backend
3. Port forwarding isn't configured correctly

## Debug Steps

1. Check container services: `incus exec aitbc -- ps aux | grep uvicorn`
2. Check nginx logs: `incus exec aitbc -- journalctl -u nginx -f`
3. Check nginx config: `incus exec aitbc -- nginx -T`
4. Test backend directly: `incus exec aitbc -- curl http://127.0.0.1:8000/v1/health`
