# Epic ABS-231 — Phase 3 (Knowledge: ADRs & Policies) Merge Log

> Append-only. Each entry records one story merge onto `epic/ABS-231-phase3-knowledge`.
> Entries are never edited or removed. The human gate is the epic→`main` PR (Epic Integration seat) — never here.

---

## Entry 1 — ABS-378 (2026-07-17)

| Field | Value |
|-------|-------|
| **Story** | ABS-378 — S1: Knowledge schema migration (`adr` type, `adr-lifecycle`, `policy`/`policy_revision` tables) |
| **MR** | !42 (source `ABS-378-auto` → target `epic/ABS-231-phase3-knowledge`) |
| **Commit merged** | `7dc36f3` feat(db): knowledge migration — adr type, adr-lifecycle, policy/policy_revision [ABS-378] |
| **Epic branch tip after merge** | `6806bf5` (GitLab merge commit into the epic branch) |
| **Epic branch created** | Off `main` `ac339ae` — Merging seat pinned the canonical name `epic/ABS-231-phase3-knowledge` (first story; zero pre-existing `epic/ABS-231*` heads) |
| **Rebase** | `478224c` → `7dc36f3`, replayed onto epic tip `ac339ae`; clean, no conflicts |
| **Migration prefix** | `009_knowledge_adr_policy.sql` — next free prefix on `main` (001–007 present); integrity guard satisfied (no edits to pre-existing migrations); binding operator bsa-decision 2026-07-17T17:24 |
| **Gate sequence** | DE → System Architect Stage 1 (APPROVED → In Test) → QAS In Test (APPROVED) → PO Story Acceptance (ACCEPTED → Merging) |
| **Local CI (RTE, post-rebase onto `main` ac339ae)** | `pnpm -r typecheck` PASS (5 pkgs) · `pnpm lint` PASS · core `pnpm test` **172/172 pass, 0 skipped** (DB-gated, real Postgres backend-db-1) incl. all ABS-378 tests + Phase-1 conformance |
| **Remote CI** | None on the GitLab fallback (Bitbucket down 2026-07-16); validation is local per the epic-ABS-229 precedent |
| **ORCH_AUTOMERGE** | 1 — merged by epic-automerge-watcher (ADR-A-0014); no `main` merge |
| **Exit** | `Merging → Docs` (watcher transition; canonical merged-exit) |

---

## Entry 2 — ABS-380 (2026-07-17)

| Field | Value |
|-------|-------|
| **Story** | ABS-380 — S3: Policy CRUD + effective-policy resolution (Org ∪ Project) with `policy_rev` |
| **MR** | !52 (source `ABS-380-auto` → target `epic/ABS-231-phase3-knowledge`) |
| **Commit merged** | `b55770a` feat(api): policy CRUD + effective-policy resolution (Org ∪ Project) [ABS-380] |
| **Epic branch tip after merge** | `c7e3994` (GitLab merge commit into the epic branch) |
| **Rebase** | None required — `b55770a` parent already == epic tip `61e54fd`; linear, fast-forwardable, zero conflict |
| **Gate sequence** | BE → System Architect Stage 1 (APPROVED → Security Review) → Security Review (PASS) → QAS In Test (APPROVED → Story Acceptance) → PO Story Acceptance (ACCEPTED → Merging) |
| **CI evidence (RTE)** | No rebase needed → relied on the Architecture + Security + QAS suites independently re-run on `b55770a` (posted to tracker): `pnpm -r typecheck` PASS (5 pkgs) · `pnpm lint` PASS · core **181/181** · resolver `policy-resolution` **9/9** · routes `policy-routes` **9/9**; 16 pre-existing server-suite failures (`bootstrap-promotion` 3, `command-routes` 8, `report-routes` 5) proven **zero-regression** vs parent `61e54fd` (environment-class, out of scope) |
| **Remote CI** | None on the GitLab fallback (Bitbucket down 2026-07-16); validation is the re-run gate suites per the epic-ABS-229 precedent |
| **ORCH_AUTOMERGE** | Effective auto-merge — GitLab merged MR !52 onto the epic branch (project default; no pipeline gate), same path as Entry 1; no `main` merge |
| **Exit** | `Merging → Docs` (canonical merged-exit) |

---

## Entry 3 — ABS-379 (2026-07-18)

| Field | Value |
|-------|-------|
| **Story** | ABS-379 — S2: ADR importer + lifecycle transitions (human-only acceptance) |
| **MR** | !62 (source `ABS-379-auto` → target `epic/ABS-231-phase3-knowledge`) |
| **Commits merged** | `b9a9d83` feat(api): ADR importer + lifecycle human-only guard (ABS-231 S2) [ABS-379] · `f159bff` fix(api): harden ADR-Accepted guard + wire superseded bus event [ABS-379] |
| **Epic branch tip after merge** | `c721087` (GitLab merge commit) |
| **Rebase** | Pre-rebase SHAs `906c0d4`+`c85f073` (branched off ABS-378 tip `61e54fd`) rebased onto epic tip `fc24ee8` (after ABS-380 merge); clean 2-commit replay → `b9a9d83`+`f159bff`; no conflicts |
| **Gate sequence** | BE → System Architect Stage 1 CHANGES REQUESTED (iter 1: denylist→allowlist + supersedes bus publish) → BE fixes → System Architect Stage 1 APPROVED (re-review) → Security Review PASSED → QAS In Test (APPROVED for RTE) → PO Story Acceptance (ACCEPTED → Merging) |
| **CI evidence (RTE)** | `pnpm typecheck` PASS · `pnpm lint` PASS · **18/18** `adr-import-routes` tests (DB-gated, live Postgres) · live HTTP verify: viewer→403, orchestrator→403, admin→200 (be-developer + arch re-ran deterministic gates independently) |
| **Remote CI** | None on the GitLab fallback (Bitbucket down 2026-07-16); validation is the gate-suite re-run per epic-ABS-229 precedent |
| **ORCH_AUTOMERGE** | 1 — GitLab merged MR !62 onto the epic branch (project default on push; no pipeline gate); same path as Entries 1–2; no `main` merge |
| **Exit** | `Merging → Docs` (canonical merged-exit) |

---

## Entry 4 — ABS-381 (2026-07-18)

| Field | Value |
|-------|-------|
| **Story** | ABS-381 — S4: `policies` agent op + `capabilities` advertisement |
| **MR** | !64 (source `ABS-381-auto` → target `epic/ABS-231-phase3-knowledge`) |
| **Commits merged** | `9b3fbba` feat(api): policies agent op + capabilities advertisement (ABS-231 S4) [ABS-381] · `e9ff29d` docs(qa): ABS-381 QA validation report — APPROVED |
| **Epic branch tip after merge** | `e33ab57` (GitLab merge commit into the epic branch) |
| **Rebase** | None required — story branch parent `1a18648` already == epic tip `1a18648`; linear, fast-forwardable, zero conflict |
| **Gate sequence** | BE → System Architect Stage 1 (APPROVED → In Test) → QAS In Test (APPROVED → Story Acceptance) → PO Story Acceptance (ACCEPTED → Merging) |
| **CI evidence (RTE)** | No rebase needed → relied on gate-suite re-runs (BE, arch, QAS ran independently): `pnpm -r typecheck` PASS (5 pkgs) · `pnpm lint` PASS · **142/142** `test-backend-tracker.sh` (Test 16: 10 new `policies` assertions + Test 14 capabilities); 0 regressions vs parent `1a18648` |
| **Remote CI** | None on the GitLab fallback (Bitbucket down 2026-07-16); validation is the gate-suite re-run per epic-ABS-229 precedent |
| **ORCH_AUTOMERGE** | 1 — GitLab merged MR !64 onto the epic branch (rebase strategy; no pipeline gate); same path as Entries 1–3; no `main` merge |
| **Exit** | `Merging → Docs` (canonical merged-exit) |

---

## Entry 5 — ABS-383 (2026-07-18)

| Field | Value |
|-------|-------|
| **Story** | ABS-383 — S6: ADR register + policy editor with effective-policy preview |
| **MR** | !66 (source `ABS-383-auto` → target `epic/ABS-231-phase3-knowledge`) |
| **Commits merged** | `c8908a3` feat(ui): ADR register + policy editor with effective-policy preview [ABS-383] · `51e5723` docs(qa): ABS-383 QA validation report — APPROVED |
| **Epic branch tip after merge** | `b090167` (GitLab merge commit into the epic branch) |
| **Rebase** | None required — story branch parent `e517459` already == epic tip `e517459`; linear, fast-forwardable, zero conflict |
| **Gate sequence** | FE → System Architect Stage 1 (APPROVED → In Test) → QAS In Test (APPROVED → Design Test) → qas-design Design Test (PASS → Story Acceptance) → PO Story Acceptance (ACCEPTED → Merging) |
| **CI evidence (RTE)** | No rebase needed → relied on gate-suite evidence: `pnpm lint` PASS · `pnpm -r typecheck` PASS (5 pkgs) · `pnpm --filter @agentic-backend/web build` PASS (181 kB, 304 ms); 11 files +1037/−13; all 5 ACs verified by QAS + qas-design + system-architect independently |
| **Remote CI** | None on the GitLab fallback (Bitbucket down 2026-07-16); validation is the gate-suite re-run per epic-ABS-229/ABS-231 precedent |
| **ORCH_AUTOMERGE** | 1 — GitLab auto-merged MR !66 onto the epic branch (project default on push; no pipeline gate); same path as Entries 1–4; no `main` merge |
| **Exit** | `Merging → Docs` (canonical merged-exit) |

---

## Entry 6 — ABS-382 (2026-07-18)

| Field | Value |
|-------|-------|
| **Story** | ABS-382 — S5: `build_packet` policy injection — revision-pinned, cached, audited |
| **MR** | !67 (source `ABS-382-auto` → target `epic/ABS-231-phase3-knowledge`) |
| **Commits merged** | `474bfdc` feat(orchestrator): revision-pinned policy injection in build_packet [ABS-382] · `08627d4` docs(qa): ABS-382 QA validation report — APPROVED [ABS-382] |
| **Epic branch tip after merge** | `b3f3943` (GitLab merge commit into the epic branch) |
| **Rebase** | `0a0a916`/`ef04ad4` → `474bfdc`/`08627d4`, replayed onto epic tip `040071b` (story branch had forked at `e517459`, behind after Entry 5/ABS-383 merged); clean, zero conflicts |
| **Gate sequence** | BE → System Architect Stage 1 (APPROVED → Security Review) → security-engineer Security Review (APPROVED) → QAS (APPROVED → Story Acceptance) → PO Story Acceptance (ACCEPTED → Merging) |
| **CI evidence (RTE, post-rebase onto epic tip `040071b`)** | `shellcheck -x scripts/orchestrator.sh` — identical finding set vs epic baseline (no new findings) · `tests/test-orchestrator.sh` **1166/1166 pass, 0 fail** (EXITCODE 0), incl. 9 new ABS-382 assertions + `policies-cap-tracker.sh` fixture |
| **Remote CI** | None on the GitLab fallback (Bitbucket down 2026-07-16); validation is the gate-suite re-run per epic-ABS-229/ABS-231 Entry 1–5 precedent |
| **ORCH_AUTOMERGE** | 1 — GitLab auto-merged MR !67 onto the epic branch (project default on push; no pipeline gate); same path as Entries 1–5; no `main` merge |
| **Exit** | `Merging → Docs` (canonical merged-exit) |

---

## Entry 7 — ABS-385 (2026-07-18)

| Field | Value |
|-------|-------|
| **Story** | ABS-385 — S8: Documentation — knowledge model, `policies` op, ADR-import runbook |
| **MR** | !68 (source `ABS-385-auto` → target `epic/ABS-231-phase3-knowledge`) |
| **Commits merged** | `6c66385` docs(knowledge): Phase-3 knowledge surface — API ref, knowledge guide, ADR-import runbook [ABS-385] · `aae4ca2` docs(qa): ABS-385 QA validation report — APPROVED [ABS-385] |
| **Epic branch tip after merge** | `b60285a` (GitLab merge commit into the epic branch) |
| **Rebase** | None required — story branch parent `91553d71` already == epic tip `91553d71`; linear, fast-forwardable, zero conflict |
| **Gate sequence** | tech-writer → System Architect Stage 1 (APPROVED → In Test) → QAS In Test (APPROVED → Story Acceptance) → PO Story Acceptance (ACCEPTED → Merging) |
| **CI evidence (RTE)** | No rebase needed → relied on gate-suite evidence: awk lint gate (0 new overlong lines; 1 pre-existing 126-char line unchanged) · merge-base gate (S1–S5 SHAs ABS-378..382 all ancestors of HEAD, exit 0) · system-architect verified all factual claims against merged S1–S5 source (exact match on all 11 verified items) · QAS verified all 4 ACs; 3 new doc files + 424-line API extension |
| **Remote CI** | None on the GitLab fallback (Bitbucket down 2026-07-16); validation is the gate-suite evidence per epic-ABS-229/ABS-231 Entry 1–6 precedent |
| **ORCH_AUTOMERGE** | 1 — GitLab auto-merged MR !68 onto the epic branch (project default on push; no pipeline gate); same path as Entries 1–6; no `main` merge |
| **Exit** | `Merging → Docs` (canonical merged-exit) — last Phase-3 child; epic JOIN for ABS-231 fires |

---

## Entry 8 — ABS-384 (2026-07-18)

| Field | Value |
|-------|-------|
| **Story** | ABS-384 — S7: Conformance suite — knowledge parity, resolution matrix, injection, human-only rejections |
| **MR** | !69 (source `ABS-384-auto` → target `epic/ABS-231-phase3-knowledge`) |
| **Commits merged** | `3693685` feat(api): §10 conformance suite — ADR/policy/human-only/export round-trip [ABS-384] · `03d18f9` fix(tests): wire §10 Cases 4+5 into conformance suite, fix security auto-pass [ABS-384] · `f477afd` docs(qa): ABS-384 QA validation report — APPROVED [ABS-384] |
| **Epic branch tip after merge** | `78369a4` (GitLab merge commit into the epic branch) |
| **Rebase** | Pre-rebase tip `7d27577` (3 story commits on parent `6806bf5`, forked before entries 2–7); replayed onto epic tip `203fb35` (entry 7/ABS-385); clean, zero conflicts → new SHAs `3693685`/`03d18f9`/`f477afd` |
| **Gate sequence** | BE → System Architect Stage 1 CHANGES REQUESTED (iter 1: §10 Cases 4+5 absent, security auto-pass, tautological anti-test) → BE fixes (iter 2) → System Architect Stage 1 APPROVED → Security Review PASSED → QAS In Test APPROVED → PO Story Acceptance ACCEPTED → Merging |
| **CI evidence (RTE)** | `tests/test-backend-tracker.sh` **187/187 PASS** (Tests 17–22 cover §10 Cases 1–7) · `tests/test-tracker-adapter-lint.sh` **21/21 PASS** (all 7 §10 markers required) · `pnpm lint` PASS · `pnpm typecheck` PASS · `bash -n` syntax OK on all 3 test files |
| **Remote CI** | None on the GitLab fallback (Bitbucket down 2026-07-16); validation is the gate-suite evidence per epic-ABS-231 Entry 1–7 precedent |
| **ORCH_AUTOMERGE** | 1 — GitLab auto-merged MR !69 onto the epic branch (project default on push; no pipeline gate); same path as Entries 1–7; no `main` merge |
| **Exit** | `Merging → Docs` (canonical merged-exit) — final S7; all 8 Phase-3 stories (ABS-378..385) now merged; epic ABS-231 JOIN fires |

---
