# LEGACY-CALLERS-1 — progress ledger (append only)

## 2026-10-19 — Phase 0 evidence pass (read-only; nothing changed, no probes sent)

Baseline: `origin/main` = `465f39eeb`. Read window: host `date` 2026-10-19 08:40 CEST. All five rpc units restarted in the 18-Oct ~11:05–11:07 wave (`ExecMainStartTimestamp` per `systemctl show`): hub 11:07:29 (MainPID 63438), hub1 11:05:37, node0 11:05:00, node1 11:06:13, node2 11:06:50. Evidence window = ~21.5 h since restart. **All findings coder-reported until director-verified.**

### Surface 1 — replay guard (`bridge_lock`, `cross_chain_lock`)

**Counters** (`/metrics` on each host's rpc :8202, read 19 Oct ~08:3x CEST):

| host | `bridge_lock legacy_refused` | `bridge_lock new_form` | `legacy_accepted` | `cross_chain_lock` |
|---|---|---|---|---|
| hub | 2 | 1 | — (no series) | — (no series) |
| hub1 | — | — | — | — |
| node0 | — | — | — | — |
| node1 | — | — | — | — |
| node2 | — | — | — | — |

"—" = HELP/TYPE lines present, zero label series: the counter never incremented → **zero guarded-lock requests of any form** on those hosts since restart. Hub's 2/1 matches the director's 18-Oct read exactly — no movement in ~21.5 h.

**Journal pairing** (`journalctl -u aitbc-blockchain-rpc --since restart`):
- hub lock-path lines, complete: 2× `POST /rpc/bridge/lock ← 127.0.0.1 (UA: curl/8.14.1) → 400` at 11:07:52, 11:08:52 (23 s / 83 s post-restart — probes, matches counter delta of 2) + 1× `POST /rpc/bridge/lock ← 127.0.0.1 (UA: python-httpx/0.28.1) → 403` at 12:34:32 (the SHADOW-LOCK-1 attempt — invalid signature; adjacent journal shows `ait-shadow-soak` context, signature verification runs after the form check so it never counted).
- hub1/node0/node1/node2: **zero** lock-path lines; zero 4xx on lock endpoints of any kind.
- 403 bucket (all rpc paths, all hosts since restart): only hub's single 403 above. Everything else is 404/405 noise — all from 127.0.0.1. Notable: 1299× `GET /rpc/accounts/0xCA78267E…` → 404 (Python-urllib, loopback — some poller hammering a wrong-shaped route; unrelated to locks, flagged as an observation).
- **No external IPs appear in any rpc error journal since restart.**

**Signing-caller enumeration** (the stronger check, per prompt):
- `cli/aitbc_cli/commands/cross_chain.py:238-254,438-442,562` — always stamps `issued_at`+`nonce` into the signed dict. **new-form only.**
- `cli/aitbc_cli/commands/bridge.py` — `--wallet-name` generates issued_at/nonce itself; `--signature` accepts `--issued-at`/`--nonce` (both-or-neither; help at ~:228 explicitly documents "omit both for the legacy six-field form"). **old-form only by deliberate manual construction.**
- `aitbc/bridge/client.py:74-93` — forwards issued_at/nonce only when the caller supplies them. **old-form-capable, opt-in.**
- `aitbc/trading/bridge.py`, `apps/trading/.../clients/bridge.py:40-65`, `bridge_client_adapter.py` — wrappers migrated by CALLERS-NEWFORM-1 (`1d9cf9975`, 18 Oct); forward what callers supply.
- MCP `aitbc_mcp_rpc_tools.py:1634-1745` — issued_at/nonce optional params; omitting sends old form. **opt-in.**

Verdict: **no evidence of any live old-form caller** — counter + journal + caller enumeration all agree. The only old-form paths are deliberate manual opt-ins.

**Unconditional-guard deletion surface** (for the Phase-1 prompt): flag fields `config.py:535,541`; `require_guard` param + the flag-off return branch in `apply_replay_guard_fields` (`rpc/utils.py:494-530`); `legacy_accepted` label + `_LEGACY_ACCEPT_WARNED` + its WARNING (`rpc/utils.py:470-491`); flag-off tests in `test_replay_guard_metrics.py`, `test_cross_chain_router.py` ~:545; CLI help text `commands/bridge.py` ~:228; env lines `BRIDGE_LOCK_REQUIRE_REPLAY_GUARD` + `CROSS_CHAIN_REQUIRE_REPLAY_GUARD` on 5 hosts.

### Surface 2 — `/v1/marketplace/*` aliases

Traffic source: **hub nginx access.log** (retention ~11 days, back to 8 Oct — **under the 2-week bar**; a retention extension would be its own named step, not proposed here). Gateway itself logs no access lines (0 "marketplace" in `aitbc-api-gateway` journal since 11 Oct).

- `/v1/marketplace/*`: **5 requests in ~11 days — all scanner noise.** Distinct external IPs, Chrome UAs, ~one/day, every one `GET /v1/marketplace/offer/{plugin_id}` (literal `{plugin_id}` or `%7B…%7D` — a spec-placeholder probe) → **404**. No real caller.
- `/v1/market/*` control: ~11,200 requests in the same window.
- Repo/website callers of the old prefix: only the shim code itself (`api-gateway/main.py:120-135`, `market/main.py`, `coordinator-api/main.py`) + `test_marketplace_aliases.py` + frozen `docs/releases/*`.

Verdict: **dead** (scanner-only traffic on a literal placeholder). Caveat: 11-day window; a longer window would need the retention step.

Removal would touch: gateway `main.py:120-135` (marketplace rewrite entries), `market/main.py` + `coordinator-api/main.py` shim mounts, `test_marketplace_aliases.py`, restart = api-gateway only.

### Surface 3 — dead code (`add_to_agent_stake`, retired transfer routes)

- `retired.py` (`PROTOCOL_TRANSFER_RPC_RETIRED = True`, BNT-2 decision 2026-10-12): 11 route stubs refuse with **HTTP 410** before any logic — `agent_staking.py:43,120,174,207` (4), `bounty.py:60,122,162,223,253` (5), `staking.py:94,186` (2). All still mounted via `routers/agent_economy.py` etc. and reachable (returning 410).
- Callers in CLI/MCP/website/scripts/docs: **none found** (only monitoring name-mentions in `aitbc_rules.yml:166-176` and `fleet-config-check.sh`'s digest spec — those reference the `agent_stake` *table*, not the routes).
- Live tests pin the 410s (`test_retired_protocol_transfers.py`) and the chain-admission behavior (`test_supported_chain_admission.py`).

Verdict: the unreachable post-raise bodies are **dead by construction**; the 410 stubs themselves are the API contract (410 vs unmount→404 is the design choice). Deleting bodies touches the 3 route files + tests; unmounting additionally touches routers + OpenAPI surface.

### Surface 4 — `MARKETPLACE_*` env fallbacks

- All 5 hosts: **zero** `MARKETPLACE_*` names in `/etc/aitbc/*.env`; zero in systemd unit files/drop-ins.
- Repo readers: exactly one fallback — `apps/market/src/market_service/config.py:49-59` (`MARKET_BIND_HOST`/`MARKET_BIND_PORT` accept `MARKETPLACE_BIND_*` via `AliasChoices`). The `*_AGENT_MARKETPLACE_ADDRESS` read in `contract_integration.py:57` is a different (contract-address) family, not the rename surface.

Verdict: **not set anywhere** → the alias fallback is dead. Removal: the two `AliasChoices` second entries + market-service restart.

### Surface 5 — `hub2` / `aitbc3`

- **Functional**: `node="aitbc3"` is a **live Prometheus label** for node2 (hub `/api/v1/label/node/values` returns `aitbc3` among `hub1,node0,node1,node2` — note: no `hub` value exists under that label either) → renaming is a monitoring-config change, not a code cleanup. `offers.py:100` treats `aitbc3`/`aitbc3-provider`/`-provider` as provider-id conventions (skip reputation lookup) — functional string convention, not the host. `register_bridge_validators.py:21` `--rpc-url http://aitbc3:8202` — example that still resolves on the LAN (aitbc3 = node2's legacy LAN name). `test_website_discoverability.py:36` — a *guard test* asserting `hub2.aitbc` does NOT appear in the website — keep.
- **Text/comments**: `hub_discovery.py:33` docstring (`hub2.example.net` — generic example); incident-history comments in `sync_block_import.py:762`, `transactions.py:262`, test docstrings; `install-nginx-node.sh:4`.
- **Frozen history**: `docs/releases/*`, `aitbc_rules_test.yml` (fixture names deliberate), `test_sync_state_divergence.py` (hub2-incident regression), `test_offer_quote.py` fixtures, `test_no_fleet_details_are_published.py` notes.

Verdict: not a deletion surface — the live label + conventions need a monitoring-config decision (report only).

### Surface 6 — `GPU_MARKETPLACE` intake (question only)

- No type allowlist at admission — `rpc/transactions.py` special-cases known types (`:161-241` GOV_PROPOSE/BRIDGE_LOCK/FEE_SWEEP/GPU_DEREGISTER/GPU_ALLOCATE/MESSAGE); unmatched types take the generic path at apply (v9 signature still required).
- `GPU_MARKETPLACE` is not in `_ZERO_VALUE_TX_TYPES` (`state_transition.py:85`) nor the `is_offer` zero-value check (`transactions.py:414`) → an old-type offer would be treated as an ordinary value transfer.
- A counter-only intake change = a type-name check + metric at the rpc admission path — small, rides along surface-1's rpc restart wave if wanted.

### Item 7 — deploy plan by service (plan only)

| surface | service to restart | wave class |
|---|---|---|
| 1 replay-guard unconditional | `aitbc-blockchain-rpc` ×5, serial | rpc-only restarts; does not interrupt block production (poa lives in blockchain-node) |
| 2 marketplace aliases | `aitbc-api-gateway` (hub) | separate wave — do not bundle with rpc |
| 3 dead-code bodies | `aitbc-blockchain-rpc` ×5 | separate wave from surface 1 per prompt |
| 4 env fallbacks | market service (where it runs) | separate wave |
| 5 hub2/aitbc3 | none (monitoring config, not code) | n/a |
| 6 intake counter | `aitbc-blockchain-rpc` | could ride any rpc wave |

### Corrections to the director's pre-read

- "The two rpc processes' behaviour…" — confirmed; nothing found wrong.
- One nuance on the counter baseline: hub's `legacy_accepted` has **no series** (not just zero) — the label materializes only on first increment, so absence = no flag-off old-form successes ever.
- `aitbc3` is not merely historical: it is node2's **live** Prometheus node-label — the prompt's "not historical fixtures" carve-out needed this verified; it is a functional monitoring identity.

### CLI/MCP gaps

- No CLI read of replay-guard counters per host (used `/metrics` scrape directly) — suggest `aitbc rpc metrics --host H --match replay_guard`.
- No names-only env scan across hosts — suggest `aitbc ops env-names --match PATTERN`.
- No tool pairing counter deltas with journal lines — done by hand.

Nothing was changed on any host; no probe was sent to any lock route (the `legacy_refused` counter was only read, never moved); no env value, key, signature or nonce was printed.
