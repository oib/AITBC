# AITBC workspace guide for agents

This file exists so future sessions do not accidentally edit the wrong copy of the repo.

## The four sites

| site | host / path | role | what to do here |
|---|---|---|---|
| **gitea** | `https://gitea.bubuit.net/oib/AITBC.git` (https) or `http://gitea.bubuit.net:3000/oib/aitbc.git` (http) | **primary source of truth** | fetch, push, fast-forward `main` / `release/v0.24.0` |
| **github** | `https://github.com/oib/AITBC.git` | public mirror, may lag behind gitea | read-only reference, do not push release work here |
| **aitbc3** | SSH `aitbc3` (`/opt/aitbc`) | **shop node** | full working repo; run shop/follower services; commit and push to gitea |
| **hub.aitbc** | SSH `hub.aitbc` (`/opt/aitbc`) | **hub + customer node** | full working repo; run hub services; live validation of AI jobs, escrow, marketplace |
| **localhost (this IDE)** | `/home/oib/windsurf/aitbc` and `/opt/aitbc` | staging / IDE only | NOT the live repo; use only for notes, scripts and local experiments |

## Where the full repo lives

The canonical, full AITBC repository is only on the two remote nodes:

- `aitbc3:/opt/aitbc`
- `hub.aitbc:/opt/aitbc`

Both remotes point to gitea as `origin` and GitHub as `github`.

`/home/oib/windsurf/aitbc` (this directory) is a partial local staging checkout used for notes, plans and temporary scripts.
`/opt/aitbc` on the IDE host has been reset to gitea `main` (`eec9f22ac`) and is clean. It is safe to read and run local verification, but still use `aitbc3` or `hub.aitbc` for any edits that affect live services or the gitea `main` branch. The stale `cli-canonical` (`a4472e97`) branch still exists in the Git history but is no longer on `main`.

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

## Task tracking

`AGENTS.md` is for workspace rules and conventions only. Open tasks, assignments and current state belong in `TASKLIST.md` in the same directory.
