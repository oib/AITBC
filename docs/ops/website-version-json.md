# Proposal: website/version.json for the hub build line

Status: **proposal only — not implemented.** Installing the hook is an
operator-gated action and requires its own task.

## Problem

The WEB-3 footer wants a "build <short commit> · <date>" line, but no public
endpoint reports a commit or build identifier (`/explorer-api/health` returns
only the app version `2.0.0`, which is static). Without a build step on the
node there is currently no way for a browser to answer "which build is this?".

## Proposal

Serve a small `website/version.json` from the hub checkout, written by a
`post-merge` git hook after every `git pull`:

```json
{"commit": "<short sha>", "date": "<committer date ISO>"}
```

- The file is **gitignored** (`website/version.json` is listed in
  `.gitignore`), so writing it never dirties the tree.
- The hook lives at `/opt/aitbc/.git/hooks/post-merge` on the hub — a
  host-local file, not tracked in the repo. Writing it is an operator action
  on the live checkout, gated behind a named task like any other host
  mutation.
- Content sketch for the hook (for the later task; do not install now):

  ```sh
  #!/bin/sh
  cd "$(git rev-parse --show-toplevel)" || exit 0
  printf '{"commit":"%s","date":"%s"}\n' \
    "$(git rev-parse --short HEAD)" \
    "$(git show -s --format=%cI HEAD)" > website/version.json
  ```

- Once served, the footer build line reads `/version.json` with a fetch;
  absence is non-fatal (the line stays omitted, matching today's behaviour).
- WEB-4's endpoint contract test should list `/version.json` once it is
  served, so a regression that drops the file is caught.

## Why not alternatives

- A repo-tracked `version.json` would need a commit per deploy — churn, and
  it would drift from the actual checkout whenever the pull is manual.
- Exposing the commit through an existing backend route would require a
  code/config change on the hub — out of scope for a repo-only task and
  unnecessary once a static file can carry the same fact.
