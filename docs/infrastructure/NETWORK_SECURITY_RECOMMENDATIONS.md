# Network Security Recommendations for AITBC

**Last Updated:** June 2, 2026  
**Target Audience:** System Administrators

This document provides network security recommendations for AITBC deployments. These are recommendations for system administrators to implement - AITBC does not automate firewall configuration as this is infrastructure-level security.

## Overview

AITBC services run on the following ports:
- **8006** - Blockchain Node RPC
- **8011** - Coordinator API
- **8014** - Hermes Service
- **7070** - P2P Bind Port
- **5173** - Marketplace Web UI (development only)

## Firewall Recommendations

### Basic Firewall Rules

Using `ufw` (Ubuntu/Debian):

```bash
# Default deny incoming
sudo ufw default deny incoming

# Allow outgoing
sudo ufw default allow outgoing

# Allow SSH (adjust port as needed)
sudo ufw allow 22/tcp

# Allow AITBC services
sudo ufw allow 8006/tcp  # Blockchain Node RPC
sudo ufw allow 8011/tcp  # Coordinator API
sudo ufw allow 8014/tcp  # Hermes Service
sudo ufw allow 7070/tcp  # P2P Bind Port

# Enable firewall
sudo ufw enable
```

### Production Firewall Rules

For production deployments, restrict access to specific IP ranges:

```bash
# Allow SSH from specific management IPs
sudo ufw allow from 192.168.1.0/24 to any port 22

# Allow Blockchain Node RPC from trusted nodes only
sudo ufw allow from 10.0.0.0/8 to any port 8006

# Allow Coordinator API from application servers
sudo ufw allow from 10.0.1.0/24 to any port 8011

# Allow Hermes Service from agent servers
sudo ufw allow from 10.0.2.0/24 to any port 8014

# Allow P2P from blockchain network
sudo ufw allow from 10.0.0.0/8 to any port 7070
```

### Using `firewalld` (RHEL/CentOS):

```bash
# Add AITBC services
sudo firewall-cmd --permanent --add-port=8006/tcp
sudo firewall-cmd --permanent --add-port=8011/tcp
sudo firewall-cmd --permanent --add-port=8014/tcp
sudo firewall-cmd --permanent --add-port=7070/tcp

# Reload firewall
sudo firewall-cmd --reload
```

## TLS/SSL Recommendations

### Enable TLS for All Services

AITBC services should be configured with TLS in production:

**Coordinator API (8011):**
- Use reverse proxy (nginx/apache) with TLS termination
- Configure valid SSL certificates
- Enforce HTTPS only
- HSTS headers

**Blockchain Node RPC (8006):**
- Use TLS for RPC communication
- Configure client certificate authentication
- Disable HTTP in production

**Hermes Service (8014):**
- Enable TLS for agent communication
- Use mutual TLS for agent authentication

### Nginx Reverse Proxy Example

```nginx
server {
    listen 443 ssl http2;
    server_name api.aitbc.example.com;

    ssl_certificate /etc/ssl/certs/aitbc-api.crt;
    ssl_certificate_key /etc/ssl/private/aitbc-api.key;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    location / {
        proxy_pass http://localhost:8011;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## DDoS Protection Recommendations

### Rate Limiting

Configure rate limiting at the network level:

```nginx
# Nginx rate limiting
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;

server {
    location / {
        limit_req zone=api_limit burst=20 nodelay;
        proxy_pass http://localhost:8011;
    }
}
```

### Using Cloudflare or Similar Services

- Configure Cloudflare for DNS and DDoS protection
- Enable "Under Attack Mode" during attacks
- Use API Shield for API endpoint protection
- Configure rate limiting rules

### Local DDoS Mitigation

```bash
# Install fail2ban
sudo apt install fail2ban

# Configure /etc/fail2ban/jail.local
[aitbc-api]
enabled = true
port = 8011
filter = aitbc-api
logpath = /var/log/aitbc/coordinator-api.log
maxretry = 5
bantime = 3600
```

## Network Segmentation

### Recommended Network Layout

```
Management Network (192.168.1.0/24)
├── Bastion Host (SSH access)
├── Monitoring Server
└── Admin Workstations

Application Network (10.0.1.0/24)
├── Coordinator API Servers
├── Marketplace Service
└── Web UI Servers

Blockchain Network (10.0.0.0/8)
├── Blockchain Nodes
├── P2P Communication
└── RPC Endpoints

Agent Network (10.0.2.0/24)
├── Hermes Service
├── Agent Workers
└── GPU Providers
```

### VLAN Configuration

Configure VLANs to isolate network segments:

```bash
# Example using VLAN tagging
# Management VLAN 10
# Application VLAN 20
# Blockchain VLAN 30
# Agent VLAN 40
```

## Monitoring and Alerting

### Network Monitoring

Monitor for:
- Unusual traffic patterns
- Port scanning attempts
- DDoS attack indicators
- Failed authentication attempts

### Log Aggregation

Centralize logs for security analysis:

```bash
# Configure rsyslog to forward logs
*.* @@logserver.example.com:514
```

### Alerting

Set up alerts for:
- Firewall rule changes
- High connection rates
- Failed login attempts
- Unusual outbound traffic

## Additional Recommendations

### 1. Disable Unused Services

```bash
# Disable development web UI in production
sudo systemctl disable aitbc-marketplace-web

# Disable unused ports
sudo ufw deny 5173/tcp  # Development UI
```

### 2. Use VPN for Management Access

- Require VPN for SSH access
- Use MFA for VPN authentication
- Rotate VPN credentials regularly

### 3. Regular Security Audits

- Review firewall rules monthly
- Audit TLS certificates for expiration
- Review access logs weekly
- Update security recommendations quarterly

### 4. Network Time Protocol (NTP)

- Configure NTP for accurate time
- Use trusted NTP servers
- Monitor NTP service health

### 5. DNS Security

- Use DNSSEC if available
- Configure DNS filtering
- Monitor DNS queries for anomalies

## Security Checklist

- [ ] Firewall configured with default deny
- [ ] Only required ports open
- [ ] TLS enabled for all services
- [ ] Valid SSL certificates installed
- [ ] HSTS headers configured
- [ ] Rate limiting configured
- [ ] DDoS protection in place
- [ ] Network segmentation implemented
- [ ] Log aggregation configured
- [ ] Monitoring and alerting active
- [ ] VPN required for management access
- [ ] Regular security audits scheduled

## References

- [AITBC Security Hardening Guide](SECURITY_HARDENING.md)
- [SystemD Services Documentation](SYSTEMD_SERVICES.md)
- [Setup Documentation](../getting-started/SETUP.md)
