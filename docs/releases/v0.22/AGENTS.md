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

**Open: 27** — Agent A 22, Agent B 2 (one partial), plus 3 unassessed noted at the end.

Fix suggestions are starting points, not specifications. Pattern discovery and
architectural validation still apply.

---

## Agent A — Core / Shared / Bridge / Infrastructure

Scope: `aitbc/`, `apps/blockchain-node`, `apps/blockchain-event-bridge`,
`apps/blockchain-explorer`, `contracts/`, `scripts/`, `packages/`, tests and docs.

### Contracts — 3

All three are unbounded loops that become un-callable as data grows: denial of service
arriving through ordinary use, not attack. They share a fix shape, so do them together.

**SC-05 — `distributeAgentEarnings`** · *verified: 4 `break` statements in `AgentStaking.sol`*
Loops `pool.stakers` unbounded with a nested inner scan, and `break`s on the first ACTIVE
stake per staker — so anyone holding several concurrent stakes on one agent is paid for
only one of them.

> **Fix:** move to **pull-based accounting**. Record an accumulator (`rewardPerShare`) on
> the pool and let stakers call `claim()`, rather than iterating and pushing payments.
> This removes the loop and the gas ceiling at once. Fix the under-payment in the same
> pass: accumulate across *all* of a staker's active stakes instead of `break`ing on the
> first match. Add a test with one staker holding three concurrent stakes — it should fail
> before the fix.

**SC-06 — `_slashAllStakesForAgent`** · *verified: 4 refs*
Loops all historical stakes with an external token transfer per iteration, so slashing
eventually cannot execute at all.

> **Fix:** paginate — `slashStakes(agent, startIndex, count)` with a bounded batch, called
> repeatedly until exhausted. Track progress on-chain so a partially-completed slash can
> resume. Prefer crediting a claimable balance over transferring per stake.

**SC-12 — `getBountyStats`** · *verified: `i < bountyCounter` loop*
Walks every bounty ever created; it is a `view`, but another contract can call it on-chain.

> **Fix:** maintain running counters (`activeCount`, `completedCount`, `totalValue`)
> updated on each state transition, and have the getter read them. O(1) instead of O(n).

### Ops — 4

**OPS-03 / OPS-08 — `scale_balances_3600x.py`** · *verified: `"simplified implementation"` marker; production chain-id default present*
**Release-blocking before any hard fork.** The script writes a hand-rolled sha256 as the
genesis state root; the node computes a Merkle Patricia Trie root and will not agree, so
the chain fails genesis validation *after* an irreversible ×3600 balance rewrite. It also
defaults `--chain-id` to the production domain and `--data-path` to `/var/lib/aitbc/data`,
so running it bare targets production.

> **Fix:** import the chain's actual state-root implementation from
> `apps/blockchain-node` rather than recomputing it — if that is not importable, that is
> the real finding and should be raised as such. Remove the production defaults (require
> both flags explicitly), and add a typed confirmation before the rewrite. Verify by
> running the migration against a copy and booting a node on the result; a genesis the
> node rejects is the failure this is meant to prevent.

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

### Packages — 6

**Start with PKG-05: it is now unblocked** and will likely surface PKG-08/09/14 as real
type errors rather than findings someone has to notice by reading.

**PKG-05 — `@ts-nocheck`** · *verified: 5 files*
Disables type checking file-wide while `lint` runs `tsc --noEmit`, so the gate reports zero
errors regardless of correctness.

> **Fix:** PKG-06 (closed) added the missing devDependencies, so `npm install && npx tsc
> --noEmit` now works. Remove the pragmas one file at a time and fix what surfaces. If a
> file genuinely cannot be typed yet, scope it out of `tsconfig`'s `include` with a comment
> explaining why — a visible exclusion beats an invisible one.

**PKG-03 — plugin loader** · *verified: 1 `import_module` call, no allowlist*
Arbitrary code execution by design: `importlib.import_module` on a module path taken from a
manifest, then called with `manifest.config`.

> **Fix:** two layers. (1) An allowlist of importable module prefixes, checked before
> import — this alone closes the common case. (2) Signature verification of manifests
> before load, reusing `aitbc.crypto` rather than a new scheme. Until both exist, make
> `load_plugin` refuse manifests from any untrusted source rather than documenting the
> risk in a docstring. Largest package item.

**PKG-08 — `useWalletTheme`** · *verified: `setTimeout` stub present*
A stub whose name and return shape imply on-chain persistence; `setPreference` just
`setTimeout`s and updates local state.

> **Fix:** either wire it to `AgentIdentity.themePreference(address)` via ethers/viem, or
> make the stub honest — return a `notImplemented` flag, or throw. Same class as CORE-24
> and the gpu 501s: do not report success for work not done.

**PKG-09 — duplicate `localStorage` owner** · *verified: 3 owners of the key*
`usePreferences` and `ThemeProvider` independently own
`localStorage["aitbc-theme-preference"]` with no cross-instance sync, so they silently
diverge when both mount.

> **Fix:** single source of truth — have `usePreferences` delegate to the
> `ThemeProvider` context instead of re-reading storage. If both must remain, add a
> `storage` event listener so they converge.

**PKG-10 — placeholder visual regression** · *verified: placeholder marker present*
The suite renders nothing; it sets a DOM attribute and asserts it was set, so it passes
with the theming entirely broken.

> **Fix:** either wire up a real Playwright screenshot diff, or rename it to what it is
> (`test_theme_attribute.py`) and drop the "visual regression" claim. False confidence in
> CI is worse than an acknowledged gap.

**PKG-14 — unguarded `matchMedia`** · *verified: 3 calls*
`readPreference` calls `window.matchMedia` with no SSR guard; safe today only because its
sole call site is inside a `useEffect`.

> **Fix:** apply the same `typeof window === "undefined"` guard `resolveMode` already uses
> a few lines above. One line, and it removes a latent SSR crash.

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

### Open — 2

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

**APP-35 — unlocked registry mutation (partial)** · *verified: lock present in `load_balancer.py`, absent in `agent_discovery.py`*
The load balancer now has an `asyncio.Lock`; `agent_discovery` still mutates its registry
without one.

> **Fix:** mirror what `load_balancer.py:128` already does — an `asyncio.Lock` on the
> instance, taken around registry mutation and iteration. Check whether the hash ring is
> rebuilt on membership change while you are there; that was the other half of this
> finding.

### Closed since the last revision — do not re-do

| ID | Was | Now |
|---|---|---|
| APP-32 | Trusted-member status from `journalctl` regex | Replaced |
| APP-33 | Workflow steps slept 0.1s and marked themselves COMPLETED | Raises `NotImplementedError` |
| APP-50 | exchange API key failed open when unset | Fails closed with 401 |
| APP-64 | Event-bridge checkpoint reset to chain head, no reorg handling | Persisted checkpoint + reorg window |
| CLI-02/07/08/09 | Placeholder balance, weak redaction, dropped CLI context, fabricated stats | Closed before AITBC-91 |
| CLI-03/05/06/10/13 | In-memory credentials, process-local challenges, umask audit log, secrets TOCTOU, stub group | Closed in AITBC-91 |

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
  silently disabled. Every fix since is post-tag — the tag needs moving or superseding
  before anyone deploys from it.
