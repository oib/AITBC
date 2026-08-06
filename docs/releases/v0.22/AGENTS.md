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

**Open: 3** — OPS-16 (partial), DOC-05, APP-54 (partial), plus 3 unassessed at the end.

**24 closed on 2026-08-06**: APP-35, PKG-03/05/08/09/10/14, SC-05/06/12, OPS-03/08/17,
TEST-03/04/06/07/08, DOC-02/03/07 — all with tests or an executed check, listed in the
table at the end.

Full default `pytest` run: **2 failures, 0 errors**, down from 10 failures and 93 errors.
Both remaining failures are `tests/integration/test_auth.py`, which needs a live
coordinator and failed before this work. Contracts: 115 passing, 2 pre-existing
`initialize()` failures.

Fix suggestions are starting points, not specifications. Pattern discovery and
architectural validation still apply.

---

## Agent A — Core / Shared / Bridge / Infrastructure

Scope: `aitbc/`, `apps/blockchain-node`, `apps/blockchain-event-bridge`,
`apps/blockchain-explorer`, `contracts/`, `scripts/`, `packages/`, tests and docs.

### Contracts — 0

SC-05, SC-06 and SC-12 are closed; see the table at the end of this document.

### Ops — 1 (partial)

**OPS-16 — `eval "$cmd"`** · *partial: 1 of 18 files converted*
`scripts/testing/test_resource.sh` is done and verified — `run_test` takes argv, and the two
call sites that piped input use a `run_test_with_input` helper. An argument containing
`; echo INJECTED` is passed through literally instead of being executed.

> **Remaining: 17 files.** An automated conversion was written and abandoned: it rewrites
> the helper definitions cleanly, but the call sites in `scripts/workflow/` are not argv.
> They are multi-line shell blocks with pipes, `ssh` with nested quoting, and `$VAR`
> expansion — genuine shell programs passed as strings. Converting the definition without
> the call sites leaves the script silently broken (the whole command string becomes
> `argv[0]`), which is worse than the `eval`. **Do these per script, running each one**, and
> expect some to need their call sites restructured rather than re-quoted. The variable
> interpolation (`$TEST_PROFILE`, `$CHAIN_ID`) is why this is worth doing: the injection
> surface is no longer only file-local literals.

### Packages — 0

All six are closed. PKG-05 turned out to be the load-bearing one: removing the pragmas was
trivial, but none of the `lint` or `test` gates in `packages/` could run at all — no
tsconfig, no workspace root, no ESLint config, no jest config. They run now.

### Tests / Docs — 1

**DOC-05 — `docs/agent-outputs/`** · *verified: 357 tracked files*
DOC-03 and DOC-07 are closed. DOC-05 is not, and is left deliberately.

> **Not done, needs a decision first.** The suggestion is to "prune completed-ticket outputs
> to an external log store". No external log store exists, so following it means deleting
> 357 files of historical record — QA validations, design notes, merge logs — several of
> which are still linked from live documents. That is a call about what the project keeps,
> not a hygiene fix. Decide the retention rule (and where pruned records go) before
> deleting anything.

---

## Agent B — Apps / CLI / Service Layer

Scope: `apps/*` (except blockchain-node, event-bridge, explorer), `cli/`.

### Open — 1 (partial)

**APP-54 — `simple_exchange` on stdlib `http.server`** · *partial: HTTP surface now pinned*
Runs on `BaseHTTPRequestHandler` rather than the `src/<pkg>/` FastAPI layout every sibling
uses. This is *why* it cannot use shared `aitbc.auth` and hand-rolls its own request
handling and API-key check. The largest single item in either list.

> **Done: the prerequisite.** `apps/exchange/tests/test_http_contract.py` — 57
> characterisation tests over a real socket, recording all 27 routes, which endpoints
> require `X-Api-Key`, the CORS headers, and the malformed-request responses. The existing
> suite could not serve as the contract the fix note assumed: it covers `db.py` and never
> issues a request.
>
> Two things it corrected on the way. `/api/wallet/balance`, `/api/total-supply` and
> `/api/treasury-balance` **require an API key** despite reading like public reads. And
> `do_GET`'s guard tests for a leading `//` as well as `..`, but the path is normalised
> before it runs — `//health` is served as `/health` with a 200, so the `//` and `\\` arms
> are dead code. Do not carry that assumption into the rewrite.
>
> **Remaining: the migration itself.** Move to `apps/exchange/src/exchange_api/` on FastAPI,
> one router at a time, and replace the hand-rolled `_require_api_key` with the shared
> `aitbc.auth` dependency. `test_http_contract.py` should pass unchanged against the result;
> any line that has to be edited is a behavioural change someone chose.

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
| TEST-03 | Property tests skipped as "broken"; running them found `sign_transaction_hash` raising on every call since eth-account 0.13, `verify_signature` recovering the wrong way and comparing a stripped address, and signing accepting a zero private key | All fixed; `verify_block_signature` also widened to accept standard v=27/28 signatures; 36 property tests pass |
| TEST-04 | Five production suites each skipped silently when no coordinator was running, so an empty run read as a pass | Gate defined once in `tests/production/conftest.py`; `AITBC_REQUIRE_PRODUCTION_SERVICES=1` makes a missing service fail the run; a skipped run says so in the summary |
| TEST-06/07 | `pytest tests/` gave 23 collection errors from directories excluded from `testpaths` and left to rot | `tests/core` (365 tests), `tests/property_tests`, `tests/verification` recovered and added; orphaned suites deleted; `tests/` removed from `sys.path` where it shadowed the real `cli` package; `--import-mode=importlib` resolves the `tests` package collision (93 errors) |
| TEST-08 | `tests/archived_phase_tests/` and `tests/staking/` | Deleted. The 53 "passing" archived tests asserted against their own inline mocks and imported nothing from the codebase |
| DOC-02 | Two diverged spec sets; the coordinator pair shared 1 path out of 354 | `docs/api/` is the single generated set (now including wallet and agent-coordinator); `make openapi-check` fails on drift |
| DOC-03 | Six version-prefixed files loose in `docs/releases/` | Moved into `docs/releases/<version>/` |
| DOC-07 | Three `.orig` files in `docs/meta/pre-boilerplate-backup/` | Renamed to `.md` rather than deleted — CLAUDE.md cites one as live context. Surfaced and fixed 3 links that never resolved |
| OPS-17 | Four scripts each spelled out the service list inline, already diverged | One `lib/services.sh`; shutdown reverses startup order explicitly |

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
