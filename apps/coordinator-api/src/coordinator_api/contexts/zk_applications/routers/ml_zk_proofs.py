import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from aitbc.rate_limiting import rate_limit

from ..services.zk_proofs import ZKProofService

router = APIRouter(prefix="/ml-zk", tags=["ml-zk"])

zk_service = ZKProofService()

#: Answered to a caller whose inputs the circuit refused. It names the constraints because a
#: caller cannot otherwise tell an out-of-range learning rate from a broken coordinator: until
#: V23-94 the training circuit accepted only ``learning_rate = 0`` and the modular one accepted
#: anything at all, so a refusal was nearly unreachable and every one was reported as a 500.
UNPROVABLE_INPUTS = (
    "The circuit refused these inputs. Values are fixed point scaled by 1e6, the learning rate "
    "must satisfy 0 < learning_rate < 1e6, and parameters and gradients are range-bounded. "
    "GET /v1/ml-zk/circuits publishes the scale and every enforced range."
)


class MLProofRequest(BaseModel):
    """Body for both ML prove endpoints.

    This was ``dict[str, Any]``, read with ``proof_request["inputs"]`` and
    ``proof_request["private_inputs"]``, so a caller who omitted either got a ``KeyError``
    reported as ``500 Internal server error``. ``private_inputs`` was mandatory here even
    though ``generate_proof`` defaults it to ``None`` and does nothing with a falsy value
    (V23-94).
    """

    inputs: dict[str, Any]
    private_inputs: dict[str, Any] | None = None


class MLVerifyRequest(BaseModel):
    """Body for both ML verify endpoints.

    ``verification_key`` is absent by design: the key is chosen server-side from the circuit,
    because a verifier that accepts the key from the party being verified checks nothing.
    """

    proof: dict[str, Any]
    public_signals: list[str]


async def _prove(circuit_name: str, proof_request: MLProofRequest) -> dict[str, Any]:
    """Prove, or say whose fault it is.

    ``generate_proof`` answers ``None`` for two unrelated reasons: this coordinator holds no
    usable proving key for the circuit, and the inputs do not satisfy it. The first is a 503,
    the second a 400. Both used to reach a subscript of ``None`` -- a ``TypeError``, caught by
    a bare ``except Exception`` and answered ``500``, with the type checker's complaint about
    each subscript silenced by a ``type: ignore[index]``. So V23-94's corrected range checks
    would have reported every refused learning rate as a server fault (V23-94).

    There is no ``try`` here because ``generate_proof`` catches its own exceptions and folds
    them into that same ``None``.
    """
    if circuit_name not in zk_service.available_circuits:
        # The detail is a constant because tests/security/test_http_exception_hardening.py
        # refuses an interpolated detail on any 5xx, and it is right to: the rule cannot tell a
        # circuit name from an exception message. Which circuit is implied by the endpoint, and
        # the name an operator needs goes to the log.
        logging.getLogger(__name__).error("No usable proving key for circuit '%s'", circuit_name)
        raise HTTPException(status_code=503, detail="This circuit has no usable proving key on this node")

    proof_result = await zk_service.generate_proof(
        circuit_name=circuit_name, inputs=proof_request.inputs, private_inputs=proof_request.private_inputs
    )
    if proof_result is None:
        raise HTTPException(status_code=400, detail=UNPROVABLE_INPUTS)
    return proof_result


@router.post("/prove/training")
@rate_limit(rate=20, per=60)
async def prove_ml_training(request: Request, proof_request: MLProofRequest) -> dict[str, Any]:
    """Generate ZK proof for ML training verification"""
    proof_result = await _prove("ml_training_verification", proof_request)

    return {
        "proof_id": proof_result["proof_id"],
        "proof": proof_result["proof"],
        "public_signals": proof_result["public_signals"],
        "verification_key": proof_result["verification_key"],
        "circuit_type": "ml_training",
    }


@router.post("/verify/training")
@rate_limit(rate=20, per=60)
async def verify_ml_training(request: Request, verification_request: MLVerifyRequest) -> dict[str, Any]:
    """Verify ZK proof for ML training"""
    try:
        # The verification key is chosen server-side from the circuit. This endpoint used to
        # require verification_request["verification_key"] — the caller supplied the key
        # their proof would be checked against, which made the answer meaningless.
        verification_result = await zk_service.verify_proof(
            proof=verification_request.proof,
            public_signals=verification_request.public_signals,
            circuit_name="ml_training_verification",
        )

        return {
            "verified": verification_result.get("verified", False),
            "computation_correct": verification_result.get("computation_correct", False),
            "privacy_preserved": verification_result.get("privacy_preserved", False),
            "reason": verification_result.get("error"),
        }
    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/prove/modular")
@rate_limit(rate=20, per=60)
async def prove_modular_ml(request: Request, proof_request: MLProofRequest) -> dict[str, Any]:
    """Generate ZK proof using the modular ML circuit"""
    proof_result = await _prove("modular_ml_components", proof_request)

    return {
        "proof_id": proof_result["proof_id"],
        "proof": proof_result["proof"],
        "public_signals": proof_result["public_signals"],
        "verification_key": proof_result["verification_key"],
        "circuit_type": "modular_ml",
        "optimization_level": "phase3_optimized",
    }


@router.post("/verify/inference")
@rate_limit(rate=20, per=60)
async def verify_ml_inference(request: Request, verification_request: MLVerifyRequest) -> dict[str, Any]:
    """Verify ZK proof for ML inference"""
    try:
        # See verify_ml_training: the key is the service's, not the caller's.
        verification_result = await zk_service.verify_proof(
            proof=verification_request.proof,
            public_signals=verification_request.public_signals,
            circuit_name="ml_inference_verification",
        )

        return {
            "verified": verification_result.get("verified", False),
            "computation_correct": verification_result.get("computation_correct", False),
            "privacy_preserved": verification_result.get("privacy_preserved", False),
            "reason": verification_result.get("error"),
        }
    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/circuits")
@rate_limit(rate=200, per=60)
async def list_ml_circuits(request: Request) -> dict[str, Any]:
    """List available ML ZK circuits"""
    circuits = [
        {
            "name": "ml_inference_verification",
            "description": "Verifies neural network inference correctness without revealing inputs/weights",
            "input_size": "configurable",
            "security_level": "128-bit",
            "performance": "<2s verification",
            "optimization_level": "baseline",
        },
        {
            "name": "ml_training_verification",
            "description": "Verifies gradient descent training without revealing training data",
            "epochs": 3,
            "parameters": 4,
            # Callers need the scale to submit anything provable, so it is published rather
            # than left in the .circom (V23-94). learning_rate and every parameter are
            # integers scaled by 1e6: a learning rate of 0.01 is 10000.
            "fixed_point_scale": 1000000,
            "constraints": {"learning_rate": "0 < learning_rate < 1000000", "parameters": "0 <= value < 2**40"},
            "security_level": "128-bit",
            "performance": "<5s verification",
            "optimization_level": "baseline",
        },
        {
            "name": "modular_ml_components",
            # This used to read "0 non-linear constraints for maximum performance", with
            # "zero_non_linear_constraints" listed under features. That was accurate and it
            # was the defect: the constraint removed to reach zero was the only check on the
            # learning rate, so every learning rate proved (V23-94).
            "description": "Modular ML training circuit built from reusable components, with an enforced learning-rate range",
            "components": ["ParameterUpdate", "VectorParameterUpdate", "LearningRateValidation", "TrainingEpoch"],
            "epochs": 3,
            "parameters": 4,
            "fixed_point_scale": 1000000,
            "constraints": {
                "learning_rate": "0 < learning_rate < 1000000",
                "gradients": "0 <= value < 2**20, one row per epoch",
                "parameters": "0 <= value < 2**40",
            },
            "security_level": "128-bit",
            "performance": "<1s verification",
            "optimization_level": "phase3_optimized",
            "features": ["modular_architecture", "cached_compilation"],
        },
    ]

    return {"circuits": circuits, "count": len(circuits)}
