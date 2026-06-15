from typing import Any

from fastapi import APIRouter, HTTPException, Request

from aitbc.rate_limiting import rate_limit

from ....services.fhe_service import FHEService
from ....services.zk_proofs import ZKProofService

router = APIRouter(prefix="/v1/ml-zk", tags=["ml-zk"])

zk_service = ZKProofService()

# Lazy instantiation of FHEService to avoid import-time errors
_fhe_service: FHEService | None = None


def get_fhe_service() -> FHEService:
    """Get or create FHEService instance"""
    global _fhe_service
    if _fhe_service is None:
        _fhe_service = FHEService()
    return _fhe_service


@router.post("/prove/training")
@rate_limit(rate=20, per=60)
async def prove_ml_training(request: Request, proof_request: dict) -> dict[str, Any]:
    """Generate ZK proof for ML training verification"""
    try:
        circuit_name = "ml_training_verification"

        # Generate proof using ML training circuit
        proof_result = await zk_service.generate_proof(
            circuit_name=circuit_name, inputs=proof_request["inputs"], private_inputs=proof_request["private_inputs"]
        )

        return {
            "proof_id": proof_result["proof_id"],  # type: ignore[index]
            "proof": proof_result["proof"],  # type: ignore[index]
            "public_signals": proof_result["public_signals"],  # type: ignore[index]
            "verification_key": proof_result["verification_key"],  # type: ignore[index]
            "circuit_type": "ml_training",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/verify/training")
@rate_limit(rate=20, per=60)
async def verify_ml_training(request: Request, verification_request: dict, test_mode: bool = False) -> dict[str, Any]:
    """Verify ZK proof for ML training"""
    try:
        verification_result = await zk_service.verify_proof(
            proof=verification_request["proof"],
            public_signals=verification_request["public_signals"],
            verification_key=verification_request["verification_key"],
            test_mode=test_mode,
        )

        return {
            "verified": verification_result.get("verified", False),
            "computation_correct": verification_result.get("computation_correct", False),
            "privacy_preserved": verification_result.get("privacy_preserved", False),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/prove/modular")
@rate_limit(rate=20, per=60)
async def prove_modular_ml(request: Request, proof_request: dict) -> dict[str, Any]:
    """Generate ZK proof using optimized modular circuits"""
    try:
        circuit_name = "modular_ml_components"

        # Generate proof using optimized modular circuit
        proof_result = await zk_service.generate_proof(
            circuit_name=circuit_name, inputs=proof_request["inputs"], private_inputs=proof_request["private_inputs"]
        )

        return {
            "proof_id": proof_result["proof_id"],  # type: ignore[index]
            "proof": proof_result["proof"],  # type: ignore[index]
            "public_signals": proof_result["public_signals"],  # type: ignore[index]
            "verification_key": proof_result["verification_key"],  # type: ignore[index]
            "circuit_type": "modular_ml",
            "optimization_level": "phase3_optimized",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/verify/inference")
@rate_limit(rate=20, per=60)
async def verify_ml_inference(request: Request, verification_request: dict, test_mode: bool = False) -> dict[str, Any]:
    """Verify ZK proof for ML inference"""
    try:
        verification_result = await zk_service.verify_proof(
            proof=verification_request["proof"],
            public_signals=verification_request["public_signals"],
            verification_key=verification_request["verification_key"],
            test_mode=test_mode,
        )

        return {
            "verified": verification_result["verified"],
            "computation_correct": verification_result["computation_correct"],
            "privacy_preserved": verification_result["privacy_preserved"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fhe/inference")
@rate_limit(rate=20, per=60)
async def fhe_ml_inference(request: Request, fhe_request: dict) -> dict[str, Any]:
    """Perform ML inference on encrypted data"""
    try:
        fhe_service = get_fhe_service()

        # Setup FHE context
        context = fhe_service.generate_fhe_context(
            scheme=fhe_request.get("scheme", "ckks"), provider=fhe_request.get("provider", "tenseal")
        )

        # Encrypt input data
        encrypted_input = fhe_service.encrypt_ml_data(
            data=fhe_request["input_data"], context=context, provider=fhe_request.get("provider")
        )

        # Perform encrypted inference
        # If model is a string (model name), create a mock model dict
        model = fhe_request["model"]
        if isinstance(model, str):
            import random

            input_size = len(fhe_request["input_data"])
            model = {
                "name": model,
                "weights": [random.uniform(-0.5, 0.5) for _ in range(input_size)],
                "biases": [random.uniform(-0.1, 0.1) for _ in range(input_size)],
            }

        encrypted_result = fhe_service.encrypted_inference(
            model=model, encrypted_input=encrypted_input, provider=fhe_request.get("provider")
        )

        return {
            "fhe_context_id": id(context),
            "encrypted_result": encrypted_result.ciphertext.hex(),
            "result_shape": encrypted_result.shape,
            "computation_time_ms": fhe_request.get("computation_time_ms", 0),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
            "epochs": "configurable",
            "security_level": "128-bit",
            "performance": "<5s verification",
            "optimization_level": "baseline",
        },
        {
            "name": "modular_ml_components",
            "description": "Optimized modular ML circuits with 0 non-linear constraints for maximum performance",
            "components": ["ParameterUpdate", "TrainingEpoch", "VectorParameterUpdate"],
            "security_level": "128-bit",
            "performance": "<1s verification",
            "optimization_level": "phase3_optimized",
            "features": ["modular_architecture", "zero_non_linear_constraints", "cached_compilation"],
        },
    ]

    return {"circuits": circuits, "count": len(circuits)}
