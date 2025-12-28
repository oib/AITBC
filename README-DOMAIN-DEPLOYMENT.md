# AITBC Domain Deployment Guide

## Overview

Deploy AITBC services to your existing domain: **https://aitbc.bubuit.net**

## Service URLs

- **Marketplace**: https://aitbc.bubuit.net/Marketplace
- **Trade Exchange**: https://aitbc.bubuit.net/Exchange
- **API**: https://aitbc.bubuit.net/api
- **Blockchain RPC**: https://aitbc.bubuit.net/rpc
- **Admin**: https://aitbc.bubuit.net/admin

## Prerequisites

1. Incus access (add user to incus group):
```bash
sudo usermod -aG incus $USER
# Log out and back in
```

2. Domain pointing to your server

## Deployment Steps

### 1. Deploy Services
```bash
./deploy-domain.sh
```

### 2. Configure Port Forwarding
Forward these ports to the container IP (10.1.223.93):
- Port 80 → 10.1.223.93:80
- Port 443 → 10.1.223.93:443

### 3. Install SSL Certificate
```bash
incus exec aitbc -- certbot --nginx -d aitbc.bubuit.net
```

### 4. Verify Services
Visit the URLs to ensure everything is working.

## Nginx Configuration

The nginx configuration handles:
- HTTPS redirection
- SSL termination
- Path-based routing
- API proxying
- Security headers

Configuration file: `/home/oib/windsurf/aitbc/nginx-aitbc.conf`

## Service Management

### Check running services:
```bash
incus exec aitbc -- ps aux | grep python
```

### View logs:
```bash
incus exec aitbc -- journalctl -u aitbc-coordinator -f
```

### Restart services:
```bash
incus exec aitbc -- pkill -f uvicorn
incus exec aitbc -- /home/oib/start_aitbc.sh
```

### Update nginx config:
```bash
incus file push nginx-aitbc.conf aitbc/etc/nginx/sites-available/aitbc
incus exec aitbc -- nginx -t && incus exec aitbc -- systemctl reload nginx
```

## API Endpoints

### Coordinator API
- GET `/api/marketplace/offers` - List GPU offers
- POST `/api/miners/register` - Register miner
- POST `/api/marketplace/bids` - Create bid
- GET `/api/marketplace/stats` - Marketplace stats

### Blockchain RPC
- GET `/rpc/head` - Get latest block
- GET `/rpc/getBalance/{address}` - Get balance
- POST `/rpc/admin/mintFaucet` - Mint tokens

## Security Considerations

1. **Firewall**: Only open necessary ports (80, 443)
2. **SSL**: Always use HTTPS
3. **API Keys**: Use environment variables for sensitive keys
4. **Rate Limiting**: Configure nginx rate limiting if needed

## Monitoring

### Health checks:
- https://aitbc.bubuit.net/health

### Metrics:
- https://aitbc.bubuit.net/metrics (if configured)

## Troubleshooting

### Services not accessible:
1. Check port forwarding
2. Verify nginx configuration
3. Check container services

### SSL issues:
1. Renew certificate: `incus exec aitbc -- certbot renew`
2. Check nginx SSL config

### API errors:
1. Check service logs
2. Verify API endpoints
3. Check CORS settings

## Customization

### Add new service:
1. Update nginx-aitbc.conf
2. Add service to start_aitbc.sh
3. Restart services

### Update UI:
1. Modify HTML files in apps/
2. Update base href if needed
3. Restart web servers

## Production Tips

1. Set up monitoring alerts
2. Configure backups
3. Use environment variables for config
4. Set up log rotation
5. Monitor resource usage
