"""Tests for advanced AI module"""
import sys
from pathlib import Path

# Add coordinator path for imports
coordinator_path = Path("/opt/aitbc/apps/agent-coordinator/src")
if str(coordinator_path) not in sys.path:
    sys.path.insert(0, str(coordinator_path))

import pytest
from datetime import UTC, datetime

from app.ai.advanced_ai import (
    MLModel,
    NeuralNetwork,
    AdvancedAIIntegration,
)


class TestMLModel:
    """Test MLModel dataclass"""

    def test_ml_model_creation(self):
        """Test creating MLModel with default values"""
        model = MLModel(
            model_id='model-1',
            model_type='random_forest',
            features=['feature1', 'feature2'],
            target='target',
            accuracy=0.95,
        )
        assert model.model_id == 'model-1'
        assert model.model_type == 'random_forest'
        assert model.features == ['feature1', 'feature2']
        assert model.target == 'target'
        assert model.accuracy == 0.95
        assert model.parameters == {}
        assert model.training_data_size == 0
        assert model.last_trained is None

    def test_ml_model_with_values(self):
        """Test creating MLModel with custom values"""
        now = datetime.now(UTC)
        model = MLModel(
            model_id='model-1',
            model_type='neural_network',
            features=['feature1', 'feature2', 'feature3'],
            target='target',
            accuracy=0.98,
            parameters={'epochs': 100, 'batch_size': 32},
            training_data_size=10000,
            last_trained=now,
        )
        assert model.model_type == 'neural_network'
        assert len(model.features) == 3
        assert model.accuracy == 0.98
        assert model.parameters == {'epochs': 100, 'batch_size': 32}
        assert model.training_data_size == 10000
        assert model.last_trained == now


class TestNeuralNetwork:
    """Test NeuralNetwork dataclass"""

    def test_neural_network_creation(self):
        """Test creating NeuralNetwork with default values"""
        network = NeuralNetwork(
            input_size=10,
            hidden_sizes=[64, 32],
            output_size=1,
        )
        assert network.input_size == 10
        assert network.hidden_sizes == [64, 32]
        assert network.output_size == 1
        assert network.weights == []
        assert network.biases == []
        assert network.learning_rate == 0.01

    def test_neural_network_with_values(self):
        """Test creating NeuralNetwork with custom values"""
        network = NeuralNetwork(
            input_size=20,
            hidden_sizes=[128, 64, 32],
            output_size=5,
            learning_rate=0.001,
        )
        assert network.input_size == 20
        assert network.hidden_sizes == [128, 64, 32]
        assert network.output_size == 5
        assert network.learning_rate == 0.001


class TestAdvancedAIIntegration:
    """Test AdvancedAIIntegration class"""

    def test_advanced_ai_integration_initialization(self):
        """Test AdvancedAIIntegration initialization"""
        ai = AdvancedAIIntegration()
        assert ai.models == {}
        assert ai.neural_networks == {}
        assert ai.training_data == {}
        assert ai.predictions_history == []
        assert ai.model_performance == {}

    def test_add_ml_model(self):
        """Test adding ML model"""
        ai = AdvancedAIIntegration()
        model = MLModel(
            model_id='model-1',
            model_type='random_forest',
            features=['feature1'],
            target='target',
            accuracy=0.95,
        )
        ai.models['model-1'] = model
        assert 'model-1' in ai.models
        assert ai.models['model-1'].model_id == 'model-1'

    def test_add_neural_network(self):
        """Test adding neural network"""
        ai = AdvancedAIIntegration()
        network = NeuralNetwork(
            input_size=10,
            hidden_sizes=[64, 32],
            output_size=1,
        )
        ai.neural_networks['network-1'] = network
        assert 'network-1' in ai.neural_networks
        assert ai.neural_networks['network-1'].input_size == 10

    def test_predictions_history(self):
        """Test predictions history tracking"""
        ai = AdvancedAIIntegration()
        prediction = {'model_id': 'model-1', 'input': [1, 2, 3], 'output': 0.95}
        ai.predictions_history.append(prediction)
        assert len(ai.predictions_history) == 1
        assert ai.predictions_history[0] == prediction

    def test_model_performance_tracking(self):
        """Test model performance tracking"""
        ai = AdvancedAIIntegration()
        ai.model_performance['model-1'].append(0.95)
        ai.model_performance['model-1'].append(0.97)
        assert len(ai.model_performance['model-1']) == 2
        assert ai.model_performance['model-1'][0] == 0.95
        assert ai.model_performance['model-1'][1] == 0.97
