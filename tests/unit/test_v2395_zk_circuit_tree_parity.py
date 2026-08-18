"""The two ZK circuit trees, and the drift between them that V23-94 fixed only half of.

`ml_training_verification.circom` and `modular_ml_components.circom` exist **twice**:

    apps/coordinator-api/src/coordinator_api/contexts/zk_applications/zk-circuits/  (loaded at runtime)
    apps/zk-circuits/                                                              (the build tree)

V23-94 fixed the learning-rate constraints in the first one, because that is the copy
`ZKProofService` resolves. The second copy kept the broken sources for a further release: a
`LessThan(252)` against the literal `1` and a `GreaterThan(252)` against the literal `0`, which
together demand an integer strictly between 0 and 1 and so are satisfied by nothing at all. Two
copies of one circuit, one fixed and one not, and nothing in the repository compared them.

That is the gap these tests close. The sources are now byte-identical and so are the compiled
artifacts, which is a stronger statement than "both look fixed": identical sources through one
compiler give identical `.r1cs`, so a diff in the artifacts means somebody edited a circuit and
shipped without rebuilding.

The key-material tests read the binary headers rather than checking that files exist, because the
build tree's failure mode was keys that existed and were simply for a different circuit:
`circuit_0001.zkey` is a 741-variable key -- the shape of `receipt_simple` -- sitting in a
directory whose `modular_ml_components.r1cs` has 766 wires. A `.zkey` records the variable count
of the constraint system it was generated against, so the mismatch is stated in the files
themselves; the filename was the only thing that ever claimed otherwise.

They use `coordinator_api...services.zkey_header`, the parser the service already ships, rather
than a second copy of the format. That module exists because of the same class of bug one layer
over: `receipt_simple` carried a proving key for a 0-public-signal circuit next to a verification
key for a 1-public-signal one (V23-26a), and `_0001` turned out to be a name rather than a
contribution count (V23-91). Reusing it means a format fix lands in one place.

The pattern tests read every `.circom` in the repository with comments stripped. `LossConstraint`
sat in the tree for three releases containing a division by a signal -- an expression circom
refuses to compile -- and survived because no `main` instantiated it and **circom compiles
nothing a main does not reach**. Comments are stripped because the fixed circuits quote the old
broken constraints in their docblocks, on purpose, and a guard that cannot tell a warning from
the thing it warns about would force those explanations back out of the tree.

Still open, deliberately out of scope here: `apps/zk-circuits/` also holds `receipt_simple_clean.circom`
and six `test*.circom` files with committed `.wtns` output -- a committed scratchpad wanting a
triage of its own (flagged in V23-94).
"""

import json
import re
from pathlib import Path

import pytest
from coordinator_api.contexts.zk_applications.services.zkey_header import (
    read_r1cs_header,
    read_zkey_contribution_count,
    read_zkey_header,
)

REPO = Path(__file__).resolve().parents[2]
SERVICE_TREE = REPO / "apps" / "coordinator-api" / "src" / "coordinator_api" / "contexts" / "zk_applications" / "zk-circuits"
BUILD_TREE = REPO / "apps" / "zk-circuits"

# The circuits that exist in both trees. These are the two that drifted.
SHARED_CIRCUITS = ("ml_training_verification", "modular_ml_components")

TREES = {"service": SERVICE_TREE, "build": BUILD_TREE}

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"//[^\n]*")


def _circom_sources() -> list[Path]:
    """Every circuit source in the repository, excluding vendored circomlib."""
    return sorted(p for p in REPO.glob("apps/**/*.circom") if "node_modules" not in p.parts)


def _code_only(source: Path) -> str:
    """The source with comments removed, so a guard cannot fire on its own documentation.

    Block comments go first: the fixed circuits quote the old broken constraints inside
    `/* ... */` docblocks, and those quotes contain `//` line comments of their own.
    """
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", source.read_text()))


# ---------------------------------------------------------------------------------------------
# The two trees hold the same circuits
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("circuit", SHARED_CIRCUITS)
def test_circuit_sources_are_identical_in_both_trees(circuit: str) -> None:
    """The drift itself: one tree fixed, one not, for a release.

    Byte equality rather than a semantic comparison because there is no reason for these to
    differ at all. Two copies of a circuit that are allowed to differ *somewhere* is how one
    of them ends up being the broken one nobody is looking at.
    """
    service = (SERVICE_TREE / f"{circuit}.circom").read_bytes()
    build = (BUILD_TREE / f"{circuit}.circom").read_bytes()
    assert service == build, (
        f"{circuit}.circom differs between the two trees. The coordinator loads the copy under "
        f"apps/coordinator-api/...; apps/zk-circuits/ is the build tree. Whichever you edited, "
        f"copy it to the other and rebuild with scripts/zk/build-circuits.sh."
    )


@pytest.mark.parametrize("circuit", SHARED_CIRCUITS)
def test_compiled_artifacts_are_identical_in_both_trees(circuit: str) -> None:
    """Identical sources through one compiler produce identical artifacts.

    So a difference here does not mean the trees disagree about the circuit -- it means an
    artifact was not rebuilt after its source changed, which is the state that made a .circom
    edit unfalsifiable in the first place (V23-94).
    """
    for artifact in (f"{circuit}.r1cs", f"{circuit}.sym", f"{circuit}_js/{circuit}.wasm"):
        service = SERVICE_TREE / artifact
        build = BUILD_TREE / artifact
        assert service.exists(), f"missing {service}"
        assert build.exists(), f"missing {build}"
        assert service.read_bytes() == build.read_bytes(), (
            f"{artifact} differs between the trees while the sources match -- one side was not "
            f"rebuilt. Run scripts/zk/build-circuits.sh --install for that tree."
        )


# ---------------------------------------------------------------------------------------------
# Key material belongs to the circuit it sits next to
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("tree", sorted(TREES))
@pytest.mark.parametrize("circuit", SHARED_CIRCUITS)
def test_proving_key_matches_the_constraint_system_beside_it(tree: str, circuit: str) -> None:
    """The build tree shipped keys for a different circuit, and the wire count says so.

    A .zkey records the variable count of the system it was generated against. When that
    disagrees with the .r1cs next to it, the key cannot prove that circuit -- and nothing but
    the filename ever claimed it could. `snarkjs zkey verify` is the full check; this is the
    part of it that needs no toolchain, so it runs in the ordinary suite.
    """
    directory = TREES[tree]
    r1cs = read_r1cs_header(directory / f"{circuit}.r1cs")
    zkey = read_zkey_header(directory / f"{circuit}_0001.zkey")

    assert zkey.is_groth16, f"{tree} tree: {circuit}_0001.zkey is not a groth16 key"
    assert zkey.n_vars == r1cs.n_wires, (
        f"{tree} tree: {circuit}_0001.zkey was generated for {zkey.n_vars} variables but "
        f"{circuit}.r1cs has {r1cs.n_wires} wires. The key is for a different circuit. "
        f"Re-run the ceremony: scripts/zk/build-circuits.sh --install --ceremony."
    )
    assert zkey.n_public == r1cs.n_public, (
        f"{tree} tree: {circuit}_0001.zkey declares {zkey.n_public} public signals, {circuit}.r1cs has {r1cs.n_public}."
    )


@pytest.mark.parametrize("tree", sorted(TREES))
@pytest.mark.parametrize("circuit", SHARED_CIRCUITS)
def test_proving_key_carries_a_real_contribution(tree: str, circuit: str) -> None:
    """`_0001` is a filename. The contribution count is what the artifact says about itself.

    `modular_ml_components_0001.zkey` was once a key straight out of `groth16 setup`, carrying
    no phase-2 contribution at all, and it was accepted for three releases because its name
    ended in `_0001` (V23-91). The build tree had no key for this circuit under any name until
    now, so this is the first run where the assertion means anything there.
    """
    count = read_zkey_contribution_count(TREES[tree] / f"{circuit}_0001.zkey")
    assert count >= 1, (
        f"{tree} tree: {circuit}_0001.zkey carries {count} contributions -- it is raw "
        f"`groth16 setup` output with a misleading name, and its toxic waste was never discarded."
    )


@pytest.mark.parametrize("tree", sorted(TREES))
@pytest.mark.parametrize("circuit", SHARED_CIRCUITS)
def test_verification_key_is_exported_from_that_proving_key(tree: str, circuit: str) -> None:
    """A vkey for the wrong circuit verifies nothing, and looks fine on disk."""
    vkey = json.loads((TREES[tree] / f"{circuit}_js" / "verification_key.json").read_text())
    zkey = read_zkey_header(TREES[tree] / f"{circuit}_0001.zkey")

    assert vkey["protocol"] == "groth16", f"{tree}/{circuit}: unexpected protocol {vkey['protocol']!r}"
    assert vkey["nPublic"] == zkey.n_public, (
        f"{tree} tree: {circuit} verification_key.json declares {vkey['nPublic']} public signals "
        f"but its proving key has {zkey.n_public}. Re-export it with "
        f"`snarkjs zkey export verificationkey`."
    )
    # IC is one point per public signal plus one.
    assert len(vkey["IC"]) == vkey["nPublic"] + 1, f"{tree}/{circuit}: IC length disagrees with nPublic"


def test_both_trees_agree_on_the_public_signal_layout() -> None:
    """Same circuit, same published interface -- whichever key a caller happens to hold."""
    for circuit in SHARED_CIRCUITS:
        layouts = {
            tree: json.loads((directory / f"{circuit}_js" / "verification_key.json").read_text())["nPublic"]
            for tree, directory in TREES.items()
        }
        assert len(set(layouts.values())) == 1, f"{circuit}: trees disagree on public signals: {layouts}"


# ---------------------------------------------------------------------------------------------
# The constraint bugs, as patterns, across every circuit in the repository
# ---------------------------------------------------------------------------------------------


def test_no_unaudited_variant_of_a_shared_circuit_reappears() -> None:
    """`modular_ml_components_{clean,simple,v2,working}.circom` -- four dead copies, all broken.

    Every one had a `LearningRateValidation` template containing no constraints at all, and
    every one carried `LossConstraint`'s division by a signal. Nothing in the repository
    referenced any of them, and `_clean` and `_working` were byte-identical to each other. They
    are deleted; a circuit named `_working` that does not constrain its only scalar input is the
    most expensive filename in the tree.
    """
    variants = sorted(
        p.name
        for base in SHARED_CIRCUITS
        for p in BUILD_TREE.glob(f"{base}_*.circom")
        # A trailing `_js` is the generated witness directory, not a source variant.
        if p.stem != base
    )
    assert variants == [], (
        f"unaudited near-copies of a shared circuit are back: {variants}. A variant is a circuit "
        f"nothing compiles and nobody checks; put the change in the canonical source instead."
    )


def test_no_circuit_range_checks_against_a_literal_zero_or_one() -> None:
    """The build-tree bug: `lr < 1` and `lr > 0` over the integers is satisfied by nothing.

    A field has no fractions, so a fixed-point circuit compares against its *scale* -- the
    fixed circuits use `LessThan(LR_BITS)` against `LR_SCALE`, with `IsZero()` for the lower
    bound. A comparator bounded by a bare `0` or `1` is either unsatisfiable or a booleanity
    check written the long way round.
    """
    offenders = []
    for source in _circom_sources():
        code = _code_only(source)
        # component <name> = LessThan(...) / GreaterThan(...), then <name>.in[1] <== <literal>
        comparators = set(re.findall(r"component\s+(\w+)\s*=\s*(?:Less|Greater)Than\s*\(", code))
        for name in sorted(comparators):
            bound = re.search(rf"\b{re.escape(name)}\.in\[1\]\s*<==\s*([^;]+);", code)
            if bound and bound.group(1).strip() in {"0", "1"}:
                offenders.append(f"{source.relative_to(REPO)}: {name} bounded by {bound.group(1).strip()}")

    assert offenders == [], "comparator bounded by a literal 0 or 1:\n  " + "\n  ".join(offenders)


def test_no_circuit_asserts_a_nilpotent_product() -> None:
    """`lr * (1 - lr) === lr` rearranges to `lr^2 === 0`, so it admits only lr = 0.

    A prime field has no nilpotents. This was written as `// Ensures 0 < lr < 1` and enforced
    exactly the one value that comment excludes, which made every training epoch a no-op while
    the circuit still asserted `training_complete = 1`.

    `x * (1 - x) === 0` is deliberately not flagged: that one is the standard booleanity
    constraint and is correct.
    """
    offenders = []
    for source in _circom_sources():
        for match in re.finditer(r"(\w+)\s*\*\s*\(\s*1\s*-\s*(\w+)\s*\)\s*===\s*(\w+)\s*;", _code_only(source)):
            left, inner, result = match.groups()
            if left == inner == result:
                offenders.append(f"{source.relative_to(REPO)}: {left} * (1 - {inner}) === {result}")

    assert offenders == [], "constraint reduces to x^2 === 0, satisfied only by x = 0:\n  " + "\n  ".join(offenders)


def test_no_circuit_divides_by_a_signal() -> None:
    """Division by a signal is not a quadratic constraint, so circom refuses to compile it.

    `LossConstraint` contained `diff_squared * (1 - diff_squared / tolerance_squared) === 0` and
    reached three releases because no `main` instantiated it. Dividing by a compile-time
    constant is fine -- it is multiplication by a precomputed inverse -- so this looks at what
    the denominator is: template parameters are SCREAMING_CASE by convention here, signals are
    lowercase.
    """
    offenders = []
    for source in _circom_sources():
        for line in _code_only(source).splitlines():
            if not any(op in line for op in ("<==", "===", "==>")):
                continue
            for denominator in re.findall(r"/\s*([A-Za-z_]\w*)", line):
                if not denominator.isupper():
                    offenders.append(f"{source.relative_to(REPO)}: divides by signal {denominator!r} -- {line.strip()}")

    assert offenders == [], "division by a signal will not compile:\n  " + "\n  ".join(offenders)
