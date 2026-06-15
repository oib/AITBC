"""
Advanced AI/ML Integration for AITBC Agent Coordinator
Implements machine learning models, neural networks, and intelligent decision making
"""

from __future__ import annotations

import statistics
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

np: Any = None
try:
    import numpy as np
except ImportError:
    pass

from aitbc import get_logger

logger = get_logger(__name__)


@dataclass
class MLModel:
    """Represents a machine learning model"""

    model_id: str
    model_type: str
    features: list[str]
    target: str
    accuracy: float
    parameters: dict[str, Any] = field(default_factory=dict)
    training_data_size: int = 0
    last_trained: datetime | None = None


@dataclass
class NeuralNetwork:
    """Simple neural network implementation"""

    input_size: int
    hidden_sizes: list[int]
    output_size: int
    weights: list[np.ndarray] = field(default_factory=list)
    biases: list[np.ndarray] = field(default_factory=list)
    learning_rate: float = 0.01


class AdvancedAIIntegration:
    """Advanced AI/ML integration system"""

    def __init__(self) -> None:
        self.models: dict[str, MLModel] = {}
        self.neural_networks: dict[str, NeuralNetwork] = {}
        self.training_data: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.predictions_history: list[dict[str, Any]] = []
        self.model_performance: dict[str, list[float]] = defaultdict(list)

    async def create_neural_network(self, config: dict[str, Any]) -> dict[str, Any]:
        """Create a new neural network"""
        try:
            network_id = config.get("network_id", str(uuid.uuid4()))
            input_size = config.get("input_size", 10)
            hidden_sizes = config.get("hidden_sizes", [64, 32])
            output_size = config.get("output_size", 1)
            learning_rate = config.get("learning_rate", 0.01)
            layers = [input_size] + hidden_sizes + [output_size]
            weights = []
            biases = []
            for i in range(len(layers) - 1):
                limit = np.sqrt(6 / (layers[i] + layers[i + 1]))
                weights.append(np.random.uniform(-limit, limit, (layers[i], layers[i + 1])))
                biases.append(np.zeros((1, layers[i + 1])))
            network = NeuralNetwork(
                input_size=input_size,
                hidden_sizes=hidden_sizes,
                output_size=output_size,
                weights=weights,
                biases=biases,
                learning_rate=learning_rate,
            )
            self.neural_networks[network_id] = network
            return {
                "status": "success",
                "network_id": network_id,
                "architecture": {"input_size": input_size, "hidden_sizes": hidden_sizes, "output_size": output_size},
                "created_at": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            logger.error("Error creating neural network: %s", e)
            return {"status": "error", "message": str(e)}

    def _sigmoid(self, x: np.ndarray) -> np.ndarray:
        """Sigmoid activation function"""
        return 1 / (1 + np.exp(-np.clip(x, -500, 500)))

    def _sigmoid_derivative(self, x: np.ndarray) -> np.ndarray:
        """Derivative of sigmoid function"""
        s = self._sigmoid(x)
        return s * (1 - s)

    def _relu(self, x: np.ndarray) -> np.ndarray:
        """ReLU activation function"""
        return np.maximum(0, x)

    def _relu_derivative(self, x: np.ndarray) -> np.ndarray:
        """Derivative of ReLU function"""
        return (x > 0).astype(float)

    async def train_neural_network(
        self, network_id: str, training_data: list[dict[str, Any]], epochs: int = 100
    ) -> dict[str, Any]:
        """Train a neural network"""
        try:
            if network_id not in self.neural_networks:
                return {"status": "error", "message": "Network not found"}
            network = self.neural_networks[network_id]
            X = np.array([data["features"] for data in training_data])
            y = np.array([data["target"] for data in training_data])
            if y.ndim == 1:
                y = y.reshape(-1, 1)
            losses = []
            for _epoch in range(epochs):
                activations = [X]
                z_values = []
                for i in range(len(network.weights) - 1):
                    z = np.dot(activations[-1], network.weights[i]) + network.biases[i]
                    z_values.append(z)
                    activations.append(self._relu(z))
                z = np.dot(activations[-1], network.weights[-1]) + network.biases[-1]
                z_values.append(z)
                activations.append(self._sigmoid(z))
                predictions = activations[-1]
                loss = -np.mean(y * np.log(predictions + 1e-15) + (1 - y) * np.log(1 - predictions + 1e-15))
                losses.append(loss)
                delta = (predictions - y) / len(X)
                network.weights[-1] -= network.learning_rate * np.dot(activations[-2].T, delta)
                network.biases[-1] -= network.learning_rate * np.sum(delta, axis=0, keepdims=True)
                for i in range(len(network.weights) - 2, -1, -1):
                    delta = np.dot(delta, network.weights[i + 1].T) * self._relu_derivative(z_values[i])
                    network.weights[i] -= network.learning_rate * np.dot(activations[i].T, delta)
                    network.biases[i] -= network.learning_rate * np.sum(delta, axis=0, keepdims=True)
            self.training_data[network_id].extend(training_data)
            predictions = (activations[-1] > 0.5).astype(float)
            accuracy = np.mean(predictions == y)
            self.model_performance[network_id].append(accuracy)
            return {
                "status": "success",
                "network_id": network_id,
                "epochs_completed": epochs,
                "final_loss": losses[-1] if losses else 0,
                "accuracy": accuracy,
                "training_data_size": len(training_data),
                "trained_at": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            logger.error("Error training neural network: %s", e)
            return {"status": "error", "message": str(e)}

    async def predict_with_neural_network(self, network_id: str, features: list[float]) -> dict[str, Any]:
        """Make predictions using a trained neural network"""
        try:
            if network_id not in self.neural_networks:
                return {"status": "error", "message": "Network not found"}
            network = self.neural_networks[network_id]
            x = np.array(features).reshape(1, -1)
            activation = x
            for i in range(len(network.weights) - 1):
                activation = self._relu(np.dot(activation, network.weights[i]) + network.biases[i])
            prediction = self._sigmoid(np.dot(activation, network.weights[-1]) + network.biases[-1])
            prediction_record = {
                "network_id": network_id,
                "features": features,
                "prediction": float(prediction[0][0]),
                "timestamp": datetime.now(UTC).isoformat(),
            }
            self.predictions_history.append(prediction_record)
            return {
                "status": "success",
                "network_id": network_id,
                "prediction": float(prediction[0][0]),
                "confidence": max(prediction[0][0], 1 - prediction[0][0]),
                "predicted_at": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            logger.error("Error making prediction: %s", e)
            return {"status": "error", "message": str(e)}

    async def create_ml_model(self, config: dict[str, Any]) -> dict[str, Any]:
        """Create a new machine learning model"""
        try:
            model_id = config.get("model_id", str(uuid.uuid4()))
            model_type = config.get("model_type", "linear_regression")
            features = config.get("features", [])
            target = config.get("target", "")
            model = MLModel(
                model_id=model_id,
                model_type=model_type,
                features=features,
                target=target,
                accuracy=0.0,
                parameters=config.get("parameters", {}),
                training_data_size=0,
                last_trained=None,
            )
            self.models[model_id] = model
            return {
                "status": "success",
                "model_id": model_id,
                "model_type": model_type,
                "features": features,
                "target": target,
                "created_at": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            logger.error("Error creating ML model: %s", e)
            return {"status": "error", "message": str(e)}

    async def train_ml_model(self, model_id: str, training_data: list[dict[str, Any]]) -> dict[str, Any]:
        """Train a machine learning model"""
        try:
            if model_id not in self.models:
                return {"status": "error", "message": "Model not found"}
            model = self.models[model_id]
            if model.model_type == "linear_regression":
                accuracy = await self._train_linear_regression(model, training_data)
            elif model.model_type == "logistic_regression":
                accuracy = await self._train_logistic_regression(model, training_data)
            else:
                return {"status": "error", "message": f"Unsupported model type: {model.model_type}"}
            model.accuracy = accuracy
            model.training_data_size = len(training_data)
            model.last_trained = datetime.now(UTC)
            self.model_performance[model_id].append(accuracy)
            return {
                "status": "success",
                "model_id": model_id,
                "accuracy": accuracy,
                "training_data_size": len(training_data),
                "trained_at": model.last_trained.isoformat(),
            }
        except Exception as e:
            logger.error("Error training ML model: %s", e)
            return {"status": "error", "message": str(e)}

    async def _train_linear_regression(self, model: MLModel, training_data: list[dict[str, Any]]) -> float:
        """Train a linear regression model"""
        try:
            X = np.array([[data[feature] for feature in model.features] for data in training_data])
            y = np.array([data[model.target] for data in training_data])
            X_b = np.c_[np.ones((X.shape[0], 1)), X]
            try:
                theta = np.linalg.inv(X_b.T.dot(X_b)).dot(X_b.T).dot(y)
            except np.linalg.LinAlgError:
                theta = np.linalg.pinv(X_b.T.dot(X_b)).dot(X_b.T).dot(y)
            model.parameters["theta"] = theta.tolist()
            predictions = X_b.dot(theta)
            ss_total = np.sum((y - np.mean(y)) ** 2)
            ss_residual = np.sum((y - predictions) ** 2)
            r_squared = 1 - ss_residual / ss_total if ss_total != 0 else 0
            return max(0, r_squared)
        except Exception as e:
            logger.error("Error training linear regression: %s", e)
            return 0.0

    async def _train_logistic_regression(self, model: MLModel, training_data: list[dict[str, Any]]) -> float:
        """Train a logistic regression model"""
        try:
            X = np.array([[data[feature] for feature in model.features] for data in training_data])
            y = np.array([data[model.target] for data in training_data])
            X_b = np.c_[np.ones((X.shape[0], 1)), X]
            theta = np.zeros(X_b.shape[1])
            learning_rate = 0.01
            epochs = 1000
            for _epoch in range(epochs):
                z = X_b.dot(theta)
                predictions = 1 / (1 + np.exp(-np.clip(z, -500, 500)))
                gradient = X_b.T.dot(predictions - y) / len(y)
                theta -= learning_rate * gradient
            model.parameters["theta"] = theta.tolist()
            predictions = (predictions > 0.5).astype(int)
            accuracy = float(np.mean(predictions == y))
            return accuracy
        except Exception as e:
            logger.error("Error training logistic regression: %s", e)
            return 0.0

    async def predict_with_ml_model(self, model_id: str, features: list[float]) -> dict[str, Any]:
        """Make predictions using a trained ML model"""
        try:
            if model_id not in self.models:
                return {"status": "error", "message": "Model not found"}
            model = self.models[model_id]
            if "theta" not in model.parameters:
                return {"status": "error", "message": "Model not trained"}
            theta = np.array(model.parameters["theta"])
            x = np.array([1] + features)
            if model.model_type == "linear_regression":
                prediction = float(x.dot(theta))
            elif model.model_type == "logistic_regression":
                z = x.dot(theta)
                prediction = 1 / (1 + np.exp(-np.clip(z, -500, 500)))
            else:
                return {"status": "error", "message": f"Unsupported model type: {model.model_type}"}
            prediction_record = {
                "model_id": model_id,
                "features": features,
                "prediction": prediction,
                "timestamp": datetime.now(UTC).isoformat(),
            }
            self.predictions_history.append(prediction_record)
            return {
                "status": "success",
                "model_id": model_id,
                "prediction": prediction,
                "confidence": min(1.0, max(0.0, prediction)) if model.model_type == "logistic_regression" else None,
                "predicted_at": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            logger.error("Error making ML prediction: %s", e)
            return {"status": "error", "message": str(e)}

    async def get_ai_statistics(self) -> dict[str, Any]:
        """Get comprehensive AI/ML statistics"""
        try:
            total_models = len(self.models)
            total_networks = len(self.neural_networks)
            total_predictions = len(self.predictions_history)
            model_stats = {}
            for model_id, performance_list in self.model_performance.items():
                if performance_list:
                    model_stats[model_id] = {
                        "latest_accuracy": performance_list[-1],
                        "average_accuracy": statistics.mean(performance_list),
                        "improvement": performance_list[-1] - performance_list[0] if len(performance_list) > 1 else 0,
                    }
            training_stats = {}
            for model_id, data_list in self.training_data.items():
                training_stats[model_id] = len(data_list)
            return {
                "status": "success",
                "total_models": total_models,
                "total_neural_networks": total_networks,
                "total_predictions": total_predictions,
                "model_performance": model_stats,
                "training_data_sizes": training_stats,
                "available_model_types": list({model.model_type for model in self.models.values()}),
                "last_updated": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            logger.error("Error getting AI statistics: %s", e)
            return {"status": "error", "message": str(e)}


ai_integration = AdvancedAIIntegration()
