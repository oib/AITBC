# Island subscription check — API key wiring

`aitbc-island-subscription-check.timer` (daily) runs
`island-subscription-check.sh`, which calls `aitbc ipfs island swarm-key`
against the coordinator — the same swarm-key gate a fresh island join hits.
It is installed on the shop node only.

## History

The unit failed starting 2026-10-03 after the coordinator-api teardown
removed `/etc/aitbc/aitbc-coordinator-api.env`, whose `MINER_API_KEYS`
entry was the last working leg of the CLI's API-key resolution on that
node. The fix is a dedicated env file wired straight into the unit.

## Operator setup (the file is never in the repo)

Create `/etc/aitbc/aitbc-island-subscription-check.env` by hand:

```bash
sudo install -m 600 -o root -g root /dev/null /etc/aitbc/aitbc-island-subscription-check.env
echo 'AITBC_API_KEY=<the node miner API key>' | sudo tee /etc/aitbc/aitbc-island-subscription-check.env
```

- Variable: `AITBC_API_KEY` — the node's miner API key (the same
  credential class listed in `MINER_API_KEYS` on the coordinator; this
  node subscribes to the island as a miner). The value is an operator
  secret — never commit it, never paste it into tickets or docs.
- File: `/etc/aitbc/aitbc-island-subscription-check.env`, mode `600`,
  owner `root`.
- The unit loads it via `EnvironmentFile=-...` — the leading dash makes
  it optional, so a missing file fails the *check* with a clear message
  rather than failing the unit start.

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl start aitbc-island-subscription-check.service
journalctl -u aitbc-island-subscription-check.service -n 5
```

Expected journal line on success:

```text
aitbc-island-sub-check[...]: [info] island subscription active (ait-localnet-island, wallet default)
```

## Exit codes

| code | meaning | action |
|---|---|---|
| 0 | subscription active | none |
| 1 | subscription expired / missing | `aitbc ipfs island subscribe` to renew |
| 2 | coordinator unreachable | transient — check network / hub side |
| 3 | `AITBC_API_KEY` not configured | create the env file above |
| 4 | configured key refused (HTTP 401/403) | rotate/repair the key value |
| 5 | check inconclusive, other reason | read the journal line |

The `AitbcSystemdUnitFailed` alert (shared rules file) fires on this:
a oneshot unit that exits non-zero stays in systemd's `failed` state
until the next successful run, so a single failed run holds
`node_systemd_unit_state{state="failed"}==1` past the 15-minute `for:`
hold and the alert fires.
