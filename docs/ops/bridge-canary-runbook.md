# Bridge deposit canary — staged re-run (post-shadow-window)

> Tracked copy of the operator canary runbook (sanitized; TOPOLOGY keeps
> the scratch original).

Re-run of the 2026-09-29 ETH→AIT deposit canary, now exercising the
serialization + auto-abandon + dust/queue code shipped in `676db189` and
`29a9ac2a`. Send is an operator action (operator Sepolia wallet);
detection/verification commands are agent-runnable.

## 0. Ordering — record the window verdict FIRST

Any canary case that produces a tx the v9 policy would reject bumps
`v9_would_reject_*` by design. The plain deposit canary below sends a
normal signed ETH tx — it does NOT touch v9 counters, but the moment it
generates an AIT payout TRANSFER it adds a checked tx to the mix.
Therefore:

```bash
# capture the window verdict before anything else runs
AITBC_FLEET_DOMAIN=aitbc.bubuit.net \
  scripts/monitoring/fleet-config-check.sh hub hub1 node0 node1 node2 \
  | sed -n '/v9 shadow window/,/deposit ALERT/p' | tee /tmp/v9-window-verdict.txt
```

- If the canary run adds optional negative cases (unsigned/wrong signer),
  list expected counter deltas per case below and diff counters after.
- Plain canary: expected `v9_shadow_checked_transfer_total` +≥1 on the
  proposer that applies the payout; `v9_would_reject_total` delta = 0.

## 1. Operator sends the Sepolia deposit

From the operator's Sepolia wallet (same as the 0x1df445b5 canary):

- to: `0x09362894C18f7CbCdb85b124ef4c8F63DEC09B32` (bridge wallet)
- value: ~0.0015 ETH (above `MIN_ETH_DEPOSIT=0.001`, small)
- data: UTF-8 `0x90030c53…` — the AIT canary recipient (42-char 0x hex —
  the tightened parser now rejects anything malformed at once)
- record the Sepolia tx hash

## 2. Monitor detection (agent)

```bash
ssh hub 'journalctl -u aitbc-bridge-monitor --since "-15min" --no-pager \
  | grep -iE "deposit|payout|deferred|in flight|ALERT"'
```

Expected sequence (new code paths):

- `Found deposit: 0x… amount: 0.0015 ETH`
- `Built signed payout: … (nonce=N)` then `Payout for deposit 0x…
  broadcast as 0x… — awaiting 2-block seal`
- If another payout were in flight: `Deposit 0x… deferred — a payout is
  already in flight` → pays after the first seals (serialization proof).
- `Payout 0x… sealed at height … — deposit 0x… COMPLETED`

## 3. Verify ledger + chain (agent)

```bash
ssh hub 'cd /opt/aitbc && venv/bin/python -m bridge_monitor.admin status <eth_tx_hash>'
# expect: status completed, ait_tx_hash set, signed_tx cleared/kept per path

# payout sealed on-chain, all hosts agree
for h in hub hub1 node0 node1 node2; do
  ssh $h "curl -s http://127.0.0.1:8202/rpc/transaction/<ait_payout_hash> \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get(\"block_height\"), d.get(\"status\"))'"
done
```

## 4. Audit + counters (agent)

```bash
scripts/monitoring/bridge-payout-audit.py hub  # row listed, payout sealed
for h in hub hub1 node0 node1 node2; do
  ssh $h "curl -s http://127.0.0.1:9009/metrics | grep -E '^v9_'"
done  # diff against the window-verdict capture; plain canary must add no
      # would_reject
```

## 5. Pass criteria

- [ ] Deposit detected within one poll interval of Sepolia confirmation
      depth (BRIDGE_CONFIRMATIONS=3 blocks).
- [ ] Exactly one signed envelope, exactly one payout, sealed +2 blocks
      → `COMPLETED` (never completed-before-sealed).
- [ ] Ledger row complete; audit lists it; no ALERT lines.
- [ ] `v9_would_reject_*` unchanged vs the captured window verdict;
      `v9_shadow_checked_transfer_total` +1 on the applying node once the
      series exists (post-pin deploy it always exists).
- [ ] Restart idempotency (spot check): `systemctl restart
      aitbc-bridge-monitor` after COMPLETED → no re-pay (COMPLETED row +
      cursor past block). NB: a monitor restart is safe mid-window; a
      validator restart is not.

## Optional negative cases (list expected deltas before running)

- Unsigned user-type tx via RPC: `v9_would_reject_total` +1,
  `v9_would_reject_missing_signature_<type>_total` +1 on the applying
  nodes — only valid as a shadow-mode observation; at v9 it must reject.
- Wrong-signer tx: rejected by the existing v7+ signature check (not a
  v9 counter — documents the pre-existing gate still works).

## Notes

- Dust (<0.001 ETH) is no longer invisible: a sub-minimum send now lands
  as a `FAILED` ledger row (`below MIN_ETH_DEPOSIT — dust inflow`) —
  include a dust send in the canary only if you want to see it; it costs
  gas for a known-outcome row.
- Funding whitelist is live since 2026-09-30: `BRIDGE_FUNDING_SOURCES`
  on hub = `0x02b8…` (treasury key reused per O-7 — operator decision
  30 Sep). A send **from** that address records `FUNDING`, no payout,
  no alert; every other inflow keeps the deposit path. The match is
  lowercased on both sides — a canary sender differing from the
  treasury only by case still records `FUNDING` and never pays out;
  use a clearly different address. **Mainnet caveat (BR-5):** this
  key lives in internet-facing hub processes — move the funding
  source to a separate wallet before real ETH is involved.
