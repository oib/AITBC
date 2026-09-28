# AITBC workspace guide for agents

This file exists so future sessions do not accidentally edit the wrong copy of the repo.

## The sites

Which hosts fill which of these roles is deployment-specific and is not
recorded in this repository. On the operator IDE host see
`/home/oib/windsurf/aitbc/AGENTS.md` and `TOPOLOGY.md`.

| site | host / path | role | what to do here |
|---|---|---|---|
| **gitea** | `https://gitea.invalid/oib/AITBC.git` (standard https — works from every host) / `http://gitea.invalid:3000/oib/aitbc.git` (http — only reachable from the LAN nodes; off-LAN hosts must use https) | **primary source of truth** | fetch, push, fast-forward `main` |
| **github** | `https://github.com/oib/AITBC.git` | public mirror, may lag behind gitea | **push only from IDE `/opt/aitbc` with the dedicated GitHub token**; live nodes do not store GitHub credentials and must not push to this remote |
| **shop node** | SSH target, `/opt/aitbc` | shop / follower | full working repo; run shop and follower services; commit and push to gitea |
| **customer node** | SSH target, `/opt/aitbc` | customer / follower (gpu) | `market_role=customer`, `enable_block_production=false`; scenario-play customer tests and paid market jobs run here |
| **hub node** | SSH target, `/opt/aitbc` | hub / proposer | full working repo; run hub and proposer services |
| **replica** | SSH target, `/opt/aitbc` | follower / customer replica | pull-only, no commits |
| **localhost (this IDE)** | `/home/oib/windsurf/aitbc` and `/opt/aitbc` | staging / IDE only | `/home/oib/windsurf/aitbc` is a partial staging checkout for notes and temporary scripts. `/opt/aitbc` is a non-active canonical clone (no `data/` or `venv/`, so no services run here); it is safe for gitea commits/pushes that do not require active node features. |

## Where the full repo lives

The canonical, full AITBC repository lives at `/opt/aitbc` on the commit/push
nodes (the shop/follower and the hub/proposer), with a pull-only follower
deployment on the replica. Do not commit or push from the replica.

Both remotes point to gitea as `origin`. `github` should remain a read-only reference on live nodes; the GitHub mirror is maintained from the IDE host `/opt/aitbc` using a dedicated, non-shared token.

> **Repository visibility note:** Gitea is the private, single-operator development repository. GitHub is the public mirror. AITBC software users other than the operator have no access to the Gitea instance, so deployment/setup scripts that must work for public users should continue to reference GitHub. Only the operator's live nodes and tooling should treat Gitea as the primary source of truth.
>
> **GitHub mirror policy (2026-08-24):** the public GitHub mirror is no longer pushed from any live node. The only host that holds the GitHub token is the IDE host, in `/opt/aitbc`. Live nodes pull/fetch from Gitea and may keep a `github` remote for reference, but must not store GitHub credentials or push to GitHub.

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
   ssh <hub-node>    # hub/proposer work
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

- The path is `/opt/aitbc` **and** `hostname` returns the shop or hub node name.
- `git remote -v` shows `origin` = gitea.
- `git branch --show-current` is `main` or `cli-docs-tests` (or another explicit feature branch), not a stale `cli-canonical`.

If the path is `/home/oib/windsurf/aitbc` on the IDE host, treat it as documentation/scratch space only. `/opt/aitbc` on the IDE host is a non-active canonical checkout and may be used for gitea commits/pushes that do not require live services.

## Release notes

The release change log is at:

```
<shop-node>:/opt/aitbc/docs/releases/v0.25/v0.25.8_change.log
```

Update it on `<shop-node>`, commit, and push to gitea `main`. Do not create new release docs in the local IDE checkout.

Append entries with `scripts/release/append-changelog.sh <file>`, piping the entry in on stdin. It refuses when the entry's `### ` header already exists and avoids heredoc-over-ssh quoting damage.

## Useful remotes by node

On the LAN nodes (`<shop-node>` and peers) `origin` uses the http endpoint on port 3000:

```text
origin  http://gitea.invalid:3000/oib/aitbc.git (fetch)
origin  http://gitea.invalid:3000/oib/aitbc.git (push)
github  https://github.com/oib/AITBC.git (fetch)
gitea   https://gitea.invalid/oib/AITBC.git (fetch)
gitea   https://gitea.invalid/oib/AITBC.git (push)
```

Off-LAN nodes (`<hub-node>`, the replica) cannot reach port 3000; their `origin` is the standard https endpoint:

```text
origin  https://gitea.invalid/oib/AITBC.git (fetch)
origin  https://gitea.invalid/oib/AITBC.git (push)
github  https://github.com/oib/AITBC.git (fetch)
```

> `github` is **fetch-only** on live nodes. No GitHub token should be configured on any live node.

On the IDE `/opt/aitbc` the remote names have been aligned with the remote nodes:

```text
origin  https://gitea.invalid/oib/AITBC.git (fetch)
origin  https://gitea.invalid/oib/AITBC.git (push)
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
- edit `/opt/aitbc/docs/releases/v0.25/v0.25.8_change.log` and push it
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

This is mirrored on every node. Note per-host quirks:
- At least one host did not have `fd-find`/`ripgrep` installed at all (not just
  a missing symlink); both were installed from the stock Debian repo. Check
  rather than assume.
- Each host's `~/.profile` trailer (the extra `. "$HOME/.cargo/env"` /
  `. "$HOME/.local/bin/env"` lines) differs -- check what a host actually had
  before assuming another host's trailer applies to it.


## Operational hints

- After starting or restarting a live service, watch its logs in real time with `journalctl`:

  ```bash
  # shop node
  ssh <shop-node> 'journalctl -f -u aitbc-blockchain-node -u aitbc-blockchain-p2p -u aitbc-blockchain-rpc'

  # hub node
  ssh <hub-node> 'journalctl -f -u aitbc-coordinator-api -u aitbc-exchange -u aitbc-market -u aitbc-pool-hub'
  ```

  Use `-n 50` to see the last 50 lines, and add `--no-pager` for non-interactive output.

- **Chain store path**: the live chain database is
  `DATA_DIR / "data" / <chain_id> / "chain.db"`
  (`apps/blockchain-node/src/aitbc_chain/config.py:89-93`) — resolve
  `DATA_DIR` via `AITBC_DATA_DIR`/`--data-dir` first; the deployment's
  actual chain_id lives in the node's env, not in this file. Probing the
  wrong path mutates the host: `sqlite3 <path>` silently *creates* a 0-byte
  database when handed a missing path.

- **`python` does not exist on the nodes** — `zsh: command not found:
  python` is a dead end. Use `/opt/aitbc/venv/bin/python` (absolute path,
  no `source venv/bin/activate` needed; that is where the project deps
  live) or `python3` for the system interpreter (3.13.5). Same for pip:
  `/opt/aitbc/venv/bin/pip`. Poetry is its own venv:
  `/opt/aitbc/venv-poetry/bin/poetry`.

- **systemd `EnvironmentFile=` does not strip inline `#` comments** — a comment
  on an assignment line becomes part of the value (8 Sep: a
  `BOND_SLASH_AUTHORITY_ADDRESS=<addr>  # note` line gave 6 units a 110-byte
  env value). Annotate env files on their own line, and verify with
  `scripts/monitoring/fleet-config-check.sh`, which now shape-checks every
  `*_ADDRESS` value (`^0x[0-9a-fA-F]{40}$`).

- **Fleet nodes are deliberately isolated from each other** — no inter-node
  ssh, and hub/hub1 sit on private incus subnets behind their TLS edges (`ns2`,
  `ns3`). Each node sees the others only as a real island would: over the
  public HTTPS hostnames. The only host with ssh reach to every node is the
  operator's IDE host (jump aliases `hub`, `hub1`, `node0..2`). So the env
  sections of `fleet-config-check.sh` — including the faucet-budget rule —
  run from the IDE host; from a fleet node they are skipped by design, not
  broken. Do not add ssh keys or routes between nodes to "fix" this.

- **coordinator-api schema migrations run at service start**: the unit's
  `ExecStartPre` runs `alembic upgrade head` against the service's own
  `DATABASE_URL` (environment via `EnvironmentFile=/etc/aitbc/aitbc-coordinator-api.env`,
  `PYTHONPATH` set inside the command to repo root + service src + every
  `packages/py/*/src`). A failed migration fails the start — deliberate,
  after two restart-before-migrate incidents left the API 500ing on a
  missing column. If the service won't start after a pull, check
  `journalctl -u aitbc-coordinator-api` for alembic output first.

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

**Hardhat (mocha) -- needs a host with a Node toolchain.**

```bash
ssh <node> 'bash -lc "cd /opt/aitbc/contracts && npx hardhat test"'   # 246 tests
```

This needs Node (24.20 / npm 11.16) and installed `node_modules`, which in a
typical deployment only one host has; the IDE host may have no npm at all. That
matters more than it looks: the Hardhat suites are the *only* coverage for
`AgentStaking`, `PaymentProcessor` and `EscrowService`, which forge reports at
or near 0% lines. If that host is unavailable, those contracts are effectively
untested there. Both CI pipelines (`.github/workflows/ci.yml` and
`.gitea/workflows/ci.yml`) do run `npx hardhat test`; the caveat applies only
to local dev hosts without a Node toolchain.

## Wallet key mismatches

If a wallet's stored key does not match the address it is supposed to control,
do **not** attempt to regenerate the key from the address. A public address
cannot be reversed to a private key, and any regenerated key would be a new
wallet unrelated to the original funds.

Recommended response:

1. Record the mismatch in the IDE-local `LIVE_VALIDATION_SUMMARY.md` under the relevant
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
  transactions, blocks, mempool, bridge, cross-chain, GPU, AI jobs, market,
  escrow, disputes, contracts, subscription, islands, and governance/identity.
- Mutating tools (start/stop/restart, cron jobs, CLI commands, staking,
  transfers, market listings, GPU registration, bridge operations, escrow,
  governance, etc.) are gated with `dry_run=true` by default and require
  `confirm=true` to execute.
- The generic fallback `call_aitbc_http` can reach any known service, but only
  pre-mapped local service names and paths are allowed.

Use the typed MCP tools first. Drop to explicit SSH only when the MCP server
itself is being debugged or a specific one-off command has no MCP wrapper.

## Gitea CLI (`tea`)

`tea` is a command-line helper for Gitea, similar to `gh` for GitHub. It operates on the repository in `$PWD` and persists logins in `$XDG_CONFIG_HOME/tea`.

### Setup

```bash
# Interactive login
tea login add

# Non-interactive (only if the user explicitly provides a token)
tea login add --name my-gitea --url https://gitea.invalid --token "$GITEA_TOKEN"
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
Live validation notes are tracked in `/home/oib/windsurf/aitbc/docs/LIVE_VALIDATION_SUMMARY.md`.
These files are intentionally not tracked in the canonical shop-node / hub-node repository.

## Market service operational notes

- The market service needs `BLOCKCHAIN_RPC_API_KEY` in its environment
  (e.g. `/etc/aitbc/aitbc-market.env`) to call the escrow release/refund
  endpoints. Set it to the same value the blockchain RPC uses and restart the
  service: `sudo systemctl restart aitbc-market`.
- After code or route changes in `apps/market/src/market_service/`,
  remove `__pycache__` and restart the service to ensure the new code is loaded.
- Targeted market verification:
  ```bash
  venv/bin/python -m pytest -q apps/market/tests/test_market_job.py apps/market/tests/test_market_job_sweeper.py
  venv/bin/python -m mypy --show-error-codes apps/market/src/market_service/services/market_service.py apps/market/src/market_service/main.py cli/aitbc_cli/commands/market/host.py
  venv/bin/python -m ruff check apps/market/src/market_service/services/market_service.py apps/market/src/market_service/main.py apps/market/src/market_service/domain/market.py cli/aitbc_cli/commands/market/host.py apps/market/tests/test_market_job.py
  ```

## Agent-coordinator faucet (coin requests)

- `/api/v1/agent/coin-requests/{register,execute}` are reachable with the *published* `FOLLOWER_API_KEY`, so the key is not a security boundary. Protection is policy: per-identity first grant, the 3 AIT ceiling, rolling aggregate budgets (`COIN_REQUEST_AUTO_BUDGET_PER_HOUR`/`_PER_DAY`, AIT amounts, defaults 24/60; `COIN_REQUEST_AUTO_APPROVE_MAX` likewise, default 3), and per-IP route limits (30/min register, 20/min execute) keyed on `X-Real-IP`.
- The per-IP key is only trustworthy because both TLS edges (`ns2` for hub, `ns3` for hub1) set `X-Real-IP $remote_addr` and each hub's nginx only trusts its own incus bridge in `set_real_ip_from`. Do not widen those ranges or pass the header through at the edge.
- **hub and hub1 each run an agent-coordinator with their own `coin_requests` DB and both hold the genesis key**, so two live faucets would double the fleet budget. hub1's `/etc/aitbc/aitbc-agent-coordinator.env` therefore sets `COIN_REQUEST_AUTO_BUDGET_PER_HOUR=0` — every registration there parks at manual review; `/execute` still pays operator-approved rows. Keep that if hub1 is ever re-promoted alongside hub.
- Alert on `coin_request_auto_budget_trips_total` at `/v1/metrics` (agent-coordinator, `127.0.0.1:8107` behind nginx). Sustained trips are a drain attempt or a fleet rollout — inspect the sender/wallet mix before approving pending rows.
- Do not leave live probe rows in `hermes_coin_requests.db`: unexecuted probes have `transaction_hash IS NULL` and can be deleted by id; anything executed stays and gets `approved_by='probe'`.
- Focused checks (dev node, needs the service `PYTHONPATH`): `PYTHONPATH=/opt/aitbc:/opt/aitbc/apps/agent-coordinator/src:/opt/aitbc/apps/coordinator-api/src venv/bin/python -m pytest -q apps/agent-coordinator/tests/`.

## Validator gossip topology

- The intended backend is **`mesh` on every host** (node process only): each
  host's `blockchain.env` carries `GOSSIP_BACKEND=mesh` and
  `GOSSIP_MESH_PEER_URLS` = the other four hosts (public `wss://<host>/rpc/gossip/ws`;
  node0/1/2 additionally reach each other over the LAN `ws://10.1.223.x:8202`).
  The **rpc unit deliberately keeps `GOSSIP_BACKEND=redis`** — it is the
  local-bus bridge; only the node process dials peers (see `mesh.py` and
  commit `3a18de6ea9`).
- The fleet silently regressed to hub-and-spoke for 18 days (Sep 9–27 2026)
  because `GOSSIP_BACKEND=redis` lines in `aitbc-blockchain-node.env`/`-rpc.env`
  and a `GOSSIP_BACKEND=websocket` in `blockchain.env` shadowed the mesh config.
  **Gossip keys live only in `blockchain.env` now; do not add `GOSSIP_BACKEND`,
  `GOSSIP_WEBSOCKET_URL`, or `GOSSIP_MESH_PEER_URLS` to unit-specific env
  files** — `fleet-config-check.sh`'s mesh section fails if they reappear or if
  the running backend (read from `/proc/<pid>/environ`) is not `mesh`.
- Env-file backups from the restore live at `/etc/aitbc/*.bak-20260927-*-mesh`
  on each host.

## Validator production & key layout

- Four validators rotate block production. The rotation order is the
  *address-sorted* active set — `[hub 0x02B8, node1 0x241D, node2 0x4364,
  hub1 0x9Ea1]` — not `VALIDATOR_SET` order (`MultiValidatorPoA.select_proposer`
  sorts by address). Selection is `(height+round) % len(set)`; node0 is a
  non-producing follower. The round window derives to
  `max(30, max_empty_block_interval)` = 60 s when
  `CONSENSUS_PROPOSER_ROUND_SECONDS` is unset (deliberate: a round longer
  than the 60 s heartbeat stalls the chain two heartbeat cycles per silent
  proposer — see `_scale_the_proposer_round_to_the_heartbeat`).
- **Round-0 owners never produce heartbeat blocks — intended.** The hybrid
  gate fires at ≥60 s idle, exactly when round 0 ends, so every empty block
  is produced at round ≥1 by the *next* validator in the sorted set. That is
  the deliberate price of the C-2 fix (heartbeat-aligned round): a silent
  proposer is skipped within one heartbeat cycle instead of two. It is
  deterministic — each proposer derives the round from the timestamp it is
  about to stamp — so there is no double-proposal risk at the boundary.
- **Liveness needs 3-of-4, not just one validator.** Every multi-validator
  block requires the proposer plus `multi_validator_min_attestations` (=2)
  remote attestations — the proposer cannot attest its own block — so
  production needs 3 of the 4 validators reachable to each other. One
  validator down: the chain continues (~1 extra round window per height the
  dead validator would have owned). Two down, or any node cleanly cut off:
  production stalls (`got 0 attestation(s), need 2`) and **no fork forms** —
  an isolated proposer produces nothing to diverge with. A 2–2 split stalls
  both halves for the same reason. Forks only arise from *asymmetric*
  failure: attestation traffic flows but block gossip/pull does not, so the
  isolated proposer gathers signatures on a block the majority never sees
  and the majority then produces a competing block at the same height — the
  attester lock below makes those signers wait for (and fetch) the block
  they signed instead of building a rival. That
  is what `scripts/multi-node/partition-fork-test.sh` engineers on purpose
  (attest channels open, `blocks.*` + pulls closed). When a fork does form,
  deterministic fork choice (branch weight first — distinct proposers, then
  segment length, full-tie deferral for one round window, then
  `(round, hash)`; `8b82864c9`, `26add79f4`, `9d61f2b1d`+) settles the split
  on heal; a non-empty losing segment is undone via the per-block delta
  journal (`state/block_deltas.py` — see below) rather than needing manual
  repair.
- **Each validator holds exactly its own key.** `validator-secrets.env` (last
  EnvironmentFile, wins) carries `VALIDATOR_KEYS={"<own addr>":"<key>"}`,
  `PROPOSER_ID=<own addr>`, `PROPOSER_KEY=<own key>`; `node.env` carries the
  per-host `ENABLE_BLOCK_PRODUCTION=true` override. Keys must never appear in
  the unit env files or on a second host — between ~Sep 9–13 and 2026-09-27
  hub held all four and signed every block, which is the centralisation the
  Sep-3 rotation work removed.
- **Stale-head rejoin (2026-09-27) — fixed in layers.** A validator
  restarting behind the tip used to propose on its stale head and fork
  (hub's `DEFAULT_PEER_RPC_URL` was empty — self-source). Three layers now:
  (a) hub's `CHAIN_SYNC_SOURCES` maps the chain to hub1; (b) the
  **pre-proposal freshness gate** (`consensus/proposal_freshness.py`, live
  since `454dcfa7a`, hardened `6e1d02e67`) asks every `GOSSIP_MESH_PEER_URLS`
  peer for `/rpc/head` before building a block — peer ahead → bulk-pull from
  that peer and skip (re-kicked each check, peer quarantined ~10 windows when
  its pull doesn't move the head); same height → hash *vote* (a rival hash
  must strictly outvote us to hold; ties proceed);
  all unreachable → propose anyway (`proposal_freshness_unverified_total`,
  never cached; every verdict expires after `PROPOSAL_FRESHNESS_CACHE_TTL_SECONDS=5s`);
  (c) **deterministic fork choice** (`8b82864c9`, hardened `ba17138438`):
  the push path decides only tip
  races (rival shares our head's parent, head has no descendants) by
  `(round, hash)`; the pull resolver compares branch weight — distinct
  proposers in the segment, then length, then `(round, hash)` — so a lone
  isolated node's branch loses to the majority even when its fork-point
  round is lower. The rival side is fully validated (signature, timestamp
  sanity, proposer schedule for its claimed round) BEFORE any of our rows
  are touched, and delete+append share one transaction — a rival that
  fails validation can never shorten our chain. Provably-empty losing
  blocks (`tx_count==0`, unchanged state root) are deleted outright;
  non-empty journaled blocks are reverted through the delta journal.
  Only a non-empty segment with no journal (pre-journal history) or a
  revert whose recomputed state root misses the ancestor's still
  escalates to an operator resync.

  Verified live: hub restarted 3+ heights behind with production ON pulled
  from hub1 and did not fork; a network cut of node2 (blackhole routes to all
  four peers, ~2 windows, timed so node2 owned no round during it) produced
  zero proposals and clean catch-up on restore. Manual repair remains only
  for forks whose losing blocks predate the delta journal (no undo data) or
  whose revert fails the ancestor state-root check: delete diverged rows
  from `block`, then `python -m aitbc_chain.sync_cli --source https://<peer>`
  with `PYTHONPATH=/opt/aitbc:/opt/aitbc/apps/blockchain-node/src`.
- **Non-empty-segment undo (`state/block_deltas.py`).** Every block apply —
  follower import and local production — runs under a `BlockDeltaJournal`
  attached to the apply session. It records before-images for ORM
  inserts/updates/deletes and for the raw `UPDATE account` balance/nonce
  writes that bypass dirty tracking, and persists them inside the same
  commit as the block (`block_state_delta` table). The journal is
  **fail-closed**: an unresolved insert pk, an unrecognised DML against a
  chain table (`query().update`, Core `update()/delete()`, `bulk_*`, raw
  SQL outside the account-PK form), or a mid-apply transaction boundary
  (listeners no longer cover the next connection) stamps an `incomplete`
  sentinel row, and `revert_losing_segment` refuses that block outright —
  the resolver escalates instead of partially undoing. Revert replays a
  complete segment's deltas in reverse, then verifies the recomputed
  account state root against the common ancestor's recorded root — a second
  net, since the root covers only `account`; side-table completeness is
  proven by `tests/test_block_deltas_differential.py`, which snapshots
  every chain table around apply+revert for TRANSFER, GPU_MARKET variants,
  GPU_REGISTER, ESCROW lock/release/refund, BRIDGE lock/release/refund,
  BOND lock/release/slash and GOVERNANCE_EXECUTE. Orphaned transactions
  requeue through real mempool admission — the confirmed `Transaction` row
  stores the full signed `envelope` (auto-migrated column), not a
  reconstruction. An orphan that fails requeue AND is absent from the
  winning branch logs a WARNING with hash+sender and increments
  `sync_fork_orphaned_tx_lost_total` (`ForkOrphanedTxLost` alert — a user's
  confirmed transaction is gone; reconcile by hand). Delta rows older than
  10k blocks are pruned on each persist, well past `max_reorg_depth`. A
  journal gap or root mismatch increments `sync_fork_reorg_unsafe_total`
  and escalates — never a wrong revert. `SYNC_FORK_UNDO_ENABLED=false`
  restores escalate-only behaviour. **The delta-sync fast path is NOT
  journaled** — a follower catching up via the `/rpc/sync` state dump writes
  state as a blob, so those blocks carry no delta rows; any later reorg
  needing to undo them fails closed and escalates (same as pre-journal
  history).
- **Attester lock — a signature is a commitment.** A validator that signs a
  peer's block X at height h records `(h, X)` in-memory
  (`RemoteAttestationService._attested`, per chain instance). While the lock
  is live — one proposer round (`consensus_proposer_round_seconds`=60) — the
  node (a) refuses to attest a rival hash at h, and (b) will not propose at
  h: `PoAProposer._honor_attestation_lock` instead queries every mesh peer's
  `/rpc/block/{h}` for the locked hash and kicks `pull_from_peer` toward the
  first peer serving it, so the head advances onto the attested block
  through the normal (fully validating) import path. If no peer serves X the
  proposal stays suppressed until the lock expires, capping the stall at one
  round window. Locks are **in-memory only** — a restart forgets them, which
  is safe: a restart outlasts the lock window anyway and the freshness gate
  still covers stale-head proposals. `ATTESTATION_LOCK_ENABLED=false`
  restores legacy behaviour. This closes the equivocation that turned the
  2026-09-27 asymmetric partitions into forks (hub1 attested node2's block,
  never received it, then proposed a rival one round later).
- **Sync sources:** every node's `DEFAULT_PEER_RPC_URL` (or
  `CHAIN_SYNC_SOURCES` override) must point at a *peer*, never itself.
  Followers use `https://hub.aitbc.bubuit.net`; hub uses
  `CHAIN_SYNC_SOURCES=ait-hub.aitbc.bubuit.net:https://hub1.aitbc.bubuit.net`
  (set 2026-09-27 — an empty source is what made hub's sync gate blind).
- **Validator rejoin runbook — required for EVERY validator restart or
  deploy, including routine rolling updates.** A validator that rejoins even
  one height behind can still own the next round slot and propose on a stale
  parent, creating a same-height fork. Procedure:
  1. Create a runtime drop-in before restarting:
     `mkdir -p /run/systemd/system/aitbc-blockchain-node.service.d` and write
     `no-prod.conf` containing `[Service]` + `Environment="ENABLE_BLOCK_PRODUCTION=false"`,
     then `systemctl daemon-reload`.
  2. `systemctl restart aitbc-blockchain-node`.
  3. Wait until the node's head height AND hash exactly match a peer's
     (`curl -s http://127.0.0.1:8202/rpc/status` vs e.g.
     `https://node1.aitbc.bubuit.net/rpc/status`). Height alone is not enough —
     same height with a different hash means a fork is already present.
  4. Remove the drop-in (`rm no-prod.conf`, `rmdir` the .d dir),
     `systemctl daemon-reload`, restart again. The second restart lands on a
     current head, so proposing is safe.
  The freshness gate (`454dcfa7a`, hardened `6e1d02e67`) blocks stale-head
  proposals on its own and fork choice (`8b82864c9`+) resolves same-height
  splits deterministically, so this runbook is defence in depth rather than
  the only line — keep it: an *asymmetric* partition (attestations flow,
  block gossip/pull does not) still produces a same-height fork that only
  fork choice can heal, and the delta journal auto-reverts the losing
  segment (empty or not) once a winner is decided.

## Trading authentication

- Trading's protected routers require `X-Trading-Api-Key` matching `TRADING_API_KEY`; `X-API-Key` and `BLOCKCHAIN_RPC_API_KEY` are a separate blockchain RPC credential, not substitutes.
- Provision trading's key in its protected systemd env file (`/etc/aitbc/aitbc-trading.env`) and the same value in each coordinator service env that calls it. Restart those processes after changing the key: trading captures it at module import and portfolio aggregation at initialization. Never log the value.
- The CLI reads `TRADING_API_KEY` from the process environment or a readable trading env file into `CLIConfig.trading_api_key` (`SecretStr`). It is deliberately env-only, not a plaintext `aitbc config set` key.
- Focused auth regression checks: `venv/bin/python -m pytest -q tests/unit/test_settlement_sdk.py tests/unit/test_trading_sdk.py tests/unit/test_trade_auth.py apps/trading/tests/test_main.py` on a dev node with isolated test data.
