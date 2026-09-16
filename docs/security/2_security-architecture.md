# AITBC Security Documentation

This document outlines the security architecture, threat model, and implementation details for the AITBC platform.

## Overview

AITBC implements defense-in-depth security across multiple layers:

- Network security with TLS termination
- API authentication and authorization
- Secrets management and encryption
- Infrastructure security best practices
- Monitoring and incident response

## Threat Model

### Threat Actors

| Actor | Motivation | Capabilities | Impact |
|-------|-----------|--------------|--------|
| External attacker | Financial gain, disruption | Network access, exploits | High |
| Malicious insider | Data theft, sabotage | Internal access | Critical |
| Competitor | IP theft, market manipulation | Sophisticated attacks | High |
| Casual user | Accidental misuse | Limited knowledge | Low |

### Attack Vectors

1. **Network Attacks**
   - Man-in-the-middle (MITM) attacks
   - DDoS attacks
   - Network reconnaissance

2. **API Attacks**
   - Unauthorized access to marketplace
   - API key leakage
   - Rate limiting bypass
   - Injection attacks

3. **Infrastructure Attacks**
   - Host compromise / privilege escalation between co-located services
   - Lateral movement across the shared container bridge (unfiltered — see [Network Policy](../deployment/NETWORK_POLICY.md))
   - Secrets exfiltration from env files or the API-key store
   - Supply chain attacks

4. **Blockchain-Specific Attacks**
   - 51% attacks on consensus
   - Transaction replay attacks
   - Smart contract exploits
   - Miner collusion

### Security Controls

| Control | Implementation | Mitigates |
|---------|----------------|-----------|
| TLS 1.3 | Terminated by nginx on the proxy host (not by AITBC) | MITM, eavesdropping |
| API Keys | `X-API-Key` / `X-Api-Key` header (per-service) | Unauthorized access |
| JWT auth | `Authorization: Bearer <jwt>` (coordinator customer path) | Unauthorized access |
| Rate Limiting | `aitbc.rate_limiting` per-route decorators + middleware | DDoS, abuse |
| Network Policies | Host/perimeter firewall + bind-address control (no Kubernetes) | Lateral movement, exposure |
| Secrets Mgmt | Env files under `/etc/aitbc/` (0600), systemd `EnvironmentFile` | Secrets exfiltration |
| RBAC | Role dependencies in `aitbc/auth` (`require_admin`, `require_client`, `require_miner`) | Privilege escalation |
| Monitoring | Prometheus + AlertManager | Incident detection |

## Security Architecture

### Network Security

#### TLS Termination

TLS terminates on the proxy host in front of the fleet, not on any AITBC
service. Services speak cleartext HTTP on loopback or a container-internal
address; none listens on `443`. See
[Network Policy](../deployment/NETWORK_POLICY.md).

#### Certificate Management

Out of scope. AITBC provisions no certificates and runs no ACME client — see
[SSL/TLS Configuration](ssl-tls-configuration.md). Certificates belong to
whoever operates the terminator.

### API Security

#### Authentication — mixed model (shared `aitbc/auth` library)

There is no single "API key for all services" scheme:

- **Coordinator API (8203)** — customers authenticate with `Authorization: Bearer <jwt>`; the JWT is issued by the wallet-signed login flow (`POST /v1/auth/nonce` → `POST /v1/login`). `X-Api-Key` is read by `APIKeyAuthenticator` for service/legacy callers; miner routes accept either (`require_miner`).
- **Blockchain node RPC (8202)** — admin/control mutations (`/rpc/contracts/deploy`, `/rpc/governance/*`, `/rpc/escrow/*` router-level incl. GETs, `/rpc/gpu/*` writes, `/rpc/identity/*`, `/rpc/chains/*`, `/rpc/importBlock`) require `X-API-Key` matching `BLOCKCHAIN_RPC_API_KEY`. `POST /rpc/transaction` and `POST /rpc/staking/stake` are **signature-verified** (wallet signature in the body — no header key). `/rpc/subscribe`, `/rpc/heartbeat` and lease revocation additionally accept peer keys from `BLOCKCHAIN_RPC_API_KEY_PEERS`. `/rpc/force-sync` requires an admin-signed request body (no header key).
- **Gossip WebSocket** — restricted topics require a signed validator challenge; there is no `?api_key=` WS auth.
- **Marketplace (8102)** — only the admin `POST /v1/marketplace/parameters/apply` route is key-gated (`X-Api-Key`).

Keys and JWT secrets live in `/etc/aitbc/*.env` files (mode `0600`) loaded by systemd `EnvironmentFile` — not in a secrets manager; see below.

#### Authorization

- Role dependencies from `aitbc/auth/dependencies.py` (`require_admin`, `require_client`, `require_admin_or_client`, `require_miner`, `APIKeyAuthenticator`)
- Per-route rate limiting
- Sensitive chain-control routes (e.g. `/rpc/force-sync`) require an admin signature over the request body, not just a key

#### API Key Format

```
Header: X-API-Key: <key>    # blockchain RPC / escrow
Header: X-Api-Key: <key>    # coordinator service/legacy callers, marketplace admin
```

### Secrets Management

#### systemd + env files (no Kubernetes)

The deployment is **systemd units behind nginx** — there is no Kubernetes, SealedSecrets, or etcd in this deployment.

- Service secrets are env files under `/etc/aitbc/` (e.g. `blockchain.env`, `blockchain-secrets.env`, `node.env`) with mode `0600`, loaded via systemd `EnvironmentFile=`
- API keys issued to callers are stored as SHA-256 digests in `API_KEY_STORAGE_PATH` (default `/var/lib/aitbc/api_keys.json`, mode `0600`) managed by `aitbc/auth/api_key.py` — plaintext keys are never persisted
- Wallet keystore under `$AITBC_DATA_DIR/keystore`

#### Secret Rotation

- Manual rotation: update the env file and restart the unit (`systemctl restart <unit>`)
- API keys can be rotated by generating a new key via `APIKeyManager` and distributing it; the old digest is removed from the store
- Audit trail via systemd journal (`journalctl -u <unit>`)

## Implementation Details

### 1. TLS Configuration

TLS terminates at nginx on the proxy host; backend services speak plain HTTP on loopback/bridge addresses. The public surfaces are `https://hub.aitbc.bubuit.net/rpc` (blockchain) and the coordinator/marketplace paths under the same terminator — raw backend ports such as `:8202`/`:8203` are internal-only.

```nginx
# nginx reverse proxy (simplified)
location /rpc/ {
    proxy_pass http://127.0.0.1:8202/rpc/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;    # WebSocket pass-through
    proxy_set_header Connection "upgrade";
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header Host $host;
}
```

### 2. API Authentication — real dependency model

Authentication is applied per route via FastAPI dependencies from `aitbc/auth/dependencies.py` and the node's `rpc/escrow_routes.py` — not a blanket middleware over `/v1/`:

```python
# Coordinator customer route: Bearer JWT (roles admin/client)
@router.post("/jobs")
async def create_job(user: AdminOrClientDep, ...):
    client_id = user["sub"]

# Blockchain RPC mutation: X-API-Key against BLOCKCHAIN_RPC_API_KEY
@router.post("/importBlock", dependencies=[Depends(verify_rpc_api_key)])

# Node-internal subscription route: own key OR configured peer keys
@router.post("/subscribe", dependencies=[Depends(verify_rpc_peer_key)])
```

`POST /rpc/force-sync` instead requires `admin_address` + `admin_signature` in the body, verified with `verify_admin_signature`.

### 3. Secrets Management Setup

```bash
# Env files live under /etc/aitbc with owner-only permissions
install -m 0600 /dev/null /etc/aitbc/blockchain-secrets.env
cat > /etc/aitbc/blockchain-secrets.env <<'EOF'
BLOCKCHAIN_RPC_API_KEY=...
BLOCKCHAIN_RPC_API_KEY_PEERS=key1,key2   # peer-node subscribe/heartbeat keys
PROPOSER_PRIVATE_KEY=...
EOF

# systemd unit loads them
# /etc/systemd/system/aitbc-blockchain-node.service:
#   EnvironmentFile=/etc/aitbc/blockchain.env
#   EnvironmentFile=/etc/aitbc/blockchain-secrets.env
```

Caller-facing API keys are issued and validated by `aitbc/auth/api_key.py::APIKeyManager` (SHA-256 digests in `/var/lib/aitbc/api_keys.json`, `0600`, file-locked).

### 4. Network Policy — host and bridge level

There is no Kubernetes NetworkPolicy. Access control is (see [Network Policy](../deployment/NETWORK_POLICY.md)):

- **Perimeter/host firewall** — only the authorized public surfaces are internet-reachable (nginx 443/80, blockchain P2P 7070 on the hub, IPFS swarm ports)
- **nginx** — the only public HTTP entry; proxies `/rpc/`, `/api/`, `/c/`, `/explorer-api/` to internal listeners
- **Bind addresses** — the shared container bridge is unfiltered and not exclusive to AITBC, so a bind-all port is reachable by every co-located container; bind decisions control lateral-movement blast radius

## Security Best Practices

### Development Environment

- Use 127.0.0.2 for local development (not 0.0.0.0)
- Separate API keys for dev/staging/prod
- Enable debug logging only in development
- Use self-signed certificates for local TLS

### Production Environment

- Enable all security headers
- Implement comprehensive logging
- Use external secret management
- Regular security audits
- Penetration testing quarterly

### Monitoring and Alerting

#### Security Metrics

- Failed authentication attempts
- Unusual API usage patterns
- Certificate expiry warnings
- Secret access audits

#### Alert Rules

```yaml
- alert: HighAuthFailureRate
  expr: rate(auth_failures_total[5m]) > 10
  for: 2m
  labels:
    severity: warning
  annotations:
    summary: "High authentication failure rate detected"

- alert: CertificateExpiringSoon
  expr: cert_certificate_expiry_time < time() + 86400 * 7
  for: 1h
  labels:
    severity: critical
  annotations:
    summary: "Certificate expires in less than 7 days"
```

## Incident Response

### Security Incident Categories

1. **Critical**: Data breach, system compromise
2. **High**: Service disruption, privilege escalation
3. **Medium**: Suspicious activity, policy violation
4. **Low**: Misconfiguration, minor issue

### Response Procedures

1. **Detection**: Automated alerts, manual monitoring
2. **Assessment**: Impact analysis, containment
3. **Remediation**: Patch, rotate credentials, restore
4. **Post-mortem**: Document, improve controls

### Emergency Contacts

- Security Team: security@aitbc.io
- On-call Engineer: +1-555-SECURITY
- Incident Commander: incident@aitbc.io

## Compliance

### Data Protection

- GDPR compliance for EU users
- CCPA compliance for California users
- Data retention policies
- Right to deletion implementation

### Auditing

- Quarterly security audits
- Annual penetration testing
- Continuous vulnerability scanning
- Third-party security assessments

## Security Checklist

### Pre-deployment

- [ ] Authenticated routes wired to the right dependency (JWT bearer / `X-API-Key` / peer key / admin signature)
- [ ] TLS certificates valid and properly configured on the nginx terminator
- [ ] Env files under `/etc/aitbc/` are mode `0600` and not committed to the repo
- [ ] Public surface limited to the authorized list in [Network Policy](../deployment/NETWORK_POLICY.md)
- [ ] Role dependencies (`require_admin`/`require_client`/`require_miner`) configured correctly
- [ ] Monitoring and alerting active
- [ ] Backup encryption enabled
- [ ] Security headers configured

### Post-deployment

- [ ] Security testing completed
- [ ] Documentation updated
- [ ] Team trained on procedures
- [ ] Incident response tested
- [ ] Compliance verified

## References

- [OWASP API Security Top 10](https://owasp.org/www-project-api-security/)
- [Kubernetes Security Best Practices](https://kubernetes.io/docs/concepts/security/)
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework)
- [CERT Coordination Center](https://www.cert.org/)

## Security Updates

This document is updated regularly. Last updated: 2024-12-22

For questions or concerns, contact the security team at security@aitbc.io
