# bc-3 genesis — treasury address single source of truth (#489)

Phase-1 SOT design for the bc-3 reset (chain id and authority rotation
decided on #410; treasury form decided 2-of-3 client-side multisig on
#489). The pattern is bc-2's proven one — `classes.json` is the only file
that names the address; every other surface *cites* it.

## classes.json extension

bc-2's `classes.json` carries treasury as a bare string. bc-3 upgrades it
to a structured object:

```json
"treasury": {
  "address": "0x<minted 2-of-3 — operator item, never committed before mint>",
  "kind": "client-multisig-2-of-3",
  "signers": "off-fleet — operator custody; key material never in repo or env",
  "feeds": [
    "allocations.json — the 100M-AIT treasury row",
    "env:SELL_TREASURY_ADDRESS (hub, hub1 exchange.env)",
    "env:ESCROW_FEE_RECIPIENT (all 5, R8 fresh custody — own key, see below)",
    "genesis parameters.treasury-adjacent cites"
  ],
  "proof": {
    "challenge": "check-alloc-file.py rendered challenge — chain-derived post-e15202f7b",
    "type": "personal_sign per signer, >= threshold — 2 of 3 proofs required",
    "verified_by": "check-alloc-file.py --treasury-proof (repeatable flag, 2 files)"
  },
  "supersedes": "bc-2 0x4aF8F36d91ff6b0125D18A76f242184e4F083EE0"
}
```

`escrow_fee_recipient` stays under `authorities` with its own custodied
key per the #410 R8 ruling — it is treasury-adjacent but NOT the treasury
address; a `feeds` env that restates the treasury literal for the fee role
is a defect the gates catch.

## Gate checks

Pre-cut (before `build-genesis.py` consumes the values):

1. `scripts/ops/key-audit.py --find-address <bc-2 treasury>` on all 5
   hosts → no unexpected hits (proves no stale copies landed).
2. `tests/unit/test_treasury_sot.py` — literal-outside-SOT scan: the
   bc-3 treasury literal may appear only in `classes.json`,
   `allocations.json`, and allowlisted doc cites.
3. `check-alloc-file.py --classes --require-classes --treasury-proof`
   all PASS with **2 of 3** signer proofs.
4. The three signer keys' custody is evidenced by the challenge proofs
   themselves (no fleet key material required or wanted).
5. Every `feeds` surface greps clean: env literal == SOT literal.

Post-cut:

6. `verify-genesis-root.py` + classes-vs-genesis diff: genesis
   `parameters` and the allocation row match the SOT exactly once.
7. On-chain treasury row = SOT address, exactly once.
8. Zero hits for the superseded bc-2 literal inside bc-3 genesis inputs
   and fresh envs (replay-across-resets risk).
9. Old literal retired from active envs (the bc-2 decommission drain
   table covers it; this check keeps the table honest).
