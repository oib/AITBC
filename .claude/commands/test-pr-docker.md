---
description: Test PR with Docker image build workflow
argument-hint: [PR-number]
allowed-tools: [Read, Write, Edit, Bash, Grep, Glob]
---

> **⚠️ Not applicable to AITBC.** This command assumes a Docker-based PR image-build workflow
> (`./scripts/dev-docker.sh`, `docker-compose.staging.yml`, a `build-docker-image` PR label) that
> does not exist in this repo. AITBC is explicitly **Docker-free** — it "deploys exclusively via
> systemd" (see `.gitignore`'s "Deployment: Docker-free project" section, which actively
> gitignores `Dockerfile`/`docker-compose.yml`/`.dockerignore`). There is no Docker registry CI
> path, no `dev-docker.sh` script, and no `build-docker-image` label wired up. Left as inert
> reference/template content rather than force-adapted into a Docker workflow this project
> doesn't have; do not run the steps below as written.

Test the Docker registry PR workflow by adding the `build-docker-image` label to a PR and verifying the build.

> **Host note**: label-triggered image builds assume GitHub Actions. Commands below use `gh`
> (this repo is GitHub-hosted).

## Workflow

### 1. Get PR Number

If argument provided ($1):

- Use as PR number
- Fetch PR details: `gh pr view $1`

If no argument:

- Check if current branch has open PR
- Extract PR number from branch

### 2. Add Label to PR

Add `build-docker-image` label:

```bash
gh pr edit {PR-number} --add-label "build-docker-image"
```

Confirm label added:

```bash
gh pr view {PR-number} --json labels
```

### 3. Monitor Build

Explain to user:

- GitHub Actions will build Docker image (~5-10 min)
- Image will be tagged as `pr-{number}`
- Build status visible in PR checks
- Can monitor at: `https://github.com/oib/AITBC/actions`

Provide link to PR:

```bash
gh pr view {PR-number} --web
```

### 4. Verification Steps

Once build completes, guide user through verification:

**On Linux machine**:

```bash
# Pull PR-specific image
./scripts/dev-docker.sh pull-pr {PR-number}

# Verify image exists
docker images | grep AITBC

# AITBC-400: Use {{PROJECT}}_IMAGE_TAG environment variable instead of editing compose file
# Set the tag before running docker compose:
export {{PROJECT}}_IMAGE_TAG=pr-{PR-number}

# Or update docker-compose.staging.yml image tag temporarily:
# Change: image: {{REGISTRY}}/AITBC/dev:${{PROJECT}_IMAGE_TAG:-latest}
# To:     image: {{REGISTRY}}/AITBC/dev:pr-{PR-number}

# Restart with PR image
./scripts/dev-docker.sh restart

# Verify services running
./scripts/dev-docker.sh status

# Check health
curl http://localhost:3000/api/health
```

### 5. Testing Complete

After verification:

```bash
# Revert docker-compose.dev.yml
# Remove label to stop builds
gh pr edit {PR-number} --remove-label "build-docker-image"
```

## Success Criteria

- ✅ Label added successfully
- ✅ GitHub Actions build triggered
- ✅ Image built with pr-{number} tag
- ✅ Image pullable on Linux machine
- ✅ Services start correctly
- ✅ Hot-reload verified
- ✅ Health check passes

## Output

Report each step's status:

- PR number and URL
- Label addition confirmation
- Build status (link to Actions)
- Verification instructions
- Expected next steps

This validates the entire PR Docker workflow before relying on it for future PRs.

## Status

Marked not-applicable per the scope note at the top of this file — AITBC has no Docker build
workflow to test. Kept as inert reference content, not customized further.
