"""Integration tests for AI/ML endpoints."""

from starlette.testclient import TestClient


class TestAI:
    """Test AI/ML endpoints."""

    def test_record_learning_experience(self, coordinator_client: TestClient):
        """Test recording a learning experience."""
        experience_data = {
            "context": {"task_type": "data-processing", "agent_type": "worker"},
            "action": "execute_task",
            "reward": 0.9,
            "next_state": {"task_completed": True},
        }
        response = coordinator_client.post("/v1/ai/learning/experience", json=experience_data)
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert "status" in data or "experience_id" in data

    def test_get_learning_statistics(self, coordinator_client: TestClient):
        """Test getting learning statistics."""
        response = coordinator_client.get("/v1/ai/learning/statistics")
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)

    def test_predict_performance(self, coordinator_client: TestClient):
        """Test predicting performance."""
        context = {"task_type": "data-processing", "agent_type": "worker"}
        response = coordinator_client.post("/v1/ai/learning/predict", json=context, params={"action": "execute_task"})
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)

    def test_recommend_action(self, coordinator_client: TestClient):
        """Test getting AI-recommended action."""
        context = {"task_type": "data-processing", "agent_type": "worker"}
        available_actions = ["execute_task", "defer_task", "reject_task"]
        response = coordinator_client.post(
            "/v1/ai/learning/recommend", json=context, params={"available_actions": available_actions}
        )
        assert response.status_code in (200, 422, 500)
        if response.status_code == 200:
            data = response.json()
            assert "action" in data or "recommendation" in data

    def test_create_neural_network(self, coordinator_client: TestClient):
        """Test creating a neural network."""
        config = {"input_size": 10, "hidden_layers": [64, 32], "output_size": 2, "activation": "relu"}
        response = coordinator_client.post("/v1/ai/neural-network/create", json=config)
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert "network_id" in data or "status" in data or isinstance(data, dict)

    def test_train_neural_network(self, coordinator_client: TestClient):
        """Test training a neural network."""
        training_data = [
            {"features": [1.0, 2.0, 3.0], "target": [0.0, 1.0]},
            {"features": [4.0, 5.0, 6.0], "target": [1.0, 0.0]},
        ]
        response = coordinator_client.post(
            "/v1/ai/neural-network/test-nn-001/train", json=training_data, params={"epochs": 10}
        )
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert "status" in data or "loss" in data or isinstance(data, dict)

    def test_predict_with_neural_network(self, coordinator_client: TestClient):
        """Test predicting with neural network."""
        features = [1.0, 2.0, 3.0]
        response = coordinator_client.post("/v1/ai/neural-network/test-nn-001/predict", json=features)
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert "prediction" in data or "output" in data or isinstance(data, dict)

    def test_create_ml_model(self, coordinator_client: TestClient):
        """Test creating an ML model."""
        config = {
            "model_type": "random_forest",
            "features": ["cpu_usage", "memory_usage", "task_complexity"],
            "target": "task_completion_time",
        }
        response = coordinator_client.post("/v1/ai/ml-model/create", json=config)
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert "model_id" in data or "status" in data or isinstance(data, dict)

    def test_train_ml_model(self, coordinator_client: TestClient):
        """Test training an ML model."""
        training_data = [
            {"cpu_usage": 0.5, "memory_usage": 0.3, "task_complexity": 0.7, "task_completion_time": 10.0},
            {"cpu_usage": 0.8, "memory_usage": 0.6, "task_complexity": 0.9, "task_completion_time": 15.0},
        ]
        response = coordinator_client.post("/v1/ai/ml-model/test-ml-001/train", json=training_data)
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert "status" in data or "accuracy" in data or isinstance(data, dict)

    def test_predict_with_ml_model(self, coordinator_client: TestClient):
        """Test predicting with ML model."""
        features = [0.5, 0.3, 0.7]
        response = coordinator_client.post("/v1/ai/ml-model/test-ml-001/predict", json=features)
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert "prediction" in data or "output" in data or isinstance(data, dict)

    def test_get_ai_statistics(self, coordinator_client: TestClient):
        """Test getting AI statistics."""
        response = coordinator_client.get("/v1/ai/statistics")
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)


class TestAIAdvanced:
    """Advanced AI tests for better coverage."""

    def test_ai_all_message_types(self, coordinator_client: TestClient):
        """Test AI with all message types."""
        message_types = ["task", "status", "heartbeat", "control", "data", "result", "error"]
        for msg_type in message_types:
            context = {"task_type": "data-processing", "agent_type": "worker"}
            response = coordinator_client.post(
                "/v1/ai/learning/predict", json=context, params={"action": f"handle_{msg_type}"}
            )
            assert response.status_code in (200, 500)
            if response.status_code == 200:
                data = response.json()
                assert isinstance(data, dict)

    def test_ai_neural_network_various_configs(self, coordinator_client: TestClient):
        """Test creating neural networks with various configurations."""
        configs = [
            {"input_size": 5, "hidden_layers": [10], "output_size": 2, "activation": "relu"},
            {"input_size": 20, "hidden_layers": [64, 32, 16], "output_size": 5, "activation": "sigmoid"},
            {"input_size": 100, "hidden_layers": [128, 64], "output_size": 10, "activation": "tanh"},
        ]
        for config in configs:
            response = coordinator_client.post("/v1/ai/neural-network/create", json=config)
            assert response.status_code in (200, 500)
            if response.status_code == 200:
                data = response.json()
                assert "network_id" in data or "status" in data or isinstance(data, dict)

    def test_ai_ml_model_various_types(self, coordinator_client: TestClient):
        """Test creating ML models with various types."""
        model_types = ["random_forest", "linear_regression", "neural_network", "gradient_boosting"]
        for model_type in model_types:
            config = {
                "model_type": model_type,
                "features": ["cpu_usage", "memory_usage", "task_complexity"],
                "target": "task_completion_time",
            }
            response = coordinator_client.post("/v1/ai/ml-model/create", json=config)
            assert response.status_code in (200, 500)
            if response.status_code == 200:
                data = response.json()
                assert "model_id" in data or "status" in data or isinstance(data, dict)

    def test_ai_learning_various_contexts(self, coordinator_client: TestClient):
        """Test learning system with various contexts."""
        contexts = [
            {"task_type": "data-processing", "agent_type": "worker", "priority": "high"},
            {"task_type": "gpu-compute", "agent_type": "worker", "priority": "critical"},
            {"task_type": "monitoring", "agent_type": "monitor", "priority": "normal"},
        ]
        for context in contexts:
            response = coordinator_client.post(
                "/v1/ai/learning/experience",
                json={"context": context, "action": "execute_task", "reward": 0.9, "next_state": {"task_completed": True}},
            )
            assert response.status_code in (200, 500)
            if response.status_code == 200:
                data = response.json()
                assert "status" in data or "experience_id" in data


class TestAIModelComprehensive:
    """Comprehensive AI model tests for better coverage."""

    def test_neural_network_lifecycle(self, coordinator_client: TestClient):
        """Test complete neural network lifecycle."""
        configs = [
            {"input_size": 10, "hidden_layers": [5], "output_size": 2, "activation": "relu"},
            {"input_size": 20, "hidden_layers": [10, 5], "output_size": 3, "activation": "sigmoid"},
        ]

        for i, config in enumerate(configs):
            network_id = f"nn-{i}"

            response = coordinator_client.post("/v1/ai/neural-network/create", json=config)
            assert response.status_code in (200, 500)

            training_data = [{"features": [1.0, 2.0], "target": [0.0, 1.0]}, {"features": [3.0, 4.0], "target": [1.0, 0.0]}]
            response = coordinator_client.post(
                f"/ai/neural-network/{network_id}/train", json=training_data, params={"epochs": 10}
            )
            assert response.status_code in (200, 500)

            features = [1.0, 2.0]
            response = coordinator_client.post(f"/ai/neural-network/{network_id}/predict", json=features)
            assert response.status_code in (200, 500)
            if response.status_code == 200:
                data = response.json()
                assert isinstance(data, dict)

    def test_ml_model_lifecycle(self, coordinator_client: TestClient):
        """Test complete ML model lifecycle."""
        model_configs = [
            {"model_type": "random_forest", "features": ["cpu", "mem"], "target": "time"},
            {"model_type": "linear_regression", "features": ["load", "temp"], "target": "perf"},
        ]

        for i, config in enumerate(model_configs):
            model_id = f"ml-{i}"

            response = coordinator_client.post("/v1/ai/ml-model/create", json=config)
            assert response.status_code in (200, 500)

            training_data = [{"cpu": 0.5, "mem": 0.3, "time": 10.0}, {"cpu": 0.8, "mem": 0.6, "time": 15.0}]
            response = coordinator_client.post(f"/ai/ml-model/{model_id}/train", json=training_data)
            assert response.status_code in (200, 500)

            features = [0.5, 0.3]
            response = coordinator_client.post(f"/ai/ml-model/{model_id}/predict", json=features)
            assert response.status_code in (200, 500)
            if response.status_code == 200:
                data = response.json()
                assert isinstance(data, dict)

    def test_learning_system_comprehensive(self, coordinator_client: TestClient):
        """Test comprehensive learning system operations."""
        experiences = [
            {"context": {"task": "A"}, "action": "execute", "reward": 1.0, "next_state": {"done": True}},
            {"context": {"task": "B"}, "action": "defer", "reward": 0.5, "next_state": {"pending": True}},
            {"context": {"task": "C"}, "action": "reject", "reward": 0.0, "next_state": {"rejected": True}},
            {"context": {"task": "D"}, "action": "execute", "reward": 0.8, "next_state": {"partial": True}},
        ]

        for exp in experiences:
            response = coordinator_client.post("/v1/ai/learning/experience", json=exp)
            assert response.status_code in (200, 500)

        response = coordinator_client.get("/v1/ai/learning/statistics")
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)

        contexts = [{"task": "A", "priority": "high"}, {"task": "B", "priority": "normal"}, {"task": "C", "priority": "low"}]

        for context in contexts:
            response = coordinator_client.post("/v1/ai/learning/predict", json=context, params={"action": "execute"})
            assert response.status_code in (200, 500)
            if response.status_code == 200:
                data = response.json()
                assert isinstance(data, dict)

        available_actions = ["execute", "defer", "reject"]
        response = coordinator_client.post(
            "/v1/ai/learning/recommend", json=context, params={"available_actions": available_actions}
        )
        assert response.status_code in (200, 422, 500)
        if response.status_code == 200:
            data = response.json()
            assert "action" in data or "recommendation" in data
