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
   - Container escape
   - Pod-to-pod attacks
   - Secrets exfiltration
   - Supply chain attacks

4. **Blockchain-Specific Attacks**
   - 51% attacks on consensus
   - Transaction replay attacks
   - Smart contract exploits
   - Miner collusion

### Security Controls

| Control | Implementation | Mitigates |
|---------|----------------|-----------|
| TLS 1.3 | cert-manager + ingress | MITM, eavesdropping |
| API Keys | X-API-Key header | Unauthorized access |
| Rate Limiting | slowapi middleware | DDoS, abuse |
| Network Policies | Kubernetes NetworkPolicy | Pod-to-pod attacks |
| Secrets Mgmt | Kubernetes Secrets + SealedSecrets | Secrets exfiltration |
| RBAC | Kubernetes RBAC | Privilege escalation |
| Monitoring | Prometheus + AlertManager | Incident detection |

## Security Architecture

### Network Security

#### TLS Termination
```yaml
# Ingress configuration with TLS
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/ssl-protocols: "TLSv1.3"
spec:
  tls:
  - hosts:
    - api.aitbc.io
    secretName: api-tls
```

#### Certificate Management
- Uses cert-manager for automatic certificate provisioning
- Supports Let's Encrypt for production
- Internal CA for development environments
- Automatic renewal 30 days before expiry

### API Security

#### Authentication
- API key-based authentication for all services
- Keys stored in Kubernetes Secrets
- Per-service key rotation policies
- Audit logging for all authenticated requests

#### Authorization
- Role-based access control (RBAC)
- Resource-level permissions
- Rate limiting per API key
- IP whitelisting for sensitive operations

#### API Key Format
```
Header: X-API-Key: aitbc_prod_ak_1a2b3c4d5e6f7g8h9i0j
```

### Secrets Management

#### Kubernetes Secrets
- Base64 encoded secrets (not encrypted by default)
- Encrypted at rest with etcd encryption
- Access controlled via RBAC

#### SealedSecrets (Recommended for Production)
- Client-side encryption of secrets
- GitOps friendly
- Zero-knowledge encryption

#### Secret Rotation
- Automated rotation every 90 days
- Zero-downtime rotation for services
- Audit trail of all rotations

## Implementation Details

### 1. TLS Configuration

#### Coordinator API
```yaml
# Helm values for coordinator
ingress:
  enabled: true
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/force-ssl-redirect: "true"
    nginx.ingress.kubernetes.io/ssl-protocols: "TLSv1.3"
  tls:
    - secretName: coordinator-tls
      hosts:
        - api.aitbc.io
```

#### Blockchain Node RPC
```yaml
# WebSocket with TLS
wss://api.aitbc.io:8080/ws
```

### 2. API Authentication Middleware

#### Coordinator API Implementation
```python
from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

async def verify_api_key(api_key: str = Security(api_key_header)):
    if not verify_key(api_key):
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.url.path.startswith("/v1/"):
        api_key = request.headers.get("X-API-Key")
        if not verify_key(api_key):
            raise HTTPException(status_code=403, detail="API key required")
    response = await call_next(request)
    return response
```

### 3. Secrets Management Setup

#### SealedSecrets Installation
```bash
# Install sealed-secrets controller
helm repo add sealed-secrets https://bitnami-labs.github.io/sealed-secrets
helm install sealed-secrets sealed-secrets/sealed-secrets -n kube-system

# Create a sealed secret
kubeseal --format yaml < secret.yaml > sealed-secret.yaml
```

#### Example Secret Structure
```yaml
apiVersion: bitnami.com/v1alpha1
kind: SealedSecret
metadata:
  name: coordinator-api-keys
spec:
  encryptedData:
    api-key-prod: AgBy3i4OJSWK+PiTySYZZA9rO43cGDEQAx...
    api-key-dev: AgBy3i4OJSWK+PiTySYZZA9rO43cGDEQAx...
```

### 4. Network Policies

#### Default Deny Policy
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  - Egress
```

#### Service-Specific Policies
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: coordinator-api-netpol
spec:
  podSelector:
    matchLabels:
      app: coordinator-api
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: ingress-nginx
    ports:
    - protocol: TCP
      port: 8011
```

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
- [ ] All API endpoints require authentication
- [ ] TLS certificates valid and properly configured
- [ ] Secrets encrypted and access-controlled
- [ ] Network policies implemented
- [ ] RBAC configured correctly
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
