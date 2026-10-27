# Fleet wave runbook — rolling service restarts across the validator set

> How a restart wave runs: read the workspace holds file, gate each host
> with `hold-check.sh`, fast-forward pull, then restart **serially — one
> validator at a time** — with readback and head-equality checks between
> hosts. Written after INC-hub1-restart-0618 (a wave brief that lacked the
> active hold restarted hub1 inside its soak window; #601, #624).
>
> Authorization basis: the 23 Oct restart rule covers **restarts only** —
> a restart needs no named operator line. Pulls, `systemctl
> daemon-reload`, env edits and deletions are **not** covered by it:
> pulls fall under the pull/deploy rules and the active holds, and the
> rest need their own go. `tasks/HOLDS.md` referenced throughout lives in
> the operator's workspace checkout — it is not in this repository. This
> document carries no keys and no addresses.

## Before you start (every host, in order)

1. **Read the holds file** — `tasks/HOLDS.md` in the workspace checkout is
   the live list; a brief that contradicts it loses. Every wave brief
   lists the active holds in its header; absence of the list means the
   brief is stale — stop and ask.
2. **Gate the host** — `scripts/ops/hold-check.sh <host>` exits non-zero
   when the holds file's "Binding now" table names the host with
   restart/pull/deploy scope; it fails closed (exit 2) when the file is
   unreadable. During a failover-drill window additionally run
   `scripts/ops/failover-preflight.sh` before touching a hub's
   node/rpc/coordinator units.
3. **Phase-0 fresh-start check** — before restarting anything, read
   `ActiveEnterTimestamp` for every unit you are about to touch and
   compare it against the baseline in the brief. A timestamp *newer* than
   the baseline means somebody already restarted it: stop and report, do
   not restart again.

```bash
# per host, read-only:
hold-check.sh <host> tasks/HOLDS.md
ssh <host> 'systemctl show aitbc-blockchain-node aitbc-blockchain-rpc \
    -p ActiveEnterTimestamp -p MainPID'
```

## The wave itself (serial — never parallel across validators)

Validators restart **one at a time**: PBFT keeps producing while at most
one of four validators is down; a second concurrent restart risks the
quorum. Wait for heads equal before the next host.

For each host in the wave order:

```bash
# 1. tag the action — every mutating command gets a logger line
ssh <host> 'logger -t coder<X> "<ROW> <host> restart"; \
    systemctl restart aitbc-blockchain-node; \
    sleep 5; systemctl restart aitbc-blockchain-rpc'

# 2. read back — record new ActiveEnterTimestamp + MainPID
ssh <host> 'systemctl show aitbc-blockchain-node aitbc-blockchain-rpc \
    -p ActiveEnterTimestamp -p ExecMainStartTimestamp -p MainPID -p ActiveState'
```

`NRestarts` does **not** rise on a manual `systemctl restart` — it only
counts automatic restarts. Proof of the restart is the new
`ActiveEnterTimestamp`/`ExecMainStartTimestamp` and the new `MainPID`,
not a counter.

```bash
# 3. heads equal across the fleet before the next host
for h in <all five hosts>; do
  ssh $h "sqlite3 'file:/var/lib/aitbc/data/<chain>/chain.db?mode=ro' \
      'select max(height) from block'"
done
# plus: curl -s <host>:9090/api/v1/alerts → expect no firing alerts;
# journalctl -u aitbc-blockchain-node -n 30 for a clean resubscribe.
```

The proposer (hub) goes **last** in a wave: after its restart confirm
blocks keep advancing and the other validators follow.

## Pull step (when the wave includes a checkout change)

A pull is not covered by the restart rule — it needs pull/deploy
authorization and a clear holds read for that host.

- `git fetch origin && git merge --ff-only origin/main` — **ff only**,
  never a merge commit, never a force.
- A `unit file changed on disk` warning after a pull means the repo unit
  changed while the installed unit under `/etc/systemd/system` did not:
  daemon-reload needs its own go — report it, do not run it inside the
  wave.

## Ledger

Every restart goes in the row ledger (`tasks/progress/<ROW>.md`) with the
authorizing go quoted verbatim — comment link or typed line — plus host,
unit, old/new `ActiveEnterTimestamp`, new `MainPID`, and the head read.
Quote the go exactly; do not paraphrase an authorization.

## Rollback

- A restart has no code rollback of its own — the running binary did not
  change. If the restarted unit misbehaves: capture the journal
  (`journalctl -u <unit> -n 200`), post the failure on the row, and stop
  the wave — do not restart the next host.
- If a pull moved the checkout and the new code is bad, the revert is a
  new commit on `main` (the fleet tracks the remote), not a local reset:
  flag it on the row; the reset path is its own decision, not part of the
  wave.
- A host that fails to come back: stop, leave it down rather than
  retry-looping, and escalate — a second validator down breaks PBFT.
