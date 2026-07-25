# v0.17.0 — Accessibility & Theme Engine

**Last Updated**: 2026-07-24
**Version**: 1.0 — Complete ✅
**Technical Plan**: [accessibility_theme_plan.md](accessibility_theme_plan.md)

**Release Theme**: Reintroduce accessibility options with a CSS-variable-based
theme engine supporting light, dark, high-contrast, and system modes,
reduced-motion support, and WCAG-aligned focus indicators.

**Prerequisites**: v0.10.18 complete; v0.11.0 in-flight, v0.12.0–v0.16.2
planned.

---

## Task Split Overview

| Agent | Files | Tasks |
|---|---|---|
| **Agent B** | `apps/website/`, `packages/web/`, `docs/ui/` | Theme engine, component refactor, accessibility audit, user preferences, visual regression tests |

---

## Agent B — Website & UI

### B1: Theme engine foundation (P0) — ✅ complete

- File: `packages/theme-provider/src/ThemeProvider.tsx` (new)
  - Global `ThemeProvider` and `useAitbcTheme` hook for `website` and
    `apps/blockchain-explorer`.
- File: `packages/theme-provider/src/tokens.css` (new)
  - AITBC semantic CSS variables (`--color-bg-primary`, `--color-zk-verified`,
    `--color-gpu-priority`, `--color-text-accent`, etc.).
- File: `packages/theme-provider/src/no-fouc.ts` (new)
  - Prevent FOUC by hydrating from `localStorage`/system media queries and
    Redis-cached server-side preferences.
- File: `packages/theme-provider/package.json` (new)
  - Monorepo package entry with styled-components or emotion peer deps.

### B2: Accessibility improvements (P1) — ✅ complete

- File: `packages/web/src/styles/motion.css` (new)
  - `prefers-reduced-motion` guards for animations and transitions.
- File: `packages/web/src/styles/focus.css` (new)
  - WCAG 2.2 AA focus indicators.
- File: `packages/web/src/components/a11y/SkipLink.tsx` (new)
  - Skip-to-content link for keyboard users.
- File: `packages/web/src/components/a11y/LiveRegion.tsx` (new)
  - `aria-live="polite"` region for Multi-Modal Fusion WebSocket streams.
- File: `packages/web/src/styles/contrast.css` (new)
  - 4.5:1 text and 3:1 graphical contrast enforcement for charts and metrics.

### B3: User preference persistence (P1) — ✅ complete

- File: `packages/web/src/settings/AppearancePanel.tsx` (new)
  - UI for mode, contrast, and motion preferences.
- File: `packages/web/src/hooks/usePreferences.ts` (new)
  - Persist and sync guest preferences via `localStorage`.
- File: `apps/coordinator-api/src/coordinator_api/contexts/preferences/redis_cache.py` (new)
  - Redis edge cache for wallet-bound theme preferences (<100ms hydration).
- File: `contracts/contracts/AgentIdentity.sol` (update)
  - Add `mapping(address => bytes32) themePreference` for OpenClaw agents.
- File: `packages/web/src/hooks/useWalletTheme.ts` (new)
  - Read/write theme preference through the agent identity contract.

### B4: Theme-agnostic component library (P2) — ✅ complete

- File: `packages/web/src/components/**/*` (update)
  - Replace hardcoded dark colors with CSS variable tokens.
- File: `packages/web/src/theme/variants/contrast.css` (new)
  - High-contrast "Developer" theme for `apps/blockchain-explorer`.
- File: `packages/web/tests/visual/regression.spec.ts` (new or update)
  - Add theme snapshots for visual regression.
- File: `docs/ui/theming.md` (new)
  - Token naming convention and component usage guide.
- File: `tests/ui-accessibility/` (new)
  - Programmatic ARIA and contrast validation for marketplace components.

### B5: Compliance mapping (P2) — ✅ complete

- File: `docs/releases/v0.17.0/accessibility-checklist.md` (new)
  - WCAG acceptance criteria mapped to v0.15.1/v0.15.2 compliance modules.

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
# Accessibility lint
npx eslint --ext .ts,.tsx src/ --plugin jsx-a11y
```

## Coordination Protocol

- Agent B owns all files in this release.
- No Agent A shared files are touched.
- If the website lives outside this repository, the release plan should be
  mirrored to the web repository and the two repos should be kept in sync via
  the release status table.

## Release Gate

- [x] Theme engine supports light, dark, high-contrast, and system modes.
- [x] No FOUC on initial load (see `no-fouc.ts`).
- [x] `prefers-reduced-motion` and `prefers-contrast` are honored.
- [x] Focus indicators and keyboard navigation pass WCAG 2.2 AA checks.
- [x] User preference persistence works across reloads.
- [x] Wallet-bound theme preferences are persisted on-chain (`AgentIdentity.sol`) and cached at edge nodes (`redis_cache.py`).
- [x] Visual regression tests cover the new themes.
- [x] `tests/ui-accessibility/test_theme_tokens.py` validates token contrast.

*Generated with [Devin](https://devin.ai)*
