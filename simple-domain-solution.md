# Simple Domain Solution for AITBC

## Problem
- Incus container exists but you don't have access
- Services need to run locally
- Domain https://aitbc.bubuit.net needs to access local services

## Solution Options

### Option 1: SSH Tunnel (Recommended)

Create SSH tunnels from your server to your local machine:

```bash
# On your server (aitbc.bubuit.net):
ssh -R 8000:localhost:8000 -R 9080:localhost:9080 -R 3001:localhost:3001 -R 3002:localhost:3002 user@your-local-ip

# Then update nginx on server to proxy to localhost ports
```

### Option 2: Run Services Directly on Server

Copy the AITBC project to your server and run there:

```bash
# On server:
git clone https://gitea.bubuit.net/oib/aitbc.git
cd aitbc
./run-local-services.sh
```

### Option 3: Use Local Nginx

Run nginx locally and edit your hosts file:

```bash
# 1. Install nginx locally if not installed
sudo apt install nginx

# 2. Copy config
sudo cp nginx-local.conf /etc/nginx/sites-available/aitbc
sudo ln -s /etc/nginx/sites-available/aitbc /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default

# 3. Test and reload
sudo nginx -t
sudo systemctl reload nginx

# 4. Edit hosts file
echo "127.0.0.1 aitbc.bubuit.net" | sudo tee -a /etc/hosts

# 5. Access at http://aitbc.bubuit.net
```

### Option 4: Cloudflare Tunnel (Easiest)

Use Cloudflare tunnel to expose local services:

```bash
# 1. Install cloudflared
wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared-linux-amd64.deb

# 2. Login
cloudflared tunnel login

# 3. Create tunnel
cloudflared tunnel create aitbc

# 4. Create config file ~/.cloudflared/config.yml:
tunnel: aitbc
ingress:
  - hostname: aitbc.bubuit.net
    service: http://localhost:3001
  - path: /api
    service: http://localhost:8000
  - path: /admin
    service: http://localhost:8000
  - path: /rpc
    service: http://localhost:9080
  - path: /Exchange
    service: http://localhost:3002
  - service: http_status:404

# 5. Run tunnel
cloudflared tunnel run aitbc
```

## Current Status

✅ Services running locally:
- API: http://127.0.0.1:8000/v1
- Admin: http://127.0.0.1:8000/admin
- Blockchain: http://127.0.0.1:9080/rpc
- Marketplace: http://127.0.0.1:3001
- Exchange: http://127.0.0.1:3002

❌ Domain access not configured

## Quick Test

To test if the domain routing would work, you can:

1. Edit your local hosts file:
```bash
echo "127.0.0.1 aitbc.bubuit.net" | sudo tee -a /etc/hosts
```

2. Install and configure nginx locally (see Option 3)

3. Access http://aitbc.bubuit.net in your browser

## Recommendation

Use **Option 4 (Cloudflare Tunnel)** as it's:
- Free
- Secure (HTTPS)
- No port forwarding needed
- Works with dynamic IPs
- Easy to set up
