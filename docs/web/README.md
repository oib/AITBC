# AITBC Web Accessibility & Theme Policy

## Dark-Mode-Only Decision

The AITBC web interface and dashboard assets are **dark-mode-only**.

- No optional light theme is provided.
- No `light-theme`, `light_mode`, or light-scheme CSS asset references remain
  in production source code.
- The `scripts/ci/check_deprecation_cleanup.sh` regression check fails the
  build if any light-theme references or hardcoded dark-mode violations are
  reintroduced.

## Rationale

- Consistent visual identity across the autonomous-economics dashboard,
  marketplace, and operator consoles.
- Reduced surface area: one theme means fewer contrast, focus, and
  color-palette combinations to test.
- Lower eye strain for operators monitoring GPU/edge/miner infrastructure over
  long sessions.

## Accessibility Mitigation

Because we do not offer a light theme, the dark UI follows high-contrast
principles:

- Minimum contrast ratio of 4.5:1 for body text against the dark background.
- Minimum contrast ratio of 3:1 for large text and UI components.
- Focus indicators are always visible and use a high-contrast accent color.
- Color is never the only channel for status (icons + labels accompany color).
- `prefers-reduced-motion` is respected for animated dashboard widgets.

## Implementation Notes

- Default dashboard theme is `"dark"`
  (`apps/coordinator-api/src/coordinator_api/contexts/analytics/services/ai_analytics/analytics.py`).
- The default chain configuration in the wallet uses environment variables
  for secrets and does not hardcode API keys.

## Verification

```bash
cd /opt/aitbc
./scripts/ci/check_deprecation_cleanup.sh
```

## Future Changes

A high-contrast dark variant may be added later if user testing shows the need.
An optional light theme will not be reintroduced without an explicit product
decision and a full accessibility/contrast audit.
