# KNOWN — dedupe registry for stress findings (seed: 2026-10-29)

File a finding as `STRESS-<class>-N` (milestone `stress-1`, linked on #706)
only if it does not match an entry below. Update this file as issues land.

## Closed recently — do not refile
- #703 refund emission-before-seal race — fixed + recovered (221fc615c)
- #704 rejected-tombstone import poison — fixed (0198f8626); node2 attestation
  deficit cleared, scar exited the window ~h10309
- #705 reconnect retry suppression + lease re-registration + BroadcastSkipped
  semantics — fixed (0a7eed292); `GossipBlockDeliveryFailing` is the real
  critical now; `BroadcastSkipped` = genuine publish failure only
- #696 shared transfer-ledger service — live (dd6a7343a + eb8b14054);
  `BRIDGE_LEDGER_URL` fleet-wide, `BRIDGE_LEDGER_API_KEY` dedicated env

## Open / expected noise — dedupe against these
- `AITBCJournalErrors` on node1 rpc — intermittent restart-window noise
- node1 `bridge-headers store failed` lines — pre-existing, unrelated to stress
- island `bc-2-island-1` low head cadence vs bc-2 — expected
- `STAKE_*` consensus path: HTTP 410 unarmed at v17 (#649) — expected refusal,
  not a finding; agent-staking `/v1/agent-staking/*` is the exercisable lane
- `ESCROW_FEE_SWEEP`/`RECEIPT_CLAIM` — node-emitted, no wallet path; watch-only
- `HTLC_*`, unsigned `AUTO_STAKE` — dead shapes, replay-suite only
- island `AttestationArrival*` share on bc-2-island-1 has 2 validators —
  different baseline than bc-2

## Recently observed anomalies under watch
- `gossip_mesh_peer_publish_dropped_total` — inflight-cap drops are NOT
  covered by the delivery critical (#705 caveat); a finding here is real
