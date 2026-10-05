# Deploy: native-energy-rate guard (SD-7)

Deployment and rollback plan for the Task-A2 stack — **not executed yet**;
push, host changes and restarts all need the operator's named go.

Stack contents (on top of the v11 bake `d6fc3aba19`):

| commit | scope |
|---|---|
| `751b98935d` | POST band `ENERGY_RATE_MIN/MAX_AIT_PER_EUR` (0.5/8), int64 pre-check, refresher band refusal |
| `1d3c06e417` | `aitbc_native_energy_rate.prom` textfile export + three hub-only alert rules + promtool cases |
| `13175eba79` | shared `DEFAULT_MAX_RATE_AGE_SECONDS = 86400` bound by coordinator, node fallback, CLI |
| `b43c6d147d` | version-bump invariant test (test-only) |

## What goes where

| file | host(s) | destination | restart needed |
|---|---|---|---|
| `scripts/monitoring/native-energy-rate-refresh.sh` | hub only | `/usr/local/sbin/native-energy-rate-refresh.sh` (timer `ExecStart`) | none — next `aitbc-native-energy-rate-refresh` run picks it up |
| `apps/coordinator-api/` (config.py, market_gpu.py) | hub only | `/opt/aitbc` pull | `aitbc-coordinator-api` restart — the band check is process code |
| `scripts/monitoring/aitbc_hub_rules.yml` | hub only | `/etc/prometheus/aitbc_hub_rules.yml` | `promtool check` + `systemctl reload prometheus` (or HUP) |
| `aitbc/market/energy_pricing.py`, `cli/`, `apps/blockchain-node/rpc/escrow_routes.py` | all five | `/opt/aitbc` pull | none dedicated — the window value is unchanged (86400); rides the normal repo rollout. The node fallback and CLI binding are value-identical, so skipping a restart loses nothing. |

Prerequisite on hub: `/var/lib/prometheus/node-exporter/` already exists
(the authority exporter writes there). `TEXTFILE_DIR` defaults to it; no
env line needed.

## Order matters

The rules must go live **after** the refresher has run once — otherwise
`NativeEnergyRateRefreshStale` (`absent()` arm) fires immediately on a
legitimately missing file.

1. **Repo pull on hub** — verify: `git -C /opt/aitbc log -1` shows the stack tip.
2. **Install the refresher** — copy the script to `/usr/local/sbin/`,
   keep a `.bak-a2` of the old one. Verify: `bash -n` clean,
   `diff` against the repo copy empty.
3. **Restart `aitbc-coordinator-api` on hub** — the band check is code in
   that process. Verify: service active, and a probe POST with
   `ait_per_eur: "0.1"` returns 400 "plausible band" (rejection, not
   silence — that is the check working).
4. **Run the refresher once** (`systemctl start aitbc-native-energy-rate-refresh.service`)
   — writes the first `.prom` and re-attests. Verify:
   `/var/lib/prometheus/node-exporter/aitbc_native_energy_rate.prom`
   exists with all four series, and `journalctl -u aitbc-native-energy-rate-refresh`
   shows the re-attest POST.
5. **Deploy the rules** — copy `aitbc_hub_rules.yml` to `/etc/prometheus/`,
   `promtool check rules` clean, `systemctl reload prometheus`. Verify:
   `curl 'localhost:9090/api/v1/rules'` lists `aitbc-native-energy-rate`
   and all three alerts are inactive (healthy), not pending/firing.
6. **Fleet pull** on node0/hub1/node1/node2 — verify `git log -1` matches.
   No restarts required for A2 alone (window value identical); restart
   cadence belongs to whatever deploy they ride.

## Verify after

- `curl localhost:9090/api/v1/query?query=aitbc_native_energy_rate_ait_per_eur`
  returns ~4.0 on hub.
- `time() - aitbc_native_energy_rate_refresh_timestamp_seconds` is under
  the run interval (fresh).
- A stored rate outside [0.5, 8] makes the next refresher run exit 1 with
  a `plausible band` journal line — and makes `NativeEnergyRateOutOfBand`
  pending, then firing after 5m.

## Rollback (reverse order)

1. Rules: restore the previous `/etc/prometheus/aitbc_hub_rules.yml`,
   `systemctl reload prometheus`. The three alerts vanish.
2. Textfile: `rm /var/lib/prometheus/node-exporter/aitbc_native_energy_rate.prom`
   (series drop immediately; safe even while rules are still loaded —
   `absent()` would fire `NativeEnergyRateRefreshStale`, so do the rules
   rollback first).
3. Refresher: restore `/usr/local/sbin/native-energy-rate-refresh.sh.bak-a2`.
4. Coordinator: check out the pre-stack `/opt/aitbc`, restart
   `aitbc-coordinator-api`. The POST returns to accepting any positive
   rate — the original SD-7 exposure, so only roll this back if the band
   itself is wrong; the fix-forward is adjusting
   `ENERGY_RATE_MIN/MAX_AIT_PER_EUR` in `/etc/aitbc/aitbc-coordinator-api.env`
   (and matching overrides for the refresher env) rather than reverting.

## What this does NOT cover

- `native_energy_rates` rows can still be written out-of-band (direct
  SQL) — the version-bump invariant test in `b43c6d147d` is what would
  flag a future in-repo write path; nothing here prevents SQL writes.
- The deploy does not load rules anywhere except hub, and the alerts are
  hub-only by construction (the series only exist where the timer runs).
