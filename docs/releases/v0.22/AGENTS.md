# v0.22 Open Tasks — Agent Split

Remaining open v0.22 findings, assigned to Agent A or Agent B, each with a suggested fix.

See [`release.log`](./release.log) for the full ledger and original evidence.

> **Every item below was re-verified against the code on 2026-08-06**, at
> `main` = `cb400eb9e`. Each carries what the check found, so the next person can repeat it
> in seconds rather than trusting this file.
>
> This document has been wrong in both directions before — real findings recorded as
> fabricated after reading already-fixed code, and unfixed findings recorded as closed
> without running anything. **Re-verify before starting.**

**Open: 15** — Agent A 14, Agent B 1, plus 3 unassessed noted at the end.

**12 closed on 2026-08-06** (APP-35, PKG-03/05/08/09/10/14, SC-05/06/12, OPS-03/08) — all
with tests, listed in the table at the end. Full unit suite 1245 passing; contracts 115
passing with 2 pre-existing `initialize()` failures unrelated to this work.

Fix suggestions are starting points, not specifications. Pattern discovery and
architectural validation still apply.

---

## Agent A — Core / Shared / Bridge / Infrastructure

Scope: `aitbc/`, `apps/blockchain-node`, `apps/blockchain-event-bridge`,
`apps/blockchain-explorer`, `contracts/`, `scripts/`, `packages/`, tests and docs.

### Contracts — 0

SC-05, SC-06 and SC-12 are closed; see the table at the end of this document.

### Ops — 2

**OPS-16 — `eval "$cmd"`** · *verified: 24 files under `scripts/testing`, `scripts/workflow`*
Latent injection surface. Currently safe only because the strings are file-local literals.

> **Fix:** the blocker is the data format, not the `eval`. Commands are stored as
> `"name:command"` strings in arrays; convert to parallel arrays or an associative array
> of argv arrays, then invoke `"${cmd[@]}"`. Do one script end-to-end first and run it
> before converting the rest — these scripts need to be executable to validate the change.

**OPS-17 — service-management duplication** · *verified: 8 scripts*
Four overlapping scripts with different service lists; a service added to one is easy to
forget in the others.

> **Fix:** one parameterised script (`manage-services.sh start|stop|status|restart`) with
> the service list defined once at the top. Keep the old names as thin wrappers that
> forward, so existing runbooks and systemd units keep working.

### Packages — 0

All six are closed. PKG-05 turned out to be the load-bearing one: removing the pragmas was
trivial, but none of the `lint` or `test` gates in `packages/` could run at all — no
tsconfig, no workspace root, no ESLint config, no jest config. They run now.

### Tests / Docs — 9

**DOC-02 — diverged OpenAPI specs** · *verified: 4 specs in `docs/api/`, 3 in `docs/openapi/`*
Two sets for the same services, diverged, with no indication which is canonical.

> **Fix:** the one that actively misleads — do it first. `docs/api/` looks newer and more
> complete. Pick it, delete or regenerate the other, and add a make target that emits specs
> from the running apps so they cannot drift again.

**TEST-03 — disabled property tests** · *verified: 1 module-level skip*
> **Fix:** run them and see what breaks. The skip reason ("Skipping broken test file") does
> not say. If the hypothesis strategies have drifted from the current validators, repair
> them; if the tests encode obsolete behaviour, delete them. A permanently skipped file is
> zero coverage either way.

**TEST-04 — service-gated production suites** · *verified: 5 files*
> **Fix:** either stand up the agent coordinator in CI (docker-compose service, or the app
> in-process via TestClient), or convert to mocked integration tests. Whichever you pick,
> make the skip *loud* — a suite that silently skips reads as passing.

**TEST-06 / TEST-07 — shell tests in `tests/`** · *verified: 112 scripts; `test-orchestrator.sh` 5,440 lines*
> **Fix:** move the 112 `test-*.sh` into `tests/orchestrator.d/` (already exists and is used
> by `staged-suite.sh`) or a new `tests/tooling/`, so `pytest tests/` no longer walks them.
> Split `test-orchestrator.sh` by topic in the same pass — it is unreviewable at 5,440 lines.

**TEST-08 — stale test dirs** · *verified: 2 dirs*
> **Fix:** delete `tests/staking/` (a README describing where tests should live, no tests)
> and either delete `tests/archived_phase_tests/` or move it under `docs/archive/`. Check
> CI collection first — neither has an `__init__.py`, so it is unclear whether they run.

**DOC-03 / DOC-05 / DOC-07 — doc hygiene** · *verified: 6 loose release files; 32 agent-output entries; 3 `.orig` files*
> **Fix:** standardise release docs on one layout (per-version directory) and migrate the 6
> loose files; prune completed-ticket outputs from `docs/agent-outputs/` to an external log
> store; delete `docs/meta/pre-boilerplate-backup/` now the migration has stabilised. All
> three are mechanical — good first tasks, low risk.

---

## Agent B — Apps / CLI / Service Layer

Scope: `apps/*` (except blockchain-node, event-bridge, explorer), `cli/`.

### Open — 1

**APP-54 — `simple_exchange` on stdlib `http.server`** · *verified: `http.server` in `server.py`, `db.py`*
Runs on `BaseHTTPRequestHandler` rather than the `src/<pkg>/` FastAPI layout every sibling
uses. This is *why* it cannot use shared `aitbc.auth` and hand-rolls its own request
handling and API-key check. The largest single item in either list.

> **Fix:** migrate to `apps/exchange/src/exchange_api/` on FastAPI, one router at a time,
> keeping the existing handlers callable so behaviour can be diffed as you go. Replace the
> hand-rolled `_require_api_key` with the shared `aitbc.auth` dependency once routing is on
> FastAPI. Take the existing tests in `apps/exchange/tests/` as the contract — they should
> keep passing throughout, and pin the current HTTP responses before starting so a
> behavioural change is visible rather than assumed.

### Closed since the last revision — do not re-do

| ID | Was | Now |
|---|---|---|
| APP-32 | Trusted-member status from `journalctl` regex | Replaced |
| APP-33 | Workflow steps slept 0.1s and marked themselves COMPLETED | Raises `NotImplementedError` |
| APP-50 | exchange API key failed open when unset | Fails closed with 401 |
| APP-64 | Event-bridge checkpoint reset to chain head, no reorg handling | Persisted checkpoint + reorg window |
| CLI-02/07/08/09 | Placeholder balance, weak redaction, dropped CLI context, fabricated stats | Closed before AITBC-91 |
| CLI-03/05/06/10/13 | In-memory credentials, process-local challenges, umask audit log, secrets TOCTOU, stub group | Closed in AITBC-91 |
| APP-35 | `agent_discovery.py` mutated the registry without a lock | `asyncio.Lock` on all 5 mutation sites |
| PKG-08/09/10/14 | `useWalletTheme` stub, three owners of the theme key, placeholder visual regression, unguarded `matchMedia` | Closed |
| SC-12 | `getBountyStats` scanned `bountyCounter` | Maintained counters; `_setBountyStatus` the sole writer |
| SC-05 | `distributeAgentEarnings` pushed in a loop and counted rewards it never credited | Pull-based `pendingRewards` + `claimPoolRewards` |
| SC-06 | `_slashAllStakesForAgent` unbounded, one token transfer per stake; reporter paid from the agent's whole slashing history | Batched via `maxSlashBatch`/`slashProgress` + `continueSlashing`; one aggregated transfer; reward from what this report actually slashed |
| OPS-03/08 | Genesis state root was a sha256 of a concatenated string, not the node's MPT root; `--chain-id`/`--data-path` defaulted to production and nothing was confirmed | Root computed with the node's `StateManager` and byte-for-byte equal to it; both flags required; typed confirmation with `CONFIRM_BALANCE_MIGRATION` for automation |
| PKG-05 | `@ts-nocheck` on 5 files — and no tsconfig, no workspace root, no ESLint config, no jest config, so *none* of `lint`/`test` could run | All gates run and pass; pragmas removed; `packages/pnpm-workspace.yaml` un-ignored from the blanket `*.yaml` rule |
| PKG-03 | Plugin loader imported and called whatever a manifest named | Boundary-correct module allowlist (default `aitbc_plugins` only) + optional injected signature verifier, both checked before the import |

---

## Convention

A finding is closed when its failure mode has been reproduced as a test, or the absence of
the defect demonstrated by **executing the affected path** — not when a plausible-looking
change has been made nearby.

Both failure modes have occurred in this release. One pass declared 15 real findings
"fabricated" after reading code that had been fixed hours earlier. A later pass recorded
APP-29 and APP-71 as closed when one had no enforcing constraint and the other re-created
the outage it was meant to fix.

## Unassessed

`release.log` marks everything not in its Closed or Open tables as **unassessed** — neither
confirmed fixed nor confirmed open. Do not read absence from this file as either.

## Adjacent findings, not yet ticketed

- `cli/aitbc_cli/utils/__init__.py::encrypt_value` is base64, not encryption, while
  `config.py set-secret` reports "saved (encrypted)". Either implement real encryption or
  stop claiming it.
- `v0.22.0` is tagged at `a5d84956f`, which has the ZK proving keys deleted and proving
  silently disabled. **Superseded by `v0.22.1` at `b2539661b`**, which restores the 21
  artifacts and narrows the ignore rule to `*.ptau`. `v0.22.0` is left in place rather than
  moved, since a tag that has been published should not change meaning — do not deploy from
  it. Note that the fixes listed in the closed table are *later* than `v0.22.1` too, so a
  further tag is needed before release.
