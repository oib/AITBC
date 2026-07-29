# Vendored: impeccable (design-quality detector)

This directory version-pins the [`impeccable`](https://github.com/pbakaus/impeccable)
design-quality detector, which backs the design-system adapter's `check(change_ref)`
operation and the `design-system-check` quality gate (see
[`adrs/agentic/ADR-A-0017-design-quality-detector-backing.md`](../../adrs/agentic/ADR-A-0017-design-quality-detector-backing.md)).

## Pin record (self-hosting / governor)

| Field | Value |
| ----- | ----- |
| Package | `impeccable` |
| **Pinned version** | **`3.2.1`** |
| Source | https://github.com/pbakaus/impeccable (npm: `impeccable`) |
| License | Apache-2.0 (retained: [`LICENSE`](./LICENSE); attributed in repo [`NOTICE`](../../NOTICE)) |
| Vendoring | `npm ci --omit=optional` from the committed `package-lock.json` |
| Optional dep omitted | `puppeteer` (URL-scan only; we feed rendered HTML, not live URLs) |

The pin is machine-readable in [`package.json`](./package.json) (`dependencies.impeccable`,
an exact version) and byte-locked in [`package-lock.json`](./package-lock.json)
(SHA-512 integrity per package). Upgrading the detector = a deliberate bump of both files.

## Why a locked manifest, not a committed payload (#PATH_DECISION)

ADR-A-0017 constraint 2 requires the detector to be "vendored and version-pinned,
never floating"; the acceptance criterion is specifically **"no *unpinned* network
fetch in a governed run."** Two ways satisfy that:

1. **Commit the raw payload** (`node_modules`, ~7 MB / ~660 files). `node_modules/` is
   gitignored repo-wide and this is a Markdown/shell governance repo with no
   committed-JS precedent — committing it is heavy and noisy.
2. **Commit an integrity-locked manifest** (`package.json` exact-pin +
   `package-lock.json`) consumed by a **pinned** `npm ci --omit=optional`. ← chosen.

Option 2 is a *pinned* fetch (integrity-hashed, `npm ci` refuses to deviate from the
lockfile), never floating/unpinned — so it satisfies the AC's literal wording and the
guardrail while keeping the repo lean. If a strictly air-gapped governed run is later
required, swap this for a committed payload or a git submodule pinned to `v3.2.1`
without changing the gate contract.

## Re-vendoring / upgrading

```bash
cd vendor/impeccable
# edit package.json -> dependencies.impeccable to the new version, then:
rm -f package-lock.json && npm install --omit=optional --package-lock-only
# update the Pin record above, adjust NOTICE if the license/authorship changes,
# and re-run the design-system-check Test Plan (bad -> FAIL, good -> PASS, determinism).
```

`node_modules/` here is gitignored and materialized on demand by
[`scripts/design-system-check.sh`](../../scripts/design-system-check.sh) via
`npm ci --omit=optional`.
