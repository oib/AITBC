---
description: Test PR with Docker image build workflow
argument-hint: [PR-number]
allowed-tools: [Read, Write, Edit, Bash, Grep, Glob]
---

> **📋 TEMPLATE**: This command is a template. See "Customization Guide" below to adapt for your infrastructure.

Test the Docker registry PR workflow by adding the `build-docker-image` label to a PR and verifying the build.

> **Host note**: label-triggered image builds assume GitHub Actions. Commands below use `{{GIT_HOST_CLI}}` (`bb` on Bitbucket, `gh` on GitHub); on Bitbucket, manage labels/triggers via the PR web UI or your Pipelines trigger of choice.

## Workflow

### 1. Get PR Number

If argument provided ($1):

- Use as PR number
- Fetch PR details: `{{GIT_HOST_CLI}} pr view $1`   # bb pr view (Bitbucket) / gh pr view (GitHub)

If no argument:

- Check if current branch has open PR
- Extract PR number from branch

### 2. Add Label to PR

Add `build-docker-image` label:

```bash
{{GIT_HOST_CLI}} pr edit {PR-number} --add-label "build-docker-image"   # gh syntax; Bitbucket: add the label via the PR web UI
```

Confirm label added:

```bash
{{GIT_HOST_CLI}} pr view {PR-number} --json labels   # bb pr view (Bitbucket) / gh pr view --json labels (GitHub)
```

### 3. Monitor Build

Explain to user:

- GitHub Actions will build Docker image (~5-10 min)
- Image will be tagged as `pr-{number}`
- Build status visible in PR checks
- Can monitor at: `https://oib/AITBC/actions`

Provide link to PR:

```bash
{{GIT_HOST_CLI}} pr view {PR-number} --web   # bb pr view (Bitbucket) / gh pr view --web (GitHub)
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
{{GIT_HOST_CLI}} pr edit {PR-number} --remove-label "build-docker-image"   # gh syntax; Bitbucket: remove the label via the PR web UI
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

## Customization Guide

To adapt this command for your infrastructure, replace these placeholders:

| Placeholder       | Description               | Example               |
| ----------------- | ------------------------- | --------------------- |
| `AITBC` | Your Linear ticket prefix | `WOR`, `PROJ`, `TASK` |
| `{{GIT_HOST_CLI}}` | Your host's PR CLI        | `bb` (Bitbucket), `gh` (GitHub) |
