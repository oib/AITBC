# Security Documentation

This directory contains security best practices and guidelines for deploying and operating the AITBC platform.

## Core Security Guides

- [API Key Management](api-key-management.md) - Key generation, storage, and rotation
- [Password Policies](password-policies.md) - Password requirements and hashing
- [SSL/TLS Configuration](ssl-tls-configuration.md) - Certificate management and TLS setup
- [Firewall Rules](firewall-rules.md) - UFW and iptables configuration
- [Network Security](network-security.md) - Network segmentation and VPN access
- [Database Security](database-security.md) - PostgreSQL security and backup encryption
- [Secret Management](secret-management.md) - Environment variables and secret storage
- [Access Control](access-control.md) - RBAC and principle of least privilege
- [Input Validation](input-validation.md) - Input validation and sanitization
- [Web Security](web-security.md) - XSS, CSRF, and SQL injection prevention
- [Output Encoding](output-encoding.md) - Safe output handling
- [Authentication](authentication.md) - MFA, session management, and JWT security
- [Rate Limiting](rate-limiting.md) - Token bucket algorithm and IP-based limiting
- [Logging and Monitoring](logging-monitoring.md) - Security logging and intrusion detection
- [Incident Response](incident-response.md) - Incident response procedures
- [Security Audits](security-audits.md) - Regular audits and compliance
- [Vulnerability Scanning](vulnerability-scanning.md) - Dependency and code scanning

## Additional Security Documentation

- [✅ Environment Configuration Security - COMPLETED](CONFIGURATION_SECURITY_FIXED.md)
- [✅ Helm Values Secret References - COMPLETED](HELM_VALUES_SECURITY_FIXED.md)
- [Infrastructure Security Fixes - Critical Issues Identified](INFRASTRUCTURE_SECURITY_FIXES.md)
- [🚀 Package Publishing Security Guide](PUBLISHING_SECURITY_GUIDE.md)
- [AITBC Agent Wallet Security Model](SECURITY_AGENT_WALLET_PROTECTION.md)
- [Critical Wallet Security Fixes - Implementation Summary](WALLET_SECURITY_FIXES_SUMMARY.md)
- [Security Scanning Implementation - COMPLETED](security-scanning-implementation-completed.md)

## Policies

See [policies/](policies/) for project policies and procedures.
