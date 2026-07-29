# Orchestrator SOP — Change Log (append-only)

Per-ticket history for [`ORCHESTRATOR_SOP.md`](./ORCHESTRATOR_SOP.md). This file
is the conflict-free replacement for the old single-line `**Version**:`
parenthetical that everyone edited at once (ABS-215).

**How to add an entry (implementer seats):** append **one new line** to the
bottom of the list below — one ticket per line — and never edit or reflow
existing lines. This file carries `merge=union` in `.gitattributes`, so two
branches that each append their own line auto-merge with **zero conflict** and
**no hand-resolve** (#EXPORT_CRITICAL). Editing an existing line, or reordering,
re-introduces the conflict magnet — don't.

<!-- APPEND BELOW — one ticket per line, newest last. Do not edit prior lines. -->

- SOP v1.6 baseline: orchestrator event loop (ABS-52..55)
- hardening (ABS-111)
- assignee-at-spawn (ABS-126)
- turn-cap-salvage + handoff-transition-default-on (ABS-175)
- packet-cache-signature hardening (ABS-202)
- multi-orchestrator operating mode (ABS-181/ABS-188)
- claim-assign cosmetic layer (ABS-186)
- claim mutex test suite + tuning (ABS-187)
- escalation-resume-to-origin ADR-A-0019 (ABS-204)
- shared-file conflict-magnet fix: per-story test files + append-only SOP change log (ABS-215)
- progress-based watchdog: telemetry idle-detection + absolute MAX_LIFETIME, kill-switch ORCH_WATCHDOG_IDLE (ABS-225)
- STATION-GUARD flag-conditional enforcement: flag-set conditional stations count as mandatory (ABS-247)
- per-epic merge token held across bounce: ORCH_MERGE_QUEUE, livelock-prevention (ABS-256)
- handoff commit verification: ORCH_VERIFY_COMMITS, commits: field contract, In Progress→Ready for Development edge (ABS-255)
- crashed-spawn stdout/Result-JSON retained as evidence; $pf.diag gains subtype= line (ABS-265)
- poisoned-session guard: denial-hit sessions dropped; ORCH_SESSION_POISON_GUARD; salvage birth state (ABS-254)
- STATION-GUARD merge-boundary: Docs-landing exempt from station-order check; Needs PO Decision Docs exit (ABS-266)
- STATION-GUARD pre-filled epic DoR gate: JOIN-rest park redirect + epic_visited_grooming discriminator (ABS-271)
- Kleinbefunde bundle: kind-header write guard + non-silent parser warning; account-switch session invalidation on startup; PushNotification + macOS dialog SOP rule for session-local watchers (ABS-302)
- suite drift fix: test-epic-join-resting.sh pins ABS-214 JOIN-rest edge + ABS-271 STATION-GUARD redirect (ABS-309)
- handoff marker duty verification: ORCH_VERIFY_MARKERS, JOIN-exempt + bsa pile-empty claims verified before handoff acceptance, MARKER-MISSING refusal path mirrors ABS-255 (ABS-297)
- lane field as first-class ticket attribute: create --lane / update <id> lane / search --lane; batch-candidate label superseded by lane: fastlane (ABS-319)
- fastlane collapsed chain: lane=fastlane routes to a Solo-Seat (dev+scoped-tests+self-review) + ONE combined review/test gate (In Review) + merge-queue; QAS (In Test) and PO (Story Acceptance) fold forward via FASTLANE-COLLAPSE; kill-switch ORCH_FASTLANE_COLLAPSE; lane=normal unchanged; merge-token/full-suite/human-merge untouched (ABS-322)
- async fastlane PO-acceptance daily batch: fastlane tickets past the combined gate + merge-queue rest at Docs for scripts/fastlane-acceptance-batch.sh (list/accept/reject); accept records a kind:decision only (no merge, AC5); reject records defects + routes Docs -> Ready for Development (new legal edge) as po-agent, incrementing the ABS-74 rework counter (AC4); acceptance timing/batching changes, semantics unchanged (ABS-323)
- fastlane bundling: several eligible lane=fastlane tickets at Ready for Development share ONE Solo-Seat run / branch / PR — deterministic capped chunks, the lexicographically-first member is the LEAD (spawns once with the whole roster in its seat_note: per-ticket atomic commits [ABS-XXX] on branch <lead>-auto, one PR referencing all ids), non-lead members fold via FASTLANE-BUNDLE-FOLD; combined gate attributes pass/fail per ticket; cap ORCH_FASTLANE_BUNDLE_MAX (default 4), kill-switch ORCH_FASTLANE_BUNDLE; lane=normal/flagged/depends_on never bundled; bundle still ends at the merge-queue, no self-merge (ABS-324)
- priority-aware slot allocation: reconcile sweep offers free slots in canonical-priority order before the cap; ORCH_PRIORITY_DISPATCH kill-switch + ORCH_HOTFIX_CAP_BONUS no-preemption overrun; DEFER-CAP names priority (ABS-261)
- cross-reference to TRACKER-MIGRATION-RUNBOOK.md in the TRACKER_CMD switching recipe (ABS-329)
- base-freshness guard + spawn-seam env scrub + state-dir self-heal: resolve_fresh_base() + _bounded_git() replace hardcoded origin/main base; ORCH_REMOTE_PROBE_TIMEOUT; live-state var scrub in run_spawn_cmd; heal_state_dir() + acquire_lock ENOENT recovery (ABS-355)
- main-checkout seat state-dir isolation + forensic self-heal + wipe-resistant ledger: ABS-205 seam extended for main-checkout seats (ORCH_SEAT_STATE_ROOT throwaway redirect); heal_state_dir() partial-vs-full wipe classification + per-component forensic logging; rebuild_daily_ledger() reconstructs spawn-ledger from run.log INTENT-SPAWN events on self-heal; regression test ABS-393-main-checkout-state-isolation.sh (ABS-393)
- depends_on release point: merge fact (git merge-base --is-ancestor) replaces Docs-label shortcut (ABS-119); blocker satisfied on merged head OR Done — never on status string; depends-strict label opts out and waits for Done; epic-completion gate unchanged (PILOT-19)
- depends_on gate: Docs status treated as SATISFIED (post-merge structural guarantee per ABS-266); depends-strict still waits for Done; epic-JOIN gate unchanged — child in Docs still blocks JOIN; closes v3-pilot #5 downstream-wave stall (PILOT-44)
- iteration-guard cap floor is config (ITERATION_GUARD_DEFAULT_CAP); markers may only raise it (max wins, not most-recent); block message names cap source + functional/abort split; closes PILOT-32 deadlock class (PILOT-64)
- worktree-provisioning failure counter + backoff + escalation after N attempts (NOTIFY Attention-Event); git stderr captured in runlog; post-checkout main-HEAD guard prevents root cause (PILOT-66)
- rule-ledger hygiene: four misattributed sensor/kind cells corrected + twelve copy-paste risk notes replaced with per-decision LLM-only risk statements; checker-limit header added (existence not wiredness); ponytail skill shipped to harness/claude/skills/ponytail/ (.agents + .gemini mirrors); ADR-A-0010 updated to cite shipped paths only (PILOT-68 / ABS-570)
- taxonomy effects enforced: ADR-A-0018 transient class is now budget-neutral for rework counter (ORCH_REWORK_INFRA_RE, mirrors ABS-555 iteration exclusion); finished-work cap/rework escalation parks to Blocked (reached_merge_tier + escalation_park_target) instead of Needs PO Decision, keeping the merge path reachable; ADR-A-0024 HANDOFF-CLAIM-NOHASH advisory counted per role + run total in skill-mining.sh (Test 8) with measurable committing-vs-review-seat promotion criterion; ADR_AUTHORING_GUIDE.md: "Every Classification Must Name Its Effect" section + rule-ledger R-1101 (kind: unenforced); ADR-A-0018 documents each class's concrete effect (PILOT-69 / ABS-571)
- blocked-auto-release/re-block churn loop bounded: fact-fingerprint idempotency (cause-keyed, survives Re-Block), per-ticket churn cap ORCH_BLOCKED_RELEASE_CHURN_CAP (default 3), deduped Attention-Event via blocker_notified; 15-assert PILOT-72 fixture + ABS-296 updated (PILOT-72)
- remote push verification gate: ORCH_VERIFY_PUSH enforces that forward-completion handoffs (In Review..Done) have commits reachable on the active remote, not just locally; local-only commit is mis-report (ADR-A-0024); active remote via active_remote_name() never hardcoded origin (ADR-A-0030); AC3 unclean-main-checkout sensor in ops-sweep-sensors.sh; falsification fixture 7/7 (PILOT-75)
- commit-tag guard: commit-msg hook enforces [PREFIX-XXX] on story-branch seat commits; two-class exempt table (release/[no-ticket]); recover subcommand in bisect step 6 prevents dead-end Needs PO Decision for untagged culprits; 25-assert suite; docs/sop/COMMIT_TAG_GUARD_SOP.md (PILOT-79)
- run-status collector marker content check: reads marker VALUE (not existence) for fastfail/outage — empty or `0` is cleared/reset, not a human gate; fastfail is a burst counter the runner resets to "0" in place while spawning continues; gate line names the marker value; honesty invariant preserved (no state dir → `run.health: unavailable`, not silent OK); per-marker regression suite (41 tests) (PILOT-74)
- gate-seat test-tool path anchor: rte.md and qas.md carry an explicit PATH note at the staged-suite block — `tests/staged-suite.sh` is REPO-relative (resolves against the seat cwd, the target repo), NEVER prefixed with a harness/governing-checkout absolute path; in self-hosting the stable checkout is outside the seat sandbox and a misresolved read is DENIED (Pilot 8, 18 session-poison events = 16 % run cost); provider mirror regenerated; AC2 test-seat-repo-path.sh drives the real spawn seam with harness != target checkout (9/9 PASS); AC3 grep-guard blocks absolute machine paths from agent-def/skill source (ABS-599)
- station-aware salvage cap + RTE built-in cap recalibration: `salvage_max_turns()` resolves per-role (`ORCH_SALVAGE_MAX_TURNS_<ROLE>` > `builtin_role_salvage_max_turns()` built-in > default 5); rte salvage built-in=30 (ABS-453 full-suite exit cannot run in 5), rte main cap raised 60→100 (`ceil_to_10(61×1.5)` per ABS-565 formula) (ABS-605)
