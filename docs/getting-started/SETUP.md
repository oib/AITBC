# AITBC Setup Guide

**Last Updated:** 2026-08-24
**Version:** 2.1 (Canonical Gitea source, remote-installer confirmation)

Quick reference guide for AITBC setup and onboarding.

> **⚠️ v0.4.26 Update**: JWT authentication is now required. `setup.sh` automatically generates `JWT_SECRET` and `SECRET_KEY`. If upgrading from an earlier version, run `/opt/aitbc/scripts/utils/load-keystore-secrets.sh` after updating the credential files.

## `/var/lib/aitbc` must be writable by the `aitbc` group

`aitbc/auth/api_key.py` stores API keys at `/var/lib/aitbc/api_keys.json` (override with
`API_KEY_STORAGE_PATH`) and takes a file lock on `<path>.lock` beside it. `filelock` **unlinks
that lock on release**, so it is created fresh on every acquisition — which needs write
permission on the *directory*, not just on `api_keys.json`.

`APIKeyManager()` is instantiated at module scope in `aitbc.auth`, so if the directory is not
writable, every service that imports it dies during import and systemd restart-loops it. This
took down coordinator-api, pool-hub, gpu, marketplace and trading at once.

```bash
sudo chown root:aitbc /var/lib/aitbc && sudo chmod 2775 /var/lib/aitbc
```

`setup.sh` now sets this and verifies it; `keystore/` and `credentials/` stay `root:root 700`,
so the group on the parent does not expose them.

## Database migrations

`update.sh` runs `alembic upgrade head` for every `apps/*/alembic.ini` whose unit is linked,
stopping each service around its own migration — a SQLite column conversion rebuilds the table,
which is not safe under a process holding the file open.

**blockchain-node is skipped unless you pass `DATABASE_URL`.** It keeps one database per island
under `/var/lib/aitbc/data/<island>/chain.db`, while its Alembic default is
`/var/lib/aitbc/data/chain.db` — a file no running node uses. Migrate each island explicitly,
with the node stopped:

```bash
sudo systemctl stop aitbc-blockchain-node aitbc-blockchain-rpc
sudo DATABASE_URL=sqlite:////var/lib/aitbc/data/<island>/chain.db \
  /opt/aitbc/venv/bin/alembic -c /opt/aitbc/apps/blockchain-node/alembic.ini upgrade head
sudo systemctl start aitbc-blockchain-node aitbc-blockchain-rpc
```

Every `env.py` prints its resolved target to stderr before doing anything. Read that line
before letting a migration proceed — it is the only thing that tells you which file you are
about to rewrite.

## Documentation Structure

This guide has been split into topic-focused files for easier navigation:

### Core Topics

- **[Quick Start](./setup-quick-start.md)** - 5-minute quick start, install profiles, and node profiles
- **[Service Selection](./setup-service-selection.md)** - Role-based service selection and backup service
- **[Subscription System](./setup-subscription.md)** - Lease-based subscription system and sync modes
- **[Configuration](./setup-configuration.md)** - Runtime directories, secrets, and per-service environment files
- **[Security](./setup-security.md)** - Service user security configuration
- **[Reference](./setup-reference.md)** - Essential links, common commands, and troubleshooting

## Quick Navigation

**For New Users:**

1. Start with [Quick Start](./setup-quick-start.md)
2. Review [Service Selection](./setup-service-selection.md) for your node type
3. Configure [Subscription System](./setup-subscription.md) if joining as follower

**For Configuration:**

1. Check [Configuration](./setup-configuration.md) for runtime directories
2. Review [Security](./setup-security.md) for service user setup
3. See [Reference](./setup-reference.md) for common commands

**For Troubleshooting:**

- See [Reference](./setup-reference.md#troubleshooting) for common issues and solutions

## Agent / IDE assistant quick reference

After you know a node's role, dump only the MCP tools that matter for it so an agent's context window is not swamped by the full 216-tool list:

```bash
# Replace <role> with hub, customer, shop, follower, customer2, or follower2
/opt/aitbc/scripts/dump_mcp_tools.py --role <role> --output mcp-tools.md
```

- `--include-generic` adds the tools that work on every role (e.g. blockchain height, node status).
- `--read-only` or `--destructive` further narrows the list.
- `--filter "wallet|gpu"` matches name, description, or tags with a regex.

For an unfiltered reference, omit `--role`.

## Follower Node Quick Setup

For a follower node joining an open island (e.g. `hub.aitbc.bubuit.net`):

```bash
sudo /opt/aitbc/scripts/deployment/setup.sh \
  --open-island https://hub.aitbc.bubuit.net \
  --node-id <unique-node-id>
```

Use the hub **base URL** (`https://...`) without a trailing `/rpc` path — the sync code appends `/rpc/head` at runtime. To re-run setup on an existing install, add `--force`. To clone from a specific URL, add `--remote URL`. To clone from the canonical operator Gitea repo, add `--gitea` (or `--gitea https://your-gitea.example.com/oib/aitbc.git` for a private instance).

`setup.sh` now:

- Defaults to the public GitHub mirror `https://github.com/oib/AITBC.git` so new installations work without access to the private Gitea.
- Clones from the canonical Gitea repo with `--gitea` (default: `https://gitea.bubuit.net/oib/AITBC.git`) for operator nodes.
- Adds both `github` and `gitea` named remotes so either can be used later.
- Downloads any remote installer (NodeSource, etc.) to a temp file, prints its
  line count and SHA-256, and requires operator confirmation before running it.
- Sets `DEFAULT_PEER_RPC_URL` to the hub for follower profiles.
- Creates missing `/etc/aitbc/<unit>.env` files required by `EnvironmentFile=/etc/aitbc/%N.env`.
- Installs the `filelock` package if the selected profile omits it.
- Handles `set -e` safely during service counting and PostgreSQL database checks.

See [setup-reference.md](./setup-reference.md) for troubleshooting.

---

**Note**: This file has been split into topic-focused files for easier navigation. See the [Documentation Structure](#documentation-structure) section above for links to the individual topic files.
