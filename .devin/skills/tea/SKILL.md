---
name: tea
description: Gitea command-line helper (tea) reference and workflow guide
argument-hint: "[subcommand] [args]"
triggers:
  - user
  - model
allowed-tools:
  - exec
  - read
  - grep
---

You are a helpful assistant for the `tea` Gitea CLI.
`tea` is a command-line productivity helper for Gitea, similar to `gh` for GitHub.
It operates on the repository in `$PWD` and persists configuration in `$XDG_CONFIG_HOME/tea`.

## Global options

- `--debug`, `--vvv` — enable debug output
- `--help`, `-h` — show help
- `--version`, `-v` — show version

## Setup

`tea` needs at least one Gitea login to work. If no login exists in `$XDG_CONFIG_HOME/tea`,
prompt the user to create one before running privileged commands. Do not guess tokens.

```bash
# Add a login interactively
tea login add

# Add a login non-interactively (only if the user explicitly provides a token)
tea login add --name my-gitea --url https://gitea.example.com --token $GITEA_TOKEN
```

## Common workflows

### Pull requests

```bash
# List PRs in the current repo
tea pr list

# Check out a PR into a local branch
tea pr checkout 42

# Show PR details
tea pr view 42

# Create a PR from the current branch
tea pr create --title "fix: ..." --body "..."
```

### Issues

```bash
# List open issues
tea issue list

# View an issue
tea issue view 7

# Create an issue
tea issue create --title "..." --body "..."
```

### Repository operations

```bash
# Show current repo info
tea repo view

# List repos for the logged-in user
tea repo list

# Clone a repo
tea clone owner/repo
```

### Direct API calls

For endpoints not covered by first-class commands, use `tea api`.
It already sends the configured token.

```bash
tea api /repos/owner/repo/pulls
tea api /repos/owner/repo/issues --method POST --data '{"title":"bug"}'
```

## Entities and aliases

- `issues`, `issue`, `i`
- `pulls`, `pull`, `pr`
- `labels`, `label`
- `milestones`, `milestone`, `ms`
- `releases`, `release`, `r`
- `times`, `time`, `t`
- `organizations`, `organization`, `org`
- `repos`, `repo`
- `branches`, `branch`, `b`
- `actions`, `action`
- `wiki`
- `webhooks`, `webhook`, `hooks`, `hook`
- `comments`, `comment`, `c`

## Helpers

- `open`, `o` — open the repo (or a specific path) in the browser
- `notifications`, `notification`, `n` — show notifications
- `clone`, `C` — clone a repository
- `api` — make an authenticated API request
- `whoami` — show current user
- `admin`, `a` — admin operations

## Notes

- `tea` assumes the local `main` branch tracks the upstream repo in an upstream/fork workflow.
- Local git state should be published before running mutating `tea` commands.
- Use `tea --debug <command>` when a command fails and the user wants details.
- Prefer `tea pr checkout` to fetch and switch to a PR branch.
- Prefer `tea pr create` over raw `tea api` for creating PRs.
