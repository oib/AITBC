# Offsite infrastructure loss runbook — gitea container + at1 IDE host

> Covers the two single-copy infrastructure dependencies identified in
> the R13-00 resilience review (#1226): the Gitea container (sole copy of
> the ledger repo + issue database) and at1 (sole holder of the
> fleet-offsite backup set + agent workspaces). Both are **untested
> recovery paths** — this runbook is the first written procedure.

## A. Gitea container loss (`gitea`, 10.0.3.107)

**What is lost**: `/var/lib/gitea` — all repos (incl. `oib/aitbc`, the
issue ledger DB), user accounts, tokens, CI runner registration.

**What survives**:
- Every fleet node's `/opt/aitbc` git clone (full history to last ff).
- GitHub public mirror `github.com/oib/AITBC` — **lags gitea**, may be
  days/weeks behind; usable for code but NOT for the issue ledger.
- Issue ledger content: **only in gitea DB — no backup exists** (R13-00
  gap). Comments/status/labels since the last mirror push are unrecoverable
  unless gitea DB backups are added (see #1238).

**Recovery procedure**:
1. Rebuild the container from the Incus image; install gitea binary
   matching prior version (record version in advance — check
   `/srv/gitea/gitea --version` now and store it here when known).
2. Restore `/etc/gitea/app.ini` from config backup (PostgreSQL backend —
   the gitea DB lives in postgres on the same container host or external;
   **verify where the DB actually lives before assuming** — check
   `app.ini` `[database]` now and record it).
3. Re-create repos; push `main` from any fleet clone:
   `git push --mirror` equivalent or fresh clone + push from node2/hub.
   Ledger issues do NOT restore from git — accept the loss or rebuild
   the register from `tasks/_source/tasks.json` (the local task ledger
   on at1/workspace is the closest surviving copy of row state).
4. Re-register the `oib` user, re-mint tokens (`gitea admin user
   generate-access-token`), update `~/.git-credentials` (at1),
   `/root/.gitea_token` (hub), node credential helpers.
5. Re-point `gitea.bubuit.net` DNS/nginx; verify `tea` login + a test
   issue comment.
6. Re-register gitea-runner if CI is revived.

**RTO estimate**: untested — realistically 2–4h for code, longer if the
issue ledger must be reconstructed by hand. **This is the weakest
recovery story in the fleet.**

## B. at1 IDE host loss (80.109.18.113)

**What is lost**:
- `~/windsurf/aitbc/backups/fleet-nightly/` — **the only offsite copy of
  all five hosts' backups** (age-encrypted, 14 generations).
- Agent workspaces, `tasks/_source` register working copy, IDE state,
  `~/.git-credentials`, tea logins.

**What survives**:
- All five fleet nodes' on-host `/var/backups/aitbc/` (30-day retention)
  — the primary copies; at1 only held the off-host second copy.
- `origin/main` on gitea — all pushed work safe; **unpushed worktree
  commits are lost** (check `git worktree list` habit: push or accept).
- The chain itself — fully replicated across validators.

**Recovery procedure**:
1. Provision new host; install git/tea/ssh keys; restore ssh config
   aliases (they live in `~/.ssh/config` — keep a copy off-host).
2. Re-establish gitea access: `~/.git-credentials` entry + tea logins
   (`gitea` RO, `gitea-rw`) — tokens may need re-minting via
   `ssh gitea 'sudo -n -u git /srv/gitea/gitea ... generate-access-token'`.
3. Rebuild workspace: clone repo to `~/windsurf/aitbc` + `/opt/aitbc`
   reference clone; restore `tasks/_source` from the newest off-host copy
   (see gap below).
4. **Re-seed offsite backups**: install `offsite-pull-backups.timer`
   (user unit, repo: `scripts/ops/offsite-pull-backups.*`) on the new
   host; first run re-pulls all 5 hosts' current generations — the
   on-host 30-day window means nothing is lost if recovery happens
   within retention.
5. Optional second offsite target (R13-OPS-1, #1238): evaluate ns3-bubu
   or a cheap storage VPS as a mirror destination so at1 is no longer
   single-point.

**RTO estimate**: untested — ~1–2h for repo+access, backups re-seed on
the next 02:30 timer tick automatically.

## Cross-cutting gaps (feed #1238)

- No gitea DB backup → issue ledger single-copy.
- at1 is single-point for offsite backups AND the agent workspace —
  correlated loss (host failure takes both).
- Neither procedure has been rehearsed; first real event will be the
  test. Recommend a tabletop walk-through at the next ops review.
