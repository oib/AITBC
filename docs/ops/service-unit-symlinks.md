# Service units are symlinks into the checkout — keep node trees clean

The systemd units on every node are **symlinks into the live repo
checkout**, not copies: install links them
(`scripts/deployment/setup.sh` does `ln -sf "$svc_file"
/etc/systemd/system/`; `deploy.sh` does the same for `systemd/*.service`),
so `/etc/systemd/system/aitbc-*.service` resolves to
`/opt/aitbc/apps/*/aitbc-*.service` on every `daemon-reload` and unit
start.

Consequence: **a working-tree edit on a node is a live-config change.**
`systemctl cat aitbc-blockchain-node` shows whatever the checkout
contains — a dirty or stale tree can silently change what systemd runs
the next time the unit is reloaded or started. There is no "it only
matters at the next pull" — the unit file content *is* the tree.

## The 28 Oct incident (node0)

During the v17 arming wave, node0's checkout carried a manual
`ReadWritePaths=p` line — a leftover in-place edit. Because the unit
files are symlinks, the malformed line propagated into the live unit
definitions (`ReadWritePaths` takes absolute paths; `p` is not one).
Caught by `git status` on the node showing a dirty tree where a clean
checkout was expected; fixed by restoring the file in the tree, not by
editing the unit.

## Rules

- **Never edit `.service` / `.timer` files in a node's checkout.** A
  repo-side change rides the normal path — edit in a worktree, commit,
  push, pull on the node, `systemctl daemon-reload`.
- **Per-host unit differences go in drop-ins** — real files on the
  systemd side, not symlinks:
  `/etc/systemd/system/<unit>.d/*.conf` (or `systemctl edit <unit>`).
- **Per-host *values* go in `/etc/aitbc/*.env`** — the designed config
  surface, also real files rather than symlinks.
- **The hygiene check is `git status --porcelain` on the node** — a
  dirty checkout on a live node means the live unit set may differ from
  the repo definition. Treat unexpected `.service`/`.timer` diffs as
  live-config drift, not editor noise. (The same check guards node
  pulls in the update flow; here it additionally guards the units
  systemd already loads.)

## Checking what is live

```bash
readlink /etc/systemd/system/aitbc-blockchain-node.service      # → /opt/aitbc/...
systemctl cat aitbc-blockchain-node | head -20                  # live definition
cd /opt/aitbc && git status --porcelain | grep -E '\.service|\.timer'  # drift?
ls /etc/systemd/system/aitbc-*.service.d/ 2>/dev/null           # drop-ins in play
```
