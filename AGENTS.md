# AITBC workspace guide for agents

This file exists so future sessions do not accidentally edit the wrong copy of the repo.

## The AITBC sites and live nodes

| site / node | host / path | role | what to do here |
|---|---|---|---|
| **gitea** | `https://gitea.bubuit.net/oib/AITBC.git` (https) or `http://gitea.bubuit.net:3000/oib/aitbc.git` (http) | **primary source of truth** | fetch, push, fast-forward `main` / `release/v0.24.0` |
| **github** | `https://github.com/oib/AITBC.git` | public mirror, may lag behind gitea | **push only from IDE `/opt/aitbc` with the dedicated GitHub token**; live nodes do not store GitHub credentials and must not push to this remote |
| **hub.aitbc** | SSH `hub.aitbc` (`/opt/aitbc`) / `192.168.100.10` (reached via proxy) | **hub + customer (nogpu)** | full working repo; run hub services; live validation of AI jobs, escrow, marketplace; PBFT proposer |
| **hub2.aitbc** | SSH `hub2.aitbc` (`/opt/aitbc`) / `10.177.61.28` | **follower / customer replica + PBFT validator (nogpu)** | live deployment; run follower blockchain RPC/explorer and customer services; pull updates via gitea or bundle (do not commit/push here) |
| **node0** | SSH `node0` (`/opt/aitbc`) / `10.1.223.93` | **follower / customer (gpu)** | pure follower; `market_role=customer`, `enable_block_production=false`; safe for `update.sh` as customer |
| **node1** | SSH `node1` (`/opt/aitbc`) / `10.1.223.40` | **follower / customer + PBFT validator (gpu)** | `BLOCKCHAIN_MODE=follower`; Hermes installed but not currently running as a shop; PBFT block producer |
| **node2** | SSH `node2` (`/opt/aitbc`) / `10.1.223.136` | **follower / shop + PBFT validator (gpu)** | main shop node; runs Hermes, FFmpeg, Whisper, GPU miner, marketplace, pool hub; commit and push to gitea |
| **localhost (this IDE)** | `/home/oib/windsurf/aitbc` and `/opt/aitbc` | staging / IDE only | `/home/oib/windsurf/aitbc` is a partial staging checkout for notes and temporary scripts. `/opt/aitbc` is a non-active canonical clone (no `data/` or `venv/`, so no services run here); it is safe for gitea commits/pushes that do not require active node features. |

## Where the full repo lives

The canonical, full AITBC repository is only on the two remote nodes:

- `node2:/opt/aitbc`
- `hub.aitbc:/opt/aitbc`

Both remotes point to gitea as `origin`. `github` should remain a read-only reference on live nodes; the GitHub mirror is maintained from the IDE host `/opt/aitbc` using a dedicated, non-shared token.

> **Repository visibility note:** Gitea is the private, single-operator development repository. GitHub is the public mirror. AITBC software users other than the operator have no access to the Gitea instance, so deployment/setup scripts that must work for public users should continue to reference GitHub. Only the operator's live nodes and tooling should treat Gitea as the primary source of truth.
>
> **GitHub mirror policy (2026-08-24):** the public GitHub mirror is no longer pushed from `node2` or `hub.aitbc`. The only node that holds the GitHub token is the IDE host, in `/opt/aitbc`. Live nodes pull/fetch from Gitea and may keep a `github` remote for reference, but must not store GitHub credentials or push to GitHub.

`/home/oib/windsurf/aitbc` (this directory) is a partial local staging checkout used for notes, plans and temporary scripts.
`/opt/aitbc` on the IDE host is a canonical clone at gitea `main` and is intentionally non-active: its `data/` and `venv/` directories have been removed so no AITBC service can start from it. It can be used for reading code, running local static checks, and for gitea commits/pushes that do not require live services or production data. Live work must still use `node2` or `hub.aitbc`.

### Why keep a non-active `/opt/aitbc` clone on the IDE host?

A full, clean clone at `/opt/aitbc` is useful because it is:

- **A stable `main` reference** for reading the whole codebase with IDE index, search, go-to-definition, and diff tools, without waiting on SSH round-trips.
- **A local static-check runner** for `mypy`, `no_float_money.py`, OpenAPI drift checks, `pytest` dry-runs, and other read-only verification before changes are pushed to the live nodes.
- **A comparison baseline** against `node2` and `hub.aitbc` (`diff`, `rsync -n`, or `git diff /opt/aitbc <(ssh node ...)`).
- **A safe place to stage canonical doc updates** such as `AGENTS.md`: edit, commit, and push to gitea from here when no live services or production data are required; otherwise stage on a live node.

It is **not** for:

- Starting or running live services (`aitbc-blockchain-node`, `aitbc-coordinator`, etc.).
- Holding production `data/`, chain databases, or wallet files.

### Keeping `/opt/aitbc` clean

To stay a reliable reference, it should track gitea `main` closely:

```bash
cd /opt/aitbc
git fetch origin
git reset --hard origin/main
# remove any build artifacts or untracked files when they accumulate
git clean -fdx
```

Always re-create the `data/` and `venv/` directories inside the live nodes (`node2`, `hub.aitbc`), never here.

## Using sshfs to edit the canonical repo from the IDE

The IDE host cannot safely `git commit` from `/home/oib/windsurf/aitbc` or `/opt/aitbc`, but you may still want to read or edit a live checkout through the local editor. `sshfs` can mount a remote working tree on the IDE host:

```bash
mkdir -p /tmp/hub_aitbc
sshfs -o idmap=user,reconnect,ServerAliveInterval=15 hub.aitbc:/opt/aitbc /tmp/hub_aitbc
# or for the shop node
sshfs -o idmap=user,reconnect,ServerAliveInterval=15 node2:/opt/aitbc /tmp/node2_aitbc
```

After mounting, `/tmp/hub_aitbc` is the live working tree. Be aware of the following:

- **Do not run `git` inside the mount from the IDE host.** `git` may trigger `detected dubious ownership` because the directory is owned by `root` (or the remote user) and `git config safe.directory` is required. Always `ssh` to the node for `git add` / `git commit` / `git push`.
- **The mount may cache files.** This has caused `read`/`edit` tools to see stale versions of files. If a file seems out of sync, `ssh` into the node and read it directly, or unmount and remount.
- **Some `sshfs` options are not supported.** `Cache=no` and `KernelCache=no` will fail with `fuse: unknown option(s)`. Use `reconnect` and `ServerAliveInterval` instead.
- **Symlinks may not list or read** depending on the remote configuration (`ls: cannot read symbolic link`). File contents are still accessible through `ssh`.
- **Unmount when done**:
  ```bash
  fusermount -u /tmp/hub_aitbc
  rmdir /tmp/hub_aitbc
  ```

Use the mount only for file inspection and text editing. Prefer to commit and push from `node2` or `hub.aitbc`; `/opt/aitbc` on the IDE host may also be used for gitea commits and pushes as long as no active node features are required.

## Standard workflow

1. Always start live work by SSHing to the correct node:
   ```bash
   ssh node2       # shop/follower work
   ssh hub.aitbc    # hub/customer work
   ```
2. Verify where you are before any `git` command:
   ```bash
   hostname && git rev-parse --show-toplevel && git branch --show-current
   ```
3. Make sure the node is on the latest gitea `main`:
   ```bash
   cd /opt/aitbc
   git fetch origin
   git status --short
   ```
4. Edit, then commit and push to gitea:
   ```bash
   git add <file>
   git commit -m "type(scope): description"
   git push origin HEAD:main
   ```

   Do **not** use `--no-verify` to skip the pre-commit gates. The same checks run on Gitea and GitHub CI, and bypassing them locally only moves the failure to the server.
5. Fast-forward the local `main` ref if you need it in sync:
   ```bash
   git fetch origin main:main
   ```

## GitHub mirror workflow

The GitHub public mirror is optional. To keep it in sync:

1. Make sure the canonical gitea `main` is already pushed from `node2` or `hub.aitbc`.
2. On the IDE host `/opt/aitbc` only:
   ```bash
   cd /opt/aitbc
   git fetch origin
   git checkout main
   git merge --ff-only origin/main
   git push github HEAD:main
   ```
3. Never run `git push github` from `node2` or `hub.aitbc`.

The GitHub token lives in memory (`git credential.helper cache`) or a secure helper on the IDE host and is not persisted in the repo.

## Anti-confusion checks

Before touching anything, confirm at least one of these is true:

- The path is `/opt/aitbc` **and** `hostname` returns `node2` or `hub.aitbc.bubuit.net`.
- `git remote -v` shows `origin` = gitea.
- `git branch --show-current` is `main` or `cli-docs-tests` (or another explicit feature branch), not a stale `cli-canonical`.

If the path is `/home/oib/windsurf/aitbc` on the IDE host, treat it as documentation/scratch space only. `/opt/aitbc` on the IDE host is a non-active canonical checkout and may be used for gitea commits/pushes that do not require live services.

## Release notes

The release change log is at:

```
node2:/opt/aitbc/docs/releases/v0.25/v0.25.2_change.log
```

Update it on `node2`, commit, and push to gitea `main`. Do not create new release docs in the local IDE checkout.

## Useful remotes by node

On `node2` and `hub.aitbc`:

```text
origin  http://gitea.bubuit.net:3000/oib/aitbc.git (fetch)
origin  http://gitea.bubuit.net:3000/oib/aitbc.git (push)
github  https://github.com/oib/AITBC.git (fetch)
```

> `github` is **fetch-only** on live nodes. No GitHub token should be configured on `node2` or `hub.aitbc`.

On the IDE `/opt/aitbc` the remote names have been aligned with the remote nodes:

```text
origin  https://gitea.bubuit.net/oib/AITBC.git (fetch)
origin  https://gitea.bubuit.net/oib/AITBC.git (push)
github  https://github.com/oib/AITBC.git (fetch)
github  https://github.com/oib/AITBC.git (push)
```

> `/opt/aitbc` is the only clone that should hold the GitHub token. Use a non-persistent `git credential` helper (e.g. `cache` with a short timeout) or a secure environment-based helper. Do not write the token into the URL or `/root/.git-credentials` on any node.

`main` should track `origin/main` (gitea). If it does not, run:

```bash
git branch --set-upstream-to=origin/main main
```

## No secrets in the repo

- Never commit tokens, private keys, wallet secrets, or API credentials to the repo.
- `qa-cycle.py` now reads `GITEA_TOKEN` from the environment or `~/.gitea_token`, never from a file inside the repo.
- Never store GitHub, Gitea, or other git tokens in `~/.git-credentials`, `git remote` URLs, or shell history on live nodes. Use `git credential.helper cache` with a short timeout, a secrets-manager-backed helper, or interactive entry only.
- If a secret is accidentally committed or exposed, rotate it immediately and scrub the file from git history with `git filter-repo` (or `git filter-branch` as fallback), then force-push from `node2` or `hub.aitbc`.

## When not to act

Do not, from the IDE host:
- edit `/opt/aitbc/docs/releases/v0.25/v0.25.2_change.log` and push it
- reset or force-push `main`
- force-push or rewrite git history
- assume `/opt/aitbc` is the same tree as `node2` or `hub.aitbc`
- run active AITBC services, store production `data/`, chain databases, or wallet files in `/opt/aitbc`

Do not, on `node2` or `hub.aitbc`:
- push to the `github` remote or store a GitHub token
- store any git credential in `~/.git-credentials`

## Operational hints

- After starting or restarting a live service, watch its logs in real time with `journalctl`:

  ```bash
  # shop node
  ssh node2 'journalctl -f -u aitbc-blockchain-node -u aitbc-blockchain-p2p -u aitbc-blockchain-rpc'

  # hub node
  ssh hub.aitbc 'journalctl -f -u aitbc-coordinator-api -u aitbc-exchange -u aitbc-marketplace -u aitbc-pool-hub'
  ```

  Use `-n 50` to see the last 50 lines, and add `--no-pager` for non-interactive output.

## Wallet key mismatches

If a wallet's stored key does not match the address it is supposed to control,
do **not** attempt to regenerate the key from the address. A public address
cannot be reversed to a private key, and any regenerated key would be a new
wallet unrelated to the original funds.

Recommended response:

1. Record the mismatch in `LIVE_VALIDATION_SUMMARY.md` under the relevant
   scenario or finding.
2. Check whether the original seed phrase, private key, or backup still exists
   on the node (e.g. `/var/lib/aitbc/wallets/`, `~/.aitbc/wallets/`, or the
   wallet daemon). Do not search for these files unless explicitly asked.
3. If the original seed is available, import or derive the correct key into a
   new wallet and migrate funds/balances to it.
4. If the original seed is not available, the key cannot be safely recovered.
   Recommend deprecating the mismatched wallet and creating a fresh wallet with
   a new, safely-backed-up seed. Do not attempt to brute-force or reconstruct
   the missing key.

This is a data integrity / operator-recovery issue, not a CLI bug that can be
fixed by code changes alone.

## Use the AITBC MCP server

When operating the live AITBC nodes, prefer the MCP server in `mcp-server/`
over arbitrary SSH or shell commands.

- The canonical server is `mcp-server/aitbc_mcp_server.py`, which imports the
  typed RPC tool set from `mcp-server/aitbc_mcp_rpc_tools.py`.
- It provides read-only tools for nodes, services, chain state, accounts,
  transactions, blocks, mempool, bridge, cross-chain, GPU, AI jobs, marketplace,
  escrow, disputes, contracts, subscription, islands, and governance/identity.
- Mutating tools (start/stop/restart, cron jobs, CLI commands, staking,
  transfers, marketplace listings, GPU registration, bridge operations, escrow,
  governance, etc.) are gated with `dry_run=true` by default and require
  `confirm=true` to execute.
- The generic fallback `call_aitbc_http` can reach any known service, but only
  pre-mapped local service names and paths are allowed.

Use the typed MCP tools first. Drop to explicit SSH only when the MCP server
itself is being debugged or a specific one-off command has no MCP wrapper.

## CI runner (gitea-runner)

The Gitea Actions runner is a separate Debian host reachable over SSH:

```bash
ssh gitea-runner
```

Key details from inspection:

- Binary: `/opt/gitea-runner/act_runner`
- Config: `/opt/gitea-runner/config.yaml`
- Service: `gitea-runner.service`
- Version: `act_runner v0.2.13`
- Active label: `debian`
- Capacity: `1`
- Executor: host executor (`debian:host`)
- Cached Python venvs: `/opt/gitea-runner/.cache/aitbc-venvs`
- Work directory: `/opt/aitbc`
- Python on host: `/usr/bin/python3` (3.13.5)

Useful commands:

```bash
# Runner service status
systemctl is-active gitea-runner
systemctl status gitea-runner

# Recent runner logs
journalctl -u gitea-runner -n 50 --no-pager

# Follow runner logs live
journalctl -u gitea-runner -f

# Inspect config (do not edit the runner token)
cat /opt/gitea-runner/config.yaml

# Restart the runner after config changes
sudo systemctl restart gitea-runner

# Test a workflow locally before pushing (stop daemon first to avoid cache races)
sudo systemctl stop gitea-runner
cd /opt/gitea-runner
./act_runner exec -c /opt/gitea-runner/config.yaml \
  -C /tmp/aitbc_ci2 \
  -W .gitea/workflows/ci.yml \
  -E push -i -self-hosted
```

The runner registration file `/opt/gitea-runner/.runner` contains a token. Treat it as secret and do not commit or copy it.

## Gitea CLI (`tea`)

`tea` is a command-line helper for Gitea, similar to `gh` for GitHub. It operates on the repository in `$PWD` and persists logins in `$XDG_CONFIG_HOME/tea`.

### Setup

```bash
# Interactive login
tea login add

# Non-interactive (only if the user explicitly provides a token)
tea login add --name my-gitea --url https://gitea.bubuit.net --token "$GITEA_TOKEN"
```

### Common workflows

```bash
# Show current repo info
tea repo view

# Pull requests
tea pr list
tea pr view 42
tea pr checkout 42
tea pr create --title "fix(scope): description" --body "..."
tea pr merge --style rebase 42

# Issues
tea issue list
tea issue view 7
tea issue create --title "..." --body "..."

# Direct API calls (token is sent automatically)
tea api /repos/oib/aitbc/pulls
tea api /repos/oib/aitbc/actions/runs

# Open the current repo in a browser
tea open
```

### Notes

- `tea` assumes local `main` tracks the upstream repo in an upstream/fork workflow.
- Publish local git state before running mutating `tea` commands.
- Use `tea --debug <command>` when a command fails and the user wants details.
- Prefer `tea pr checkout` over manual `git fetch` for PR branches.

## Task tracking

`AGENTS.md` is for workspace rules and conventions only.
Open tasks, assignments and current state are tracked in `/home/oib/windsurf/aitbc/TASKLIST.md`.
Live validation notes are tracked in `/home/oib/windsurf/aitbc/LIVE_VALIDATION_SUMMARY.md`.
These files are intentionally not tracked in the canonical `node2` / `hub.aitbc` repository.
