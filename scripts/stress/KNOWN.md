# KNOWN — dedupe registry for stress findings (seed: 2026-10-29)

File a finding as `STRESS-<class>-N` (milestone `stress-1`, linked on #706)
only if it does not match an entry below. Update this file as issues land.

## Closed recently — do not refile
- #703 refund emission-before-seal race — fixed + recovered (221fc615c)
- #704 rejected-tombstone import poison — fixed (0198f8626); node2 attestation
  deficit cleared, scar exited the window ~h10309
- #705 reconnect retry suppression + lease re-registration + BroadcastSkipped
  semantics — fixed (0a7eed292); `GossipBlockDeliveryFailing` is the real
  critical now; `BroadcastSkipped` = genuine publish failure only
- #696 shared transfer-ledger service — live (dd6a7343a + eb8b14054);
  `BRIDGE_LEDGER_URL` fleet-wide, `BRIDGE_LEDGER_API_KEY` dedicated env


## STRESS-2 series — dedupe against these
- STRESS-ENV-GAP-1 (#721) hub1 python3 missing eth_keys — fixed via
  PYTHONPATH dispatch; operator-signed plays pin node1 anyway
- STRESS-DOS-1 (#722, open) hub1 intake saturation kills sshd banner —
  hub1 stays SMALL LOAD; bounded re-test is A's gated leg only
- STRESS-UNBOND-SILENT-1 (#719, open) agent-stake records are per-host
  local DBs — response contract fixed (36d9263ee: `funds_released:false,
  next:"complete"`); canonical-status desync open — pin lifecycle to one
  rpc host; cross-host status reads are the probe
- STRESS-WATCHER-1 (#741) stress-2 maturity watcher fired ~22h early on
  node1 and swallowed refusals — armed unbond/complete legs silently lost;
  verify-first item for stress-3
- Armed timer lost = finding class 1: a queued maturity/execute leg that
  never lands gets filed, not quietly re-run

## STRESS-1 series (closed — do not refile)
- STRESS-SYNC-1 (#712) mempool-view NULL-height tx row poisons block commit —
  UNIQUE(tx_hash) rollback mislabeled `concurrent duplicate`; cleared by
  deleting the poison row; fix = UPSERT tx row with block_height at commit
- STRESS-MEMPOOL-1 (#717) in-memory `_slots` nonce index desyncs from pg
  mempool — phantom occupancy locks the sender's next nonce until rpc restart;
  fix = verify occupancy against pg at check time
- STRESS-CLI-1 (#707) harness `cli wallet address <name>` positional arg —
  resolves empty; use `wallet --wallet-name <n> balance` JSON
- STRESS-CLI-2 (#708) stub plays echo ok/null tx_hash — 02/03/04/05/06/11/13
  were no-ops pre-skeletons; lifecycle bodies landed 7c183c7/39c5f4d/44da2e1
- #709/#710 operator-wallet staging + addr resolution — superseded by
  STRESS_OPERATOR_WALLET_<host> pin (node1 -> agent-econ-operator)
- `aitbc bounty deploy|expire` CLI signature fails require_operator_signature
  (403) — plays use direct signed envelopes on /rpc/bounty/*; CLI fix = B lane
- BRIDGE_REFUND emission-before-seal (#703 class) — unlock fired on an
  unsealed lock emits a refund that dies at apply; terminal + stranded
- Agent-stake `unbond` returns ok-shaped response while stake stays active —
  quietly-swallowed gated refusal; maturity legs need state-verify, not just
  exit-code

## Open / expected noise — dedupe against these
- `AITBCJournalErrors` on node1 rpc — intermittent restart-window noise
- node1 `bridge-headers store failed` lines — pre-existing, unrelated to stress
- island `bc-2-island-1` low head cadence vs bc-2 — expected
- `STAKE_*` consensus path: HTTP 410 unarmed at v17 (#649) — expected refusal,
  not a finding; agent-staking `/v1/agent-staking/*` is the exercisable lane
- `ESCROW_FEE_SWEEP`/`RECEIPT_CLAIM` — node-emitted, no wallet path; watch-only
- `HTLC_*`, unsigned `AUTO_STAKE` — dead shapes, replay-suite only
- island `AttestationArrival*` share on bc-2-island-1 has 2 validators —
  different baseline than bc-2

## Probe artifacts (stress-3) — harness quirks, NOT findings
- `baseline.sh` `journal_err_1h: 1` on a silent host = `wc -l` counting
  journalctl's `-- No entries --` line, not a real error
- `baseline.sh` `mempool: -1` = parse fallback: `/rpc/mempool` response is
  not the `transactions[]` shape the probe expects; check the actual
  endpoint shape before treating it as a finding
- harness `cli()` appends `--rpc-url` — flag-less subcommands break
  (`exchange-island` resolves rpc from island credentials). Play 22 calls
  `$AITBC_BIN` directly for this reason; check `--help | grep rpc-url`
  before wiring a new subcommand through `cli()`
- storm sizing is host-scaled: STORM_N=150 spawned 150 concurrent CLI
  processes and saturated hub's small VPS (load ~90, sshd down ~15min,
  chain paused while hub held the proposer slot). Never run N=150 on
  hub/hub1-class hosts — cap at ~20-40 (A's bounded ladder), and prefer
  the big nodes for storm legs
- rpc rate limiter is **per-worker in-memory** (1000 req/60s each) —
  storms from one client IP see nondeterministic 429s by worker fan and
  the effective ceiling is fan-dependent; a `429` row in the run log is
  the limiter, not a defect (stress-3 storm pass 1 hit this)
- lock-window artifacts: `03`/`04` `no ESCROW_LOCK sealed carrying job`
  fails are usually poll-window misses — lock-seal latency ran ~10-25
  blocks under load; verify the lock on-chain (`payload.job_id`) before
  treating as a finding

## Operator funding rule (2026-10-30) — NOT a finding
- Default wallets are fine for plays (each host's `default`); new exercise
  wallets may be funded FROM TREASURY — coin-grant `0xCE6C…` on bc-2, island
  genesis on island chains (dev-fleet funding, no escalation needed)
- Top-ups trigger at the ~50k floor and are logged as TRANSFER plays:
  `aitbc transactions send --from <treasury-wallet> --to <addr> --amount <AIT>`
- `insufficient balance` failures = top-up signal, NOT a defect — dedupe
  them out before filing

## Recently observed anomalies under watch
- `gossip_mesh_peer_publish_dropped_total` — inflight-cap drops are NOT
  covered by the delivery critical (#705 caveat); a finding here is real
