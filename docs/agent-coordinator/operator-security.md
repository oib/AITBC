# Agent Coordinator - Security

**Last Updated**: 2026-06-30
**Version**: 1.0

## Network Security

### Bind to Specific Interface

```bash
# In service file, change --host 0.0.0.0 to --host 127.0.0.1 for local only
--host 127.0.0.1
```

### Use Firewall

```bash
# Allow only specific IPs
ufw allow from 192.168.1.0/24 to any port 9001
```

## Authentication

### Current Status

- **Future implementation:** API key authentication and JWT tokens
- **Current status:** No authentication (open access)
- **Recommendation:** Deploy behind reverse proxy with authentication

## Data Encryption

### Redis Encryption

Configure Redis with TLS.

### API Encryption

Use HTTPS in production.

## Related Topics

- [Deployment](./operator-deployment.md) - Installation and service configuration
- [Performance Tuning](./operator-performance.md) - Load balancing and resource limits
- [Scaling](./operator-scaling.md) - Horizontal scaling and Redis clustering
