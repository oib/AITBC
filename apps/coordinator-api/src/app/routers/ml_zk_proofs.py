from sqlalchemy.orm import Session
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from ..storage import Annotated[Session, Depends(get_session)], get_session
from ..services.zk_proofs import ZKProofService
from ..services.fhe_service import FHEService

router = APIRouter(prefix="/v1/ml-zk", tags=["ml-zk"])

zk_service = ZKProofService()
fhe_service = FHEService()

@router.post("/prove/training")
async def prove_ml_training(proof_request: dict):
    """Generate ZK proof for ML training verification"""
    try:
        circuit_name = "ml_training_verification"

        # Generate proof using ML training circuit
        proof_result = await zk_service.generate_proof(
            circuit_name=circuit_name,
            inputs=proof_request["inputs"],
            private_inputs=proof_request["private_inputs"]
        )

        return {
            "proof_id": proof_result["proof_id"],
            "proof": proof_result["proof"],
            "public_signals": proof_result["public_signals"],
            "verification_key": proof_result["verification_key"],
            "circuit_type": "ml_training"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/verify/training")
async def verify_ml_training(verification_request: dict):
    """Verify ZK proof for ML training"""
    try:
        verification_result = await zk_service.verify_proof(
            proof=verification_request["proof"],
            public_signals=verification_request["public_signals"],
            verification_key=verification_request["verification_key"]
        )

        return {
            "verified": verification_result["verified"],
            "training_correct": verification_result["training_correct"],
            "gradient_descent_valid": verification_result["gradient_descent_valid"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/prove/modular")
async def prove_modular_ml(proof_request: dict):
    """Generate ZK proof using optimized modular circuits"""
    try:
        circuit_name = "modular_ml_components"

        # Generate proof using optimized modular circuit
        proof_result = await zk_service.generate_proof(
            circuit_name=circuit_name,
            inputs=proof_request["inputs"],
            private_inputs=proof_request["private_inputs"]
        )

        return {
            "proof_id": proof_result["proof_id"],
            "proof": proof_result["proof"],
            "public_signals": proof_result["public_signals"],
            "verification_key": proof_result["verification_key"],
            "circuit_type": "modular_ml",
            "optimization_level": "phase3_optimized"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/verify/inference")
async def verify_ml_inference(verification_request: dict):
    """Verify ZK proof for ML inference"""
    try:
        verification_result = await zk_service.verify_proof(
            proof=verification_request["proof"],
            public_signals=verification_request["public_signals"],
            verification_key=verification_request["verification_key"]
        )

        return {
            "verified": verification_result["verified"],
            "computation_correct": verification_result["computation_correct"],
            "privacy_preserved": verification_result["privacy_preserved"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/fhe/inference")
async def fhe_ml_inference(fhe_request: dict):
    """Perform ML inference on encrypted data"""
    try:
        # Setup FHE context
        context = fhe_service.generate_fhe_context(
            scheme=fhe_request.get("scheme", "ckks"),
            provider=fhe_request.get("provider", "tenseal")
        )

        # Encrypt input data
        encrypted_input = fhe_service.encrypt_ml_data(
            data=fhe_request["input_data"],
            context=context,
            provider=fhe_request.get("provider")
        )

        # Perform encrypted inference
        encrypted_result = fhe_service.encrypted_inference(
            model=fhe_request["model"],
            encrypted_input=encrypted_input,
            provider=fhe_request.get("provider")
        )

        return {
            "fhe_context_id": id(context),
            "encrypted_result": encrypted_result.ciphertext.hex(),
            "result_shape": encrypted_result.shape,
            "computation_time_ms": fhe_request.get("computation_time_ms", 0)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/circuits")
async def list_ml_circuits():
    """List available ML ZK circuits"""
    circuits = [
        {
            "name": "ml_inference_verification",
            "description": "Verifies neural network inference correctness without revealing inputs/weights",
            "input_size": "configurable",
            "security_level": "128-bit",
            "performance": "<2s verification",
            "optimization_level": "baseline"
        },
        {
            "name": "ml_training_verification",
            "description": "Verifies gradient descent training without revealing training data",
            "epochs": "configurable",
            "security_level": "128-bit",
            "performance": "<5s verification",
            "optimization_level": "baseline"
        },
        {
            "name": "modular_ml_components",
            "description": "Optimized modular ML circuits with 0 non-linear constraints for maximum performance",
            "components": ["ParameterUpdate", "TrainingEpoch", "VectorParameterUpdate"],
            "security_level": "128-bit",
            "performance": "<1s verification",
            "optimization_level": "phase3_optimized",
            "features": ["modular_architecture", "zero_non_linear_constraints", "cached_compilation"]
        }
    ]

    return {"circuits": circuits, "count": len(circuits)}
