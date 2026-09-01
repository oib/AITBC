"""G3 health check for the computation_correct ZK gate.

Runs a pair of synthetic ``receipt_model`` proofs through the live
``verify_model_proof`` path and confirms the gate still accepts a correct
computation and rejects an incorrect one.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from aitbc.aitbc_logging import get_logger

from .model_registry import compute_public_inputs, expected_public_signals, get_model
from .zk_proofs import zk_proof_service

logger = get_logger(__name__)


def _synthetic_job(prompt: str, model_name: str = "linear-1") -> Any:
    """Return a lightweight object with the fields the ZK helpers need."""
    return SimpleNamespace(
        payload={"type": "inference", "prompt": prompt, "model": model_name},
        constraints={"models": [model_name]},
    )


async def run_computation_correct_health_check() -> dict[str, Any]:
    """Run a good-probe and a bad-probe through the computation_correct gate.

    Returns a dict with ``computation_correct_healthy`` True only when:
    - the ZK service is enabled and the receipt_model circuit is available,
    - a correct computation returns ``computation_correct: True``,
    - an incorrect computation returns ``computation_correct: False``.
    """
    if not zk_proof_service.is_enabled():
        return {
            "status": "disabled",
            "computation_correct_healthy": False,
            "reason": "ZK proof service is disabled",
        }
    if "receipt_model" not in zk_proof_service.available_circuits:
        return {
            "status": "unhealthy",
            "computation_correct_healthy": False,
            "reason": "receipt_model circuit is not available",
        }

    model = get_model("linear-1")
    if model is None:
        return {
            "status": "unhealthy",
            "computation_correct_healthy": False,
            "reason": "linear-1 model is not registered",
        }

    good_job = _synthetic_job("computation correct health check good")
    bad_job = _synthetic_job("computation correct health check bad")

    # The actual output in ``result`` is ignored by compute_public_inputs today;
    # the coordinator computes the expected output from the input.  For the bad
    # probe we use a different input, which yields different public signals.
    result: dict[str, Any] = {"output": "ignored"}

    try:
        good_proof = await zk_proof_service.generate_model_proof(good_job, result)
        bad_proof = await zk_proof_service.generate_model_proof(bad_job, result)

        if not good_proof or not bad_proof:
            return {
                "status": "unhealthy",
                "computation_correct_healthy": False,
                "reason": "failed to generate one or both health-check proofs",
                "good_proof_generated": good_proof is not None,
                "bad_proof_generated": bad_proof is not None,
            }

        good_expected = expected_public_signals(compute_public_inputs(good_job, result, model)["public_inputs"])

        good_verify = await zk_proof_service.verify_model_proof(
            good_proof["proof"], good_proof["public_signals"], good_expected
        )
        # Verify the bad proof against the *good* expected public signals.  This
        # is the mismatch the gate must catch: a proof for a different input.
        bad_verify = await zk_proof_service.verify_model_proof(bad_proof["proof"], bad_proof["public_signals"], good_expected)

        good_ok = good_verify.get("computation_correct") is True
        bad_ok = bad_verify.get("computation_correct") is False

        healthy = good_ok and bad_ok
        return {
            "status": "healthy" if healthy else "unhealthy",
            "computation_correct_healthy": healthy,
            "good_probe": {
                "computation_correct": good_verify.get("computation_correct"),
                "verified": good_verify.get("verified"),
                "public_signals_match": good_proof["public_signals"] == good_expected,
            },
            "bad_probe": {
                "computation_correct": bad_verify.get("computation_correct"),
                "verified": bad_verify.get("verified"),
                "public_signals_match": bad_proof["public_signals"] == good_expected,
                "expected_public_for_good_input": good_expected,
                "actual_public_signals_for_bad_input": bad_proof["public_signals"],
            },
        }
    except Exception as e:
        logger.exception("computation_correct health check failed")
        return {
            "status": "unhealthy",
            "computation_correct_healthy": False,
            "reason": f"health check raised an exception: {e}",
        }
