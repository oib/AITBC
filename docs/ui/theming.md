# AITBC Theming Guide

## Tokens

Semantic CSS variables are defined in `packages/theme-provider/src/tokens.css`:

- `--color-bg-primary`: primary surface background
- `--color-bg-secondary`: secondary surface background
- `--color-text-primary`: primary text
- `--color-text-secondary`: secondary/muted text
- `--color-text-accent`: accent links and active states
- `--color-zk-verified`: ZK proof success indicator
- `--color-gpu-priority`: GPU priority queue indicator
- `--color-focus-ring`: focus indicator color

## Theme modes

Modes are applied through the `data-aitbc-theme` attribute:

- `dark` (default)
- `light`
- `high-contrast`

```tsx
import { ThemeProvider } from "@aitbc/theme-provider";

<ThemeProvider>
  <App />
</ThemeProvider>
```

Use `useAitbcTheme()` to read or change the current mode, reduced-motion, and
high-contrast preferences.

## No-FOUC

Add the inline script from `packages/theme-provider/src/no-fouc.ts` to the
`<head>` of the document so the correct theme is applied before React hydrates.

## Accessibility

- `prefers-reduced-motion` is honored via `packages/web/src/styles/motion.css`.
- `prefers-contrast: more` increases focus ring width and uses a high-visibility
  focus color.
- Focus indicators are defined in `packages/web/src/styles/focus.css`.
