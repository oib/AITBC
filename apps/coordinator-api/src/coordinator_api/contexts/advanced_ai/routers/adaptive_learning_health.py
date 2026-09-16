"""Adaptive Learning health check router.

Reports the real state of the in-process ``AdaptiveLearningService``
(contexts/analytics/services/ai_analytics/adaptive_learning.py). This is a
capability of the coordinator-api process — there is no separate
adaptive-learning daemon on this surface.
"""

import sys
from datetime import UTC, datetime
from typing import Annotated, Any

import psutil
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from aitbc.aitbc_logging import get_logger
from aitbc.rate_limiting import rate_limit

from ....storage import get_session
from ...analytics.services.ai_analytics.adaptive_learning import (
    AdaptiveLearningService,
    LearningAlgorithm,
    LearningEnvironment,
    ReinforcementLearningAgent,
    RewardType,
)

logger = get_logger(__name__)
router = APIRouter()


def _base_status(service: AdaptiveLearningService) -> dict[str, Any]:
    """Fields common to both health responses — all derived from the live service."""
    return {
        "service": "adaptive-learning",
        "runs_in_process": "coordinator-api",
        "timestamp": datetime.now(UTC).isoformat(),
        "registered_agents": len(service.learning_agents),
        "registered_environments": len(service.environments),
        "registered_reward_functions": len(service.reward_functions),
        "active_training_sessions": len(service.training_sessions),
    }


@router.get("/health", tags=["health"], summary="Adaptive Learning Service Health")
@rate_limit(rate=1000, per=60)
async def adaptive_learning_health(request: Request, session: Annotated[Session, Depends(get_session)]) -> dict[str, Any]:
    """
    Health check for the in-process Adaptive Learning Service.

    Reports real service state and system metrics — no standalone daemon
    exists on this surface.
    """
    try:
        service = AdaptiveLearningService(session)
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        service_status = {
            "status": "healthy",
            **_base_status(service),
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "system": {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_available_gb": round(memory.available / 1024**3, 2),
                "disk_percent": disk.percent,
                "disk_free_gb": round(disk.free / 1024**3, 2),
            },
            "algorithms": [algo.value for algo in LearningAlgorithm],
            "reward_types": [rt.value for rt in RewardType],
            "operations": [
                "create_learning_environment",
                "create_learning_agent",
                "train_agent",
                "evaluate_agent",
                "get_agent_performance",
                "create_reward_function",
                "calculate_reward",
            ],
        }
        logger.info("Adaptive Learning Service health check completed successfully")
        return service_status
    except Exception as e:
        logger.error("Adaptive Learning Service health check failed: %s", e)
        return {
            "status": "unhealthy",
            "service": "adaptive-learning",
            "timestamp": datetime.now(UTC).isoformat(),
            "error": "Health check failed",
        }


@router.get("/health/deep", tags=["health"], summary="Deep Adaptive Learning Service Health")
@rate_limit(rate=1000, per=60)
async def adaptive_learning_deep_health(request: Request, session: Annotated[Session, Depends(get_session)]) -> dict[str, Any]:
    """
    Deep health check: instantiates a throwaway ``ReinforcementLearningAgent``
    per ``LearningAlgorithm`` member and a ``LearningEnvironment`` to exercise
    the real construction paths (in-memory only — nothing is persisted).
    """
    try:
        service = AdaptiveLearningService(session)
        algorithm_tests: dict[str, dict[str, Any]] = {}
        for algo in LearningAlgorithm:
            try:
                agent = ReinforcementLearningAgent(f"health-probe-{algo.value}", algo, {})
                action = agent.get_action({"position": 0}, training=True)
                algorithm_tests[algo.value] = {
                    "status": "pass" if action is not None else "fail",
                }
            except Exception as e:
                logger.error("Algorithm probe failed for %s: %s", algo.value, e)
                algorithm_tests[algo.value] = {"status": "fail", "error": "instantiation/probe failed"}
        try:
            env = LearningEnvironment("health-probe-env", {})
            env_ok = isinstance(env.validate_state({}), bool) and isinstance(env.validate_action({}), bool)
            environment_test = {"status": "pass" if env_ok else "fail"}
        except Exception as e:
            logger.error("Environment probe failed: %s", e)
            environment_test = {"status": "fail", "error": "instantiation/probe failed"}
        all_pass = all(t["status"] == "pass" for t in algorithm_tests.values()) and environment_test["status"] == "pass"
        return {
            "status": "healthy" if all_pass else "degraded",
            **_base_status(service),
            "algorithm_tests": algorithm_tests,
            "environment_test": environment_test,
        }
    except Exception as e:
        logger.error("Deep Adaptive Learning health check failed: %s", e)
        return {
            "status": "unhealthy",
            "service": "adaptive-learning",
            "timestamp": datetime.now(UTC).isoformat(),
            "error": "Deep health check failed",
        }
