# AITBC Design System

**Consumed by**: UI/UX Design Agent (`.claude/agents/ui-ux-design.md`)
**Configured path**: `{{DESIGN_SYSTEM_PATH}}` (default: this file)
**Origin**: {{DESIGN_SYSTEM_ORIGIN}} (e.g. Figma export, hand-written, Claude-generated)

> This is a starter template. Replace `{{PLACEHOLDER}}` tokens with your
> project's values. The UI/UX Design Agent treats this file as the single
> source of truth for design tokens, components, accessibility standards,
> and responsive breakpoints - it will STOP and request this file if missing.
>
> **Single source of truth (ADR-A-0017).** This file is the ONE design-contract
> source of truth. The `design-system-check` gate is backed by the vendored
> `impeccable` detector (`vendor/impeccable/`), whose `init` can emit its own
> `DESIGN.md` / `.impeccable/design.json`. Treat any such impeccable file as a
> *derived reference only* — never maintain it as an independent, competing
> contract. Point the detector back here via `detector.designSystem.enabled` in
> `.impeccable/config.json` (see `profiles/neutral/adapters/design-system.md`).

---

## Design Tokens

### Colors

| Token              | Value                | Usage                       |
| ------------------ | -------------------- | --------------------------- |
| `color.primary`    | {{COLOR_PRIMARY}}    | Primary actions, links      |
| `color.secondary`  | {{COLOR_SECONDARY}}  | Secondary actions           |
| `color.background` | {{COLOR_BACKGROUND}} | Page background             |
| `color.surface`    | {{COLOR_SURFACE}}    | Cards, panels               |
| `color.text`       | {{COLOR_TEXT}}       | Body text                   |
| `color.error`      | {{COLOR_ERROR}}      | Errors, destructive actions |
| `color.success`    | {{COLOR_SUCCESS}}    | Success states              |

### Typography

| Token          | Value            | Usage            |
| -------------- | ---------------- | ---------------- |
| `font.family`  | {{FONT_FAMILY}}  | All text         |
| `font.size.sm` | {{FONT_SIZE_SM}} | Captions, labels |
| `font.size.md` | {{FONT_SIZE_MD}} | Body text        |
| `font.size.lg` | {{FONT_SIZE_LG}} | Section headings |
| `font.size.xl` | {{FONT_SIZE_XL}} | Page titles      |

### Spacing

| Token        | Value          | Usage                 |
| ------------ | -------------- | --------------------- |
| `spacing.xs` | {{SPACING_XS}} | Inline gaps           |
| `spacing.sm` | {{SPACING_SM}} | Related elements      |
| `spacing.md` | {{SPACING_MD}} | Component padding     |
| `spacing.lg` | {{SPACING_LG}} | Section separation    |
| `spacing.xl` | {{SPACING_XL}} | Page-level separation |

---

## Components

Component implementations come from **{{UI_LIBRARY}}**. Designs must
reference these components by name; do not invent new component variants
without reporting a deviation.

| Component | Variants                        | Notes                           |
| --------- | ------------------------------- | ------------------------------- |
| Button    | primary, secondary, destructive | Use `color.primary` for primary |
| Input     | text, select, checkbox          | Always paired with a label      |
| Card      | default, interactive            | Surface: `color.surface`        |
| Dialog    | modal, confirmation             | Focus-trapped, ESC to close     |
| Table     | default, sortable               | {{TABLE_COMPONENT_NOTES}}       |

Add project-specific components here as the system grows.

---

## Accessibility Standards

- **Contrast**: text/background >= 4.5:1 (body), >= 3:1 (large text) - WCAG {{WCAG_LEVEL}}
- **Focus**: visible focus indicator on all interactive elements; logical focus order
- **Labels**: every input has a programmatic label; images have alt text
- **Keyboard**: all flows completable without a pointer
- **Motion**: respect `prefers-reduced-motion`

---

## Responsive Breakpoints

| Breakpoint | Width                  | Layout rule                |
| ---------- | ---------------------- | -------------------------- |
| `mobile`   | {{BREAKPOINT_MOBILE}}  | Single column, stacked nav |
| `tablet`   | {{BREAKPOINT_TABLET}}  | {{TABLET_LAYOUT_RULE}}     |
| `desktop`  | {{BREAKPOINT_DESKTOP}} | {{DESKTOP_LAYOUT_RULE}}    |

---

**Workflow**: see `docs/sop/DESIGN_WORKFLOW_SOP.md` for how designs are
created against this file and verified by the QAS-Design Agent.
