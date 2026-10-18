# Security documentation

Start with the [security overview](SECURITY.md) — it summarizes the actual
posture and links the policies. The former generic checklists (RBAC,
password rules, input encoding, …) were boilerplate and were removed;
what remains is AITBC-specific.

## Operational hardening guides

- [API key management](api-key-management.md) — key generation, storage, rotation
- [Firewall rules](firewall-rules.md) — UFW/iptables configuration
- [Database security](database-security.md) — PostgreSQL hardening and backup encryption
- [SSL/TLS configuration](ssl-tls-configuration.md) — certificate management
- [Incident response](incident-response.md) — incident procedures
- [Vulnerability scanning](vulnerability-scanning.md) — dependency and code scanning
- [Dependency monitoring](DEPENDENCY_MONITORING.md)

## Architecture and models

- [Security architecture](2_security-architecture.md)
- [Threat model](threat-model.md) and
  [bridge threat model](../architecture/bridge-threat-model.md)
- [Bridge custodian](bridge-custodian.md) — payout wallet, envelope model
- [Key escrow threshold](KEY-ESCROW-THRESHOLD.md)

## Audits and findings

- [Security audit summary](../archive/security/security_audit_summary.md)
- [CLI audit findings](aitbc-audit-4-cli-findings.md)
- [Audit framework](4_security-audit-framework.md)
- [Chaos testing](3_chaos-testing.md)
- [Remediation plan](../archive/security/remediation-plan.md) and
  [testing procedures](../archive/security/testing-procedures.md)
- [Fixes summary](../archive/security/SECURITY_FIXES_SUMMARY.md),
  [cleanup guide](../archive/security/1_security-cleanup-guide.md),
  [audit findings](../archive/security/audit-findings.md)

## Wallets and economics

- [Agent wallet protection](SECURITY_AGENT_WALLET_PROTECTION.md)
- [Wallet security fixes summary](../archive/security/WALLET_SECURITY_FIXES_SUMMARY.md)
- [Economic analysis](economic-analysis.md),
  [performance features](performance-features.md)

See also [policies/](policies/) for project policies.
