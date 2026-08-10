# Pre-Release Checklist

> **MANDATORY**: This checklist must be completed before creating any release tag.
> No exceptions. If any item fails, the release is blocked until resolved.

## Release Information

- **Version**: _____________
- **Release branch**: `main`
- **Previous version**: _____________
- **Linear Epic/Stories**: _____________
- **Release owner**: _____________
- **Date**: _____________

---

## 1. Code Quality Gates

- [ ] All feature branches merged to `main`
- [ ] `bash -n scripts/sync-claude-harness.sh` — syntax check passes
- [ ] All test suites pass (list each with count):
  - [ ] `test-manifest-loader.sh`: ___/___
  - [ ] `test-rename-diff.sh`: ___/___
  - [ ] `test-substitutions.sh`: ___/___
  - [ ] `test-protected-files.sh`: ___/___
  - [ ] `test-preflight.sh`: ___/___
  - [ ] `test-fork-sync.sh`: ___/___
  - [ ] `test-patch-generation.sh`: ___/___
  - [ ] `test-manifest-init.sh`: ___/___
  - [ ] Total: ___/___ (zero failures)
- [ ] No merge conflict markers in any file: `grep -r '<<<<<<' . --include='*.sh' --include='*.md' --include='*.json' --include='*.toml' --include='*.yml'`
- [ ] `shellcheck scripts/*.sh` — no new warnings (document pre-existing)
- [ ] **E2E exit-gate suites** (manual — ABS-143). These are excluded from the
  `tests/test-*.sh` glob (they are `tests/e2e-*.sh`) and from the CI pipeline;
  the release owner runs them by hand and records pass/fail. They are the epic
  exit gate (ORCHESTRATOR_SOP §"epic exit gate", ABS-80) and drive the real
  `scripts/orchestrator.sh` against the mock tracker + stub spawn (no live model):
  - [ ] `bash tests/e2e-orchestrator-dryrun.sh` (v1/v2 lifecycle — ABS-55): ___ pass / ___ fail
  - [ ] `bash tests/e2e-workflow-v3.sh` (v3 full-team scenarios — ABS-80): ___ pass / ___ fail
  - [ ] Any failure investigated and either fixed or documented in Notes/Errata before tagging.
- [ ] **Suite-budget re-measurement** (ABS-603 AC5). The tentpole `tests/test-orchestrator.sh`
  grows with every epic that adds a `tests/orchestrator.d` fixture, shrinking its reserve against
  the per-suite budget. Re-measure it each release so the growth curve stays visible and the budget
  can be re-tuned before it red-lines:
  - [ ] `bash scripts/measure-suite-budget.sh --both --record` — records an isolated + under-load
    row into `docs/release/SUITE-BUDGET.md`; commit that doc change with the release.
  - [ ] If the reserve sensor fired a `LOW RESERVE` warning during `pre-release-check.sh`, decide:
    raise `PRE_RELEASE_SUITE_TIMEOUT`, adopt the staged runner (`tests/staged-suite.sh`), or split
    the tentpole. See `docs/release/SUITE-BUDGET.md` for the rationale and options.

## 2. Documentation Completeness

- [ ] `README.md` — accurate provider list, feature descriptions, version references
  (**Note**: the `version-vX.Y.Z` shield badge is **auto-stamped** by `promote-release.sh`
  and drift-checked by `generate-governor.sh --check` — no manual badge update is needed.
  See `docs/release/README-BADGE-AUTO-STAMP.md` (ABS-129).)
- [ ] `docs/HARNESS_SYNC_GUIDE.md` — reflects all sync features in this release
- [ ] `docs/HARNESS_MANIFEST_SCHEMA.md` — schema matches implementation
- [ ] `docs/guides/GETTING-STARTED.md` — setup instructions current
- [ ] `docs/guides/WORKSPACE-ADOPTION-GUIDE.md` — provider list current
- [ ] `docs/guides/OPTIONAL-FEATURES.md` — optional features list current
- [ ] `harness/claude/README.md` — Claude Code harness docs current (edit the SOURCE only). The
  live `.claude/` is **generated**, not a mirror: it equals `generated(.governor-tag)` (ABS-94,
  Phase 2b). Do NOT hand-diff `harness/claude` against `.claude` — instead verify the drift model
  holds: `bash scripts/generate-governor.sh --check` must pass (live shipped set == generated from
  the pinned tag + CLAUDE.md banner stamped with that tag). At **promotion** the release commit
  bumps `.governor-tag` to the new tag and re-runs `scripts/generate-governor.sh` so the live
  `.claude/` (and CLAUDE.md banner) roll forward to the release just cut — ABS-95 wires that step.
- [ ] `.codex/README.md` — Codex CLI setup guide current (if applicable)
- [ ] `.gemini/README.md` — Gemini CLI docs current (if applicable)
- [ ] No stale references to removed files: `grep -r 'CODEX.md\|\.codex/settings\.json\|\.codex/commands' docs/ README.md harness/claude/ .claude/ .codex/ .cursor/ .gemini/ 2>/dev/null`
- [ ] `HARNESS_CHANGELOG.yml` updated for this release (or generated via `generate-changelog.sh`)

## 3. Third-Party Integration Verification

> **CRITICAL**: For any new or updated third-party tool integration, verify against real vendor documentation. Never ship based on extrapolation alone.

- [ ] **Vendor doc verification**: Each third-party integration checked against official docs
  - [ ] Claude Code: Anthropic docs — https://docs.anthropic.com/claude-code
  - [ ] Codex CLI: OpenAI docs — https://developers.openai.com/codex
  - [ ] Cursor IDE: Cursor docs — https://docs.cursor.com
  - [ ] Gemini CLI: Google docs — https://ai.google.dev/gemini-api
- [ ] Source URLs documented in Linear tickets for QAS verification
- [ ] No fabricated configuration formats (verify every file format, directory path, config key)

## 4. SAFe Workflow Gates

- [ ] All stories QAS-approved (non-collapsible gate)
- [ ] Security Engineer review complete (where applicable, non-collapsible)
- [ ] System Architect Stage 1 approved
- [ ] All Linear tickets marked Done with evidence
- [ ] No stories in "In Progress" or "In Review" state for this release
- [ ] **Live behavioral smoke-run against the RELEASE harness source** (retro 2026-07-10 /
      ABS-170 AC5): when the release changes agent definitions or the pattern-discovery
      protocol, run ONE orchestrator smoke-story with `ORCH_HARNESS_HOME` pointed at this
      dev checkout (pre-promotion the stable governor still serves the OLD defs, so a naive
      live run does not exercise the change). Compare against baseline: same gate-verdict
      quality, no new rework bounces, run.log cost comparison documented.

## 5. Template Compatibility

- [ ] All new files use `{{PLACEHOLDER}}` tokens (not hardcoded project values)
- [ ] `scripts/setup-template.sh` can process all new files: `find . -name '*.md' -o -name '*.json' -o -name '*.toml' -o -name '*.yml' -o -name '*.mdc' | head -20`
- [ ] Example manifests updated (if manifest schema changed):
  - [ ] `examples/manifests/rendertrust.harness-manifest.yml`
  - [ ] `examples/manifests/keryk-ai.harness-manifest.yml`
- [ ] `.harness-manifest.schema.json` updated (if manifest schema changed)

## 6. Backward Compatibility

- [ ] Existing forks NOT broken by this release (no manifest = legacy behavior)
- [ ] Fork-sync CI tests pass against known fork configurations
- [ ] No breaking changes without `BREAKING CHANGES` section in release notes
- [ ] If breaking: migration guide included in docs

## 7. Release Artifacts

- [ ] Git tag created: `git tag -a vX.Y.Z -m "..."`
- [ ] Tag pushed: `git push origin main --tags`
- [ ] GitHub Release created with:
  - [ ] Accurate feature list
  - [ ] Breaking changes section (if any)
  - [ ] Errata section (if fixing previous release issues)
  - [ ] Test coverage summary
  - [ ] Source attribution (Co-Authored-By)
- [ ] Previous release issues noted (if this is a fix release)

## 8. Post-Release Verification

- [ ] Release page accessible: `gh release view vX.Y.Z`
- [ ] Tag matches template HEAD: `git log --oneline -1 vX.Y.Z`
- [ ] Linear epic/stories closed
- [ ] Feature branches cleaned up: `git branch --list 'SAW-*'` returns empty

---

## Sign-Off

| Role | Name | Date | Approved |
|------|------|------|----------|
| Release Owner | | | [ ] |
| QAS Gate | | | [ ] |
| HITL (POPM) | | | [ ] |

---

## Notes / Errata

_Document any known issues, deferred fixes, or caveats for this release._
