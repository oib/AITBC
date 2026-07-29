# Design System Adapter — Interface

> _Adapted from the clean-room blueprint. Inline `.agentic/…` names below are design-record concepts; their live homes are in the [crosswalk](../../../blueprint/CROSSWALK.md). Treat this file as the capability contract._

Mandatory **when a design system is configured** (`config.design_system.enabled: true`); the
stack fully works without one. Frontend agents must consume design tokens, component rules, and
UX constraints exclusively through this adapter — never by re-deriving them from raw sources.

## Operations

| Operation | Semantics |
|-----------|-----------|
| `get_tokens(category?)` | Design tokens (color, spacing, typography, elevation…), technology-neutral names + values. |
| `get_component_rules(component?)` | Allowed components, variants, composition rules, do/don'ts. |
| `get_ux_constraints(context?)` | Interaction/accessibility/layout constraints for a given surface. |
| `excerpt_for(ticket_scope)` | Pre-summarized guidance for embedding into ticket packets (used by the Ticket Creation Agent). |
| `check(change_ref)` | Backs the `design-system-check` quality gate: token misuse, off-system components, constraint violations. **Backing:** the vendored, version-pinned `impeccable` detector via `scripts/design-system-check.sh` (see below). |

## Backing variants

- **Figma-backed** — reads via the Figma MCP (`config.design_system.source: figma`,
  files in `design_system.figma.files`). Figma MCP becomes mandatory for frontend agents.
- **File-backed** — token files / docs in-repo or referenced
  (`source: tokens | docs`, optional `design_system.profile` file).

Either variant may additionally be governed by a company ADR
(`config.design_system.company_adr`). Playwright visual QA remains required for UI projects
regardless of design-system presence — the adapter informs *what* to check, visual QA verifies
*that it renders so*.

## `check()` backing — vendored impeccable detector (ADR-A-0017)

The `check(change_ref)` operation and the `design-system-check` gate are backed by the
[`impeccable`](https://github.com/pbakaus/impeccable) design-quality detector — a
deterministic, LLM-free CLI of anti-pattern rules (contrast, gray-on-color, AI palette,
overused fonts, tap-target size, …). It is **vendored and version-pinned** at
`vendor/impeccable/` (pin: `impeccable@3.2.1`; Apache-2.0, attributed in `NOTICE`); a
governed run performs **no unpinned/floating network fetch** (ADR-A-0013). The concrete
entry point is `scripts/design-system-check.sh`.

- **Profile gate.** The gate runs only when the design system is enabled
  (`config.design_system.enabled: true`, signalled to the script via
  `DESIGN_SYSTEM_ENABLED=true`). The **neutral** profile and backend-only stacks
  (`design-system.provider: none`) execute nothing — the gate is inert.
- **Input.** Feed the detector **rendered HTML** (e.g. the Playwright-rendered DOM) or a
  live URL — never raw `.tsx`/`.jsx`. High-value DOM rules fire on rendered output; an
  inline-style component source matches almost nothing (ABS-191 §7.1). This aligns with the
  mandated Playwright visual QA above: visual QA renders the UI, the detector inspects that
  rendered output.
- **Waivers.** Project waivers live in `.impeccable/config.json` (shared, committed) and
  `.impeccable/config.local.json` (machine-local, gitignored):
  `detector.ignoreRules` / `ignoreFiles` / `ignoreValues`. **Fence the content/text rule
  class** (e.g. `marketing-buzzword`) via `ignoreRules` so it cannot false-positive on
  legitimate prose; DOM rules stay accurate. Template: `vendor/impeccable/config.example.json`.
- **Evidence lane.** Detector exit code `0` = clean (gate **PASS**), `2` = findings (gate
  **FAIL**); the script's own exit code is the gate boolean. Findings are grouped per rule
  (`jq group_by(.antipattern)`) into a Markdown block on stdout, which the consuming gate
  (`qas-design`) posts through `$TRACKER_CMD comment --kind gate-results`.
- **Augments, never replaces.** The detector adds a deterministic floor; it does **not**
  let a design pass on detector-green alone when hand-authored DACs fail, and it does not
  collapse the designer→tester separation (`ui-ux-design` authors DACs, `qas-design`
  executes them).

### Single design-contract source of truth

`docs/design/DESIGN_SYSTEM.md` (`{{DESIGN_SYSTEM_PATH}}`) is the **single source of truth**
for the design contract. impeccable's own `DESIGN.md` / `.impeccable/design.json` is a
*derived reference only* — do **not** maintain it as an independent, competing contract
(ADR-A-0017 constraint 4). Point the detector at the repo contract via
`detector.designSystem.enabled` in `.impeccable/config.json`.
