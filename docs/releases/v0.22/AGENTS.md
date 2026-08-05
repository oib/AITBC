# v0.22 Open Tasks — Agent Split

This document assigns the remaining open v0.22 findings to Agent A or Agent B.

See [`release.log`](./release.log) for the full ledger, evidence, and verification
commands.

> **Both lists have now been verified against the code (AITBC-91, AITBC-92).**
>
> Agent B's list was ~55% stale: four of nine CLI items were already closed and its single
> APP item was half-closed and mis-described. Agent A's list, by contrast, was accurate —
> every contract and ops finding checked was genuinely open. Both are updated below with
> what was closed and what remains.

## Agent A — Core / Shared / Bridge / Infrastructure

Focus: `aitbc/`, `apps/blockchain-node`, `apps/blockchain-event-bridge`,
`apps/blockchain-explorer`, `contracts/`, ops/scripts, shared packages, and
infrastructure-wide findings.

- **CORE** — none remaining
- **Contracts** — SC-05, SC-06, SC-12 remain *(SC-08/09/10/11/14 closed, AITBC-92)*
- **Ops** — OPS-03, OPS-08, OPS-16, OPS-17 remain *(OPS-04/06/07/09/10/12/14/15/18 closed, AITBC-92)*
- **Packages** — PKG-03, PKG-05, PKG-08, PKG-09, PKG-10, PKG-14 remain
  *(PKG-01/02/04/06/07/11/12/13 closed, AITBC-92)*
- **Tests/docs** — TEST-03/04/06/07/08; DOC-02/03/05/07 remain
  *(TEST-01/02/05, DOC-01/04/06 closed)*

### What remains, and why it was not done in this pass

| ID | Why |
|---|---|
| SC-05, SC-06, SC-12 | Unbounded loops over stakers/stakes/bounties. Needs pull-based reward accounting and batched slashing — a redesign, not a patch. SC-05 also silently under-pays: the inner loop `break`s on the first matching stake. |
| OPS-03, OPS-08 | `scale_balances_3600x.py` writes a hand-rolled sha256 as the genesis state root, which the real node will not agree with. Needs the chain's actual MPT implementation. Treat as release-blocking before any hard fork. |
| OPS-16 | 37 `eval "$cmd"` sites take commands from `name:command` string arrays; converting to array invocation means restructuring that data format across 14 scripts that cannot be executed here. Currently file-local literals, so the risk is latent. |
| OPS-17 | Consolidating four overlapping service-management scripts is a behavioural change to ops tooling with the same problem. |
| PKG-03 | Plugin loader is arbitrary code execution by design (`importlib.import_module` from a manifest string). Needs an allowlist and manifest signature verification. |
| PKG-05 | Removing `@ts-nocheck` from 5 files means fixing the underlying type errors, and the packages could not install their toolchain to reveal them until PKG-06 landed. Now unblocked. |
| PKG-08/09/10/14 | Web hooks, `localStorage` divergence, placeholder visual-regression suite, SSR guard. |
| TEST-03/04/06/07/08, DOC-02/03/05/07 | Test reorganisation and doc consolidation; mechanical but large. |

## Agent B — Apps / CLI / Service Layer

Focus: `apps/*` (except core blockchain/bridge/explorer), `cli/`, and service-level
auth/endpoint findings.

### Open

- **APP-54** — `simple_exchange` runs on stdlib `http.server` (`server.py`, `db.py`)
  rather than the `src/<pkg>/` FastAPI layout every sibling service uses. This is why it
  cannot use shared `aitbc.auth` middleware and hand-rolls its own request handling. The
  largest remaining Agent B item; it is a service migration, not a patch.

### Closed under AITBC-91

| ID | Finding | Fix |
|---|---|---|
| CLI-03 | Credentials in a module-level dict — gone next invocation, while reporting "stored" | OS keyring when available, else a 0600 file store; the active backend is reported rather than silently chosen |
| CLI-05 | Multisig challenges process-local; `created_at` was `secrets.token_hex(8)` | Persisted to a 0600 store with a real ISO timestamp and a 1-hour TTL; verified working across separate processes |
| CLI-06 | Audit dir/files created with the process umask | Directory 0700, files created 0600 via `os.open` |
| CLI-10 | `secrets.json` written then chmod'ed — readable window | Created 0600 via `os.open`; parent dir 0700 |
| CLI-13 | `client.py` an unregistered 9-line stub with 0 commands | Removed, along with the four tests that existed only to assert it was empty |

### Already closed before this pass — do not re-do

| ID | Finding | Evidence |
|---|---|---|
| CLI-02 | `get_wallet_balance_in_chain` returned a placeholder `0.0` | Makes a real HTTP call to `/v1/chains/{id}/wallets/{id}/balance` |
| CLI-07 | Weak secret redaction in `env_validator` | `_looks_like_secret(key, value)` gates a `***REDACTED***` replacement |
| CLI-08 | `aitbc list` alias dropped parent context | Uses `ctx.invoke(wallet, ...)`; comment records that global flags are preserved |
| CLI-09 | `chain_manager` reported fabricated migration statistics | Hardcoded `10000`/`1000`/`300` replaced with `0` |
| APP-50 | exchange `_require_api_key` failed open when `EXCHANGE_API_KEY` was unset | Now sends 401; docstring: "A missing EXCHANGE_API_KEY is treated as an auth failure" |

The previous revision folded APP-50 into the APP-54 line as "`simple_exchange` on stdlib
`http.server` **and fail-open API key**". They are separate findings in opposite states,
and the combined wording would have sent someone to re-fix a closed one.

## Notes

- The previous claim that "APP-54 is the only remaining concrete application-level
  finding" and that "all other APP findings are closed" was not accurate. It contradicted
  `release.log`'s own Open table in the same directory, which listed APP-32, APP-33,
  APP-35 and APP-64. On checking those: **APP-32 and APP-64 are genuinely fixed** (the
  event bridge now has a persisted checkpoint and a reorg-tolerance buffer — the hardest
  of the four; the ledger simply was not updated). **APP-33 and APP-35 could not be
  confirmed closed** and should be treated as open.
- Cross-area items (e.g. TEST-08) may require both agents to coordinate.

## Convention

A finding is closed when its failure mode has been reproduced as a test, or the absence of
the defect demonstrated by executing the affected path — not when a plausible-looking
change has been made nearby. Both directions of error have already occurred in this
release: real findings recorded as fabricated after reading already-fixed code, and unfixed
findings recorded as closed without running anything.

## Sequencing for what remains

Not specifications; pattern discovery and architectural validation still apply. Everything
listed here was verified open on 2026-08-05 — but verify again before starting, since this
document has been wrong in both directions before.

### Contracts — SC-05, SC-06, SC-12

All three are unbounded loops and share a fix shape. `distributeAgentEarnings` iterates
`pool.stakers` with a nested scan, `_slashAllStakesForAgent` makes an external token
transfer per iteration, and `getBountyStats` walks every bounty ever created. Each becomes
un-callable as data grows, which is a denial of service arriving through normal use.

Consider pull-based reward accounting (stakers claim rather than being paid in a loop) and
batched, paginated slashing. Fix SC-05's under-payment at the same time: the inner loop
`break`s on the first ACTIVE stake matching a staker, so anyone with multiple concurrent
stakes on one agent is credited for only one of them.

### Ops — OPS-03/08, OPS-16, OPS-17

1. **OPS-03/08 first, and treat as release-blocking.** `scale_balances_3600x.py` writes a
   hand-rolled sha256 as the genesis state root; the real node computes an MPT root and
   will not agree, so the chain fails genesis validation after the migration. It also
   defaults `--chain-id` to the production domain and `--data-path` to `/var/lib/aitbc/data`,
   so running it with no arguments targets production. Needs the chain's actual state-root
   implementation plus an explicit confirmation gate.
2. **OPS-16** — replace `eval "$cmd"` with array invocation. The blocker is the data
   format: commands are stored as `name:command` strings in arrays across 14 scripts, so
   this is a restructure, and the scripts need to be runnable to validate it.
3. **OPS-17** — consolidate the four service-management scripts into one parameterised
   entry point. A service added to one is currently easy to forget in the others.

### Packages — PKG-03, PKG-05, PKG-08/09/10/14

1. **PKG-05 is now unblocked** — PKG-06 added the missing devDependencies, so `tsc` can
   finally report the errors that `@ts-nocheck` is hiding on 5 files. Remove the pragmas
   and fix what surfaces; until then the `lint` script's `tsc --noEmit` is a no-op.
2. **PKG-03** — the plugin loader is arbitrary code execution by design:
   `importlib.import_module` on a module path taken from a manifest, then called with
   `manifest.config`. Needs an allowlist of importable modules and signature verification
   of manifests before load. Largest package item.
3. **PKG-08/09** — `useWalletTheme` is a stub whose name and return shape imply on-chain
   persistence, and `usePreferences` / `ThemeProvider` independently own the same
   `localStorage` key with no cross-instance sync, so they silently diverge.
4. **PKG-10/14** — the "visual regression" suite renders nothing, and `readPreference`
   calls `window.matchMedia` unguarded (safe only because its sole call site is inside a
   `useEffect`).

### Tests / Docs — TEST-03/04/06/07/08, DOC-02/03/05/07

1. **DOC-02 is the one that can mislead** — `docs/api/` and `docs/openapi/` hold diverged
   specs for the same services. Pick one canonical location and generate the other, or
   delete it.
2. **TEST-03/04** — unskip the property tests (currently `skip("Skipping broken test
   file")`) and either containerise or mock the production suites, which skip entirely
   without a live coordinator on `localhost:9001`.
3. **TEST-06/07/08, DOC-03/05/07** — mechanical but large: relocate 112 shell scripts out
   of `tests/`, split the 341KB `test-orchestrator.sh`, standardise release-doc layout,
   prune `docs/agent-outputs/`, archive `pre-boilerplate-backup`.

## Adjacent finding, not yet ticketed

`cli/aitbc_cli/utils/__init__.py::encrypt_value` is base64, not encryption. `config.py
set-secret` describes itself as "Set an encrypted configuration value" and reports
"Secret saved (encrypted)". Anything relying on that wording is relying on obfuscation.
Noticed while fixing CLI-10; out of scope there, and it needs its own ticket.
