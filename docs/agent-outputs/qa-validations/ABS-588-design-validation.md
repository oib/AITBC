# Design Validation — ABS-588
**Epic-Übergabe endet an einem Branchnamen: 'Ready for Epic Acceptance' ohne prüffähiges Artefakt**

| Field | Value |
|---|---|
| Ticket | ABS-588 |
| Commit under test | `b837c0ab` (implementation), `87d1a0c1` (QA report) |
| Branch | `ABS-588-auto` |
| Remote | pushed: `origin/ABS-588-auto`, `gitlab/ABS-588-auto` |
| Validator | qas-design |
| Run date | 2026-07-27 |
| Verdict | **DESIGN APPROVED** |

---

## Pre-Check

| Check | Status | Note |
|---|---|---|
| Design seat DAC block on ticket | ⚠️ ABSENT | Design stage was SKIP-FORWARDed by the orchestrator (16:08 UTC) when the `design` flag was not yet set. No ui-ux-design seat ran; no formal DAC-numbered block exists. |
| Ticket ACs testable without design seat | ✅ PASS | 4 concrete, verifiable criteria — no subjective language; each is independently provable from the implementation text. |
| Implementation artifact exists | ✅ PASS | `b837c0ab` on `ABS-588-auto`, pushed to `origin` + `gitlab`. |
| Design-system file | N/A | This is a workflow/information-design ticket (bash + markdown agent definition); no UI design system applies. |

**Pre-check ruling**: The missing Design seat DAC block is an orchestrator process event (flag was added after the Design stage fired), not a designer omission. Since: (a) this is a non-UI/UX infrastructure ticket, (b) the ticket's 4 ACs are the stated design requirements accepted through every prior gate, and (c) the ACs are specific and testable, I treat AC1–AC4 as the design contract and proceed. This is NOT inventing criteria — the ACs originate from the original BEFUND ticket and were confirmed by the PO decision.

---

## Design AC Verification

### DAC-1 (AC1) — Exactly ONE named next step; child story list explicit; no log-mining

**PASS**

Evidence:
- `rte.md` handoff format (commit `b837c0ab`, line 307):
  ```
  **Human next step (the ONE step, ABS-588 AC1)** — open the epic MR to main yourself; **no agent opens or merges it (ADR-A-0014)**:
        glab mr create --source-branch epic/AITBC-XXX-{description} --target-branch main ...
  ```
  - Label `Human next step (the ONE step, ABS-588 AC1)` unambiguously names exactly one action.
  - The AC reference embedded in the label makes the design intent machine-pinnable.
- Child story list (line 305):
  ```
  **Stories** (all Done): AITBC-XXX AITBC-YYY …   # the child list, so the human never reconstructs it from the log (ABS-588 AC1)
  ```
  - The operator reads the story list directly from the artifact; no git log mining required.
- Test assertion PASS: `ABS-588-epic-handoff-artifact.sh` asserts `"Human next step (the ONE step"`, `"glab mr create --source-branch epic/"`, `"**Stories** (all Done):"`.

**Non-blocking observation (information design)**: The `--description-file work/scratch/<epic-id>-handoff.md` parameter in the prepared `glab mr create` command points to a file in the ephemeral RTE worktree. The human operator would need to adjust this path or substitute `--description` with the comment body text. The System Architect independently flagged this as a non-blocking refinement candidate. It does NOT violate AC1 (there is still ONE named step; the path is a template parameter, not a second step).

---

### DAC-2 (AC2) — ADR-A-0014 boundary verbatim; proven by chosen path, not merely asserted

**PASS**

Evidence:
- Verbatim boundary text retained in `rte.md` (`b837c0ab`):
  - `"You never open or merge a PR to \`main\` from this seat"` ✅
  - `"RTE does not open or touch that \`main\`-bound PR"` ✅
- The handoff artifact ITSELF embeds the constraint:
  ```
  **no agent opens or merges it (ADR-A-0014)**
  ```
  — the boundary is self-documenting in the very artifact the human reads.
- Explanatory paragraph after the handoff format explicitly states: _"This preparation opens **nothing**: RTE still never opens or merges the `main`-bound PR (ADR-A-0014 unchanged, ABS-588 AC2); the human runs the one prepared command."_
- Path (a) — "an agent OPENS the main MR" — was explicitly documented as OUT OF SCOPE with rationale in the be-developer gate-results comment. The chosen path (b+c) is boundary-neutral by construction: RTE only posts a comment; the human executes the command.
- Test assertions PASS: both verbatim boundary strings grep-asserted in `ABS-588-epic-handoff-artifact.sh`.

---

### DAC-3 (AC3) — Verification state (commit, suite, result) part of the handoff; produced at release time (no CI on live remote, ABS-559)

**PASS**

Evidence:
- Artifact format (`b837c0ab`, lines 299-311):
  ```
  - **Epic branch**: epic/AITBC-XXX-{description} @ <epic-tip sha>
  - **Full suite on epic tip** (ABS-453): <counter, e.g. 142 passed, 0 failed> @ <epic-tip sha>
  ```
  - Epic-tip sha: explicit on the `Epic branch` line AND on the `Full suite` line.
  - Suite counter (passed/failed) explicit.
  - The cross-reference of sha on two fields lets the human verify they reference the same state.
- The explanatory paragraph explicitly references ABS-559: _"The verification state (epic-tip sha + full-suite result) rides in the artifact because the live remote has no CI (ABS-559, ABS-588 AC3) — it is produced here at release time, not assumed from a pipeline."_
- The instruction text (line 236): _"FIRST post the reviewable epic-handoff artifact ... THEN release the epic"_ — production order is enforced before the transition.

---

### DAC-4 (AC4) — Missing artifact → reported finding; not silently "waiting for human"

**PASS**

Evidence:
- `EPIC-HANDOFF-READY` marker: load-bearing line in the handoff format, described as such in `rte.md`.
- `scripts/ops-sweep-sensors.sh` detector 9 `epic-handoff-missing` (`b837c0ab`):
  - Registered in `ALL_DETECTORS` and `run_one` case statement.
  - Logic: scans `OPS_TICKETS_DIR/*.md` for `status: Ready for Epic Acceptance` tickets; flags any that do NOT contain `OPS_EPIC_HANDOFF_MARKER` (default: `EPIC-HANDOFF-READY`).
  - Marker default coherence: `OPS_EPIC_HANDOFF_MARKER:-EPIC-HANDOFF-READY` matches the token in `rte.md` exactly — a rename on one side without the other is caught by the coherence assertion.
- Sensor fixture tests PASS (`test-ops-sweep-sensors.sh`, 39/39):
  - Positive: PILOT-58 (at `Ready for Epic Acceptance`, no marker) → `epic-handoff-missing PILOT-58 status=Ready-for-Epic-Acceptance,artifact=absent` emitted.
  - Negative 1: PILOT-59 (marker present) → not flagged.
  - Negative 2: PILOT-62 (wrong status) → not flagged.
- Remediation hint `post-epic-handoff-artifact` is emitted in the finding, so the ops-sweep consumer knows what corrective action to take.

---

## Summary Matrix

| DAC | Description | Verdict | Evidence |
|---|---|---|---|
| DAC-1 / AC1 | ONE named next step + child story list | **PASS** | `Human next step (the ONE step, ABS-588 AC1)` label + `**Stories** (all Done):` field in rte.md; test assertions PASS |
| DAC-2 / AC2 | ADR-A-0014 verbatim + proven by path b/c | **PASS** | Two verbatim boundary strings retained; boundary embedded in artifact; path (a) explicitly excluded; test assertions PASS |
| DAC-3 / AC3 | Verification state (sha + suite result) in artifact | **PASS** | `Epic branch … @ <sha>` + `Full suite … @ <sha>` fields; ABS-559 noted; production order enforced before release transition |
| DAC-4 / AC4 | Missing artifact → reported finding (not silent) | **PASS** | `epic-handoff-missing` detector registered; pos/neg fixtures 39/39 PASS; marker↔sensor coherence asserted |

---

## Findings

None. No design-fix or impl-fix findings.

---

## Verdict

**DESIGN APPROVED**

All 4 design ACs pass. The information design of the RTE handoff artifact is:
- **Clear**: ONE step labeled explicitly and annotated with AC reference
- **Complete**: child list, verification state (sha + suite), boundary constraint all embedded in the artifact
- **Self-enforcing**: `EPIC-HANDOFF-READY` marker → `epic-handoff-missing` sensor → finding reported if absent
- **Boundary-compliant**: ADR-A-0014 text verbatim; boundary-neutral path (b+c) by construction

Next: Story Acceptance.
