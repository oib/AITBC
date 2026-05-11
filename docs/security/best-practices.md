# Security Best Practices Guide

This guide covers security best practices for deploying and operating the AITBC platform.

## Table of Contents

- [API Key Management](#api-key-management)
- [Password Policies](#password-policies)
- [SSL/TLS Configuration](#ssltls-configuration)
- [Firewall Rules](#firewall-rules)
- [Network Security](#network-security)
- [Database Security](#database-security)
- [Secret Management](#secret-management)
- [Access Control](#access-control)
- [Input Validation](#input-validation)
- [Output Encoding](#output-encoding)
- [SQL Injection Prevention](#sql-injection-prevention)
- [XSS Prevention](#xss-prevention)
- [CSRF Protection](#csrf-protection)
- [Rate Limiting](#rate-limiting)
- [Authentication Best Practices](#authentication-best-practices)
- [Logging and Monitoring](#logging-and-monitoring)
- [Incident Response](#incident-response)
- [Security Audits](#security-audits)
- [Penetration Testing](#penetration-testing)
- [Vulnerability Scanning](#vulnerability-scanning)

## API Key Management

### Key Generation

```python
import secrets
import string

def generate_api_key():
    """Generate a secure API key"""
    alphabet = string.ascii_letters + string.digits
    return 'aitbc_' + ''.join(secrets.choice(alphabet) for _ in range(40))
```

### Key Storage

- Never store API keys in code
- Use environment variables or secret management systems
- Rotate keys regularly (every 90 days)
- Use different keys for different environments

```bash
# Environment variable
export AITBC_API_KEY="your-api-key"

# Or use secret management
aws secretsmanager get-secret-value --secret-id aitbc-api-key
```

### Key Rotation

```python
# Rotate API keys
old_key = "old-key"
new_key = generate_api_key()

# Update database
update_api_key(old_key, new_key)

# Invalidate old key
invalidate_api_key(old_key)
```

## Password Policies

### Password Requirements

- Minimum length: 16 characters
- Include uppercase, lowercase, numbers, special characters
- No common words or patterns
- Change every 90 days
- No reuse of previous 10 passwords

### Password Hashing

```python
import bcrypt

def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt)

def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed)
```

### Password Storage

- Never store passwords in plain text
- Use bcrypt or Argon2 for hashing
- Use unique salt for each password
- Never log passwords

## SSL/TLS Configuration

### Certificate Management

```bash
# Generate self-signed certificate (development only)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/ssl/private/aitbc.key \
  -out /etc/ssl/certs/aitbc.crt

# Use Let's Encrypt (production)
certbot --nginx -d your-domain.com
```

### TLS Configuration

```nginx
# Nginx TLS configuration
ssl_protocols TLSv1.2 TLSv1.3;
ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256';
ssl_prefer_server_ciphers off;
ssl_session_cache shared:SSL:10m;
ssl_session_timeout 10m;
```

### Certificate Rotation

```bash
# Auto-renew Let's Encrypt certificates
certbot renew --quiet --deploy-hook "systemctl reload nginx"

# Monitor certificate expiration
certbot certificates
```

## Firewall Rules

### UFW Configuration

```bash
# Default policies
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH
sudo ufw allow 22/tcp

# Allow AITBC services
sudo ufw allow 8080/tcp  # Blockchain
sudo ufw allow 8011/tcp  # Coordinator
sudo ufw allow 8071/tcp  # Wallet
sudo ufw allow 8102/tcp  # Marketplace

# Enable firewall
sudo ufw enable
```

### iptables Configuration

```bash
# Block all incoming except specific ports
iptables -P INPUT DROP
iptables -A INPUT -i lo -j ACCEPT
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A INPUT -p tcp --dport 22 -j ACCEPT
iptables -A INPUT -p tcp --dport 8080 -j ACCEPT
iptables -A INPUT -p tcp --dport 8011 -j ACCEPT
iptables -A INPUT -p tcp --dport 8071 -j ACCEPT
iptables -A INPUT -p tcp --dport 8102 -j ACCEPT
```

## Network Security

### Network Segmentation

```
Internet
    |
    v
[DMZ] - Public Services (Load Balancer, Nginx)
    |
    v
[Internal] - Application Services
    |
    v
[Database] - PostgreSQL, Redis
```

### VPN Access

```bash
# Configure WireGuard VPN
wg genkey | tee privatekey | wg pubkey > publickey

# Configure server
[Interface]
PrivateKey = YOUR_PRIVATE_KEY
Address = 10.0.0.1/24
ListenPort = 51820

[Peer]
PublicKey = CLIENT_PUBLIC_KEY
AllowedIPs = 10.0.0.2/32
```

### Private Networks

```bash
# Configure private network for multi-node deployment
# Use VPN or private VPC
# Restrict access to specific IP ranges
```

## Database Security

### PostgreSQL Security

```sql
-- Create dedicated user
CREATE USER aitbc WITH PASSWORD 'secure-password';

-- Grant minimum privileges
GRANT CONNECT ON DATABASE aitbc TO aitbc;
GRANT USAGE ON SCHEMA public TO aitbc;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO aitbc;

-- Enable SSL
ALTER SYSTEM SET ssl = 'on';
ALTER SYSTEM SET ssl_cert_file = '/etc/ssl/certs/postgresql.crt';
ALTER SYSTEM SET ssl_key_file = '/etc/ssl/private/postgresql.key';
```

### Connection Security

```python
# Use SSL for database connections
DATABASE_URL = "postgresql://user:pass@localhost:5432/aitbc?sslmode=require"

# Connection pooling with SSL
engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    ssl={'sslmode': 'require'}
)
```

### Backup Encryption

```bash
# Encrypt database backups
pg_dump aitbc | gpg --encrypt --recipient admin@aitbc.dev > backup.sql.gpg

# Decrypt backup
gpg --decrypt backup.sql.gpg > backup.sql
```

## Secret Management

### Environment Variables

```bash
# Never commit secrets to git
echo ".env" >> .gitignore

# Use .env files
echo "DATABASE_PASSWORD=secure-password" >> .env
```

### HashiCorp Vault

```bash
# Install Vault
wget -O- https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg

# Store secrets
vault kv put secret/aitbc/database password="secure-password"

# Retrieve secrets
vault kv get -field=password secret/aitbc/database
```

### AWS Secrets Manager

```python
import boto3

def get_secret(secret_name):
    """Retrieve secret from AWS Secrets Manager"""
    client = boto3.client('secretsmanager')
    response = client.get_secret_value(SecretId=secret_name)
    return response['SecretString']
```

## Access Control

### Role-Based Access Control (RBAC)

```python
from enum import Enum

class Role(Enum):
    ADMIN = "admin"
    USER = "user"
    MINER = "miner"
    GUEST = "guest"

def check_permission(user_role: Role, required_role: Role) -> bool:
    """Check if user has required permission"""
    role_hierarchy = {
        Role.ADMIN: 4,
        Role.MINER: 3,
        Role.USER: 2,
        Role.GUEST: 1
    }
    return role_hierarchy[user_role] >= role_hierarchy[required_role]
```

### Principle of Least Privilege

```python
# Grant minimum required permissions
def get_job(job_id: str, user_role: Role):
    """Get job with permission check"""
    if not check_permission(user_role, Role.USER):
        raise PermissionError("Insufficient permissions")
    return job_service.get_job(job_id)
```

### Service Accounts

```python
# Use service accounts for inter-service communication
SERVICE_ACCOUNT_KEY = "service-account-key"

def authenticate_service_account(key: str) -> bool:
    """Authenticate service account"""
    return key == SERVICE_ACCOUNT_KEY
```

## Input Validation

### Validate All Inputs

```python
from pydantic import BaseModel, validator

class JobCreate(BaseModel):
    payload: dict
    ttl_seconds: int
    
    @validator('ttl_seconds')
    def validate_ttl(cls, v):
        if v < 1 or v > 86400:
            raise ValueError('TTL must be between 1 and 86400 seconds')
        return v
    
    @validator('payload')
    def validate_payload(cls, v):
        if not isinstance(v, dict):
            raise ValueError('Payload must be a dictionary')
        if 'model' not in v:
            raise ValueError('Payload must include model field')
        return v
```

### Sanitize User Input

```python
import re

def sanitize_input(input_string: str) -> str:
    """Sanitize user input"""
    # Remove dangerous characters
    sanitized = re.sub(r'[<>"\']', '', input_string)
    # Limit length
    return sanitized[:1000]
```

### Type Checking

```python
from typing import Any

def validate_type(value: Any, expected_type: type) -> bool:
    """Validate value type"""
    return isinstance(value, expected_type)
```

## Output Encoding

### Encode Output

```python
import html

def encode_output(output: str) -> str:
    """Encode output to prevent XSS"""
    return html.escape(output)
```

### JSON Encoding

```python
import json

def safe_json_serialize(data: dict) -> str:
    """Safely serialize to JSON"""
    return json.dumps(data, default=str)
```

### File Download Security

```python
from pathlib import Path

def safe_file_download(file_path: Path) -> bool:
    """Validate file download request"""
    # Prevent directory traversal
    resolved_path = file_path.resolve()
    base_dir = Path("/safe/directory").resolve()
    
    if not str(resolved_path).startswith(str(base_dir)):
        return False
    
    # Check file extension
    allowed_extensions = {'.txt', '.json', '.csv'}
    if file_path.suffix not in allowed_extensions:
        return False
    
    return True
```

## SQL Injection Prevention

### Parameterized Queries

```python
from sqlmodel import Session, select

# Safe: parameterized query
def get_job_safe(session: Session, job_id: str):
    statement = select(Job).where(Job.id == job_id)
    return session.exec(statement).first()

# Unsafe: string concatenation (NEVER DO THIS)
def get_job_unsafe(session: Session, job_id: str):
    query = f"SELECT * FROM job WHERE id = '{job_id}'"  # VULNERABLE
    return session.exec(query).first()
```

### ORM Usage

```python
# Use ORM instead of raw SQL
def create_job_safe(session: Session, job_data: dict):
    job = Job(**job_data)
    session.add(job)
    session.commit()
    return job
```

### Input Sanitization

```python
def sanitize_sql_input(input_string: str) -> str:
    """Sanitize SQL input"""
    # Remove SQL keywords
    sql_keywords = ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'DROP', 'UNION']
    for keyword in sql_keywords:
        input_string = input_string.replace(keyword, '')
    return input_string
```

## XSS Prevention

### Content Security Policy

```http
# HTTP header
Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'
```

### Output Encoding

```python
import markupsafe

def safe_render_template(template: str, context: dict) -> str:
    """Safely render template"""
    return markupsafe.escape(template.format(**context))
```

### Input Sanitization

```python
import bleach

def sanitize_html(html: str) -> str:
    """Sanitize HTML input"""
    return bleach.clean(html, tags=['p', 'br', 'strong', 'em'], strip=True)
```

## CSRF Protection

### CSRF Tokens

```python
import secrets
from fastapi import Request

def generate_csrf_token() -> str:
    """Generate CSRF token"""
    return secrets.token_urlsafe(32)

def validate_csrf_token(request: Request, token: str) -> bool:
    """Validate CSRF token"""
    session_token = request.session.get('csrf_token')
    return secrets.compare_digest(session_token, token)
```

### SameSite Cookies

```python
from fastapi import Response

response = Response()
response.set_cookie(
    key="session",
    value="session-value",
    httponly=True,
    secure=True,
    samesite="strict"
)
```

## Rate Limiting

### Token Bucket Algorithm

```python
import time
from collections import defaultdict

class RateLimiter:
    def __init__(self, rate: int, per: int):
        self.rate = rate
        self.per = per
        self.tokens = defaultdict(lambda: rate)
        self.last_update = defaultdict(time.time)
    
    def allow(self, identifier: str) -> bool:
        now = time.time()
        elapsed = now - self.last_update[identifier]
        self.tokens[identifier] = min(self.rate, self.tokens[identifier] + elapsed * self.rate / self.per)
        self.last_update[identifier] = now
        
        if self.tokens[identifier] >= 1:
            self.tokens[identifier] -= 1
            return True
        return False
```

### IP-based Rate Limiting

```python
from fastapi import Request, HTTPException

rate_limiter = RateLimiter(rate=100, per=60)

@app.post("/v1/jobs")
async def submit_job(request: Request):
    client_ip = request.client.host
    if not rate_limiter.allow(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    # Process request
```

## Authentication Best Practices

### Multi-Factor Authentication (MFA)

```python
import pyotp

def generate_totp_secret() -> str:
    """Generate TOTP secret"""
    return pyotp.random_base32()

def verify_totp(secret: str, token: str) -> bool:
    """Verify TOTP token"""
    totp = pyotp.TOTP(secret)
    return totp.verify(token)
```

### Session Management

```python
import secrets
from datetime import datetime, timedelta

def create_session(user_id: str) -> dict:
    """Create session"""
    return {
        "session_id": secrets.token_urlsafe(32),
        "user_id": user_id,
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(hours=24)
    }

def validate_session(session: dict) -> bool:
    """Validate session"""
    return datetime.utcnow() < session["expires_at"]
```

### JWT Security

```python
import jwt
from datetime import datetime, timedelta

def generate_jwt(user_id: str, secret: str) -> str:
    """Generate JWT token"""
    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(hours=1),
        "iat": datetime.utcnow()
    }
    return jwt.encode(payload, secret, algorithm="HS256")

def verify_jwt(token: str, secret: str) -> dict:
    """Verify JWT token"""
    return jwt.decode(token, secret, algorithms=["HS256"])
```

## Logging and Monitoring

### Security Logging

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

### Audit Logging

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

### Intrusion Detection

```python
def detect_intrusion(user_id: str, action: str):
    """Detect suspicious activity"""
    # Check for unusual patterns
    if is_suspicious_activity(user_id, action):
        alert_security_team(user_id, action)
        lock_user_account(user_id)
```

## Incident Response

### Incident Response Plan

1. **Detection**: Identify security incident
2. **Containment**: Isolate affected systems
3. **Eradication**: Remove threat
4. **Recovery**: Restore systems
5. **Lessons Learned**: Document and improve

### Incident Response Checklist

```markdown
- [ ] Identify affected systems
- [ ] Isolate affected systems
- [ ] Preserve evidence
- [ ] Notify stakeholders
- [ ] Document timeline
- [ ] Implement fixes
- [ ] Test fixes
- [ ] Restore from backup
- [ ] Monitor for recurrence
- [ ] Conduct post-mortem
```

### Emergency Contacts

```bash
# Security team
SECURITY_TEAM_EMAIL="security@aitbc.dev"
SECURITY_TEAM_PHONE="+1-555-0100"

# Management
MANAGEMENT_EMAIL="management@aitbc.dev"

# Legal
LEGAL_EMAIL="legal@aitbc.dev"
```

## Security Audits

### Regular Audits

- Conduct quarterly security audits
- Review access logs monthly
- Audit code changes weekly
- Review third-party dependencies monthly

### Audit Checklist

```markdown
- [ ] Review user access
- [ ] Check for unused accounts
- [ ] Review API key usage
- [ ] Audit firewall rules
- [ ] Review SSL certificates
- [ ] Check for vulnerabilities
- [ ] Review logging configuration
- [ ] Test backup restoration
- [ ] Review incident response plan
```

### Compliance

- GDPR compliance
- SOC 2 Type II
- ISO 27001
- PCI DSS (if handling payments)

## Penetration Testing

### Testing Schedule

- Quarterly penetration testing
- Monthly vulnerability scanning
- Continuous security monitoring

### Testing Scope

- External penetration testing
- Internal security assessment
- Application security testing
- Network security testing

### Testing Tools

```bash
# OWASP ZAP
zap-cli quick-scan --self-contained http://localhost:8011

# Nmap
nmap -sV -sC localhost

# Nikto
nikto -h http://localhost:8011

# SQLMap
sqlmap -u "http://localhost:8011/v1/jobs" --dbs
```

## Vulnerability Scanning

### Dependency Scanning

```bash
# Python dependencies
pip-audit

# JavaScript dependencies
npm audit

# Container images
trivy image aitbc/coordinator-api:latest
```

### Code Scanning

```bash
# Bandit (Python)
bandit -r apps/

# ESLint (JavaScript)
eslint apps/

# Snyk
snyk test
```

### Remediation

```python
# Update dependencies
pip install --upgrade package-name

# Patch vulnerabilities
npm audit fix

# Rebuild images
docker build --no-cache .
```

## Production Checklist

### Pre-Deployment

```markdown
- [ ] Change all default passwords
- [ ] Remove test accounts
- [ ] Disable debug mode
- [ ] Enable SSL/TLS
- [ ] Configure firewall
- [ ] Set up monitoring
- [ ] Configure backups
- [ ] Review logs
- [ ] Test disaster recovery
- [ ] Document security procedures
```

### Post-Deployment

```markdown
- [ ] Monitor for anomalies
- [ ] Review security logs
- [ ] Test incident response
- [ ] Update documentation
- [ ] Train staff
- [ ] Schedule security reviews
```

## Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CIS Benchmarks](https://www.cisecurity.org/cis-benchmarks)
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework)
- [Security Guidelines](https://docs/deployment/security-guidelines.md)
