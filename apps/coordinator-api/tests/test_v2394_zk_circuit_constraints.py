"""V23-94: the ML circuits must refuse the learning rates their comments claim to refuse.

Both ML training circuits carried a range check that did the opposite of what it said.

`ml_training_verification.circom` asserted

    learning_rate * (1 - learning_rate) === learning_rate;  // Ensures 0 < lr < 1

which rearranges to ``learning_rate^2 === 0``. A prime field has no nilpotents, so the only
satisfying value was ``learning_rate = 0`` — the one value the comment excludes, and the one
that makes every epoch a no-op. The circuit proved that training ran and changed nothing,
while asserting ``training_complete = 1``.

`modular_ml_components.circom` had no check at all. Its `LearningRateValidation` was an empty
template under a comment saying validation was "handled externally"; nothing validated it
externally, because `POST /v1/ml-zk/prove/modular` passes `inputs` to the witness generator
unchanged. Its gradients were hardcoded to 1 inside the circuit, so the proof said nothing
about anyone's gradients.

These tests drive the service the API uses, so a regression in the circuit, the artifacts or
the ceremony all show up the same way: a proof that should not exist, or one that does not
verify. Values are fixed point at 1e6 — a learning rate of 0.01 is 10000.
"""

from __future__ import annotations

import pytest

from coordinator_api.contexts.zk_applications.services import zk_proofs as zk_module
from coordinator_api.contexts.zk_applications.services.zk_proofs import ZKProofService, snarkjs_available

pytestmark = pytest.mark.skipif(not snarkjs_available(), reason="snarkjs is not installed under apps/zk-circuits")

#: Both circuits are compiled with LR_SCALE = 1e6, so this is a learning rate of exactly 1.0.
LR_SCALE = 1000000

#: 0.01, the kind of value a caller actually wants to prove.
GOOD_LR = 10000

#: Four parameters at 10.0, 20.0, 30.0, 40.0.
PARAMS = ["10000000", "20000000", "30000000", "40000000"]

#: bn128 modulus minus one — how a caller would express -1 to a field-element input.
NEGATIVE_ONE = "21888242871839275222246405745257275088548364400416034343698204186575808495616"

UNIT_GRADIENTS = [["1", "1", "1", "1"], ["1", "1", "1", "1"], ["1", "1", "1", "1"]]


@pytest.fixture
def service(monkeypatch):
    monkeypatch.setattr(zk_module, "ENABLE_ZK_VERIFICATION", True)
    return ZKProofService()


def training_inputs(learning_rate, parameters=None) -> dict:
    return {"initial_parameters": parameters or PARAMS, "learning_rate": str(learning_rate)}


def modular_inputs(learning_rate, parameters=None, gradients=None) -> dict:
    return {
        "initial_parameters": parameters or PARAMS,
        "learning_rate": str(learning_rate),
        "gradients": gradients or UNIT_GRADIENTS,
    }


class TestTheTrainingCircuitEnforcesItsRange:
    async def test_a_real_learning_rate_proves_and_verifies(self, service):
        proof = await service.generate_proof("ml_training_verification", training_inputs(GOOD_LR))
        assert proof is not None, "0.01 is a valid learning rate and must be provable"

        result = await service.verify_proof(proof["proof"], proof["public_signals"], circuit_name="ml_training_verification")
        assert result["verified"] is True

    async def test_the_public_signals_show_the_parameters_actually_moved(self, service):
        """The old circuit's only provable input left every parameter untouched.

        Three epochs at 0.01 with a unit gradient takes 10.0 to 9.97. Asserting the arithmetic
        rather than just `training_complete` is the point: `training_complete <== 1` held for
        the no-op proof too.
        """
        proof = await service.generate_proof("ml_training_verification", training_inputs(GOOD_LR))
        assert proof is not None

        expected = [str(int(p) - 3 * GOOD_LR) for p in PARAMS]
        assert proof["public_signals"][:4] == expected
        assert proof["public_signals"][:4] != PARAMS, "a no-op update must not be provable"
        assert proof["public_signals"][4] == "1"

    async def test_a_zero_learning_rate_is_refused(self, service):
        """The one value the old constraint permitted."""
        assert await service.generate_proof("ml_training_verification", training_inputs(0)) is None

    async def test_a_learning_rate_of_exactly_one_is_refused(self, service):
        assert await service.generate_proof("ml_training_verification", training_inputs(LR_SCALE)) is None

    async def test_a_learning_rate_above_one_is_refused(self, service):
        assert await service.generate_proof("ml_training_verification", training_inputs(5 * LR_SCALE)) is None

    async def test_a_learning_rate_just_below_one_is_accepted(self, service):
        """The bound is the scale, not an arbitrary small number."""
        assert await service.generate_proof("ml_training_verification", training_inputs(LR_SCALE - 1)) is not None

    async def test_a_negative_learning_rate_is_refused(self, service):
        """Expressed as a field element, so `Num2Bits` is what has to catch it."""
        assert await service.generate_proof("ml_training_verification", training_inputs(NEGATIVE_ONE)) is None

    async def test_an_update_that_drives_a_parameter_below_zero_is_refused(self, service):
        """Field subtraction wraps, so this used to prove a parameter near the modulus."""
        inputs = training_inputs(GOOD_LR, parameters=["5000", *PARAMS[1:]])
        assert await service.generate_proof("ml_training_verification", inputs) is None


class TestTheModularCircuitValidatesAtAll:
    async def test_a_real_learning_rate_proves_and_verifies(self, service):
        proof = await service.generate_proof("modular_ml_components", modular_inputs(GOOD_LR))
        assert proof is not None

        result = await service.verify_proof(proof["proof"], proof["public_signals"], circuit_name="modular_ml_components")
        assert result["verified"] is True

    async def test_a_zero_learning_rate_is_refused(self, service):
        """`LearningRateValidation` was an empty template; this is what it was supposed to do."""
        assert await service.generate_proof("modular_ml_components", modular_inputs(0)) is None

    async def test_a_learning_rate_of_exactly_one_is_refused(self, service):
        assert await service.generate_proof("modular_ml_components", modular_inputs(LR_SCALE)) is None

    async def test_a_negative_learning_rate_is_refused(self, service):
        assert await service.generate_proof("modular_ml_components", modular_inputs(NEGATIVE_ONE)) is None

    async def test_gradients_are_an_input_and_omitting_them_fails(self, service):
        """They were hardcoded to 1 inside the circuit.

        If someone reintroduces the constant, this call starts succeeding: the witness
        generator only rejects a missing input for a signal the circuit actually declares.
        """
        inputs = modular_inputs(GOOD_LR)
        del inputs["gradients"]

        assert await service.generate_proof("modular_ml_components", inputs) is None

    async def test_the_gradients_reach_the_arithmetic(self, service):
        """Two different gradient sets must give two different final parameters."""
        doubled = [["2", "2", "2", "2"]] * 3

        unit_proof = await service.generate_proof("modular_ml_components", modular_inputs(GOOD_LR))
        doubled_proof = await service.generate_proof("modular_ml_components", modular_inputs(GOOD_LR, gradients=doubled))
        assert unit_proof is not None and doubled_proof is not None

        assert unit_proof["public_signals"][:4] == [str(int(p) - 3 * GOOD_LR) for p in PARAMS]
        assert doubled_proof["public_signals"][:4] == [str(int(p) - 6 * GOOD_LR) for p in PARAMS]

    async def test_an_out_of_range_gradient_is_refused(self, service):
        """Unbounded, a large gradient puts the product — and the parameter — anywhere."""
        oversized = [["1048576", "1", "1", "1"], *UNIT_GRADIENTS[1:]]

        assert await service.generate_proof("modular_ml_components", modular_inputs(GOOD_LR, gradients=oversized)) is None


def inference_inputs(x: str, w: str, b: str, expected: str) -> dict[str, str]:
    return {"x": x, "w": w, "b": b, "expected": expected}


class TestTheInferenceCircuitVerifiesCorrectness:
    """V23-94 follow-up: ``ml_inference_verification`` had ``verified <== 1 - diff*diff``,
    which is 1 at diff == 0 but is not enforced by an ``===`` constraint and accepts many
    non-zero diffs in the field. It was replaced with ``IsZero``.

    A correct proof with ``expected == x*w+b`` must have public signal ``verified == 1``;
    an incorrect proof must have ``verified == 0``.  The verifier must decode the public
    success signal, not just check Groth16 validity.
    """

    async def test_a_correct_inference_proves_and_is_computationally_correct(self, service):
        proof = await service.generate_proof("ml_inference_verification", inference_inputs("1", "2", "3", "5"))
        assert proof is not None, "correct inference (1*2+3 == 5) must be provable"
        assert proof["public_signals"] == ["1"]

        result = await service.verify_proof(proof["proof"], proof["public_signals"], circuit_name="ml_inference_verification")
        assert result["verified"] is True
        assert result["computation_correct"] is True

    async def test_a_wrong_inference_is_not_computationally_correct(self, service):
        proof = await service.generate_proof("ml_inference_verification", inference_inputs("1", "2", "3", "10"))
        assert proof is not None, "the circuit must still be able to compute an incorrect result"
        assert proof["public_signals"] == ["0"], "mismatched expected output must set verified=0"

        result = await service.verify_proof(proof["proof"], proof["public_signals"], circuit_name="ml_inference_verification")
        assert result["verified"] is True, "Groth16 proof is valid even though the statement is false"
        assert result["computation_correct"] is False, "verifier must read the public success signal"

    async def test_tampering_with_public_signals_breaks_verification(self, service):
        proof = await service.generate_proof("ml_inference_verification", inference_inputs("1", "2", "3", "10"))
        assert proof is not None

        # A prover cannot flip the success bit and still have a valid Groth16 proof.
        result = await service.verify_proof(proof["proof"], ["1"], circuit_name="ml_inference_verification")
        assert result["verified"] is False
        assert result["computation_correct"] is False
