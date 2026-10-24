# bc-2 Alert Window

What the monitoring stack does through the bc-2 cut — companion to
`bc2-reset-runbook.md`. Findings from `RESET-ALERTS-1` (#336 Phase 0,
read-only baseline 20 Oct: **0 firing, 0 pending**).

## The stack (unchanged by the cut)

- **Fleet rules**: `scripts/monitoring/aitbc_rules.yml` — 4 record rules +
  **53 alerts**; deployed identical (sha256) on all five hosts.
- **Hub-only rules**: `/etc/prometheus/aitbc_hub_rules.yml` — **23 alerts**
  (authority/governance float guards, bridge set, `ChainDiverged`).
- **Textfile exporters** → `/var/lib/prometheus/node-exporter/*.prom`
  (timers per `bc2-host-inventory.md`).
- **Watcher**: `aitbc-prometheus-watch.service` → `/var/log/aitbc/alerts.log`
  + its own `.prom`. **No Alertmanager exists** — silence is procedural.
- **Public page**: `website/alerts.{html,js}` via explorer-api
  `/api/alerts`.

## Procedural silence (no API silence possible)

1. The operator's window-start line **is** the silence. Nothing is
   suppressed — every firing is true (services really are down).
   `alerts.log` keeps the verbatim evidence trail with timestamps.
2. The public page shows the storm while it lasts; the A11 maintenance
   notice is the mitigation. During explorer-api downtime the page
   degrades to watcher-log state.
3. The window ends when the expected-noise list below is empty: every
   listed alert cleared within ~15 min of C7 green. Anything still
   firing then is a real finding, not residual noise.

## Expected noise — inside the window (B0 → C5)

| alert | why it fires | clears when |
|---|---|---|
| `ServiceDown` (per stopped unit, critical 1m) | intended — services stopped | units return at C5/C6 |
| `AitbcSystemdUnitFailed` | only on a *failed* bc-2 start — useful | unit healthy |
| `ChainHeadStalled` | frozen head ~17 min into the freeze | bc-2 gauge appears, `>0` arm quiet at h=0 |
| `ChainHeadMetricMissing` | rpc targets down | rpc back at C6 |
| `ChainDiverged`, `ChainDivergenceSeen` (hub-only) | hosts intentionally diverge (frozen old vs bc-2 partial) | all five agree post-C5 |
| `*Stale`/`*Unreadable`/`*Failed` check rules for suspended timers (`EscrowSettlement*`, `Attestation*Check*`, `BackupExporterMissing`, `AITBCEnvWatchStale`, `AuthorityBalance*`) | B0 suspends their exporters | timers restored in §F |
| `AITBCJournalErrors` bursts | stop/move/start error lines | settles post-C5 |
| `EscrowSettlementRefusedOn*` | settlement surface refusing | clears with bc-2 |
| `BackupStale` | B0 suspends `aitbc-backup.timer` | first post-cut generation |
| `NativeEnergyRate*Stale` | hub rate-refresh timer suspended | timer restored + first refresh |

## Expected noise — after the cut (first hour, all benign)

- **`BackupSizeCollapse`** — each bc-2 backup generation lands far under
  the 7-day median while that median still holds old-chain sizes, so the
  alert fires on every post-reset generation until the median re-anchors
  (~a week; the post-drop samples pass 50% of the `[7d]` window ~3.5 days
  after the size drop). Benign while the run journals stay clean; the
  approved handling is a per-host silence with an expiry, recorded in
  hub's `/etc/aitbc/prometheus-silences.json`.
- **`NativeEnergyRate*Stale`** — until the first refresh lands on the
  fresh service db.
- **`AttestationArrivalDegraded`** — only if early produced blocks are
  sparse; needs 30 m of sustained sub-0.97 share.

## Self-clearing by design (no action needed)

- **`V9ShadowRejection`, `V9AttestationRefusal`** — dead on bc-2 (all
  gates at 1 → v14 from block 1, no v9 shadow counters); rule removal is
  already staged per `bc2-consumers.md`.
- **`Fork*` family** — fork metrics live in the old chain db; fresh db
  has no fork rows.
- **`Messaging*` family** — **verified in code**: `collect_all` iterates
  `settings.supported_chains` only (`app.py`), every metric carries a
  `chain_id` label (`messaging_metrics.py`), and queries filter
  `chain_id == <id>` (`messaging_index.py`). After the rpc restart only
  `chain_id="bc-2"` series exist; digest labels self-segregate, so
  `MessagingIndexDigestMismatch` cannot compare old against new. Stale
  in-process label sets die with the process restart.
- **`ValidatorHubAccountMoved` / `ProposerRetiredAccountMoved`** —
  watch: movement-detection baselines may trip on the new chain's first
  state; expected to quiet once baselines re-anchor.
- **Authority/governance float guards** (hub-only) — RPC-read balances
  become the genesis floats; pass as long as the allocation keeps the
  monitored addresses ≥ threshold (the 256 AIT float band).

## What monitoring cannot see about the cut

Env *values* (name-presence only), chain-id uniformity across hosts,
genesis equality, key usability, `.pre-reset` completeness, in-window
chain writes (visible only after the fact). Those are the runbook's
anchored greps, sha256s, and journal lines — not alerts.

## Post-cut green checks (the window's exit criteria)

`ServiceDown`/`AitbcSystemdUnitFailed` = 0 ·
`ChainHeadStalled`/`MetricMissing` quiet with
`aitbc_messaging_chain_head_height{chain_id="bc-2"}` advancing ·
`SyncLagHigh` quiet on followers · `Attestation*` share ≥0.97 after ~30
blocks · every suspended-timer `*Stale`/`Failed` quiet (B0 set restored)
· authority/governance float guards quiet · `BridgeSet*` quiet ·
`ChainDiverged` quiet · next `aitbc-backup` generation green ·
`alerts.log` window entries all from the expected-noise list ·
store check: `data/` holds only `bc-2`
(`find /var/lib/aitbc/data -name chain.db` lists the single live store).

## Placement ruled; hardenings still proposed

Ruled (operator, 20 Oct): the db-scan exposure is handled **by
placement, not rules** — `.pre-reset` copies land in
`/var/lib/aitbc/.pre-reset-<YYYY-MM-DD>/`, a sibling of `data/` (runbook C2),
so `data/*/chain.db` scans see no archived store after C2.
Two optional hardenings stay proposed, not landed:

- Alert-side `{db="bc-2"}` selectors on the already-labelled arms
  (`AttestationArrivalDegraded`, `AttestationValidatorSilent`,
  `AttestationArrivalCheckFailed`, the two escrow `*CheckFailed` arms) —
  belt-and-braces against any stray `chain.db` appearing under `data/`
  in future; held as a proposed diff.
- Exporter-side `db=` labels on the unlabeled aggregate gauges
  (`aitbc_escrow_open_tx_only_locks`, `aitbc_escrow_residue_accounts`,
  `aitbc_bridge_set_*`) — bigger change (metric shape + rule migration);
  without it a stray `chain.db` under `data/` could mask or mimic the
  live chain's series. The placement convention removes today's
  exposure; the label hardening is a separate decision.
