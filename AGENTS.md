# AITBC workspace guide for agents

This file exists so future sessions do not accidentally edit the wrong copy of the repo.

## The four sites

| site | host / path | role | what to do here |
|---|---|---|---|
| **gitea** | `https://gitea.bubuit.net/oib/AITBC.git` (https) or `http://gitea.bubuit.net:3000/oib/aitbc.git` (http) | **primary source of truth** | fetch, push, fast-forward `main` / `release/v0.24.0` |
| **github** | `https://github.com/oib/AITBC.git` | public mirror, may lag behind gitea | **push only from IDE `/opt/aitbc` with the dedicated GitHub token**; live nodes do not store GitHub credentials and must not push to this remote |
| **<shop-node>** | SSH `<shop-node>` (`/opt/aitbc`) | **shop node** | full working repo; run shop/follower services; commit and push to gitea |
| **<hub-node>** | SSH `<hub-node>` (`/opt/aitbc`) | **hub + customer node** | full working repo; run hub services; live validation of AI jobs, escrow, marketplace |
| **localhost (this IDE)** | `/home/oib/windsurf/aitbc` and `/opt/aitbc` | staging / IDE only | `/home/oib/windsurf/aitbc` is a partial staging checkout for notes and temporary scripts. `/opt/aitbc` is a non-active canonical clone (no `data/` or `venv/`, so no services run here); it is safe for gitea commits/pushes that do not require active node features. |

## Where the full repo lives

The canonical, full AITBC repository is only on the two remote nodes:

- `<shop-node>:/opt/aitbc`
- `<hub-node>:/opt/aitbc`

Both remotes point to gitea as `origin`. `github` should remain a read-only reference on live nodes; the GitHub mirror is maintained from the IDE host `/opt/aitbc` using a dedicated, non-shared token.

> **Repository visibility note:** Gitea is the private, single-operator development repository. GitHub is the public mirror. AITBC software users other than the operator have no access to the Gitea instance, so deployment/setup scripts that must work for public users should continue to reference GitHub. Only the operator's live nodes and tooling should treat Gitea as the primary source of truth.
>
> **GitHub mirror policy (2026-08-24):** the public GitHub mirror is no longer pushed from `<shop-node>` or `<hub-node>`. The only node that holds the GitHub token is the IDE host, in `/opt/aitbc`. Live nodes pull/fetch from Gitea and may keep a `github` remote for reference, but must not store GitHub credentials or push to GitHub.

`/home/oib/windsurf/aitbc` (this directory) is a partial local staging checkout used for notes, plans and temporary scripts.
`/opt/aitbc` on the IDE host is a canonical clone at gitea `main` and is intentionally non-active: its `data/` and `venv/` directories have been removed so no AITBC service can start from it. It can be used for reading code, running local static checks, and for gitea commits/pushes that do not require live services or production data. Live work must still use `<shop-node>` or `<hub-node>`.

### Why keep a non-active `/opt/aitbc` clone on the IDE host?

A full, clean clone at `/opt/aitbc` is useful because it is:

- **A stable `main` reference** for reading the whole codebase with IDE index, search, go-to-definition, and diff tools, without waiting on SSH round-trips.
- **A local static-check runner** for `mypy`, `no_float_money.py`, OpenAPI drift checks, `pytest` dry-runs, and other read-only verification before changes are pushed to the live nodes.
- **A comparison baseline** against `<shop-node>` and `<hub-node>` (`diff`, `rsync -n`, or `git diff /opt/aitbc <(ssh node ...)`).
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

Always re-create the `data/` and `venv/` directories inside the live nodes (`<shop-node>`, `<hub-node>`), never here.

## Using sshfs to edit the canonical repo from the IDE

The IDE host cannot safely `git commit` from `/home/oib/windsurf/aitbc` or `/opt/aitbc`, but you may still want to read or edit a live checkout through the local editor. `sshfs` can mount a remote working tree on the IDE host:

```bash
mkdir -p /tmp/hub_node_aitbc
sshfs -o idmap=user,reconnect,ServerAliveInterval=15 <hub-node>:/opt/aitbc /tmp/hub_node_aitbc
# or for the shop node
sshfs -o idmap=user,reconnect,ServerAliveInterval=15 <shop-node>:/opt/aitbc /tmp/shop_node_aitbc
```

After mounting, `/tmp/hub_node_aitbc` is the live working tree. Be aware of the following:

- **Do not run `git` inside the mount from the IDE host.** `git` may trigger `detected dubious ownership` because the directory is owned by `root` (or the remote user) and `git config safe.directory` is required. Always `ssh` to the node for `git add` / `git commit` / `git push`.
- **The mount may cache files.** This has caused `read`/`edit` tools to see stale versions of files. If a file seems out of sync, `ssh` into the node and read it directly, or unmount and remount.
- **Some `sshfs` options are not supported.** `Cache=no` and `KernelCache=no` will fail with `fuse: unknown option(s)`. Use `reconnect` and `ServerAliveInterval` instead.
- **Symlinks may not list or read** depending on the remote configuration (`ls: cannot read symbolic link`). File contents are still accessible through `ssh`.
- **Unmount when done**:
  ```bash
  fusermount -u /tmp/hub_node_aitbc
  rmdir /tmp/hub_node_aitbc
  ```

Use the mount only for file inspection and text editing. Prefer to commit and push from `<shop-node>` or `<hub-node>`; `/opt/aitbc` on the IDE host may also be used for gitea commits and pushes as long as no active node features are required.

## Standard workflow

1. Always start live work by SSHing to the correct node:
   ```bash
   ssh <shop-node>       # shop/follower work
   ssh <hub-node>    # hub/customer work
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

1. Make sure the canonical gitea `main` is already pushed from `<shop-node>` or `<hub-node>`.
2. On the IDE host `/opt/aitbc` only:
   ```bash
   cd /opt/aitbc
   git fetch origin
   git checkout main
   git merge --ff-only origin/main
   git push github HEAD:main
   ```
3. Never run `git push github` from `<shop-node>` or `<hub-node>`.

The GitHub token lives in memory (`git credential.helper cache`) or a secure helper on the IDE host and is not persisted in the repo.

## Anti-confusion checks

Before touching anything, confirm at least one of these is true:

- The path is `/opt/aitbc` **and** `hostname` returns `<shop-node>` or `<hub-node>.bubuit.net`.
- `git remote -v` shows `origin` = gitea.
- `git branch --show-current` is `main` or `cli-docs-tests` (or another explicit feature branch), not a stale `cli-canonical`.

If the path is `/home/oib/windsurf/aitbc` on the IDE host, treat it as documentation/scratch space only. `/opt/aitbc` on the IDE host is a non-active canonical checkout and may be used for gitea commits/pushes that do not require live services.

## Release notes

The release change log is at:

```
<shop-node>:/opt/aitbc/docs/releases/v0.25/v0.25.2_change.log
```

Update it on `<shop-node>`, commit, and push to gitea `main`. Do not create new release docs in the local IDE checkout.

## Useful remotes by node

On `<shop-node>` and `<hub-node>`:

```text
origin  http://gitea.bubuit.net:3000/oib/aitbc.git (fetch)
origin  http://gitea.bubuit.net:3000/oib/aitbc.git (push)
github  https://github.com/oib/AITBC.git (fetch)
```

> `github` is **fetch-only** on live nodes. No GitHub token should be configured on `<shop-node>` or `<hub-node>`.

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
- If a secret is accidentally committed or exposed, rotate it immediately and scrub the file from git history with `git filter-repo` (or `git filter-branch` as fallback), then force-push from `<shop-node>` or `<hub-node>`.

## When not to act

Do not, from the IDE host:
- edit `/opt/aitbc/docs/releases/v0.25/v0.25.2_change.log` and push it
- reset or force-push `main`
- force-push or rewrite git history
- assume `/opt/aitbc` is the same tree as `<shop-node>` or `<hub-node>`
- run active AITBC services, store production `data/`, chain databases, or wallet files in `/opt/aitbc`

Do not, on `<shop-node>` or `<hub-node>`:
- push to the `github` remote or store a GitHub token
- store any git credential in `~/.git-credentials`

## Shell policy: Zsh / Bash / dash (three separate roles)

The nodes run three shells for three distinct purposes. Do not blur these
roles -- in particular, do not "simplify" things by making Bash the answer
to everything.

```
                    Remote node
                         |
          +--------------+--------------+
          |              |              |
       Human           Agent          Scripts
          |              |              |
        Zsh            Bash           /bin/sh
          |              |              |
      Oh My Zsh      .bash_agent       dash
          |              |              |
      interactive     agent work     POSIX/system
```

1. **Zsh** -- human interactive login shell only.
   - Root's login shell (`getent passwd root`) and Oh My Zsh config
     (`~/.zshrc`, `~/.oh-my-zsh`) are for interactive human SSH sessions.
   - Do not modify or depend on Zsh/Oh My Zsh for agent work. Agents should
     not assume Zsh-specific syntax, options, or plugins exist.

2. **Bash** -- default shell for agent (Devin, Claude, etc.) sessions.
   - Use `ssh <node> 'bash -lc "..."'` for anything needing Bash features:
     arrays, `[[ ... ]]`, shell functions, process substitution,
     `mapfile`/`readarray`, Bash-specific parameter expansion.
   - The agent environment is `~/.bash_agent` (see the section above for how
     it's wired via `~/.profile` and `BASH_ENV`). Do not assume aliases or
     interactive shell functions/prompts exist there.

3. **dash (`/bin/sh`)** -- Debian's POSIX shell, for POSIX-only scripts.
   - `/bin/sh -> dash` is Debian's default and must stay that way. Verify
     with:
     ```bash
     readlink -f /bin/sh
     ls -l /bin/sh
     dash --version   # dash has no --version flag; erroring on it is normal,
                       # it just confirms the binary is dash, not bash
     bash --version | head -1
     ```
     Expected: `/bin/sh -> dash` (or `readlink -f /bin/sh` resolving to
     `/usr/bin/dash` / `/bin/dash`).
   - **Do not change `/bin/sh` to Bash and do not run `dpkg-reconfigure
     dash`** unless there is a concrete, explicitly-approved reason. Many
     Debian package scripts and system scripts assume `/bin/sh` is strictly
     POSIX; pointing it at Bash "to make agent work easier" is the kind of
     change that turns into an incident later.
   - New system scripts intended to be portable/POSIX should use
     `#!/bin/sh` and avoid Bash-specific syntax in them.

4. **Existing scripts** -- respect the shebang that's already there.
   - Inspect the shebang before editing a script; preserve the existing
     interpreter unless there's a concrete reason to change it.
   - If a script genuinely uses Bash-only features, its shebang should be
     `#!/bin/bash`, not `#!/bin/sh`.
   - If it's POSIX-compatible (or intended to be), keep/use `#!/bin/sh` and
     do not introduce Bash-only syntax into it.

5. **Never**, on any node:
   - Change the account's login shell.
   - Replace dash with Bash as `/bin/sh`.
   - Add Oh My Zsh dependencies to agent-facing scripts or execution paths.
   - Assume aliases or interactive-shell-only functions exist in a
     non-interactive agent session.

## SSH shell environment: interactive Zsh vs. non-interactive Bash (agents)

Root's login shell on the nodes is Zsh with Oh My Zsh, and that is unchanged
for normal interactive SSH sessions. Coding agents (Devin, Claude, etc.) that
SSH in non-interactively get a separate, minimal Bash environment instead, so
agent sessions stay deterministic (no OMZ prompt/plugins, no pager hangs,
predictable `$EDITOR`/`$PAGER`).

How it works, per node:

- `~/.profile` branches on `case $- in *i*)`: an *interactive* bash login
  shell still sources `~/.bashrc` as before; a *non-interactive* bash login
  shell (`ssh host bash -lc "..."`) sources `~/.bash_agent` instead.
- `~/.bash_agent` sets `EDITOR=vim`, `VISUAL=vim`, `LANG=C.UTF-8`,
  `LC_ALL=C.UTF-8`, `PAGER=cat`, `GIT_PAGER=cat`, `SYSTEMD_PAGER=cat`. No
  aliases, no PATH override, no Oh My Zsh references -- keep it that way.
- `/etc/environment` sets `BASH_ENV=/root/.bash_agent`, picked up by PAM's
  `pam_env.so` (already active in `/etc/pam.d/sshd`). This covers the bare
  `ssh host bash` form (non-login, non-interactive), which does not read
  `~/.profile` at all.
- `~/.zshrc` / Oh My Zsh, the account's login shell, and `sshd_config` are
  untouched by this. Interactive `ssh host` still lands in Zsh with OMZ
  exactly as before.
- `/usr/local/bin/fd` is a compatibility symlink to `/usr/bin/fdfind`
  (Debian packages `fd` as `fd-find`). Not a new package install.

Agents should invoke commands as:

```bash
ssh <node> 'bash -lc "your command"'
```

This is mirrored on all five nodes: `hub.aitbc`, `node0`, `node1`,
`node2`, `hub2.aitbc`. Note per-host quirks:
- `hub2.aitbc` did not have `fd-find`/`ripgrep` installed at all (not just a
  missing symlink); both were installed from the stock Debian repo.
- Each host's `~/.profile` trailer (the extra `. "$HOME/.cargo/env"` /
  `. "$HOME/.local/bin/env"` lines) differs -- check what a host actually had
  before assuming another host's trailer applies to it.


## Operational hints

- After starting or restarting a live service, watch its logs in real time with `journalctl`:

  ```bash
  # shop node
  ssh <shop-node> 'journalctl -f -u aitbc-blockchain-node -u aitbc-blockchain-p2p -u aitbc-blockchain-rpc'

  # hub node
  ssh <hub-node> 'journalctl -f -u aitbc-coordinator-api -u aitbc-exchange -u aitbc-marketplace -u aitbc-pool-hub'
  ```

  Use `-n 50` to see the last 50 lines, and add `--no-pager` for non-interactive output.

## Smart contract test suites (two of them, different hosts)

`contracts/` carries **two** independent suites. Both must pass; neither covers
what the other does.

**Foundry (`forge`) -- runs on the IDE host.**

```bash
cd /opt/aitbc/contracts && ~/.foundry/bin/forge test              # 238 tests
cd /opt/aitbc/contracts/governance && ~/.foundry/bin/forge test   # 16 tests
```

`/usr/bin/forge` on the IDE host is **ZOE, an unrelated tool**. The real
toolchain is `~/.foundry/bin/forge` (installed via foundryup) -- use the
explicit path or the wrong binary answers.

Coverage needs a flag and a newer solc:

```bash
cd /opt/aitbc/contracts && ~/.foundry/bin/forge coverage --ir-minimum --report summary
```

`forge coverage` disables `via_ir`, which the project depends on for stack
relief, so plain `forge coverage` fails. Two things worth knowing when it does:
solc 0.8.20 reports stack-too-deep with **no source location** -- pass
`--use ~/.solc-select/artifacts/solc-0.8.34/solc-0.8.34` to get the filename.
And the usual cause is a `public` mapping over a struct with >=14 fields: the
auto-generated getter flattens the struct into that many return values and
overflows the stack. Keep such mappings `internal` and expose an explicit
`getX() returns (Struct memory)` -- returning the struct as one tuple is fine.

**Hardhat (mocha) -- runs on node2 only.**

```bash
ssh node2 'bash -lc "cd /opt/aitbc/contracts && npx hardhat test"'   # 246 tests
```

node2 is the only host with a Node toolchain (24.20 / npm 11.16) and installed
`node_modules`. The IDE host has no npm at all. This matters more than it
looks: the Hardhat suites are the *only* coverage for `AgentStaking`,
`PaymentProcessor` and `EscrowService`, which forge reports at or near 0% lines.
If node2 is unavailable, those contracts are effectively untested, and CI does
not run this suite.

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
These files are intentionally not tracked in the canonical shop-node / hub-node repository.
