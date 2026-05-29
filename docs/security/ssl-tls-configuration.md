# SSL/TLS Configuration

This guide covers certificate management, TLS configuration, and certificate rotation.

## Certificate Management

```bash
# Generate self-signed certificate (development only)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/ssl/private/aitbc.key \
  -out /etc/ssl/certs/aitbc.crt

# Use Let's Encrypt (production)
certbot --nginx -d your-domain.com
```

## TLS Configuration

```nginx
# Nginx TLS configuration
ssl_protocols TLSv1.2 TLSv1.3;
ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256';
ssl_prefer_server_ciphers off;
ssl_session_cache shared:SSL:10m;
ssl_session_timeout 10m;
```

## Certificate Rotation

```bash
# Auto-renew Let's Encrypt certificates
certbot renew --quiet --deploy-hook "systemctl reload nginx"

# Monitor certificate expiration
certbot certificates
```

## See Also

- [Network Security](network-security.md) - Network hardening
- [Firewall Rules](firewall-rules.md) - Access control
- [Secret Management](secret-management.md) - Certificate storage
