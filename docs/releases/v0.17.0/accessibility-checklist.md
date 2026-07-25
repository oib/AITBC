# v0.17.0 Accessibility Checklist

WCAG 2.2 AA acceptance criteria mapped to AITBC v0.15.1/v0.15.2 compliance
modules.

## Perceivable

- **1.4.3 Contrast (Minimum)** – `packages/theme-provider/src/tokens.css` and
  `tests/ui-accessibility/test_theme_tokens.py` enforce 4.5:1 for primary text
  and 3:1 for graphical objects.
- **1.4.4 Resize Text** – All font sizes use relative units and layout reflows
  up to 200% zoom.
- **1.4.10 Reflow** – Marketplace grids use CSS Grid with `min()` and `clamp()`
  to avoid horizontal scroll at 320px width.

## Operable

- **2.1.1 Keyboard** – `packages/web/src/components/a11y/SkipLink.tsx` and
  `packages/web/src/styles/focus.css` provide visible focus and skip links.
- **2.2.2 Pause, Stop, Hide** – `packages/web/src/styles/motion.css` honors
  `prefers-reduced-motion`.
- **2.4.7 Focus Visible** – `:focus-visible` with `--color-focus-ring` is
  applied to all interactive elements.

## Understandable

- **3.1.2 Language of Parts** – `LiveRegion` uses plain language and ARIA
  live-region politeness for Multi-Modal Fusion streams.
- **3.2.4 Consistent Identification** – Semantic tokens keep labels and status
  colors consistent across light, dark, and high-contrast modes.

## Robust

- **4.1.2 Name, Role, Value** – Buttons use explicit `type` and ARIA labels
  where text alone is insufficient.
- **4.1.3 Status Messages** – `LiveRegion` announces status updates without
  moving focus.

## Compliance Mapping

| WCAG Criterion | Component/File | v0.15.x Module |
|---|---|---|
| 1.4.3 Contrast | `tokens.css` | `aitbc/compliance/policies.py` |
| 2.1.1 Keyboard | `SkipLink.tsx`, `focus.css` | `aitbc/compliance/audit.py` |
| 2.2.2 Motion | `motion.css` | `aitbc/compliance/consent.py` |
| 4.1.3 Status | `LiveRegion.tsx` | `aitbc/compliance/retention.py` |
