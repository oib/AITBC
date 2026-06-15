"""Tests for realtime learning module"""

import sys
from pathlib import Path

# Add coordinator path for imports
coordinator_path = Path("/opt/aitbc/apps/agent-coordinator/src")
if str(coordinator_path) not in sys.path:
    sys.path.insert(0, str(coordinator_path))

import pytest
from datetime import UTC, datetime, timedelta
from collections import deque

from app.ai.realtime_learning import (
    LearningExperience,
    PredictiveModel,
    RealTimeLearningSystem,
)


class TestLearningExperience:
    """Test LearningExperience dataclass"""

    def test_learning_experience_creation(self):
        """Test creating LearningExperience with default values"""
        now = datetime.now(UTC)
        experience = LearningExperience(
            experience_id="exp-1",
            timestamp=now,
            context={"env": "prod"},
            action="process_data",
            outcome="success",
            performance_metrics={"accuracy": 0.95},
            reward=1.0,
        )
        assert experience.experience_id == "exp-1"
        assert experience.timestamp == now
        assert experience.context == {"env": "prod"}
        assert experience.action == "process_data"
        assert experience.outcome == "success"
        assert experience.performance_metrics == {"accuracy": 0.95}
        assert experience.reward == 1.0
        assert experience.metadata == {}

    def test_learning_experience_with_metadata(self):
        """Test creating LearningExperience with metadata"""
        now = datetime.now(UTC)
        experience = LearningExperience(
            experience_id="exp-1",
            timestamp=now,
            context={"env": "prod"},
            action="process_data",
            outcome="success",
            performance_metrics={"accuracy": 0.95},
            reward=1.0,
            metadata={"version": "1.0", "model": "v2"},
        )
        assert experience.metadata == {"version": "1.0", "model": "v2"}


class TestPredictiveModel:
    """Test PredictiveModel dataclass"""

    def test_predictive_model_creation(self):
        """Test creating PredictiveModel with default values"""
        now = datetime.now(UTC)
        model = PredictiveModel(
            model_id="model-1",
            model_type="linear_regression",
            features=["feature1", "feature2"],
            target="target",
            accuracy=0.92,
            last_updated=now,
        )
        assert model.model_id == "model-1"
        assert model.model_type == "linear_regression"
        assert model.features == ["feature1", "feature2"]
        assert model.target == "target"
        assert model.accuracy == 0.92
        assert model.last_updated == now
        assert isinstance(model.predictions, deque)
        assert model.predictions.maxlen == 1000

    def test_predictive_model_with_predictions(self):
        """Test creating PredictiveModel with predictions"""
        now = datetime.now(UTC)
        predictions = deque(maxlen=1000)
        predictions.append({"input": [1, 2], "output": 0.95})
        model = PredictiveModel(
            model_id="model-1",
            model_type="linear_regression",
            features=["feature1", "feature2"],
            target="target",
            accuracy=0.92,
            last_updated=now,
            predictions=predictions,
        )
        assert len(model.predictions) == 1
        assert model.predictions[0] == {"input": [1, 2], "output": 0.95}


class TestRealTimeLearningSystem:
    """Test RealTimeLearningSystem class"""

    def test_realtime_learning_system_initialization(self):
        """Test RealTimeLearningSystem initialization"""
        system = RealTimeLearningSystem()
        assert system.experiences == []
        assert system.models == {}
        assert isinstance(system.performance_history, deque)
        assert system.performance_history.maxlen == 1000
        assert system.adaptation_threshold == 0.1
        assert system.learning_rate == 0.01
        assert system.prediction_window == timedelta(hours=1)

    def test_realtime_learning_system_custom_threshold(self):
        """Test RealTimeLearningSystem with custom threshold"""
        system = RealTimeLearningSystem()
        system.adaptation_threshold = 0.05
        system.learning_rate = 0.02
        assert system.adaptation_threshold == 0.05
        assert system.learning_rate == 0.02

    def test_add_experience(self):
        """Test adding learning experience"""
        system = RealTimeLearningSystem()
        now = datetime.now(UTC)
        experience = LearningExperience(
            experience_id="exp-1",
            timestamp=now,
            context={"env": "prod"},
            action="process_data",
            outcome="success",
            performance_metrics={"accuracy": 0.95},
            reward=1.0,
        )
        system.experiences.append(experience)
        assert len(system.experiences) == 1
        assert system.experiences[0].experience_id == "exp-1"

    def test_add_predictive_model(self):
        """Test adding predictive model"""
        system = RealTimeLearningSystem()
        now = datetime.now(UTC)
        model = PredictiveModel(
            model_id="model-1",
            model_type="linear_regression",
            features=["feature1"],
            target="target",
            accuracy=0.92,
            last_updated=now,
        )
        system.models["model-1"] = model
        assert "model-1" in system.models
        assert system.models["model-1"].model_id == "model-1"

    def test_performance_history(self):
        """Test performance history tracking"""
        system = RealTimeLearningSystem()
        entry = {"timestamp": datetime.now(UTC), "reward": 1.0, "performance": {"accuracy": 0.95}}
        system.performance_history.append(entry)
        assert len(system.performance_history) == 1
        assert system.performance_history[0] == entry

    def test_performance_history_maxlen(self):
        """Test performance history respects maxlen"""
        system = RealTimeLearningSystem()
        for i in range(1005):
            entry = {"timestamp": datetime.now(UTC), "reward": float(i), "performance": {}}
            system.performance_history.append(entry)
        assert len(system.performance_history) == 1000
