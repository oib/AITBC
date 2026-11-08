# Backup assurance — verification, offsite targets, gitea backup, restore drill

> R13-OPS-1 (#1238) deliverables. Everything here is **staged**: the
> systemd units ship in the repo; installing them on hosts is a
> deliberate ops step (see "Rollout" below), not part of this change.

## 1. Nightly restore-verification (`aitbc-backup-verify.*`)

`scripts/ops/backup-verify.py` replayed the BK-1 restore drill as a
script but was never scheduled (R13-00 finding). This change adds:

- `scripts/maintenance/aitbc-backup-verify.service` — oneshot, root,
  runs the verifier against the newest `/var/backups/aitbc` generation
  with `--max-age 36` (default) and writes
  `/var/lib/prometheus/node-exporter/aitbc_backup_verify.prom`.
- `scripts/maintenance/aitbc-backup-verify.timer` — daily 02:00 +600s
  splay, `Persistent=true`. Slot chosen after the 01:00 backup and
  before the 02:30 IDE-host offsite pull, so a corrupt generation is caught
  while the on-host copy can still be re-taken.

The service is hardened (NoNewPrivileges, PrivateTmp, Protect* — same
posture as `aitbc-backup-metrics.service`) and only reads
`/var/backups/aitbc` + writes `/var/tmp` scratch and the textfile dir.

**Rollout (per host, after merge + ff):**
```bash
sudo install -m644 /opt/aitbc/scripts/maintenance/aitbc-backup-verify.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aitbc-backup-verify.timer
# first live run is a oneshot — trigger manually once and check journal:
sudo systemctl start aitbc-backup-verify.service
journalctl -u aitbc-backup-verify -n 30
```
Expected first-run output: `ok` per artifact class + a `.prom` file with
`aitbc_backup_verify_ok 1`. A `pg_dump`-header or integrity failure exits
nonzero — that is the alerting signal (wire to monitoring once proven).

## 2. Second offsite target — assessment

Current state: `~/windsurf/aitbc/backups/fleet-nightly/` on **the IDE host only**
(user timer `offsite-pull-backups.timer`, 02:30, age-encrypted, 14 gens).
Losing the IDE host loses the only off-host copy AND the workspace (correlated
loss, see `offsite-infra-loss.md`).

Options assessed:

| option | pros | cons | verdict |
|---|---|---|---|
| **LAN storage host** (existing host) | already trusted, LAN-adjacent, no new cost | shares failure domain with fleet networking; disk/memory headroom unverified | **recommended first** — cheapest real second copy |
| Cheap storage VPS | true geographic separation | new cost, new trust domain, age keys must be escrowed | phase 2 if the storage host lacks capacity |
| Backblaze/B2 object storage | cheapest per GB, versioning | egress/egress-free pulls need rclone config; new credential class | alternative to VPS |
| gitea container | already runs 24/7 | tiny disk, already single-purpose; NOT recommended | reject |

**Recommendation**: add the LAN storage host as `DEST2` in a second pull leg (the
script already parameterizes `DEST`/`HOSTS` — run a mirrored timer or
extend `HOSTS` logic). Keep the IDE host as primary until the storage host proves a full
cycle, then demote it to optional. Requires: a disk check there
(`df -h`), age recipient already shared (`AGE_RECIPIENT` env), and the
same sha256-manifest verification (built into the script).

## 3. Gitea backup procedure

The ledger repo + issue DB are single-copy on the `gitea` container
(R13-00 gap). Minimum viable procedure (staged as doc; automation is a
follow-up):

```bash
# on the gitea container, nightly via cron/systemd timer (to be installed):
# 1. gitea dump — consistent DB+repo metadata snapshot
docker exec <pg-container> pg_dump -U gitea gitea | gzip > /backup/gitea-db-$(date +%F).sql.gz
#    (adjust to however postgres runs on that host — verify first)
# 2. repos are plain git repos — tar the repo root (or rely on fleet
#    clones as the real backup; gitea DB holds issues/PRs/users)
tar czf /backup/gitea-repos-$(date +%F).tar.gz /var/lib/gitea/git/repositories
echo "$(sha256sum /backup/gitea-db-*.gz /backup/gitea-repos-*.tar.gz)" > /backup/SHA256SUMS
```

Ship `/backup/` off-host via the same offsite-pull pattern (add `gitea`
to a pull host list once ssh access from the IDE host is confirmed — currently
`ssh gitea` works from it). **Prerequisite to verify before scripting**:
where the gitea postgres actually runs (same container? external?) —
check `/etc/gitea/app.ini` `[database]` and record here.

## 4. Measured restore drill plan (RTO)

BK-1 (2026-10-13) proved DB-level restore only; full-node RTO is
unmeasured. Planned drill (needs a CW window, ~2h, on node2 or a spare):

1. Pick latest generation; `backup-verify.py --set <gen>` → baseline PASS.
2. On a scratch dir: restore chain DB + one service DB; start a
   **follower-mode** node against the restored state on a non-conflicting
   port/data dir; measure t0=restore-start → t1=`/rpc/status` answering
   with correct head → t2=head within N blocks of live.
3. Record wall-clock per stage; that is the first real RTO number.
4. Rehearse `reset-follower-to-snapshot.sh` path if the scratch node
   qualifies as a follower target.
5. Ledger results on #1226; update `backup-restore.md` RTO section.

Do NOT run against a live data dir or validator identity — follower
role only, scratch `DATA_DIR`.
