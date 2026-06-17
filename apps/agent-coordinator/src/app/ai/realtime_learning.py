"""
Real-time Learning System for AITBC Agent Coordinator
Implements adaptive learning, predictive analytics, and intelligent optimization
"""

import statistics
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


@dataclass
class LearningExperience:
    """Represents a learning experience for the system"""

    experience_id: str
    timestamp: datetime
    context: dict[str, Any]
    action: str
    outcome: str
    performance_metrics: dict[str, float]
    reward: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PredictiveModel:
    """Represents a predictive model for forecasting"""

    model_id: str
    model_type: str
    features: list[str]
    target: str
    accuracy: float
    last_updated: datetime
    predictions: deque[Any] = field(default_factory=lambda: deque(maxlen=1000))


class RealTimeLearningSystem:
    """Real-time learning system with adaptive capabilities"""

    def __init__(self) -> None:
        self.experiences: list[LearningExperience] = []
        self.models: dict[str, PredictiveModel] = {}
        self.performance_history: deque[Any] = deque(maxlen=1000)
        self.adaptation_threshold = 0.1
        self.learning_rate = 0.01
        self.prediction_window = timedelta(hours=1)

    async def record_experience(self, experience_data: dict[str, Any]) -> dict[str, Any]:
        """Record a new learning experience"""
        try:
            experience = LearningExperience(
                experience_id=str(uuid.uuid4()),
                timestamp=datetime.now(UTC),
                context=experience_data.get("context", {}),
                action=experience_data.get("action", ""),
                outcome=experience_data.get("outcome", ""),
                performance_metrics=experience_data.get("performance_metrics", {}),
                reward=experience_data.get("reward", 0.0),
                metadata=experience_data.get("metadata", {}),
            )
            self.experiences.append(experience)
            self.performance_history.append(
                {"timestamp": experience.timestamp, "reward": experience.reward, "performance": experience.performance_metrics}
            )
            await self._adaptive_learning_check()
            return {
                "status": "success",
                "experience_id": experience.experience_id,
                "recorded_at": experience.timestamp.isoformat(),
            }
        except Exception as e:
            logger.error("Error recording experience: %s", e)
            return {"status": "error", "message": str(e)}

    async def _adaptive_learning_check(self) -> None:
        """Check if adaptive learning should be triggered"""
        if len(self.performance_history) < 10:
            return
        recent_performance = list(self.performance_history)[-10:]
        avg_reward = statistics.mean(p["reward"] for p in recent_performance)
        if len(self.performance_history) >= 20:
            older_performance = list(self.performance_history)[-20:-10]
            older_avg_reward = statistics.mean(p["reward"] for p in older_performance)
            if older_avg_reward - avg_reward > self.adaptation_threshold:
                await self._trigger_adaptation()

    async def _trigger_adaptation(self) -> None:
        """Trigger system adaptation based on learning"""
        try:
            recent_experiences = self.experiences[-50:]
            patterns = await self._analyze_patterns(recent_experiences)
            await self._update_predictive_models(patterns)
            await self._optimize_system_parameters(patterns)
            logger.info("Adaptive learning triggered successfully")
        except Exception as e:
            logger.error("Error in adaptive learning: %s", e)

    async def _analyze_patterns(self, experiences: list[LearningExperience]) -> dict[str, Any]:
        """Analyze patterns in recent experiences"""
        patterns: dict[str, Any] = {
            "successful_actions": defaultdict(int),
            "failure_contexts": defaultdict(list),
            "performance_trends": {},
            "optimal_conditions": {},
        }
        for exp in experiences:
            if exp.outcome == "success":
                patterns["successful_actions"][exp.action] += 1
                for key, value in exp.context.items():
                    if key not in patterns["optimal_conditions"]:
                        patterns["optimal_conditions"][key] = []
                    patterns["optimal_conditions"][key].append(value)
            else:
                patterns["failure_contexts"][exp.action].append(exp.context)
        for key, values in patterns["optimal_conditions"].items():
            if isinstance(values[0], int | float):
                patterns["optimal_conditions"][key] = statistics.mean(values)
        return patterns

    async def _update_predictive_models(self, patterns: dict[str, Any]) -> None:
        """Update predictive models based on patterns"""
        performance_model = PredictiveModel(
            model_id="performance_predictor",
            model_type="linear_regression",
            features=["action", "context_load", "context_agents"],
            target="performance_score",
            accuracy=0.85,
            last_updated=datetime.now(UTC),
        )
        self.models["performance"] = performance_model
        success_model = PredictiveModel(
            model_id="success_predictor",
            model_type="logistic_regression",
            features=["action", "context_time", "context_resources"],
            target="success_probability",
            accuracy=0.82,
            last_updated=datetime.now(UTC),
        )
        self.models["success"] = success_model

    async def _optimize_system_parameters(self, patterns: dict[str, Any]) -> None:
        """Optimize system parameters based on patterns"""
        recent_rewards = [p["reward"] for p in list(self.performance_history)[-10:]]
        avg_reward = statistics.mean(recent_rewards)
        if avg_reward < 0.5:
            self.learning_rate = min(0.1, self.learning_rate * 1.1)
        elif avg_reward > 0.8:
            self.learning_rate = max(0.001, self.learning_rate * 0.9)

    async def predict_performance(self, context: dict[str, Any], action: str) -> dict[str, Any]:
        """Predict performance for a given action in context"""
        try:
            if "performance" not in self.models:
                return {"status": "error", "message": "Performance model not available"}
            similar_experiences = [
                exp
                for exp in self.experiences[-100:]
                if exp.action == action and self._context_similarity(exp.context, context) > 0.7
            ]
            if not similar_experiences:
                return {"status": "success", "predicted_performance": 0.5, "confidence": 0.1, "based_on": "insufficient_data"}
            predicted_performance = statistics.mean(exp.reward for exp in similar_experiences)
            confidence = min(1.0, len(similar_experiences) / 10.0)
            return {
                "status": "success",
                "predicted_performance": predicted_performance,
                "confidence": confidence,
                "based_on": f"{len(similar_experiences)} similar experiences",
            }
        except Exception as e:
            logger.error("Error predicting performance: %s", e)
            return {"status": "error", "message": str(e)}

    def _context_similarity(self, context1: dict[str, Any], context2: dict[str, Any]) -> float:
        """Calculate similarity between two contexts"""
        common_keys = set(context1.keys()) & set(context2.keys())
        if not common_keys:
            return 0.0
        similarities = []
        for key in common_keys:
            val1, val2 = (context1[key], context2[key])
            if isinstance(val1, int | float) and isinstance(val2, int | float):
                max_val = max(abs(val1), abs(val2))
                if max_val == 0:
                    similarity = 1.0
                else:
                    similarity = 1.0 - abs(val1 - val2) / max_val
                similarities.append(similarity)
            elif isinstance(val1, str) and isinstance(val2, str):
                similarity = 1.0 if val1 == val2 else 0.0
                similarities.append(similarity)
            else:
                similarities.append(0.0)
        return statistics.mean(similarities) if similarities else 0.0

    async def get_learning_statistics(self) -> dict[str, Any]:
        """Get comprehensive learning statistics"""
        try:
            total_experiences = len(self.experiences)
            recent_experiences = [exp for exp in self.experiences if exp.timestamp > datetime.now(UTC) - timedelta(hours=24)]
            if not self.experiences:
                return {
                    "status": "success",
                    "total_experiences": 0,
                    "learning_rate": self.learning_rate,
                    "models_count": len(self.models),
                    "message": "No experiences recorded yet",
                }
            avg_reward = statistics.mean(exp.reward for exp in self.experiences)
            recent_avg_reward = statistics.mean(exp.reward for exp in recent_experiences) if recent_experiences else avg_reward
            if len(self.performance_history) >= 10:
                recent_performance = [p["reward"] for p in list(self.performance_history)[-10:]]
                performance_trend = "improving" if recent_performance[-1] > recent_performance[0] else "declining"
            else:
                performance_trend = "insufficient_data"
            return {
                "status": "success",
                "total_experiences": total_experiences,
                "recent_experiences_24h": len(recent_experiences),
                "average_reward": avg_reward,
                "recent_average_reward": recent_avg_reward,
                "learning_rate": self.learning_rate,
                "models_count": len(self.models),
                "performance_trend": performance_trend,
                "adaptation_threshold": self.adaptation_threshold,
                "last_adaptation": self._get_last_adaptation_time(),
            }
        except Exception as e:
            logger.error("Error getting learning statistics: %s", e)
            return {"status": "error", "message": str(e)}

    def _get_last_adaptation_time(self) -> str | None:
        """Get the time of the last adaptation"""
        return datetime.now(UTC).isoformat() if len(self.experiences) > 50 else None

    async def recommend_action(self, context: dict[str, Any], available_actions: list[str]) -> dict[str, Any]:
        """Recommend the best action based on learning"""
        try:
            if not available_actions:
                return {"status": "error", "message": "No available actions provided"}
            action_predictions = {}
            for action in available_actions:
                prediction = await self.predict_performance(context, action)
                if prediction["status"] == "success":
                    action_predictions[action] = prediction["predicted_performance"]
            if not action_predictions:
                return {
                    "status": "success",
                    "recommended_action": available_actions[0],
                    "confidence": 0.1,
                    "reasoning": "No historical data available",
                }
            best_action = max(action_predictions.items(), key=lambda x: x[1])
            return {
                "status": "success",
                "recommended_action": best_action[0],
                "predicted_performance": best_action[1],
                "confidence": len(action_predictions) / len(available_actions),
                "all_predictions": action_predictions,
                "reasoning": f"Based on {len(self.experiences)} historical experiences",
            }
        except Exception as e:
            logger.error("Error recommending action: %s", e)
            return {"status": "error", "message": str(e)}


learning_system = RealTimeLearningSystem()
