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
ufw allow from 192.168.1.0/24 to any port 8107
```

## Authentication

### Current Status

- **Implemented:** API-key and JWT support via the shared `aitbc/auth`
  library; signed message envelopes (`aitbc-agent-msg-v1`).
- **Mode-dependent:** `AGENT_MSG_SIGNATURE_MODE`
  (`disabled`/`advisory`/`enforce` in
  `/etc/aitbc/aitbc-agent-coordinator.env`) controls whether mutating calls
  require a resolvable credential. In `enforce`, unauthenticated calls get
  `401`/`403` and `POST /v1/tasks/submit` runs `authorize_any_principal`.
- **Deployment:** the service binds `127.0.0.1:8107`; remote callers go
  through the hub nginx `/agent/` proxy (TLS + allow-list), which is the
  intended access control.

## Data Encryption

### Redis Encryption

Configure Redis with TLS.

### API Encryption

Use HTTPS in production.

## Related Topics

- [Deployment](./operator-deployment.md) - Installation and service configuration
- [Performance Tuning](./operator-performance.md) - Load balancing and resource limits
- [Scaling](./operator-scaling.md) - Horizontal scaling and Redis clustering
