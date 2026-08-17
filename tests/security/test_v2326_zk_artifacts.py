"""V23-26 / V23-26a: the committed ZK artifacts must agree with each other.

Groth16 binds a proving key to one constraint system and a verification key to one proving
key. Filenames enforce none of that, and these artifacts are binary, so divergence is
invisible in review — which is how one ``verification_key.json`` came to be copied into four
directories serving circuits with 0, 1, 5 and 5 public signals.

These tests read the binary headers. They cannot prove two files belong together (identical
public-signal counts do not make two circuits the same circuit); they prove the cases where
they demonstrably do not.
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[2]
BUILD_TREE = REPO_ROOT / "apps/zk-circuits"
SERVICE_TREE = REPO_ROOT / "apps/coordinator-api/src/coordinator_api/contexts/zk_applications/zk-circuits"

sys.path.insert(0, str(REPO_ROOT / "apps/coordinator-api/src"))

from coordinator_api.contexts.zk_applications.services.zkey_header import (  # noqa: E402
    read_r1cs_header,
    read_zkey_contribution_count,
    read_zkey_header,
)


def _zkeys(tree: Path) -> list[Path]:
    return sorted(tree.glob("*.zkey"))


def _circuit_of(zkey: Path) -> str:
    """``receipt_simple_0001.zkey`` -> ``receipt_simple``."""
    stem, _, _ = zkey.stem.rpartition("_")
    return stem


@pytest.mark.parametrize("tree", [BUILD_TREE, SERVICE_TREE], ids=["build", "service"])
def test_every_proving_key_matches_the_constraint_system_beside_it(tree: Path) -> None:
    """A ``.zkey`` next to an ``.r1cs`` for a different circuit cannot prove anything.

    ``apps/zk-circuits/modular_ml_components_000*.zkey`` were keys for a 19-wire circuit
    sitting beside a 527-wire ``.r1cs`` — copied in from the service tree without the
    constraint system they belong to.
    """
    problems: list[str] = []

    for zkey in _zkeys(tree):
        r1cs = tree / f"{_circuit_of(zkey)}.r1cs"
        if not r1cs.exists():
            continue  # covered by the service's own availability checks, not here

        key = read_zkey_header(zkey)
        circuit = read_r1cs_header(r1cs)
        if key.n_vars != circuit.n_wires or key.n_public != circuit.n_public:
            problems.append(
                f"{zkey.name}: key is for nVars={key.n_vars}/nPublic={key.n_public}, "
                f"but {r1cs.name} is nWires={circuit.n_wires}/nPublic={circuit.n_public}"
            )

    assert not problems, "proving keys do not match the circuits they sit next to:\n  " + "\n  ".join(problems)


def test_no_verification_key_is_shared_between_circuits() -> None:
    """One vkey serving several circuits means it is wrong for all but at most one of them."""
    by_content: dict[str, list[str]] = {}
    for vkey in sorted(SERVICE_TREE.rglob("verification_key.json")):
        digest = json.dumps(json.loads(vkey.read_text()), sort_keys=True)
        by_content.setdefault(digest, []).append(str(vkey.relative_to(SERVICE_TREE)))

    shared = [paths for paths in by_content.values() if len(paths) > 1]

    assert not shared, (
        "the same verification key is installed for multiple circuits: "
        f"{shared}. Export one per proving key: "
        "snarkjs zkey export verificationkey <circuit>_0001.zkey verification_key.json"
    )


def test_the_service_offers_no_circuit_whose_keys_disagree() -> None:
    """The end-to-end property: a mismatched circuit must be withheld, not served.

    Verification being disabled by default (V23-24) is not what protects this — proving
    reads the verification key too.
    """
    from coordinator_api.contexts.zk_applications.services.zk_proofs import (  # type: ignore[import-not-found]
        _verification_key_mismatch,
        ZKProofService,
    )

    service = ZKProofService()

    for name, paths in service.available_circuits.items():
        mismatch = _verification_key_mismatch(paths["zkey_path"], paths["vkey_path"])
        assert mismatch is None, f"circuit '{name}' is being offered despite mismatched keys: {mismatch}"


def test_a_mismatched_pair_is_actually_detected(tmp_path: Path) -> None:
    """Guard the guard: a checker that never fires would pass every test above."""
    from coordinator_api.contexts.zk_applications.services.zk_proofs import (  # type: ignore[import-not-found]
        _verification_key_mismatch,
    )

    zkey = SERVICE_TREE / "receipt_simple_0001.zkey"
    real = json.loads((SERVICE_TREE / "receipt_simple_js" / "verification_key.json").read_text())

    wrong = tmp_path / "verification_key.json"
    wrong.write_text(json.dumps({**real, "nPublic": real["nPublic"] + 1}))

    assert _verification_key_mismatch(zkey, wrong) is not None

    right = tmp_path / "matching.json"
    right.write_text(json.dumps(real))

    assert _verification_key_mismatch(zkey, right) is None


def test_a_placeholder_verification_key_is_rejected(tmp_path: Path) -> None:
    """The ml_inference key that shipped for three releases: nPublic matches, points are fake."""
    from coordinator_api.contexts.zk_applications.services.zk_proofs import (  # type: ignore[import-not-found]
        _verification_key_mismatch,
    )

    zkey = SERVICE_TREE / "ml_inference_verification_0001.zkey"
    header = read_zkey_header(zkey)
    fake = {
        "protocol": "groth16",
        "curve": "bn128",
        "nPublic": header.n_public,
        "vk_alpha_1": ["0x1234", "0x5678", "0x0"],
        "vk_beta_2": [["0x1234", "0x5678"], ["0x1234", "0x5678"], ["0x0", "0x0"]],
        "vk_gamma_2": [["0x1234", "0x5678"], ["0x1234", "0x5678"], ["0x0", "0x0"]],
        "vk_delta_2": [["0x1234", "0x5678"], ["0x1234", "0x5678"], ["0x0", "0x0"]],
        "IC": [["0x1234", "0x5678", "0x0"]] * (header.n_public + 1),
    }
    path = tmp_path / "verification_key.json"
    path.write_text(json.dumps(fake))

    mismatch = _verification_key_mismatch(zkey, path)
    assert mismatch is not None
    assert "not a decimal bn128 field element" in mismatch


def test_shipped_contributed_keys_report_their_count() -> None:
    """Filename `_0001` is not evidence of a contribution (V23-91)."""
    by_name = {zkey.name: read_zkey_contribution_count(zkey) for zkey in _zkeys(SERVICE_TREE)}

    assert by_name["receipt_simple_0000.zkey"] == 0
    assert by_name["receipt_simple_0001.zkey"] == 1
    assert by_name["ml_inference_verification_0001.zkey"] == 1
    assert by_name["ml_training_verification_0001.zkey"] == 1
    # modular_ml_components_0001.zkey was the regression (zero contributions under a _0001
    # name). It has since been re-generated with a real phase-2 contribution (V23-91).
    assert by_name["modular_ml_components_0001.zkey"] == 1


def test_modular_ml_is_available_with_a_contributed_key() -> None:
    from coordinator_api.contexts.zk_applications.services.zk_proofs import ZKProofService

    service = ZKProofService()
    assert "modular_ml_components" in service.available_circuits
