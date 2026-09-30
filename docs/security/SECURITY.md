# Security overview

AITBC's security posture in one page: what protects what, where the real
policies live, and where the gaps are tracked. The generic checklists that
previously filled this directory were boilerplate — they are gone; this
page and the documents it links are the current reference.

## Reporting

Report vulnerabilities privately to the operator before any public
disclosure. Do not open a public issue for a suspected vulnerability.

## Secrets and keys

- The repository carries **no secrets**: no tokens, private keys, wallet
  secrets, or API credentials — see the "No secrets in the repo" section
  of [AGENTS.md](../../AGENTS.md), including the leak/rotation procedure.
- Service secrets live in `/etc/aitbc/*.env` on the node that uses them,
  systemd `EnvironmentFile`-loaded, root-readable only.
- The bridge payout account is a dedicated hot wallet with a bounded
  float — manual sends are forbidden; every payout goes through the
  monitor ledger. See [bridge custodian](bridge-custodian.md) and the
  AGENTS.md bridge section.

## How authentication actually works

- **Chain transactions**: secp256k1 wallet signatures over the
  canonical transaction payload; v9 adds an authorization policy
  (signature + type allowlist) currently in shadow evaluation.
- **Island gossip**: restricted topics require validator signatures;
  subscription/heartbeat routes require a peer key bound to the joining
  `node_id` (`/rpc/join` issues it).
- **Coordinator API**: JWT (setup generates `JWT_SECRET`/`SECRET_KEY`).
- **Miner endpoints**: `MinerDep` API key; exchange admin routes carry
  `EXCHANGE_API_KEY`/webhook secrets.
- **TLS**: the hub terminates TLS at the edge; node-to-node gossip and
  RPC are otherwise plain HTTP on the internal/LAN side.

## Threat model and audits

- [Threat model](threat-model.md) and the
  [bridge threat model](../architecture/bridge-threat-model.md) —
  including the payout-monitor vectors (envelope nonce collision,
  head-of-line blocking, dust/funding confusion, hot-key exposure).
- Audits and findings: [audit summary](security_audit_summary.md),
  [vulnerability report](SECURITY_VULNERABILITY_REPORT.md),
  [CLI audit findings](aitbc-audit-4-cli-findings.md),
  [audit framework](4_security-audit-framework.md),
  [chaos testing](3_chaos-testing.md),
  [remediation plan](remediation-plan.md) +
  [testing procedures](testing-procedures.md).

## Operational hardening

- [API key management](api-key-management.md),
  [firewall rules](firewall-rules.md),
  [database security](database-security.md),
  [SSL/TLS configuration](ssl-tls-configuration.md),
  [incident response](incident-response.md),
  [vulnerability scanning](vulnerability-scanning.md),
  [dependency monitoring](DEPENDENCY_MONITORING.md).
- Wallet specifics:
  [agent wallet protection](SECURITY_AGENT_WALLET_PROTECTION.md),
  [wallet fixes summary](WALLET_SECURITY_FIXES_SUMMARY.md),
  [key escrow threshold](KEY-ESCROW-THRESHOLD.md).
