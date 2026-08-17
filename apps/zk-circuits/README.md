# zk-circuits

## Status

**experimental** — and specifically, **the trusted setup is development-only. These circuits
must not be used to carry value in their current state.** See [Trusted setup](#trusted-setup).

## Description

Zero-knowledge proof circuits written in Circom for ML inference verification, training verification, and receipt validation. Includes Groth16 verifier contracts and benchmarking.

## Node Type

hub, island

## GPU Required

no

## Service

No systemd service file

## Core Service

no

## Source

Circom circuits with Python compilation scripts

---

## Trusted setup

Recorded in response to V23-25, which found this undocumented. The honest answer is short:
**there was no ceremony.** What follows is what the committed artifacts actually contain,
read out of the `.zkey` files rather than reconstructed from memory.

| | |
|---|---|
| Powers of tau | `pot12_*.ptau` — a locally generated 2^12 phase 1, not a public ceremony transcript |
| Phase-2 contributions | One or two per circuit |
| Contributor identities | The placeholder strings from `package.json`: **`"1st Contributor Name"`**, `"2nd Contributor Name"`, `"Test Contributor"`, `"AITBC Phase1"` |
| Published transcripts | None |
| Attestations | None |
| Toxic waste handling | Not recorded |

The contributor names are not a documentation gap — they are the literal defaults in the
`contribute-zkey` npm script below, which means whoever ran it did not edit the command.

### What that means

A Groth16 proving key is forgeable by anyone holding the phase-2 secret from its setup. With
one contribution, from an unidentified party, with no transcript, the correct assumption is
that **the setup secret still exists and any party who has it can forge proofs that verify.**

That is why:

- A proving key whose own MPC section reports zero contributions is never loaded,
  including a `*_0000.zkey` and a file merely *named* `_0001` (V23-24, V23-91).
- Verification is off unless `COORDINATOR_ENABLE_ZK_VERIFICATION=true` (V23-24/V23-32).
- The status endpoint reports `"trusted_setup": "development-only"`, not `"completed"`.

Making these circuits production-grade needs a real multi-party ceremony with published
transcripts and named participants — a prerequisite, not a follow-up.

## Where the artifacts live

There are two copies of this circuit tree, and they are **not** mirrors of each other
(V23-26):

| Tree | Role |
|---|---|
| `apps/zk-circuits/` (here) | Where circuits are authored and compiled. Holds the `.circom` sources and the npm scripts. |
| `apps/coordinator-api/src/coordinator_api/contexts/zk_applications/zk-circuits/` | **What `ZKProofService` actually loads at runtime.** |

They diverged, in both directions and undetectably, because these are binary files that no
review reads:

- `receipt_simple` is the *same circuit* in both trees (identical `.circom`, `.r1cs`,
  `.wasm`) with **different key material under identical filenames** — two independent
  `groth16 setup` runs. A proof made with one tree's key does not verify against the other's
  verification key.
- `modular_ml_components` is a *different circuit* in each tree (527 wires here, 19 there),
  and the `.zkey` files committed here were for the other tree's circuit. They have been
  removed: this tree currently has **no proving key for its own `modular_ml_components`**.
  Regenerate with `snarkjs groth16 setup` against the `.r1cs` here, then contribute.

`tests/security/test_v2326_zk_artifacts.py` reads the binary headers and fails on both
classes of mismatch, so the next divergence is caught in CI rather than in production.

To point the service at this tree instead of its in-package copy, set
`COORDINATOR_ZK_CIRCUITS_DIR`. Note that it will find no usable `modular_ml_components` key
here until one is generated.

### This tree's two ML circuits are unsatisfiable (V23-94)

`ml_training_verification.circom` and `modular_ml_components.circom` **here** cannot produce a
proof for any input at all. Both validate the learning rate as

```circom
component lt1 = LessThan(252);   lt1.in[0] <== learning_rate;  lt1.in[1] <== 1;  lt1.out === 1;
component gt0 = GreaterThan(252); gt0.in[0] <== learning_rate; gt0.in[1] <== 0;  gt0.out === 1;
```

which asks for an integer strictly between 0 and 1. Both files were compiled with circom 2.1.9
and driven at `learning_rate` = 0, 1, 2, 10000 and 1000000; every combination is rejected, ten
for ten. The comparison has to be against a fixed-point scale, not against the literal `1`.

The service tree's copies had the same bug in two other forms — one provable only at
`learning_rate = 0`, one with the check deleted outright — and have been fixed. **Take the
corrected sources from the coordinator-api tree**, not from here. The five `modular_*` variants
in this directory (`_clean`, `_simple`, `_v2`, `_working`, and the base file) were not audited.

## Rebuilding the circuits

There was no way to do this until V23-94: the `.r1cs`, `.wasm`, `.zkey` and
`verification_key.json` files were committed with no script, no Makefile target and no
documented command, so editing a `.circom` had no route into what the service loads.

```bash
CIRCOM=/path/to/circom bash scripts/zk/build-circuits.sh                   # compile + report
CIRCOM=/path/to/circom bash scripts/zk/build-circuits.sh --install         # + .r1cs/.sym/.wasm
CIRCOM=/path/to/circom bash scripts/zk/build-circuits.sh --install --ceremony  # + new keys
```

**circom 2.x is required and is not in this repository.** `node_modules/.bin/circom` is
0.5.46, which predates `pragma circom 2.0.0` and cannot compile a single circuit in either
tree; the script refuses it by version rather than failing obscurely. snarkjs comes from this
directory's `node_modules`, the same install `NODE_PATH` points at.

`--ceremony` replaces key material, so every proof made with the old proving key stops
verifying. It belongs with a circuit change and nowhere else. Without it the script installs
the constraint system and says plainly that the existing key is now for a different one.

The script also compiles the templates no `main` reaches, in a generated harness. circom only
compiles what is reachable from `main`, which is how `LossConstraint` sat in the tree containing
`diff_squared * (1 - diff_squared / tolerance_squared) === 0` — a division by a signal, which
circom refuses to compile. Nobody found out because nothing instantiated it.

## Installing snarkjs

`ZKProofService` proves and verifies by shelling out to `node`, and node resolves
`require()` from the directory of the script it is running — which for every one of those
call sites is a tempfile under `/tmp`. So the coordinator sets `NODE_PATH` to
**`apps/zk-circuits/node_modules`**, this directory's install, and nothing else on the box
will do: a global `npm install -g snarkjs` is not on the default require path either
(V23-91).

```bash
npm install
```

`node_modules/` is gitignored, so a deployment that has never run this proves nothing —
the service logs an error at startup saying so. `COORDINATOR_SNARKJS_NODE_PATH` overrides
the location if snarkjs lives elsewhere.

`npm install` used to fail here regardless: a script named `prepare` is an npm lifecycle
hook, so every install ran `powersoftau prepare` against a gitignored `.ptau` that is not
in the tree. The ceremony step is now `prepare-phase2`.

## Regenerating a verification key

Three of the four service-tree keys were missing or placeholders (V23-26a / V23-91). They
are exported from the proving key the service actually loads — the `_0001` in the
coordinator-api tree — and live next to that circuit's `.wasm`:

```bash
snarkjs zkey export verificationkey <circuit>_0001.zkey <circuit>_js/verification_key.json
```

All four service-tree circuits now carry one. `modular_ml_components_0001.zkey` was a
`groth16 setup` output under a `_0001` name — zero phase-2 contributions, and
`snarkjs zkey verify` rejected it with `Invalid alpha1` — so the circuit was withheld
rather than given a key exported from broken material. It has since been regenerated from
the `.r1cs` and `pot12_final.ptau` in the service tree, with a real `zkey contribute`.

Before trusting any regenerated key, ask snarkjs rather than the filename:

```bash
snarkjs zkey verify <circuit>.r1cs pot12_final.ptau <circuit>_0001.zkey   # -> "ZKey Ok!"
```

That checks the key against its constraint system *and* its ceremony, which is what the
`_0001` suffix only claims. The coordinator makes the same distinction at load time by
reading the contribution count out of the zkey's own MPC section.

`scripts/zk/build-circuits.sh --ceremony` runs that command itself after every contribution,
for the same reason.

## Fixed-point inputs

The two ML training circuits take integers scaled by 10^6 (V23-94). A prime field has no
fractions, and the learning rate and the parameters have to carry the *same* scale for
`param_next = param - learning_rate * gradient` to be the exact update with no division:

| Input | Meaning | Range |
|---|---|---|
| `learning_rate` | millionths — `10000` is 0.01 | `0 < lr < 1000000`, enforced |
| `initial_parameters` | millionths — `10000000` is 10.0 | `0 <= v < 2^40`, enforced per epoch |
| `gradients` (modular only) | plain integers, one row per epoch | `0 <= v < 2^20`, enforced |

Gradients are deliberately unscaled: `learning_rate * gradient` then lands at 10^6 and matches
the parameters. Scaling them too would put the product at 10^12.

`GET /v1/ml-zk/circuits` publishes the scale and these ranges, because a caller cannot submit
anything provable without them.

---
*Last updated: 2026-08-17*
