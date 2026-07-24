# v0.17.0 — Accessibility & Theme Engine

**Last Updated**: 2026-07-24
**Version**: 0.1 — Planned 🚧

**Release Theme**: Reintroduce accessibility options with a CSS-variable-based
theme engine supporting light, dark, high-contrast, and system modes,
reduced-motion support, and WCAG-aligned focus indicators.

**Prerequisites**: v0.10.18 complete; v0.11.0 in-flight, v0.12.0–v0.16.0
planned.

---

## Task Split Overview

| Agent | Files | Tasks |
|---|---|---|
| **Agent B** | `apps/website/`, `packages/web/`, `docs/ui/` | Theme engine, component refactor, accessibility audit, user preferences, visual regression tests |

---

## Agent B — Website & UI

### B1: Theme engine foundation (P0)

- File: `packages/web/src/theme/ThemeProvider.tsx` (new or update)
  - Hydrate initial theme from `localStorage` and system media queries.
  - Support `light`, `dark`, `high-contrast`, and `system`.
- File: `packages/web/src/theme/tokens.css` (new)
  - Semantic CSS variables for backgrounds, text, accents, borders, focus.
- File: `packages/web/src/theme/no-fouc.ts` (new)
  - Prevent flash of unstyled content on initial load.

### B2: Accessibility improvements (P1)

- File: `packages/web/src/styles/motion.css` (new)
  - `prefers-reduced-motion` guards for animations and transitions.
- File: `packages/web/src/styles/focus.css` (new)
  - WCAG 2.2 AA focus indicators.
- File: `packages/web/src/components/a11y/SkipLink.tsx` (new)
  - Skip-to-content link for keyboard users.

### B3: User preference persistence (P1)

- File: `packages/web/src/settings/AppearancePanel.tsx` (new)
  - UI for mode, contrast, and motion preferences.
- File: `packages/web/src/hooks/usePreferences.ts` (new)
  - Persist and sync preferences via `localStorage`/user identity.

### B4: Theme-agnostic component library (P2)

- File: `packages/web/src/components/**/*` (update)
  - Replace hardcoded dark colors with CSS variable tokens.
- File: `packages/web/tests/visual/regression.spec.ts` (new or update)
  - Add theme snapshots for visual regression.
- File: `docs/ui/theming.md` (new)
  - Token naming convention and component usage guide.

### B5: Compliance mapping (P2)

- File: `docs/releases/v0.17.0/accessibility-checklist.md` (new)
  - WCAG acceptance criteria mapped to v0.13.0 compliance modules.

---

## Verification Commands

```bash
cd /opt/aitbc
# Python checks if any Python tooling is touched
./venv/bin/python -m ruff check .

# UI checks (example; actual command depends on the website package manager)
cd packages/web
npm run lint
npm run test
npm run build
```

## Coordination Protocol

- Agent B owns all files in this release.
- No Agent A shared files are touched.
- If the website lives outside this repository, the release plan should be
  mirrored to the web repository and the two repos should be kept in sync via
  the release status table.

## Release Gate

- [ ] Theme engine supports light, dark, high-contrast, and system modes.
- [ ] No FOUC on initial load.
- [ ] `prefers-reduced-motion` and `prefers-contrast` are honored.
- [ ] Focus indicators and keyboard navigation pass WCAG 2.2 AA checks.
- [ ] User preference persistence works across reloads.
- [ ] Visual regression tests cover the new themes.
- [ ] UI lint, tests, and build pass.

*Generated with [Devin](https://devin.ai)*
