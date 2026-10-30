# scripts/stress — STRESS-1 harness (#706)

3 coders × 5 nodes run all exercisable scenarios repeatedly until issues
surface. Every play runs from any host with only env/flag inputs.

## Layout
- `lib.sh` — helpers (source it): arg parsing (`--host --chain --wallet
  --amount --rpc-url --tag`), `rpc_get`/`rpc_post`/`cli`, `wait_seal`,
  `spend_guard` (100k units/run cap), `jsonl`, `fail` (JSONL evidence +
  exit 1), `skip_mature` (exit 77), serial-lock helpers
- `plays/NN-<slug>.sh` — one parameterized play per family; header
  comments declare `# LANE:` and `# MODE:` (loop|once)
- `run.sh <script|all> [--times N] [--until-fail] [--lane serial|parallel]
  [--include-once] [play args]` — driver, JSONL log to
  `$STRESS_STATE_DIR/stress-runs.jsonl`
- `preflight.sh` — fleet readiness ×5 (wallet, balance, ledger env, rpc)
- `baseline.sh` — heads/mempool/alerts/journal-errs snapshot
- `watch.sh --sweep|--follow` — finding collector → `stress-findings.jsonl`
- `KNOWN.md` — dedupe registry (check before filing)
- `MATURITY.md` — once-mode lock/release calendar

## Failure contract
Nonzero exit + JSONL row `{script,host,chain,step,status:"fail",reason,
tx_hash,journal_excerpt}` in `stress-runs.jsonl` — that row is the
"issue found" evidence block. `77` = skip_mature (not a failure),
`75` = serial_wait.

## Serial lane protocol
Bridge (12), governance (13), island (14) are serial — they share
nonce-sensitive windows. `serial_acquire` mkdir-locks
`$STRESS_STATE_DIR/serial.lock` (set `STRESS_SERIAL_REMOTE=hub` to take
the shared hub-side lock so all coders see it). Parallel plays call
`serial_check` and back off with exit 75 when a serial play is in flight.

## Filing findings
`watch.sh` surfaces candidates; coders judge. File real defects as
`STRESS-<class>-N` in milestone `stress-1`, link on #706, add the class
to `KNOWN.md`. Env: `STRESS_HOSTS`, `STRESS_WALLET`, `STRESS_STATE_DIR`,
`STRESS_SPEND_CAP`, `CODER`.
