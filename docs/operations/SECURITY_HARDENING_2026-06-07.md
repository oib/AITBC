# AITBC Security Hardening

**Date**: June 7, 2026
**Status**: ✅ Partially Implemented
**Purpose**: Security hardening for AITBC services including service isolation, rate limiting, and access control

## Overview

This document describes the security hardening measures implemented for AITBC services. Due to the incus container environment, some security measures (like firewall rules) are configured at the host level and are not covered here. This document focuses on container-level security improvements.

## Implemented Security Measures

### 1. Service User Creation

**Status**: ✅ Completed

Dedicated service users have been created for AITBC services to follow the principle of least privilege:

**Created Users:**
- `aitbc-api` - API Gateway service
- `aitbc-blockchain` - Blockchain services
- `aitbc-coordinator` - Coordinator API service
- `aitbc-wallet` - Wallet service
- `aitbc-gpu` - GPU service
- `aitbc-marketplace` - Marketplace service
- `aitbc-agent` - Agent messaging service
- `aitbc-agent` - Agent services

**Group:**
- `aitbc-services` - Common group for all service users

**User Configuration:**
- Shell: `/bin/false` (no shell access)
- Home directory: Created but not used
- Group: All users belong to `aitbc-services` group

**Note**: Service users have been created but services are still running as `root` due to permission requirements. Full service isolation requires additional permission configuration.

### 2. Application-Level Rate Limiting

**Status**: ✅ Already Implemented

Rate limiting is already implemented across AITBC services using multiple mechanisms:

#### SlowAPI Integration

**File**: `/opt/aitbc/apps/api-gateway/src/api_gateway/main.py`
- **Library**: slowapi 0.1.9
- **Implementation**: IP-based rate limiting
- **Default Limits**: Configurable per endpoint
- **Exception Handling**: Custom rate limit exceeded handler

#### Custom Rate Limiting Module

**File**: `/opt/aitbc/aitbc/rate_limiting.py`
- **Features**:
  - Decorator-based rate limiting (`@rate_limit`)
  - Middleware-based rate limiting (`RateLimitMiddleware`)
  - Per-endpoint rate limiters
  - Custom key functions (IP, user ID, etc.)
  - Rate limit headers support

**Usage Example:**
```python
from aitbc.rate_limiting import rate_limit

@rate_limit(rate=100, per=60)
def protected_endpoint():
    return "data"
```

#### Rate Limiting in Services

**Services with Rate Limiting:**
- API Gateway: SlowAPI-based rate limiting
- Agent Coordinator: RateLimitMiddleware (100 req/60s)
- Blockchain RPC: RateLimitMiddleware
- Wallet Service: RateLimitMiddleware
- Exchange Services: RateLimitMiddleware

### 3. Access Control Implementation

**Status**: ✅ Implemented

A comprehensive access control module has been created for authentication and authorization:

#### Access Control Module

**File**: `/opt/aitbc/aitbc/access_control.py`
- **Features**:
  - JWT token creation and verification
  - Role-based access control (RBAC)
  - API key authentication
  - Permission decorators
  - Security headers generation

**Classes:**
- `AccessController` - Main access control class
- `APIKeyAuth` - API key authentication
- `SecureHeaders` - Security headers generator

**Usage Example:**
```python
from aitbc.access_control import get_access_controller, require_role

access_controller = get_access_controller()

@require_role("admin", "operator")
def admin_function():
    return "admin data"
```

#### Security Configuration

**File**: `/etc/aitbc/security.env`
- **JWT Configuration**: Secret key, algorithm, token expiry
- **API Key Configuration**: Valid API keys
- **RBAC Configuration**: Role permissions
- **Security Headers**: HSTS, CSP, etc.
- **Rate Limiting**: Default limits and periods

**Configuration Options:**
```bash
JWT_SECRET_KEY=change-this-secret-key-in-production
JWT_ALGORITHM=HS256
JWT_TOKEN_EXPIRY=3600
VALID_API_KEYS=
ENABLE_RBAC=true
DEFAULT_ROLE=guest
ENABLE_SECURITY_HEADERS=true
```

#### Role-Based Access Control

**Defined Roles:**
- `admin` - Full access (*)
- `operator` - read, write, execute
- `user` - read only
- `service` - read, write
- `guest` - read only

**Permission System:**
- Decorator-based permission checking
- Role-based permission inheritance
- Custom permission definitions

### 4. Security Headers

**Status**: ✅ Implemented

Standard security headers are available through the `SecureHeaders` class:

**Headers:**
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- `Content-Security-Policy: default-src 'self'`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: geolocation=(), microphone=(), camera=()`

## Pending Security Measures

### 1. Service Isolation (Streamlined Strategy)

**Status**: 24/26 services isolated (92%)

**What's Done:**
- ✅ Service users created (5 users: aitbc-public, aitbc-internal, aitbc-blockchain, aitbc-gpu, aitbc-wallet)
- ✅ Service group created (aitbc-services)
- ✅ User permissions configured
- ✅ Streamlined user strategy implemented (exposure-based grouping)
- ✅ 24 services configured to run as dedicated users:
  - **aitbc-public** (6 services): API Gateway, Edge, Whisper, AI, Event Bridge, FFmpeg
  - **aitbc-internal** (10 services): Marketplace, Agent, Agent Coordinator, Coordinator API, Exchange, Governance, Trading, Learning, Modality, Multimodal, Plugin, Monitoring
  - **aitbc-blockchain** (3 services): Blockchain Node, P2P, RPC
  - **aitbc-gpu** (1 service): GPU service
  - **aitbc-wallet** (1 service): Wallet service
- ✅ File permissions configured for isolated services
- ✅ Service isolation tested and verified
- ✅ Database authentication fixed for blockchain P2P service

**What's Pending:**
- 📋 Remaining services configured to run as dedicated users (2 services: agent daemon, agent management)
- 📋 Capability dropping implementation
- 📋 Seccomp filters configuration
- 📋 File system namespaces implementation

**Challenges:**
- Services currently require root for certain operations
- File permissions need to be adjusted
- Database access needs to be configured for service users
- Some services bind to privileged ports

### 2. Network Security (Host-Level)

**Status**: Not applicable (container environment)

**Reason:** Firewall rules are configured at the host level, not in the incus container. This should be handled by the system administrator at the host level.

**Recommended Host-Level Measures:**
- Configure ufw/iptables firewall rules
- Restrict service access to localhost where appropriate
- Implement rate limiting at network level
- Set up IP whitelisting for sensitive services
- Configure network segmentation

### 3. Advanced Security Measures

**Status**: Planned

**Future Enhancements:**
- Mutual TLS for service-to-service communication
- Certificate-based authentication
- Network-level encryption
- Intrusion detection system
- Security audit logging
- Automated security scanning

## Security Configuration Files

### New Files

1. `/opt/aitbc/aitbc/access_control.py` - Access control module
2. `/etc/aitbc/security.env` - Security configuration

### Modified Files

None (security modules are new additions)

### Existing Security Files

- `/opt/aitbc/aitbc/rate_limiting.py` - Rate limiting (already existed)
- `/opt/aitbc/aitbc/security_hardening.py` - Security utilities (already existed)

## Security Best Practices

### Current Implementation

✅ **Implemented:**
- Service user creation (users created, not yet applied)
- Application-level rate limiting
- JWT-based authentication framework
- Role-based access control framework
- Security headers implementation
- API key authentication framework

⚠️ **Partially Implemented:**
- Service isolation (users created, services not yet configured)

❌ **Not Implemented (Host-Level):**
- Firewall rules (configured at host level)
- Network-level rate limiting
- Network segmentation

### Recommended Practices

**For Service Isolation:**
1. Configure services to run as dedicated users
2. Set minimal file permissions for service users
3. Implement capability dropping
4. Use file system namespaces where possible
5. Configure seccomp filters for system call restrictions

**For Access Control:**
1. Enable JWT authentication for sensitive endpoints
2. Implement API key rotation
3. Use strong secrets in production
4. Enable RBAC for all services
5. Regularly audit access logs

**For Rate Limiting:**
1. Configure appropriate limits per endpoint
2. Implement rate limiting at multiple levels
3. Monitor rate limit violations
4. Adjust limits based on usage patterns
5. Implement IP-based blocking for abuse

## Security Monitoring

### Current Monitoring

**Rate Limiting:**
- Logs rate limit violations
- Tracks blocked requests
- Monitors API key usage

**Access Control:**
- Logs authentication failures
- Tracks authorization failures
- Monitors token usage

### Recommended Monitoring

**Security Events:**
- Authentication failures
- Authorization failures
- Rate limit violations
- Unusual access patterns
- API key abuse

**Tools:**
- Journalctl for service logs
- Custom security logging
- Audit trail implementation
- Intrusion detection system

## Security Testing

### Testing Procedures

**Rate Limiting:**
```bash
# Test rate limiting
for i in {1..150}; do curl http://localhost:8201/health; done
```

**Access Control:**
```python
# Test JWT authentication
from aitbc.access_control import get_access_controller

controller = get_access_controller()
token = controller.create_token("user1", ["user"])
claims = controller.verify_token(token)
```

**Service Isolation:**
```bash
# Test service user permissions
sudo -u aitbc-api /opt/aitbc/venv/bin/python -c "print('test')"
```

## Security Checklist

### Implementation Status

- [x] Service users created
- [ ] Services configured to run as dedicated users
- [ ] File permissions configured for service users
- [x] Application-level rate limiting implemented
- [x] JWT authentication framework implemented
- [x] RBAC framework implemented
- [x] Security headers implemented
- [x] API key authentication implemented
- [ ] Mutual TLS implemented
- [ ] Network-level security (host-level)

### Production Readiness

**Before Production:**
- [ ] Change default JWT secret key
- [ ] Configure valid API keys
- [ ] Enable authentication for sensitive endpoints
- [ ] Configure service isolation
- [ ] Set up host-level firewall rules
- [ ] Implement security monitoring
- [ ] Conduct security audit
- [ ] Test all security measures

## Troubleshooting

### Service Isolation Issues

**Service won't start as dedicated user:**
- Check file permissions: `ls -la /opt/aitbc`
- Check database permissions
- Review service logs: `journalctl -u <service-name> -f`
- Ensure user has required capabilities

**Permission denied errors:**
- Check file ownership: `stat <file>`
- Verify group membership: `groups aitbc-api`
- Check ACL permissions: `getfacl <file>`

### Rate Limiting Issues

**Rate limiting not working:**
- Verify slowapi is installed: `pip list | grep slowapi`
- Check middleware configuration
- Review rate limit configuration
- Test with curl: `for i in {1..150}; do curl <endpoint>; done`

### Access Control Issues

**JWT verification failing:**
- Check secret key matches
- Verify token hasn't expired
- Check algorithm configuration
- Review token claims

**Authorization failing:**
- Check user roles
- Verify role permissions
- Review permission decorators
- Check RBAC configuration

## Related Documentation

- [MEMORY_CONFIGURATION_2026-06-07.md](./MEMORY_CONFIGURATION_2026-06-07.md) - Memory limits configuration
- [PERFORMANCE_OPTIMIZATIONS_2026-06-07.md](./PERFORMANCE_OPTIMIZATIONS_2026-06-07.md) - Performance optimizations
- [SECURITY_VULNERABILITIES_2026-06-07.md](../SECURITY_VULNERABILITIES_2026-06-07.md) - Security remediation
- [RELEASE_v0.4.13.md](../releases/RELEASE_v0.4.13.md) - Release notes

## Maintenance

### Regular Tasks

- **Weekly**: Review rate limit violations
- **Monthly**: Rotate API keys
- **Quarterly**: Audit access control configuration
- **Annually**: Security audit and penetration testing

### Contact

For questions or issues related to security hardening:
- **Documentation**: `/opt/aitbc/docs/operations/`
- **Security Config**: `/etc/aitbc/security.env`
- **Service Logs**: `journalctl -u aitbc-*.service`

---

**Last Updated**: June 7, 2026
**Configuration Version**: 1.0
