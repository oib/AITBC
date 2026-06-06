# SSL/TLS Configuration

This guide covers SSL/TLS setup for AITBC deployment using Let's Encrypt and manual certificates.

## Let's Encrypt

```bash
# Install certbot
apt install -y certbot python3-certbot-nginx

# Obtain certificate
certbot --nginx -d your-domain.com

# Auto-renewal
certbot renew --dry-run
```

## Manual Certificate

```bash
# Generate self-signed certificate
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/ssl/private/aitbc.key \
  -out /etc/ssl/certs/aitbc.crt

# Configure Nginx
nano /etc/nginx/sites-available/aitbc
```

## Nginx SSL Configuration

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/ssl/certs/aitbc.crt;
    ssl_certificate_key /etc/ssl/private/aitbc.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    location / {
        proxy_pass http://coordinator;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## See Also

- [Security/SSL-TLS Configuration](../security/ssl-tls-configuration.md) - Detailed SSL/TLS guide
- [Single Server](single-server.md) - Nginx configuration
- [Configuration](configuration.md) - Environment configuration
