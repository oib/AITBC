# AITBC workspace guide for agents

This file exists so future sessions do not accidentally edit the wrong copy of the repo.

## The four sites

| site | host / path | role | what to do here |
|---|---|---|---|
| **gitea** | `https://gitea.bubuit.net/oib/AITBC.git` (https) or `http://gitea.bubuit.net:3000/oib/aitbc.git` (http) | **primary source of truth** | fetch, push, fast-forward `main` / `release/v0.24.0` |
| **github** | `https://github.com/oib/AITBC.git` | public mirror, may lag behind gitea | read-only reference, do not push release work here |
| **aitbc3** | SSH `aitbc3` (`/opt/aitbc`) | **shop node** | full working repo; run shop/follower services; commit and push to gitea |
| **hub.aitbc** | SSH `hub.aitbc` (`/opt/aitbc`) | **hub + customer node** | full working repo; run hub services; live validation of AI jobs, escrow, marketplace |
| **localhost (this IDE)** | `/home/oib/windsurf/aitbc` and `/opt/aitbc` | staging / IDE only | NOT the live repo; use only for notes, scripts and local experiments. `/opt/aitbc` is a non-active clone: `data/` and `venv/` have been removed so it cannot be started as a node. |

## Where the full repo lives

The canonical, full AITBC repository is only on the two remote nodes:

- `aitbc3:/opt/aitbc`
- `hub.aitbc:/opt/aitbc`

Both remotes point to gitea as `origin` and GitHub as `github`.

`/home/oib/windsurf/aitbc` (this directory) is a partial local staging checkout used for notes, plans and temporary scripts.
`/opt/aitbc` on the IDE host is a read-only clone at gitea `main` and is intentionally non-active: its `data/` and `venv/` directories have been removed so no AITBC service can start from it. Use it only for reading code and running local static checks. All live work must be done on `aitbc3` or `hub.aitbc`.

### Why keep a non-active `/opt/aitbc` clone on the IDE host?

A full, clean clone at `/opt/aitbc` is useful because it is:

- **A stable `main` reference** for reading the whole codebase with IDE index, search, go-to-definition, and diff tools, without waiting on SSH round-trips.
- **A local static-check runner** for `mypy`, `no_float_money.py`, OpenAPI drift checks, `pytest` dry-runs, and other read-only verification before changes are pushed to the live nodes.
- **A comparison baseline** against `aitbc3` and `hub.aitbc` (`diff`, `rsync -n`, or `git diff /opt/aitbc <(ssh node ...)`).
- **A safe place to stage canonical doc updates** such as `AGENTS.md`: edit here, then copy to a live node for the real commit.

It is **not** for:

- Starting or running live services (`aitbc-blockchain-node`, `aitbc-coordinator`, etc.).
- Holding production `data/`, chain databases, or wallet files.
- Committing or pushing release work directly to gitea.

### Keeping `/opt/aitbc` clean

To stay a reliable reference, it should track gitea `main` closely:

```bash
cd /opt/aitbc
git fetch origin
git reset --hard origin/main
# remove any build artifacts or untracked files when they accumulate
git clean -fdx
```

Always re-create the `data/` and `venv/` directories inside the live nodes (`aitbc3`, `hub.aitbc`), never here.

## Using sshfs to edit the canonical repo from the IDE

The IDE host cannot safely `git commit` from `/home/oib/windsurf/aitbc` or `/opt/aitbc`, but you may still want to read or edit a live checkout through the local editor. `sshfs` can mount a remote working tree on the IDE host:

```bash
mkdir -p /tmp/hub_aitbc
sshfs -o idmap=user,reconnect,ServerAliveInterval=15 hub.aitbc:/opt/aitbc /tmp/hub_aitbc
# or for the shop node
sshfs -o idmap=user,reconnect,ServerAliveInterval=15 aitbc3:/opt/aitbc /tmp/aitbc3_aitbc
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

Use the mount only for file inspection and text editing. Always commit, push, and run tests from `aitbc3` or `hub.aitbc`.

## Standard workflow

1. Always start live work by SSHing to the correct node:
   ```bash
   ssh aitbc3       # shop/follower work
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
   git commit --no-verify -m "type(scope): description"
   git push origin HEAD:main
   ```
5. Fast-forward the local `main` ref if you need it in sync:
   ```bash
   git fetch origin main:main
   ```

## Anti-confusion checks

Before touching anything, confirm at least one of these is true:

- The path is `/opt/aitbc` **and** `hostname` returns `aitbc3` or `hub.aitbc.bubuit.net`.
- `git remote -v` shows `origin` = gitea.
- `git branch --show-current` is `main` or `cli-docs-tests` (or another explicit feature branch), not a stale `cli-canonical`.

If the path is `/home/oib/windsurf/aitbc` or `/opt/aitbc` on the IDE host, treat it as documentation/scratch space only.

## Release notes

The release change log is at:

```
aitbc3:/opt/aitbc/docs/releases/v0.24.0/change.log
```

Update it on `aitbc3`, commit, and push to gitea `main`. Do not create new release docs in the local IDE checkout.

## Useful remotes by node

On `aitbc3` and `hub.aitbc`:

```text
origin  http://gitea.bubuit.net:3000/oib/aitbc.git (fetch)
origin  http://gitea.bubuit.net:3000/oib/aitbc.git (push)
github  https://github.com/oib/AITBC.git (fetch)
github  https://github.com/oib/AITBC.git (push)
```

On the IDE `/opt/aitbc` the remote names have been aligned with the remote nodes:

```text
origin  https://gitea.bubuit.net/oib/AITBC.git (fetch)
origin  https://gitea.bubuit.net/oib/AITBC.git (push)
github  https://github.com/oib/AITBC.git (fetch)
github  https://github.com/oib/AITBC.git (push)
```

`main` should track `origin/main` (gitea). If it does not, run:

```bash
git branch --set-upstream-to=origin/main main
```

## No secrets in the repo

- Never commit tokens, private keys, wallet secrets, or API credentials to the repo.
- `qa-cycle.py` now reads `GITEA_TOKEN` from the environment or `~/.gitea_token`, never from a file inside the repo.
- If a secret is accidentally committed, rotate it immediately and scrub the file from git history with `git filter-repo` (or `git filter-branch` as fallback), then force-push from `aitbc3` or `hub.aitbc`.

## When not to act

Do not, from the IDE host:
- edit `/opt/aitbc/docs/releases/v0.24.0/change.log` and push it
- reset or force-push `main`
- force-push or rewrite git history
- assume `/opt/aitbc` is the same tree as `aitbc3` or `hub.aitbc`
- use `/opt/aitbc` or `/home/oib/windsurf/aitbc` for live production commits

## Operational hints

- After starting or restarting a live service, watch its logs in real time with `journalctl`:

  ```bash
  # shop node
  ssh aitbc3 'journalctl -f -u aitbc-blockchain-node -u aitbc-blockchain-p2p -u aitbc-blockchain-rpc'

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

## Task tracking

`AGENTS.md` is for workspace rules and conventions only.
Open tasks, assignments and current state are tracked in `/home/oib/windsurf/aitbc/TASKLIST.md`.
Live validation notes are tracked in `/home/oib/windsurf/aitbc/LIVE_VALIDATION_SUMMARY.md`.
These files are intentionally not tracked in the canonical `aitbc3` / `hub.aitbc` repository.
