# Failover runbook — hub→hub1 public read-path flip (drill R6)

> Rehearsed procedure for flipping hub's public RPC + explorer traffic
> to hub1 at the nginx layer, proven live in drill Round 6 on
> 2026-10-27 (issue #392). The flip is a graceful `nginx reload` of a
> prepared server-block variant — traffic gap 0 min, only added proxy
> latency.

Scope of this runbook: the nine public paths in the FLIP set —
`/rpc/head`, `/rpc/blocks/*`, `/rpc/mempool`, `/explorer-api/health`,
`/explorer-api/api/chain/head`, `/explorer-api/api/blocks/*`,
`/explorer-api/api/messages{,/topics,/state}` — plus the STAY carve-outs
that must keep answering from hub (`/rpc/islands`, `/rpc/chains`,
`/rpc/network-info`, `/rpc/subscribers`, `/rpc/market/listings`,
`/rpc/join`, messaging, payments, jobs, metrics, dashboard, …). The
STAY paths are node-local views or hub-local services: carving them out
keeps the public view identical on both sides of the flip.

## Preconditions (all measured, all must hold)

| check | source | pass condition |
|---|---|---|
| heads equal on all hosts | per-host `sqlite3 'file:…/data/<chain>/chain.db?mode=ro' 'select max(height),substr(hash,1,14) from block order by height desc limit 1'` | same height+hash everywhere |
| hub1 unit clocks | `systemctl show aitbc-blockchain-node -p ActiveEnterTimestamp --value` (rpc, coordinator-api likewise) | match the soak ledger baseline — any newer start = report and stop |
| hub1 failed units | `systemctl list-units --failed aitbc-*` | 0 |
| hub1 memory | `/sys/fs/cgroup/memory.events` + `memory.current`/`memory.max` | `oom_kill 0`, current < max |
| hub1 services | `systemctl is-active` on the 8 customer-facing units + 2 keep-offs | 8 active, 2 inactive |
| hub nginx sha | `sha256sum /etc/nginx/sites-enabled/aitbc` | equals the ledger's known-good sha — else stop and regen the variant |
| staged artifacts | `sha256sum` of the prepared variant + saved original | match the prepared values |
| hub1 public vhost canary | `curl -m8 https://hub1.<vhost>/{,/rpc/head,/explorer-api/api/chain/head,/explorer-api/health}` | 4/4 HTTP 200 |
| alerts | hub `alerts.log` tail | nothing firing that names hub1 |
| executor exclusivity | `journalctl -t <executor tags> --since -10min` on hub | no other wave in progress |

Convenience: `scripts/ops/failover-preflight.sh` implements most of this
table (heads scan with re-read on mid-block disagreement, hub1
unit/cgroup/services reads, ns3 swap, live-site sha, canary) and exits
non-zero on any FAIL. `aitbc blockchain height` is deliberately not
used for heads — it has had false-read defects; read the chain db
directly (`mode=ro`).

## Artifacts and staging

Prepare three files (off-box generation, then install on hub):

| file | content | verification |
|---|---|---|
| `aitbc.r6-orig` | byte-copy of the live `sites-enabled/aitbc`, saved at staging time | sha == live-site sha |
| `aitbc.flip-a` | the flip variant: 9 FLIP locations proxied to hub1, 22 STAY carve-outs left on hub | diff against live file must reproduce it exactly |
| `to-hub1.conf` | upstream/vhost include for the hub1 target | staged copy sha |

Stage them under `/etc/nginx/aitbc-flip/` — a directory nginx does
**not** include — so staging alone changes nothing:

```bash
ssh hub 'install -d -m755 /etc/nginx/aitbc-flip && \
  cp -p /etc/nginx/sites-enabled/aitbc /etc/nginx/aitbc-flip/aitbc.r6-orig'
scp tasks/drill-r6/aitbc.flip-a  hub:/etc/nginx/aitbc-flip/aitbc.flip-a
scp tasks/drill-r6/to-hub1.conf  hub:/etc/nginx/aitbc-flip/to-hub1.conf
ssh hub 'cd /etc/nginx/aitbc-flip && sha256sum aitbc.r6-orig aitbc.flip-a to-hub1.conf'
```

Do not `nginx -t -c` a server-block file on its own — it is an include,
not a full config; the real syntax gate runs at flip time on the whole
nginx config.

## Baseline read-back (pre-flip)

`tasks/drill-r6/readback.sh pre` (or `reverse` — same expectation):
fires one GET per FLIP and STAY path through hub's public front with a
unique User-Agent, then counts hits in hub1's nginx access log.

- PASS = hub1 served `0/9` FLIP and `0` STAY — everything answers from
  hub before the flip.

## Flip

```bash
ssh hub 'cp /etc/nginx/aitbc-flip/aitbc.flip-a /etc/nginx/sites-enabled/aitbc && \
  nginx -t && systemctl reload nginx && echo FLIPPED'
ssh hub 'sha256sum /etc/nginx/sites-enabled/aitbc'   # expect the flip-a sha
```

Then `readback.sh forward`: PASS = hub1 served `9/9` FLIP and `0` STAY.
If `nginx -t` fails, the command aborts before the reload and nothing
changed (the copy already landed but is not loaded — restore
`aitbc.r6-orig` to be tidy; see rollback).

Re-run the heads/units gate immediately before the flip, not just at
the window's start.

## Hold

Watch every ~10 min while flipped:

- `readback.sh forward` still PASS
- heads equal hub=hub1 (and the rest of the fleet)
- hub1 `memory.events` `oom_kill` stays 0; `list-units --failed aitbc-*` stays 0
- alert tail quiet for hub1

Abort → go straight to REVERT when any of: >2 consecutive 5xx on a
flipped path, heads diverge, hub1 `oom_kill` > 0, readback FAIL.

## Revert

```bash
ssh hub 'sha256sum /etc/nginx/aitbc-flip/aitbc.r6-orig'   # expect the original sha
ssh hub 'cp /etc/nginx/aitbc-flip/aitbc.r6-orig /etc/nginx/sites-enabled/aitbc && \
  sha256sum /etc/nginx/sites-enabled/aitbc && nginx -t && systemctl reload nginx'
```

Then `readback.sh reverse`: PASS = hub1 served `0/9` FLIP. Follow with
the post-revert check: heads hub=hub1 and hub1 `oom_kill` 0.

## Rollback if the flip fails

Ordered by how far the step got:

1. **`cp` done, `nginx -t` fails** — old config still loaded; traffic
   unaffected. Restore the saved original (`cp aitbc.r6-orig →
   sites-enabled/aitbc`, `nginx -t`, reload) to leave the file clean.
2. **Reload done, readback FAIL** — revert immediately (same restore);
   investigate on `127.0.0.1` paths before any second attempt.
3. **hub1 fails mid-hold** — same restore; the flip is the only change,
   so reverting always returns to the pre-drill state.

In every case the saved original under `/etc/nginx/aitbc-flip/` is the
single source of truth — verify its sha256 before copying it back.

## Proven timings (drill R6, 2026-10-27 CET)

| step | time | result |
|---|---|---|
| staging + sha verify | 11:07 | all three files match |
| readback pre | 11:07 | PASS 0/9 |
| canary | 11:07 | 4/4 200 |
| flip | **11:08:42** | reload clean, **9/9** on hub1 |
| hold | ~2 min | quiet |
| revert | **11:10:13** | PASS 0/9, live sha restored |
| heads post | 11:10 | equal hub=hub1 |

## Not covered by this runbook

- **No hub1 proposer promotion** — hub1 stays a follower; validator
  identity, proposer keys and the validator set are untouched.
- **No validator or node failover** — blockchain-node units on any host
  are never restarted by this procedure.
- **No service moves** — coordinator-api, agent-coordinator, market,
  api-gateway, pool-hub and their data stores stay on hub (that is a
  separate, heavier round needing a hub1 nginx LINE and store freezes).
- **No settlement/bridge float move** — `BRIDGE_PAYOUT_*` custody and
  the deposits DB stay on hub.
- **No consumer repoint** — `HUB_RPC_URL` and friend envs are untouched
  (they would restart validators).
- **No DNS/edge change** — `hub.…` DNS still lands on hub's nginx; only
  the upstream for the 9 flipped paths changes.
