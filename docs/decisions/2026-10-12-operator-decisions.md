# Operator decisions — 2026-10-12

One table of every operator decision taken on 12 October 2026, recorded
verbatim from the decision lists in `tasks/_source/tasks.json` (BR-8).
"Stays closed" names the gate the decision leaves shut — nothing in this
page opens a gate by itself.

| task | decision label (verbatim) | effect | what stays closed |
|---|---|---|---|
| SD-1 | "Record truth + anomaly (Recommended)" | The job-`…5c0e` R2 double-release is recorded in the repaired ledger as the known anomaly and left as is (A1). | No repair write for that row; any remedy is a separate decision. |
| SD-1 | write phase per host: node2, then node0, then node1 + hub1, then hub (each "director recommendation" after the previous verified) | The escrow-table rebuild ran serially, one host at a time, each gate re-verified before the write; fleet now carries identical 72-row tables. | — (write phase closed again after hub verified) |
| SD-1 | "rpc cache refresh by one serial rpc-only restart per written host after all hosts are done" | After all five hosts were written, each `aitbc-blockchain-rpc` was restarted once, serially, so caches reload the repaired rows. | No further restarts authorized by this decision. |
| V-3 | "Normalize + exclude (Recommended)" | The side-table canonicalization normalizes values and excludes non-deterministic columns per the shadow design. | — |
| V-3 | option A, expand to 13 tables and design the shadow soak | Committed side-root set = all 13 apply-written tables; shadow soak designed before any activation. | No activation height. |
| V-4 | "Boundary 30000, waive 22 (Recommended)" (boundary part) | Grandfathering activation boundary pinned at height 30000; the 4 underivable legacy locks below it stay derivable-exempt. | — |
| V-1 | "Boundary 30000, waive 22 (Recommended)" (waiver part) | Live exercise waived for the 22 fixture-replayable types; one live BRIDGE_RELEASE stays reserved, each exercise operator-approved at that time. | The BRIDGE_RELEASE live exercise stays unapproved. |
| V-2 | "Build shadow hooks only (Recommended)" | V-2 adversarial gate lives as shadow/counter instrumentation on its branch only; no merge, no host, no activation height. | Merge to main and arming stay closed. |
| V-3 | "Build shadow hooks only (Recommended)" | 13-table digest hook built compare-only on a branch, flag-gated default off. | Merge to main and arming stay closed. |
| V-4 | "Build shadow hooks only (Recommended)" | Seal-path missing-data guard built dry-run-only on a branch; it never rejects or mutates. | Merge to main and arming stay closed. |
| BNT-1 | "option C now (retire dead surfaces)" (recorded on BNT-2) | The unsigned-at-emission protocol transfers are accepted as dead; implementation retires their RPC surfaces (BNT-2, BNT-3 docs/CLI marks). | The `payload.auth` revival question stays open for a separate decision. |
| BR-4 | "Close BR-4 now (Recommended)" | The flag-audit task is closed. | — |
| S-11 | "Classify first (Recommended)" | S-12 classification ran read-only before any sweep decision. | — |
| S-11 | "Accept: no sweep (Recommended)" | Accepted: zero sweepable rows; no ESCROW_FEE_SWEEP batch is built. | Any future sweep is a new chain-write decision. |
| O-10 | "Keep as is, leave the branch parked (Recommended)" | The TEE-attestation gate branch stays parked unmerged. | Merge/arming the TEE gate stays closed. |
| BR-5 | "Run preflight now, read-only (Recommended)" | The one authorized live `bridge_mainnet_preflight.py` run happened (5→6 of 7 knobs fail after the env-stack correction). | The mainnet decision itself stays closed. |
| BR-6 | "Keep closed for now (Recommended)" | The B13 outbound-ledger live migration stays closed; revisit with BR-1 or before mainnet. | Live DB migration stays gated. |
| SD-5 | "Defer, no urgency (Recommended)" | The treasury top-up is deferred. | — |
| SD-2 | "Defer, no ntfy yet (Recommended)" | Alertmanager delivery stays deferred; alerts remain log lines plus fleet-check counts. | — |
| V-6 | "Not now (Recommended)" | The live exercise stays unscheduled. | V-6 live exercise stays closed. |
| BR-1 | "Park until mainnet is decided (Recommended)" | Contract deploy/ownership work stays parked. | — |
| O-8 | "Park until mainnet is decided (Recommended)" | Safe-owner/signer logistics stay parked. | — |
| M-2 | "Prepare the commands, leave the rows (Recommended)" | Offer commands prepared for node2 services; hub's two rows under another provider address stay untouched; agents never sign. | Signing/submitting offers stays with the operator. |
| S-10 | "I will pay now, command please (Recommended)" | The operator executes the 360000-unit payment with the wallet CLI; agents prepared the exact command and before/after verification only. | Any further payment is a new decision; the TEE-attestation branch stays parked. |

*Source: `tasks/_source/tasks.json`, `decisions` fields, all dated
2026-10-12. Wallet addresses are fine to name; no keys or 64-hex values
are recorded here.*
