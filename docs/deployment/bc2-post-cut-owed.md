# bc-2 post-cut owed-items sheet

Everything the cut deliberately leaves undone, in the order it may be
done. Each row names its gate: **per-item word** (the operator's verbatim
line for that item alone — an absent line means do not do it),
**operator-named** (one line names action and host, verbatim in the
window ledger), or **ungated**. No command on this sheet deletes,
unpauses, or restarts — it lists the *reads* that precede and follow
each action.

The rollback position in runbook terms: §D defines aborts only up to the
first seal (PONR); after that, abandoning bc-2 is a second reset-class
event, not an abort. The `.pre-reset` copies make restoring the old
chain *physically* possible — which is why every deletion sits behind
the soak-end gate and a per-item word.

## 1. Cut-day items (inside the window, post-PONR)

| item | host | path / unit | size | gate | precondition | verify before | verify after |
|---|---|---|---|---|---|---|---|
| F1 unfreeze — market/exchange reopen, B1 env reverted, B0 timers restored | all five | `aitbc-escrow-settlements.timer`, `aitbc-backup.timer`, `aitbc-native-energy-rate-refresh.timer`, monitor timers per `bc2-host-inventory.md`; `aitbc-market`, `aitbc-exchange` | — | operator-named | PONR (first seal) | `list-timers` shows B0 set inactive; `is-active` on stopped units | `list-timers` shows restored set active; reopened units `is-active` |
| F1a maintenance-notice takedown | hub | rendered website | — | operator-named — **own sub-item, it modifies public content** | PONR | notice page serves the window text | notice page gone |
| F2 reset record | repo | `TOPOLOGY/` | — | ungated | PONR | — | commit lands |
| consumer flips | per `bc2-consumers.md` | v9 tripwires + fixtures, `BACKUP_GOOD_CHAIN_GLOB`, `WEBSITE_CHAIN_ID`, website `chainId` handoff | — | per consumers doc | at the cut | — | per consumers doc verify column |
| genesis-builder refusal | repo | `genesis_builder.py` `LIVE_CHAIN_IDS` | — | repo change, after the cut | bc-2 live | builder refuses to rebuild `bc-2` | same |
| attestation-arrival exporter enable | all five | `aitbc-attestation-arrival.timer` (new — the M6 detector's data source; `Refs #353`) | — | operator-named | after C5 sealing — the bc-2 `chain.db` exists so the first scrape reads it instead of reporting CheckFailed noise | unit absent/inert on all five | `list-timers` active + `scrape_success 1` in `/var/lib/prometheus/node-exporter/aitbc_attestation_arrival.prom` on every host |

## 2. Soak-end gate — the row nothing proceeds past

| item | host | path / unit | size | gate | precondition | verify before | verify after |
|---|---|---|---|---|---|---|---|
| soak-end check | fleet | `post-cut-verify.py` + alert green list | — | ungated read; **gates every row below** | the 3-day soak (decided 20 Oct) has elapsed | n/a | `post-cut-verify.py --manifest <file>` green **and** every `bc2-alert-window.md` post-cut green check holds — **nothing below proceeds until this row is green; it does not name a calendar date** |

## 3. F4 — post-soak funding (after the gate, before locks unpause)

| item | host | path / unit | size | gate | precondition | verify before | verify after |
|---|---|---|---|---|---|---|---|
| fund sell-escrow `0x40c7…` from treasury | chain | treasury → `0x40c7…` | amount: operator card, not decided | operator-named chain write | soak-end gate green; **before `BRIDGE_LOCKS_PAUSED` unpause** | balances of treasury + `0x40c7…` via RPC | sealed tx; new balances |
| fund bridge payout `0x356d…` from treasury | chain | treasury → `0x356d…` | amount: operator card, not decided | operator-named chain write | same | balances of treasury + `0x356d…` via RPC | sealed tx; new balances |

## 4. Per-item deletions (last — nothing deletes while a rollback is still possible)

| item | host | path / unit | size | gate | precondition | verify before | verify after |
|---|---|---|---|---|---|---|---|
| `.pre-reset` tree | each of five | `/var/lib/aitbc/.pre-reset-<YYYY-MM-DD>/` (the whole tree: chain dir, service DBs, stray top-level `chain.db`, `*.bak` residue — per the `bc2-host-inventory.md` store list) | per C2 `du -s` evidence | **per-item word** | soak-end gate green | `du -s` + `find` listing matches the inventory list | path absent |
| old chain data dir | each of five | inside the `.pre-reset` tree (`ait-hub.aitbc.bubuit.net/`) | same | per-item word | same | same listing | same |
| stale top-level `chain.db` + `*.bak` residue | per inventory | inside the `.pre-reset` tree | same | per-item word | same | same | same |
| offline backups | A9 location | per `bc2-host-inventory.md` backup section | A9 figures | per-item word | same; **custody material (`keystore.db`, `admin_nonces.db`) deletes only after the offline backup is verified to hold a copy** | backup archive listing covers the custody files | per item |
| old-chain `data/` residue | all five | anything left under `/var/lib/aitbc/data` outside `bc-2/` | — | per-item word | same | `find /var/lib/aitbc/data -name chain.db` lists only the live store | `data/` holds only `bc-2` |

## 5. Register-row pointers (not deletions — tracked on their own rows)

| row | waits for |
|---|---|
| `SEPOLIA-REDEPLOY-1` | the unpause of `BRIDGE_LOCKS_PAUSED` lives here — rotated EVM keys (operator) + post-cut week placement |
| `PG-POST-RESET-1` | services PostgreSQL-capable; blocked by the reset |
| `LEGACY-ECONOMICS-1` (#311) | legacy economics retirement after the cut |
| `GAP-CLI-READS-1` | parked read-side CLI gaps from the drain work |
| allocation file | **done 20 Oct** — committed at `docs/deployment/bc2-genesis/`, sha256-pinned (`Refs #332`); treasury `0x4aF8F36d91ff6b0125D18A76f242184e4F083EE0` supplied off-fleet with a verified `--treasury-proof`. The only open piece is the F4 amounts card (§3, soak-end gate) |

*Decided 20 Oct: soak = 3 days; treasury single-key off-fleet; F4
amounts open. Everything above is read/plan — nothing authorizes a
deletion, an unpause, or a restart.*
