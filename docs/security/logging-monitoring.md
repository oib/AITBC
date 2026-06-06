# Logging and Monitoring

This guide covers security logging, audit logging, and intrusion detection.

## Security Logging

```python
import logging

security_logger = logging.getLogger('security')

def log_security_event(event_type: str, details: dict):
    """Log security event"""
    security_logger.info({
        "event_type": event_type,
        "timestamp": datetime.utcnow().isoformat(),
        "details": details
    })
```

## Audit Logging

```python
def log_audit(action: str, user: str, resource: str):
    """Log audit event"""
    audit_logger.info({
        "action": action,
        "user": user,
        "resource": resource,
        "timestamp": datetime.utcnow().isoformat(),
        "ip_address": get_client_ip()
    })
```

## Intrusion Detection

```python
def detect_intrusion(user_id: str, action: str):
    """Detect suspicious activity"""
    # Check for unusual patterns
    if is_suspicious_activity(user_id, action):
        alert_security_team(user_id, action)
        lock_user_account(user_id)
```

## See Also

- [Incident Response](incident-response.md) - Response procedures
- [Security Audits](security-audits.md) - Audit procedures
- [Vulnerability Scanning](vulnerability-scanning.md) - Continuous monitoring
