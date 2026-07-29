# Security Model

## Secrets

1. **No secrets in the repository, ever.** The `security-scan` gate blocks committed secrets;
   configuration files carry secret *references* (names), injected per environment.
2. **Agents do not see raw secrets** unless a human explicitly approves it for a specific task
   (`raw-secret-access` gate). Approval is per-task, never durable.
3. **Mediated access is the default.** The Secrets Adapter
   ([interface](../../profiles/neutral/adapters/secrets.md)) performs the privileged action itself and
   returns the outcome — the agent gets "deployed preview environment", not the token that did it.
4. Secret access is modeled in config (`security.secrets_adapter`, `mediated_access_only`) and
   every access/approval is logged as an audit event on the relevant ticket.

## Security-relevant work

Security-relevant tasks must involve the Security Agent or a security-review workflow step.
Triggers (via the ADR/Governance Checker + `config.security.review_triggers`):

- changes under auth/secret/credential paths (configurable glob list)
- changes to dependency manifests
- tickets labeled security
- new external system access, new adapters, new MCP grants
- anything the Review Agent flags as security-relevant during code review

The Security Agent's findings flow through the same review-followup chain as code review
findings; blocking security findings send tickets back to in-progress.

## Boundaries recap

Security-relevant human gates: `raw-secret-access`, plus the general boundaries in
[approval-boundaries.md](approval-boundaries.md) (deployments, merges). The Security Agent can
**block** (set tickets to blocked) but — like every agent — cannot accept ADRs, merge, or deploy.
