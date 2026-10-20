# bc-2 genesis inputs

The pinned inputs the `bc-2` genesis build consumes (reset planning — the
window is not scheduled or authorized). This directory holds build inputs
only; documentation stays in the parent directory.

| file | content | sha256 |
|---|---|---|
| `allocations.json` | the 25-row genesis allocation — treasury `0x4aF8F36d91ff6b0125D18A76f242184e4F083EE0` at `3600000000000000` units (100,000,000 AIT), the 256-AIT float band across 11 service floats, 2 executors, 4 authorities and the ops float, and the zero-balance retired/faucet/bond-derived rows; total `3600009216000000` units (100,000,256 AIT) | `ca4a150085cff31e9388ab504c2ed0e855e6f963bbdcbde8875b94872d281fcb` |
| `classes.json` | the class manifest the allocation checker binds the addresses to (`--classes` / `--require-classes`) | `836ae03716a97b130476c8983eb6a8d3dabf9c9eeb03530d85f6cfa69f6cbcb5` |

Verify before any build:

```bash
venv/bin/python scripts/ops/check-alloc-file.py \
  --allocations docs/deployment/bc2-genesis/allocations.json \
  --classes docs/deployment/bc2-genesis/classes.json \
  --require-classes \
  --treasury-proof <operator-held proof file>
```

The treasury spendability proof JSON lives in operator custody, not in the
repo — the pair is public data (addresses and amounts the chain will make
public anyway); the proof is a verification input, not a build input.

`tests/unit/test_bc2_genesis_files.py` pins both sha256 digests, so any
edit to either file fails loudly rather than drifting.
