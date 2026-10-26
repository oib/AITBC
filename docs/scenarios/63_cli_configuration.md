# CLI Configuration and Profiles

**Level**: Beginner
**Prerequisites**: Scenario 01 Wallet Basics
**Estimated Time**: 15 minutes
**Last Updated**: 2026-10-25
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > CLI Configuration

---

## See Also

- **Previous Scenario**: [Inter-Chain Trading](./62_interchain_trade.md)
- **Next Scenario**: [Operations Admin](./64_operations_admin.md)
- **Feature Documentation**: `cli/aitbc_cli/commands/config.py`

---

## Scenario Overview

> **Live vs. simulated:** `aitbc config` only touches the local CLI config
> files (project `.aitbc/config.yaml` and the global config, see
> `config path`). Nothing reaches the chain or a service — except that
> later commands read the values you set.

This scenario covers the `aitbc config` leaves not already played in
scenarios 30/32 (`show`, `set`, `path`, `check`, `check-keys`): single-key
reads and writes, export/import, environments, profiles, secrets, and
validation.

### Use Case

An operator keeps per-environment CLI settings (different hub URLs, chain
ids, output formats), snapshots them into profiles, and audits secrets
storage without leaking values.

### What You'll Learn

- Reading and writing config keys (`get`, `set`, `unset`, `edit`, `reset`)
- Moving config between machines (`export`, `import-config`)
- Named profiles (`profiles save`, `list`, `load`, `delete`)
- Secret keys (`set-secret`, `get-secret`) vs. plain keys
- Sanity checks (`validate`, `environments`)

---

## Prerequisites

- `aitbc` on `$PATH`; no node or service required

---

## Steps

### 1. Read config

```bash
aitbc config path                 # where the files live (played in scenario 30)
aitbc config show                 # played in scenarios 30/32
aitbc config get                  # dump effective config
aitbc config get coordinator_url
aitbc config get --global         # global file only
```

### 2. Write and remove keys

```bash
aitbc config set --key output_format --value table   # played in 07/25/34
aitbc config unset --key output_format          # remove a key
aitbc config edit                               # open the file in $EDITOR
```

`unset`/`edit`/`reset` mutate the local config. `aitbc config reset`
(optionally `--global`) restores
defaults — destructive to local settings; use `--global` deliberately and
note that it does not touch chain or service state.

### 3. Export / import

```bash
aitbc config export --format yaml
aitbc config export --format json --global
aitbc config import-config --file-path ./config-backup.yaml
aitbc config import-config --file-path ./config-backup.yaml --merge --global
```

Without `--merge`, `import-config` replaces the target config — take the
`export` snapshot first.

### 4. Environments and validation

```bash
aitbc config environments
aitbc config validate
```

`environments` lists the known environment names; `validate` reports
malformed keys and values.

### 5. Profiles

```bash
aitbc config profiles save --name hub
aitbc config profiles list
aitbc config profiles load --name hub
```

`aitbc config profiles delete --name hub` removes a saved profile —
destructive to the snapshot only; needs the operator's line if the profile
is shared.

### 6. Secrets

```bash
aitbc config set-secret --key api_token --value <secret>
aitbc config get-secret --key api_token
```

Secrets go through the CLI's secret store rather than the plain config
file. Never commit a file produced by `config export` if it may contain
resolved secrets — check with `config check-keys` (scenario 32).

<!-- COVERAGE-LEFT-1: bootstrap-env leaf (issue #445) -->

### 7. Bootstrap a starter env file

`aitbc bootstrap bootstrap-env` writes a starter `.env` template to
`--output` (default `.env` in the current directory); a local file write
only, nothing is sourced or applied:

```bash
aitbc bootstrap bootstrap-env --output /tmp/aitbc-bootstrap.env
```

Review the generated file before copying any line into a real
`/etc/aitbc/*.env` — applying it is an env edit; not played, needs the
operator's line.

---

## Cost Table

| Step | Spend |
|---|---|
| Entire scenario | 0 AIT — local files only |

---

## Verification

- `aitbc config validate` clean after `import-config`.
- `aitbc config profiles list` shows saved profiles; `load` restores the
  snapshot exactly (verify with `config get`).

## Troubleshooting

- `config get-secret` errors — the secret backend is not initialised on
  this host; `set-secret` first or fall back to a plain `config set`.
