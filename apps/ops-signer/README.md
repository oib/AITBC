# aitbc-ops-signer

Bounded, allow-listed payment signer for agent-initiated spends —
rollout step 3 of [docs/design/node-held-wallet-access.md](../../docs/design/node-held-wallet-access.md) (SEC-1).

The service listens on a unix socket (default
`/run/aitbc-ops-signer.sock`, mode 0660, group `aitbc-ops`) and accepts
exactly one request:

```json
{"op": "sign_payment", "to": "0x…", "amount_units": 360000, "memo": "S-10", "dry_run": false}
```

Replies `{ok, result, tx_hash|reason}` where `result` is `signed`,
`dry_run_pass`, `refused` (+ `reason`), or `error`. It never returns a
key, a password, or a signed blob.

## Policy (enforced inside the service, not by the caller)

- recipient must be in the allow-list file (`OPS_SIGNER_ALLOW_FILE`,
  default `/etc/aitbc/ops-signer.allow`: one `0x…` per line, `#`
  comments; a malformed line refuses the whole file);
- `amount_units` positive integer, ≤ `OPS_MAX_PER_TX` (default
  36,000,000 = 1 AIT);
- rolling 24 h total ≤ `OPS_MAX_PER_DAY` (default 180,000,000 = 5 AIT),
  kept in a local sqlite counter under `BEGIN IMMEDIATE` so two
  concurrent requests cannot both pass;
- `memo` required, pattern `^[A-Z]{1,8}-[0-9]{1,4}$` (a task id);
- peer must be uid 0 or in group `OPS_SIGNER_GROUP` (default
  `aitbc-ops`) via `SO_PEERCRED`;
- `dry_run: true` runs all checks and reports the verdict without
  signing, sending, or consuming day headroom.

The wallet password is read only from the systemd credential
`ops-wallet-pass` in `$CREDENTIALS_DIRECTORY` — never env, argv, or
logs. A missing credential makes signing refuse, not start.

## Flag

The service is inert unless `AITBC_OPS_SIGNER_ENABLED=true`. Off by
default: shipped code, nothing installed, nothing running.

## Audit

Append-only `OPS_AUDIT_LOG` (default
`/var/lib/aitbc/ops-signer-audit.log`): time, memo, recipient, amount,
result, reason, tx hash, peer uid. No key material.

## Operator rollout

See [docs/ops/ops-signer-runbook.md](../../docs/ops/ops-signer-runbook.md)
for wallet creation, funding, credential, allow-list, unit install,
canary, dry-run and rollback — all operator-owned steps.
