# 2026-10-17 — Fleet env-var cross-check (names-only, read-only)

> **Authorization**: operator's verbatim word was `go` (single-word message
> in the coder session, after the reviewer wrote "say go and I'll register
> it"). Worked from that word; registered row/chip tracking is reviewer-side.

Read-only comparison: env names set in live `/etc/aitbc/*.env` files vs names
referenced anywhere in the repository. Names only — no values were read,
no env files, services, or code were changed.

## Census

- Fleet side: `aitbc system env-names` per `aitbc*` unit, all 5 hosts —
  115 service records, **307 distinct env names**.
- Code side: literal `os.getenv`/`environ` scans + pydantic field harvest
  + `env_prefix`-joined names + `getattr(settings, …)` — repo @ `763340100`.
- Whole-repo `-w -i` rg pass per flagged name (all file types: units,
  scripts, deployment files; `.md` and `docs/releases/` excluded).

## Result — 20 names set in live env files, referenced by nothing

**Confirmed consumed via pydantic `env_prefix` joins (initially flagged,
now cleared):** `GOVERNANCE_TIMELOCK_BLOCKS`, `GOVERNANCE_VOTING_PERIOD_BLOCKS`,
`GOVERNANCE_POOLHUB_API_KEY` (`governance_` prefix),
`POOLHUB_REDIS_URL` (`poolhub_` prefix).

| name | env file (node2 attribution) | assessment |
|---|---|---|
| `SYNC_CHAIN_ID` | `blockchain.env` | stale — old sync-source scheme, replaced by `CHAIN_SYNC_SOURCES` |
| `SYNC_SOURCE_HOST`/`SYNC_SOURCE_PORT` | `blockchain.env` | stale — same |
| `SYNC_LEADER_HOST` | `blockchain.env` | stale — same. NB: `SYNC_LEADER_PORT` is set nowhere — leader is HOST-only, source/import have HOST+PORT pairs |
| `SYNC_IMPORT_HOST`/`SYNC_IMPORT_PORT` | `blockchain.env` | stale — same |
| `SYNC_MANAGED_EXTERNALLY` | node0 env files | stale — same; node0 only |
| `SYNC_REDIS_URL` | `blockchain-secrets.env` | stale — sync path takes `redis_url` via constructor arg fed from the `redis_url` settings field → env `REDIS_URL` (`chain_sync.py:28,57`, `config.py:713`, `hub_manager.py:89,97`); `SYNC_REDIS_URL` itself is never read |
| `API_HOST` | `blockchain.env` | no repo/unit consumer found |
| `WALLET_HOST` | `blockchain.env` | no repo/unit consumer found |
| `POOL_HUB_HOST`/`POOL_HUB_PORT` | hub env files | no repo/unit consumer found (hub only) |
| `PROMETHEUS_PORT` | `blockchain.env` | no repo/unit consumer found |
| `GRAFANA_PORT` | `blockchain.env` | no repo/unit consumer found |
| `MONITORING_PORT` | `blockchain.env` | no repo/unit consumer found |
| `LIBP2P_TCP_REUSEPORT` | `aitbc-island-ipfs.env` | no repo ref; possible external libp2p daemon input |
| `COINGECKO_API_KEY` | `exchange.env` | dead — `price_oracle.py` calls CoinGecko unauthenticated (hardcoded `_COINGECKO_BASE`, no key read) |
| `ENABLE_HERMES_POLLING`/`HERMES_AGENT_IDS`/`HERMES_SERVICE_URL` | hub1 env files | no code/unit/script refs — hits exist only in `docs/releases/` changelogs (a separate non-excluded rg pass); hub1 demoted — legacy or external hermes runtime input |

Fleet-unit substitution check (**all 5 hosts**: hub, hub1, node0, node1,
node2): no `aitbc-*.service` references any of the 20 names — they are
loaded ambiently via shared `EnvironmentFile` includes, consumed by
nothing in the repo.

## Caveats

- "No repo reference" covers code, units, scripts, examples, deployment
  files. Consumers outside the repo can't be ruled out (e.g. a
  hand-maintained `prometheus.yml`, external hermes/ipfs daemons). The
  port/host names in particular are the kind external tooling reads.
- These are **candidates, not kills** — per the housekeeping rule, any
  removal waits on the operator's word per deletion.
- The stale `SYNC_*` cluster sits in shared env files every unit loads,
  which is why it appeared in ~every service's name list. Live sync names
  in use today: `CHAIN_SYNC_SOURCES`, `SYNC_MANAGER_ENABLED`,
  `SYNC_STATE_ROOT_VALIDATION_ENABLED`, `SYNC_PARALLEL_*`, `SYNC_DELTA_*`,
  `SYNC_AUX_*`, `SYNC_VALIDATE_SIGNATURES_SKIP_UNTIL`.
- Reverse direction ("read by code, absent from env files") was not
  enumerated: the literal census over-counts constants (MAX_*, TOTAL_*),
  and every pydantic field is optional-by-default — expected, not drift.
  A proper list needs a narrower extractor (env-read callsites only).

## Scanner bugs found en route (for future runs)

1. `rg` invoked from Python **with no path arg reads stdin** when stdin
   isn't a TTY — returned empty for every name under a heredoc script,
   inflating the unreferenced list 25→53→… Always pass `"."` +
   `stdin=subprocess.DEVNULL`.
2. Case mismatch: env names uppercased vs lowercase pydantic field names —
   normalize both sides before comparing.
3. Missing `env_prefix` join: field names alone don't equal env names for
   `poolhub_`, `governance_`, `trading_`, `MARKET_OPS`, `COORDINATOR_OPS`
   settings classes (86 joined names harvested).
4. Regex `\b` mangled to literal backspace in one iteration — use `rg -w`.

Scratch artifacts: `/home/oib/windsurf/aitbc/scratch/envxcheck/`
(host `.raw` JSON, `fieldscan.py`, `field_idents.json`,
`prefixed_names.json`). Raw name lists retained for re-runs.

## 2026-10-17 later — removals executed (operator word: "all")

All 20 names deleted from `/etc/aitbc/*.env` fleet-wide (~58 lines): hub 14,
hub1 6, node0 11 (incl. lowercase `api_host`/`wallet_host` twins in
`blockchain.env`), node1 13, node2 14. Files touched: `blockchain.env`,
`blockchain-secrets.env`, `node.env`, `aitbc-pool-hub.env`,
`aitbc-island-ipfs.env`, `exchange.env`. Line-exact sed on
`^[[:space:]]*(export[[:space:]]+)?NAME[[:space:]]*=`; no `.bak` copies
(key-handling rule); no values printed. Verification: case-insensitive
fleet sweep = 0 remnants; `env-names` on node2 = 0 dead names. No restarts
needed — dead keys, nothing read them. Gotcha logged: remote root shell on
hub is zsh — `$NAMES` does not word-split; loops must run under `bash -c`.

Incidental find during verification: `node0:/etc/aitbc/node.env:41` held a
bare `<64-hex>@127.0.0.1:6379` line with no `NAME=` (stale redis-credential
fragment; sha256-compare showed it matches no live `REDISCLI_AUTH`/`REDIS_URL`
value — superseded, not a live-secret copy; systemd ignores `=`-less lines).
Removed ~11:57 under operator word `deletion` (coder-reported); no value
printed, no backup per key-handling rule. File now parses fully clean.
