#!/bin/bash
# Rebuild the ZK circuits the coordinator loads at runtime.
#
# Added in V23-94, because there was no way to rebuild them. The repository committed
# .r1cs, .wasm, .zkey and verification_key.json files with no script, no Makefile target and
# no documented command that produces them, so a .circom edit had no route into the artifacts
# the service actually loads. Two circuits had range checks that did the opposite of what
# their comments said, and fixing the source was not enough to fix anything.
#
# Usage:
#   bash scripts/zk/build-circuits.sh                    # compile + report, install nothing
#   bash scripts/zk/build-circuits.sh --install          # compile and install .r1cs/.sym/.wasm
#   bash scripts/zk/build-circuits.sh --install --ceremony  # also redo phase 2 and the vkey
#
# --ceremony REPLACES KEY MATERIAL. Every proof made with the old proving key stops verifying
# against the new verification key, so it belongs with a circuit change and nowhere else.
#
# circom 2.x is required and is NOT in this repository. `apps/zk-circuits/node_modules/.bin/
# circom` is 0.5.46, which predates `pragma circom 2.0.0` and cannot compile any circuit here.
# Install a 2.x release and point CIRCOM at it:
#
#   CIRCOM=/path/to/circom bash scripts/zk/build-circuits.sh
#
# snarkjs comes from apps/zk-circuits/node_modules (npm install there) — the same install
# NODE_PATH points at, so the build and the service use one snarkjs.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CIRCUITS_DIR="${CIRCUITS_DIR:-$REPO_ROOT/apps/coordinator-api/src/coordinator_api/contexts/zk_applications/zk-circuits}"
NODE_MODULES="${NODE_MODULES:-$REPO_ROOT/apps/zk-circuits/node_modules}"
SNARKJS="${SNARKJS:-$NODE_MODULES/.bin/snarkjs}"
PTAU="${PTAU:-$CIRCUITS_DIR/pot12_final.ptau}"

# All three ML circuits. receipt_simple is also built the same way, but its artifacts
# are not changed by this fix and are left out to avoid invalidating its current key.
CIRCUITS=(ml_inference_verification ml_training_verification modular_ml_components)

# Library templates that no `main` instantiates. circom only compiles what is reachable from
# main, so an uninstantiated template is never checked at all -- which is how
# `LossConstraint` sat in the tree for three releases containing a division by a signal, an
# expression circom refuses to compile (V23-94). Each entry is compiled in a generated
# harness so that cannot happen again.
HARNESSES=("modular_ml_components:LossConstraint(32)")

# pot12_final.ptau is a 2^12 phase 1, so it supports this many constraints.
PTAU_CAPACITY=4096

INSTALL=no
CEREMONY=no
for arg in "$@"; do
    case "$arg" in
        --install) INSTALL=yes ;;
        --ceremony) CEREMONY=yes ;;
        --default) ;;
        *) echo "unknown argument: $arg" >&2; exit 2 ;;
    esac
done

if [ "$CEREMONY" = yes ] && [ "$INSTALL" != yes ]; then
    echo "--ceremony without --install would generate keys and throw them away" >&2
    exit 2
fi

# ---------------------------------------------------------------------------------------------
# Toolchain
# ---------------------------------------------------------------------------------------------

CIRCOM="${CIRCOM:-$(command -v circom || true)}"

if [ -z "$CIRCOM" ]; then
    echo "circom not found. Install a 2.x release and set CIRCOM=/path/to/circom." >&2
    echo "The circom in $NODE_MODULES/.bin is 0.5.46 and cannot compile pragma circom 2.0.0." >&2
    exit 1
fi

CIRCOM_VERSION="$("$CIRCOM" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
case "$CIRCOM_VERSION" in
    2.*) ;;
    *)
        echo "circom $CIRCOM_VERSION at $CIRCOM cannot compile these circuits." >&2
        echo "They declare pragma circom 2.0.0; a 2.x release is required." >&2
        exit 1
        ;;
esac

if [ ! -x "$SNARKJS" ]; then
    echo "snarkjs not found at $SNARKJS. Run: (cd apps/zk-circuits && npm install)" >&2
    [ "$CEREMONY" = yes ] && exit 1
fi

BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

echo "circom      $CIRCOM_VERSION ($CIRCOM)"
echo "circuits    $CIRCUITS_DIR"
echo "build       $BUILD_DIR"
echo

# ---------------------------------------------------------------------------------------------
# Compile
# ---------------------------------------------------------------------------------------------

for circuit in "${CIRCUITS[@]}"; do
    source_file="$CIRCUITS_DIR/$circuit.circom"
    [ -f "$source_file" ] || { echo "no such circuit: $source_file" >&2; exit 1; }

    echo "=== $circuit ==="
    # -l resolves `include "circomlib/circuits/..."`. The sources used to include
    # "node_modules/circomlib/..." relative to the compiler's working directory, which only
    # resolved when someone happened to run circom from apps/zk-circuits (V23-94).
    # --c emits the C++ witness generator. Only modular_ml_components has one committed, and
    # it is installed below only where one already exists -- but it is built for both, so a
    # committed generator can never quietly belong to an older constraint system.
    output="$("$CIRCOM" "$source_file" --wasm --r1cs --sym --c -o "$BUILD_DIR" -l "$NODE_MODULES")"
    echo "$output" | grep -E "constraints|wires|labels|public|private" || true

    constraints="$(echo "$output" | grep -oE 'non-linear constraints: [0-9]+' | grep -oE '[0-9]+$')"
    if [ -n "$constraints" ] && [ "$constraints" -gt "$PTAU_CAPACITY" ]; then
        echo "  $constraints constraints exceeds $PTAU_CAPACITY, the capacity of $(basename "$PTAU")." >&2
        echo "  A larger phase 1 is needed before this circuit can have a proving key." >&2
        exit 1
    fi
    echo "  fits $(basename "$PTAU") ($constraints of $PTAU_CAPACITY constraints)"
    echo
done

# ---------------------------------------------------------------------------------------------
# Compile the templates no main reaches
# ---------------------------------------------------------------------------------------------

for harness in "${HARNESSES[@]}"; do
    library="${harness%%:*}"
    instantiation="${harness#*:}"
    echo "=== $library :: $instantiation ==="

    # A file with its own `main` cannot be included, so strip it.
    sed '/^component main/d' "$CIRCUITS_DIR/$library.circom" > "$BUILD_DIR/_lib_$library.circom"
    {
        echo 'pragma circom 2.0.0;'
        echo "include \"_lib_$library.circom\";"
        echo "component main = $instantiation;"
    } > "$BUILD_DIR/_harness.circom"

    "$CIRCOM" "$BUILD_DIR/_harness.circom" --r1cs -o "$BUILD_DIR" \
        -l "$NODE_MODULES" -l "$BUILD_DIR" | grep -E "constraints" || true
    echo "  compiles"
    echo
done

if [ "$INSTALL" != yes ]; then
    echo "Compiled only. Pass --install to copy the artifacts into $CIRCUITS_DIR."
    exit 0
fi

# ---------------------------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------------------------

for circuit in "${CIRCUITS[@]}"; do
    echo "=== installing $circuit ==="
    cp -f "$BUILD_DIR/$circuit.r1cs" "$BUILD_DIR/$circuit.sym" "$CIRCUITS_DIR/"
    mkdir -p "$CIRCUITS_DIR/${circuit}_js"
    cp -f "$BUILD_DIR/${circuit}_js/$circuit.wasm" "$CIRCUITS_DIR/${circuit}_js/"

    # generate_witness.js and witness_calculator.js are deliberately not overwritten. The
    # committed witness_calculator.js carries a local patch (`qualify_input`, which flattens
    # nested inputs) that a fresh circom emit would drop, and it drives the current wasm.

    if [ -d "$CIRCUITS_DIR/${circuit}_cpp" ]; then
        cp -f "$BUILD_DIR/${circuit}_cpp/." "$CIRCUITS_DIR/${circuit}_cpp/" -r
        echo "  C++ witness generator refreshed"
    fi

    if [ "$CEREMONY" != yes ]; then
        echo "  .r1cs/.sym/.wasm installed; keys untouched (no --ceremony)"
        echo "  The existing ${circuit}_0001.zkey is now for a DIFFERENT constraint system."
        echo "  Run with --ceremony, or proving will fail against it."
        continue
    fi

    "$SNARKJS" groth16 setup "$CIRCUITS_DIR/$circuit.r1cs" "$PTAU" "$CIRCUITS_DIR/${circuit}_0000.zkey"
    "$SNARKJS" zkey contribute "$CIRCUITS_DIR/${circuit}_0000.zkey" "$CIRCUITS_DIR/${circuit}_0001.zkey" \
        --name="${CONTRIBUTOR:-$(git config user.name 2>/dev/null || echo unnamed) rebuilding $circuit}" \
        -e="$(head -c 64 /dev/urandom | base64 -w0)"
    "$SNARKJS" zkey export verificationkey "$CIRCUITS_DIR/${circuit}_0001.zkey" \
        "$CIRCUITS_DIR/${circuit}_js/verification_key.json"

    # The filename is a claim; these two commands are the fact. `_resolve_proving_key` reads
    # the contribution count out of the zkey's own MPC section for the same reason (V23-91).
    "$SNARKJS" zkey verify "$CIRCUITS_DIR/$circuit.r1cs" "$PTAU" "$CIRCUITS_DIR/${circuit}_0001.zkey"
    echo "  key material replaced"
done

echo
echo "Done. This is a single-contributor local ceremony with unpublished entropy — a"
echo "development setup, not a trusted one. See apps/zk-circuits/README.md."
echo "Verify end to end with:"
echo "  venv/bin/pytest apps/coordinator-api/tests/test_v2394_zk_circuit_constraints.py"
