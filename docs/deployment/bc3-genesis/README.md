# bc-3 genesis — treasury address single source of truth (#489)

Phase-1 SOT design for the bc-3 reset (chain id and authority rotation
decided on #410; treasury form ruled 1 Nov 2026 on #489: **fixed EOA** —
a fresh single-key address generated off-fleet per the retracted-multisig
design; the earlier 2-of-3 client-side multisig sketch is superseded).
The pattern is bc-2's proven one — `classes.json` is the only file that
names the address; every other surface *cites* it.

## classes.json

bc-2's `classes.json` carries treasury as a bare string. bc-3 uses a
structured object so the decision trail, feeds and proof spec travel with
the literal:

```json
"treasury": {
  "address": "0xB0e6CF0D8dF844235A54d6D210D446099ef15a69",
  "kind": "fixed-eoa",
  "custody": "off-fleet — operator custody; key material never in repo, env, or logs",
  "feeds": [ "…surfaces that legitimately restate the literal…" ],
  "proof": { "challenge": "…", "type": "personal_sign", "verified_by": "check-alloc-file.py --treasury-proof" },
  "supersedes": "bc-2 0x4aF8F36d91ff6b0125D18A76f242184e4F083EE0"
}
```

The committed file pins the literal **once**. Everything else — genesis
`allocations.json`, env values, runbooks — either reads the SOT at build
time or is a `feeds`-listed restatement the gates check for equality.

`escrow_fee_recipient` stays under `authorities` with its own custodied
key per the #410 R8 ruling — it is treasury-adjacent but **NOT** the
treasury address; a `feeds` env that restates the treasury literal for
the fee role is a defect the gates catch.

## Challenge string versioning

The spendability-proof message is rendered by
`scripts/ops/check-alloc-file.py`'s `TREASURY_CHALLENGE_TEMPLATE`:

```
AITBC {chain_id} genesis treasury spendability proof for {address}
```

- **bc-3 rendering** (pinned in `classes.json`):
  `AITBC bc-3 genesis treasury spendability proof for 0xB0e6CF0D8dF844235A54d6D210D446099ef15a69`
- The template is chain-scoped since post-`e15202f7b`: a `bc-2` proof
  signs a different message and can never replay as a `bc-3` proof (and
  vice versa — `_LEGACY_CHAIN_ID` exists only so pre-versioning bc-2
  proof files keep verifying).
- The verifier resolves `chain_id` from `AITBC_CHAIN_ID`/`CHAIN_ID` env,
  then `allocations.json`'s `chain_id` key, else defaults to `bc-2`. For
  bc-3 checks run it with `AITBC_CHAIN_ID=bc-3` (or a `chain_id: "bc-3"`
  allocations file — the committed `classes.json` already carries it).
- Producing the signature itself is an operator item — the treasury key
  never leaves off-fleet custody. The gate below is specced now and
  stays **pending** until the proof exists.

## Gate checks

Pre-cut (before the genesis build consumes the values):

1. **No stale copies on the fleet** — runnable now, expected result is
   zero hits on every host (the address is fresh, nothing may already
   hold it):

   ```
   for h in node0 node1 node2 hub hub1; do
     ssh $h 'cd /opt/aitbc && PYTHONPATH=/opt/aitbc venv/bin/python \
       scripts/ops/key-audit.py --find-address 0xB0e6CF0D8dF844235A54d6D210D446099ef15a69'
   done
   ```

2. **Literal-outside-SOT scan** —
   `pytest tests/unit/test_treasury_sot.py`: the bc-3 literal may appear
   only under `docs/` (SOT + cites) and the test itself. Now active —
   it skipped while `classes.json` was unminted.
3. **Spendability proof** *(pending — operator item)*: the operator
   signs the printed bc-3 challenge off-fleet; verification is
   `PYTHONPATH=. python scripts/ops/check-alloc-file.py <allocations.json>
   --classes docs/deployment/bc3-genesis/classes.json --require-classes
   --treasury-proof <proof.json>` with `AITBC_CHAIN_ID=bc-3` — the proof
   file is `{address, message, signature}` and must recover to the SOT
   address over the exact challenge string.
4. Custody evidence IS the proof: no fleet key material is required or
   wanted at any point.
5. Every `feeds` surface greps clean: env literal == SOT literal.

Post-cut:

6. `verify-genesis-root.py` + classes-vs-genesis diff: genesis
   `parameters` and the allocation row match the SOT exactly once.
7. On-chain treasury row = SOT address, exactly once.
8. Zero hits for the superseded bc-2 literal inside bc-3 genesis inputs
   and fresh envs (replay-across-resets risk).
9. Old literal retired from active envs (the bc-2 decommission drain
   table covers it; this check keeps the table honest).
