# Feature: README Version Badge Auto-Stamping

> **Added**: v2.21.1 (ABS-129)
> **Scope**: `scripts/promote-release.sh` · `scripts/generate-governor.sh`

## Overview

The README version badge (`img.shields.io/badge/version-vX.Y.Z-…`) is now
**automatically stamped** with the release version during governor promotion.
No manual badge update is required. The badge is written into the release commit
by `promote-release.sh`, verified by `generate-governor.sh --check`, and exercised
end-to-end by `tests/test-harness-parity.sh`.

Before this change the badge was frozen at v2.10.0 through 11 releases. It will
no longer drift.

---

## Prerequisites

- Root `README.md` containing a shields.io version badge in the form:

  ```
  img.shields.io/badge/version-vX.Y.Z-<color>?...
  ```

- `scripts/promote-release.sh` at v2.21.1 or later
- `scripts/generate-governor.sh` at v2.21.1 or later

---

## Quick Start

Badge stamping is fully automatic — no new operator steps are required:

```bash
# Promote to a new version; badge is stamped in the release commit
bash scripts/promote-release.sh v2.22.0

# Verify badge matches the governor pin at any time
bash scripts/generate-governor.sh --check
```

Both commands were unchanged in operator interface; only their scope expanded.

---

## Core Concepts

### How the badge is stamped

`generate-governor.sh` calls an internal `build_stamped_readme()` function that
performs a **text-only sed substitution** on the shields.io badge message token:

```
Before:  img.shields.io/badge/version-v2.10.0-blue?style=flat-square
After:   img.shields.io/badge/version-v2.21.1-blue?style=flat-square
```

Only the version message segment is rewritten. The URL prefix
(`img.shields.io/badge/version-`), color class (`-blue`), and query string
(`?style=…`) are preserved verbatim. Pre-release tags are encoded with `--` per
shields.io dash-escape convention:

```
v2.22.0-rc1  →  badge message: v2.22.0--rc1
```

The stamp is **idempotent**: running it twice on an already-stamped file produces
the same result.

### Integration into promote-release.sh

`promote-release.sh` calls `generate-governor.sh --from-tree --banner-tag <ver>`
which internally runs `build_stamped_readme`. The stamped `README.md` is then
staged alongside the `.claude/` shipped set, `CLAUDE.md`, and `.governor-tag`:

```bash
git add .claude CLAUDE.md README.md .governor-tag
git commit -m "chore(release): promote governor to $tag …"
```

### The drift check

`generate-governor.sh --check` (run by `tests/test-harness-parity.sh` in CI)
now also compares the live `README.md` badge against the `.governor-tag` pin. A
mismatch exits non-zero with a human-readable message:

```
DRIFT: README.md version badge does not match generated(v2.21.1).
```

This ensures a stale badge fails the check and is never shipped silently.

### Dry-run behavior

`promote-release.sh --dry-run` exercises the badge stamp in a throwaway scratch
clone. The real `README.md` is never modified:

```bash
bash scripts/promote-release.sh v2.99.0-dryrun --dry-run
# → "README badge stamped 'v2.99.0-dryrun'"  (in scratch clone only)
# → real repo README.md is unchanged
```

### Edge cases

| Situation | Behavior |
|-----------|----------|
| No root `README.md` | Badge stamp skipped; `git add README.md` not attempted; promotion continues |
| Pre-release tag (`v1.2.3-rc1`) | Encoded as `v1.2.3--rc1` per shields.io rules |
| Badge color not lowercase alpha | Color regex (`-[a-z][a-z]*`) won't match; stamp is a silent no-op |

The color-class limitation (lowercase alpha only) is a known non-blocking
constraint. Current badge uses `blue`; hex colors in future badges would need a
regex update (tracked as a follow-up from SA review).

---

## Single Source of Truth

`.governor-tag` remains the single source of truth for the release version (ABS-39).
The README badge is a derived artifact, stamped from `.governor-tag` by the same
promotion tooling that stamps the `CLAUDE.md` provenance banner.

```
.governor-tag
    └─→ generate-governor.sh  ─→  CLAUDE.md banner (SAW-PROVENANCE-BANNER)
                               └─→  README.md badge  (version-vX.Y.Z)
```

---

## Troubleshooting

### Drift check reports stale badge

**Symptom**: `generate-governor.sh --check` exits 1:

```
DRIFT: README.md version badge does not match generated(v2.21.1).
```

**Cause**: The README was edited manually, or a pre-ABS-129 checkout is in use.

**Fix**: Re-generate from the current pin (no version bump):

```bash
# Re-stamp to current governor pin
bash scripts/generate-governor.sh

# Confirm clean
bash scripts/generate-governor.sh --check
```

### Badge not updated after promote-release.sh

**Symptom**: Release commit exists but `README.md` still shows the old version.

**Check**: Confirm `README.md` exists at the repo root and contains a badge line
matching `img.shields.io/badge/version-...-` before promotion. If the file is
absent, `build_stamped_readme` returns early (graceful skip) and the badge is not
staged.

---

## References

- ABS-129 — story tracking this feature
- ABS-39 — `.governor-tag` as single source of truth for version identity
- ABS-95 — `promote-release.sh` governor promotion mechanism
- `scripts/generate-governor.sh` — `build_stamped_readme()` implementation (~line 297)
- `scripts/promote-release.sh` — `do_promotion()` staging step (~line 148)
- `tests/test-harness-parity.sh` — parity suite that exercises the drift check
