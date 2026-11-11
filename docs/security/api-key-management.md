# API Key Management

This guide covers how AITBC service API keys are actually generated, stored,
and revoked — the shared implementation is `aitbc/auth/api_key.py`
(`APIKeyManager`).

## Key generation

Keys are minted by `APIKeyManager.generate_api_key(user_id, permissions=None)`
— `secrets.token_urlsafe(32)` (~43 chars), **not** a custom `aitbc_` prefix:

```python
from aitbc.auth.api_key import get_api_key_manager

result = get_api_key_manager().generate_api_key("svc-name", permissions=["read"])
# result["api_key"] is the plaintext — shown once, never persisted
```

## Key storage

- Plaintext keys are **never persisted**. The store keeps only the SHA-256
  digest of each key.
- Digests live in `API_KEY_STORAGE_PATH` (default
  `/var/lib/aitbc/api_keys.json`, mode `0600`), protected by a
  `<storage>.lock` file lock and written atomically — a truncated write
  cannot erase the store (APIKEY-STORE-ATOMIC-1).
- Each entry records `user_id`, `permissions`, `created_at`, `last_used`,
  and `usage_count`.
- Service-to-service keys used by callers (e.g. `BLOCKCHAIN_RPC_API_KEY`,
  market `api_key`) are **env vars** in `/etc/aitbc/*.env` (mode `0600`),
  loaded via systemd `EnvironmentFile=` — a different mechanism from the
  digest store. The digest store is for keys the *services issue to
  callers*; env keys are the ones services *present*.

## Validation and revocation

```python
mgr = get_api_key_manager()
mgr.validate_api_key(key)   # -> {"status": "success", "valid": True, ...}
mgr.revoke_api_key(key)     # removes the digest; key stops working
```

There is no `update_api_key`/`invalidate_api_key` — rotation is
revoke-old + generate-new. Usage stats (`last_used`, `usage_count`) flush
periodically; treat them as approximate.

## Operational notes

- `APIKeyAuthenticator` (the FastAPI dependency most services use) compares
  the presented `X-Api-Key` header against the service's configured
  `api_key` env value with `hmac.compare_digest` — it does **not** consult
  the digest store. The digest store backs `aitbc.auth` login/API flows.
- When a service's `auth_enabled` setting is false the authenticator is a
  no-op; when `api_key` is unset, gated routes return `501`.
- Rotate env keys by editing the env file and restarting the unit
  (`systemctl restart <unit>`); rotate issued keys via
  `revoke_api_key` + `generate_api_key`.

## See also

- [Security overview](SECURITY.md) — the consolidated page that replaced the generic checklists
- [Security architecture](2_security-architecture.md) — where keys are checked per route
