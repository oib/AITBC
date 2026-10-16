# Bridge funding-source migration plan (O-7)

Status: **testnet cutover executed 16 Oct 2026; the mainnet pass is still
ahead.** Pre-v1 the operator converted the gate to testnet ("we are pre
v1 so we dont do mainnet — convert all tasks to testnet") — steps 2–6 ran
on Sepolia: F = rehearsal signer3 `0x7bD563129Fe0822BB413b8C20Cdda1187a7091D2`,
overlap posture (`BRIDGE_FUNDING_SOURCES=F,0x02b8…` on hub's monitor env),
monitor restarted 12:07:56 CEST, a 0.001 ETH top-up from F recorded as
`FUNDING`, and a 0.001 ETH canary from signer1 (non-listed) correctly
landed as a `FAILED` deposit row ("Invalid AIT recipient address").
Open: step 8 repo copies, step 10 shrink to F alone (testnet), then the
whole plan again for mainnet. Every step that moves funds, creates a
wallet, edits a live env file, or restarts a service is marked
**[operator]** or **[agent]** per the standing authorizations. Prepared
16 Oct 2026 from `origin/main` (`b435f3ee9`) plus read-only hub
inventory.

Goal: `BRIDGE_FUNDING_SOURCES` on hub currently names the treasury /
genesis address `0x02B8F2C61DB19B04aB68cfb43d0605e63dE74c5b`. Before
mainnet the funding sender must be a separate wallet whose key never
lives on a node. (The 0x02B8 *key* is no longer loaded by any hub
service — verified 16 Oct 2026, see section 2.)

## 1. Inventory — where the address or key appears

### Live (hub)

| where | what | who reads it | breaks if the address changes |
|---|---|---|---|
| `/etc/aitbc/aitbc-bridge-monitor.env` | `BRIDGE_FUNDING_SOURCES=0x7bD5…91D2,0x02b8…4c5b` (overlap since 16 Oct, testnet F first) | `bridge_monitor/main.py` → allowlist of ETH senders whose inflows record `FUNDING` (never paid out) | a top-up from the *new* wallet while the old address is still listed still records `FUNDING`; a top-up from an address **not** listed takes the deposit path and fails (missing recipient) |
| `/etc/aitbc/node.env` + ~12 other env files | `GENESIS_WALLET_ADDRESS=0x02B8…` (address only) | informational / genesis labelling across `blockchain.env`, `exchange.env`, `aitbc-*` envs | nothing — it is an address string, not a key or an allowlist entry |
| `/etc/aitbc/aitbc-blockchain-node.env`, `validator-secrets.env` | `PROPOSER_KEY` / `VALIDATOR_KEYS` | **verified 16 Oct 2026: both files hold only the `0x2aD5…` key (hub's live identity); the 0x02B8 key is absent.** The journal line `proposer=0x02B8F2C6…` that suggested otherwise is the genesis block's historical proposer label (`Genesis block already exists: height=0 …`), printed once per node start — not a loaded key | nothing — the old key is already gone; step 9 is a confirm-only check |
| `/root/.aitbc/wallets/treasury` | keystore file, root-only | on-demand `aitbc wallet` CLI | nothing running; not a daemon load |
| `/etc/aitbc/blockchain-secrets.env` | `WALLET_IMPORT_PASSWORD` | wallet import path | unrelated to the address change |
| `/etc/aitbc/exchange.env` | `SELL_TREASURY_ADDRESS`, `SELL_ESCROW_FUNDING_SOURCES=0x34FF…9267` | exchange sell side — a **different** wallet already | none; the sell-side funding source was already separated — it is the model to mirror |

### Repo

| where | what |
|---|---|
| `apps/bridge-monitor/src/bridge_monitor/main.py:136`, `storage.py:38` | `FUNDING` classification + case-insensitive sender match |
| `apps/bridge-monitor/README.md`, `tests/test_bridge_monitor.py:397` | documented + tested behaviour |
| `scripts/monitoring/fleet-config-check.sh:786` | compares `BRIDGE_FUNDING_SOURCES` across hosts (monitor is hub-only — expect it listed only on hub) |
| `scripts/ops/bridge_outbound_collect.py:31` | notes the funding classification |
| `docs/decisions/README.md` | the 30 Sep O-7 decision record |
| `docs/ops/bridge-canary-runbook.md:109` | canary-from-different-address rule |
| `docs/security/bridge-custodian.md`, `bridge-threat-model.md` | checklist/threat-model mentions |
| `AGENTS.md` | the `BRIDGE_FUNDING_SOURCES` section — update at cutover |
| `docs/design/eth7-…`, `eth8-…` | historical design mentions — leave |

## 2. Which processes load the key today

- **`aitbc-blockchain-node` (hub)** — **verified 16 Oct 2026:** the
  unit's `EnvironmentFile=` list is `aitbc-blockchain-node.env`,
  `blockchain.env`, `node.env`, `blockchain-secrets.env`,
  `validator-secrets.env`. `PROPOSER_KEY` and `VALIDATOR_KEYS` (in both
  `aitbc-blockchain-node.env` and `validator-secrets.env`) each derive to
  `0x2aD555A9e5208A6438b24FbdA4BC83c4c2453e64` — hub's own post-rotation
  identity, and no other node's key. The 0x02B8 key is **not** present.
  The `proposer=0x02B8F2C6…` journal line is the genesis block's
  historical proposer label (`Genesis block already exists: height=0
  …`), printed once per node start — it is not evidence of a loaded key.
  (Earlier wording inferred a loaded key from that line; that inference
  was wrong.)
- **`aitbc` wallet CLI as root** — `/root/.aitbc/wallets/treasury`
  keystore, on-demand only; not a resident process.
- **`aitbc-wallet` service** — binds `127.0.0.1` (unit overrides
  `WALLET_HOST=0.0.0.0`); its `ETH_WALLET_PRIVATE_KEY` is a different
  key. Not the treasury holder.
- **`aitbc-bridge-monitor`** — holds `BRIDGE_PAYOUT_PRIVATE_KEY`
  (payout wallet `0x356d…`), **not** the funding key. It only *matches*
  the funding address; it never signs from it.

Internet-facing summary: the treasury key is **not** hot in the p2p
consensus daemon (verified 16 Oct 2026); the only remaining copy is the
offline CLI keystore. The monitor only needs the *address*.

## 3. Migration steps (in order)

1. **[operator]** Choose or create the new funding wallet **offline** —
   not on any node. Record only its public address `F` here.
2. **[operator]** Decide the cutover posture: replace-only
   (`BRIDGE_FUNDING_SOURCES=F`) or transitional overlap
   (`BRIDGE_FUNDING_SOURCES=F,0x02b8…` — the list is comma-separated).
   Overlap is the safer default: any straggler top-up from the old sender
   still records `FUNDING` instead of taking the deposit path and
   failing.
3. **[operator]** Edit `BRIDGE_FUNDING_SOURCES` in
   `/etc/aitbc/aitbc-bridge-monitor.env` on hub (value chosen in step 2).
4. **[agent]** `systemctl restart aitbc-bridge-monitor` on hub — single
   service restart, covered by standing authorization; verify
   `journalctl -u aitbc-bridge-monitor` shows a clean start and the
   ledger scan resumes at its stored height.
5. **[agent]** Verify with a read-only probe: monitor log shows the new
   allowlist loaded; `/v1/bridge/...` status routes still answer.
6. **[operator]** Send a small top-up **from F**; check the ledger
   records a `FUNDING` row (deduplicated, no payout):
   `scripts/ops/bridge-admin.sh status <tx_hash>` and
   `scripts/ops/bridge-admin.sh list --status funding` — the row's
   `status` must be `FUNDING`, not
   `FAILED`/`SUBMITTED`.
7. **[operator]** Send the next deposit canary **from a different
   address than F** — the canary must exercise the deposit path, and the
   funding match is case-insensitive, so even a case variant of F still
   records `FUNDING` (see `docs/ops/bridge-canary-runbook.md`).
8. **[agent]** Update the repo copies: `AGENTS.md` section,
   `docs/security/bridge-custodian.md` checklist,
   `docs/ops/bridge-canary-runbook.md`, `docs/decisions/README.md` O-7
   row (mark the move done, keep the record).
9. **[operator]** Retire the 0x02B8 key from `aitbc-blockchain-node`'s
   env (`PROPOSER_KEY`/`VALIDATOR_KEYS`) — **no action needed, confirmed
   16 Oct 2026**: the check below already found only `0x2aD5…` keys. If a
   future re-check finds the key back, this is cleanup, not rotation:
   the validator set already rotated 12 Oct. A removal plus
   `systemctl restart aitbc-blockchain-node` on hub would then need its
   own operator line (hub node restarts are *not* in the standing
   authorization).

   - **Phase 0 — repeat the read-only check before assuming.** Do not
     trust the journal's `proposer=` string (the genesis line always
     names the historical proposer). Instead list the unit's
     `EnvironmentFile=` entries (`systemctl cat
     aitbc-blockchain-node`), then for each file derive the public
     address of `PROPOSER_KEY` and every `VALIDATOR_KEYS` entry inside
     one short-lived process that prints only `NAME -> 0xADDRESS` —
     the key material must never reach stdout, a log, shell history, or
     a file (run e.g.
     `ssh hub '/opt/aitbc/venv/bin/python -' < derive.py`). Compare the
     results against `0x02B8…4c5b` (old) and `0x2aD5…` (live).
10. **[operator]** When confident nothing needs the old address, shrink
    the allowlist to `F` alone (if step 2 chose overlap) and repeat
    step 4–5.

Rollback per step: env edits revert to the prior value + monitor
restart (step 4 pattern); the `FUNDING` ledger rows already written stay
(append-only, correct either way); key retirement rolls back by
restoring the env var — but only if the validator set still admits it,
otherwise leave it retired and treat as a validator-ops issue.

## 4. Sepolia rehearsal (later task)

The bridge monitor watches an Ethereum-side RPC; rehearse on Sepolia:

```bash
# on hub, dry — print what the monitor would classify
cd /opt/aitbc && scripts/ops/bridge-admin.sh status <known_deposit_tx>
# propose env change against a Sepolia-funded throwaway sender S:
BRIDGE_FUNDING_SOURCES=S  (in a staging env, never live)
# send a small Sepolia ETH tx S->bridge deposit address; then check:
#   - ledger row status == FUNDING
#   - no payout envelope created
#   - alerts.log shows no deposit failure
# then a second tx from a non-listed address -> proves the deposit path
#   still fails on missing recipient exactly as documented
```

Step 9's Phase 0 (the read-only env/derived-address check) was already
run 16 Oct 2026 and found the key absent; repeat it rather than trusting
the journal before any removal.

## 5. Risks and their checks

| risk | check |
|---|---|
| K-1 sender match — canary sent from F or a case variant records `FUNDING` instead of exercising the deposit path | canary sender must be a *clearly different* address; verify the ledger row `status` is not `FUNDING` |
| float alerts during the move — `BRIDGE_LOW_FLOAT_AIT=250` vs ~746.8 AIT balance | read payout-wallet balance before and after; the alert counts balance minus non-terminal payout rows — an in-flight top-up is unaffected either way |
| in-flight top-up misclassified during the env swap | keep overlap posture (step 2) until the new sender is proven; check no `FAILED` row appears in the ledger between steps 4 and 6 |
| hub restart timing — `aitbc-bridge-monitor` `Requires=aitbc-blockchain-rpc` | restart monitor alone, never rpc; if rpc restarts for another reason the monitor follows automatically |
| key still needed for consensus — removing 0x02B8 from `PROPOSER_KEY` while it is still the active proposer stalls hub block production | moot as of 16 Oct 2026: the env check found only `0x2aD5…` keys; if the key ever reappears, run step 9 Phase 0 and require a named hub-node-restart line before touching it |
| `fleet-config-check.sh` drift alert — the var is compared across hosts | verify the script only expects it where the monitor runs (hub); if it flags followers, the fix belongs to the check, not the env |

## Out of scope (unchanged)

No wallet creation, import, or export; no fund moves; no env or unit
edits; no restarts; no key or password handling. All such steps are
marked **[operator]** above.
