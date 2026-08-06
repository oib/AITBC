# `.github/workflows/` — consumer-facing GitHub payload (NOT run here)

> **Decision record (ABS-143, 2026-07-08).** This repository's only remote is
> **Bitbucket**, and the POPM decision (2026-07-07) is **Bitbucket Pipelines, not
> a GitHub mirror**. Therefore **none** of the files in this directory execute for
> this repo. Enforced CI for this repo lives in **`bitbucket-pipelines.yml`** at
> the repo root.

These GitHub Actions files are **template payload** shipped to downstream
consumers who adopt this boilerplate on GitHub. `scripts/setup-template.sh`
substitutes the `{{PLACEHOLDER}}` tokens for the consumer's project.

## What stays here, and why

| File | Status | Rationale |
|------|--------|-----------|
| `tests.yml` | **Kept** | Fully functional, no placeholders. Runs the real `tests/tooling/test-*.sh` matrix on GitHub consumers. Mirrored by `bitbucket-pipelines.yml` for this repo. |
| `pr-validation.yml` | **Kept** | Real repo-specific gates (rebase check, hook/skills parity, hooks wiring). The `AITBC` tokens in its commit/PR-title/ticket checks are **intentional** — they are substituted per consumer by `setup-template.sh`. This repo's enforcing commit-format gate (real `ABS` prefix) is in `bitbucket-pipelines.yml`. |
| `test-fork-sync.yml` | **Kept** | Path-triggered fork-sync compatibility check for GitHub consumers. |

## What moved out (ABS-143)

`ci.yml` and `docker-build.yml` were **pure, unsubstituted app templates**
(`run: {{PACKAGE_MANAGER}} install`, `{{REGISTRY}}`, …) triggering on push to
`main`. On any future GitHub mirror they would produce a permanently red default
branch, and they describe a Next.js-style app build irrelevant to this
bash/harness repo. They now live under **`templates/.github/workflows/`** so they
are never auto-triggered. See `templates/.github/workflows/README.md`.

## Other GitHub metadata (ABS-143 decision)

- **`.github/FUNDING.yml`** — **kept**. Inert on Bitbucket; valid GitHub Sponsors
  metadata for consumers/author. No action needed.
- **`.github/ISSUE_TEMPLATE/`** — **kept**. Inert on Bitbucket; generic
  bug/feature templates useful to GitHub consumers.
