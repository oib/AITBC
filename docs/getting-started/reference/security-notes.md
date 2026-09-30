# Security notes

Baseline precautions for node operators. The consolidated reference is
[docs/security/SECURITY.md](../../security/SECURITY.md); the repository's
secret-handling rules are in the "No secrets in the repo" section of
[AGENTS.md](../../../AGENTS.md).

- Keep wallet private keys out of the repository, chat, and screenshots;
  a leaked key means the wallet, not a password reset.
- Services read secrets from `/etc/aitbc/*.env` — keep those files
  root-readable only, and never commit them.
- Use SSH keys for node access; disable password authentication.
- Restrict service ports to the interfaces they actually serve — the
  bind policy is enforced by `scripts/docs/check_bind_policy.py`.
- Chain reads are public by design; anything that mutates state requires
  a signature (wallet, peer key, or validator key depending on the path).
