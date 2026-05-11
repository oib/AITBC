"""
Tests for multi-modal fusion engine
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone


@pytest.mark.unit
class TestMultiModalFusionEngine:
    """Test Multi-Modal Fusion Engine"""

    def test_fusion_engine_initialization(self):
        """Test fusion engine initialization"""
        from app.services.multi_modal_fusion.fusion_engine import MultiModalFusionEngine

        engine = MultiModalFusionEngine()
        
        assert engine.device is not None
        assert engine.fusion_models == {}
        assert engine.performance_history == {}
        assert len(engine.fusion_strategies) > 0
        assert len(engine.modality_types) > 0

    def test_calculate_modality_weights(self):
        """Test modality weight calculation"""
        from app.services.multi_modal_fusion.fusion_engine import MultiModalFusionEngine

        engine = MultiModalFusionEngine()
        
        modalities = ["text", "image", "audio"]
        weights = engine.calculate_modality_weights(modalities)
        
        assert len(weights) == 3
        assert "text" in weights
        assert "image" in weights
        assert "audio" in weights
        assert abs(sum(weights.values()) - 1.0) < 0.01  # Weights should sum to ~1

    def test_calculate_synergy_score(self):
        """Test synergy score calculation"""
        from app.services.multi_modal_fusion.fusion_engine import MultiModalFusionEngine

        engine = MultiModalFusionEngine()
        
        # Test high synergy modalities
        score1 = engine.calculate_synergy_score(["text", "video"])
        assert score1 > 0.8
        
        # Test low synergy modalities
        score2 = engine.calculate_synergy_score(["audio", "structured"])
        assert score2 < 0.6
        
        # Test single modality
        score3 = engine.calculate_synergy_score(["text"])
        assert score3 == 0.5

    def test_estimate_complexity(self):
        """Test complexity estimation"""
        from app.services.multi_modal_fusion.fusion_engine import MultiModalFusionEngine

        engine = MultiModalFusionEngine()
        
        # Low complexity
        complexity1 = engine.estimate_complexity(["model1", "model2"], ["text"])
        assert complexity1 == "low"
        
        # High complexity
        complexity2 = engine.estimate_complexity(["model1", "model2", "model3", "model4"], ["text", "image", "video"])
        assert complexity2 in ["high", "very_high"]

    def test_estimate_memory_requirement(self):
        """Test memory requirement estimation"""
        from app.services.multi_modal_fusion.fusion_engine import MultiModalFusionEngine

        engine = MultiModalFusionEngine()
        
        memory1 = engine.estimate_memory_requirement(["model1", "model2"], "ensemble")
        memory2 = engine.estimate_memory_requirement(["model1", "model2"], "multi_modal")
        
        assert memory2 > memory1  # multi-modal should require more memory

    def test_prepare_batch_modal_data(self):
        """Test batch modal data preparation"""
        from app.services.multi_modal_fusion.fusion_engine import MultiModalFusionEngine

        engine = MultiModalFusionEngine()
        
        modal_data = {"text": "sample text", "image": "sample image"}
        batch_size = 8
        
        batch_data = engine.prepare_batch_modal_data(modal_data, batch_size)
        
        assert "text" in batch_data
        assert "image" in batch_data
        assert batch_data["text"].shape[0] == batch_size

    def test_calculate_model_weights(self):
        """Test model weight calculation"""
        from app.services.multi_modal_fusion.fusion_engine import MultiModalFusionEngine

        engine = MultiModalFusionEngine()
        
        base_models = ["model1", "model2", "model3"]
        weights = engine.calculate_model_weights(base_models)
        
        assert len(weights) == 3
        for model in base_models:
            assert model in weights
            assert weights[model] == 1.0 / 3  # Equal weighting

    @patch('app.services.multi_modal_fusion.fusion_engine.Session')
    async def test_adaptive_fusion_selection(self, mock_session):
        """Test adaptive fusion strategy selection"""
        from app.services.multi_modal_fusion.fusion_engine import MultiModalFusionEngine

        engine = MultiModalFusionEngine()
        
        modal_data = {"text": "sample", "image": "sample"}
        performance_requirements = {"accuracy": 0.9, "efficiency": 0.8}
        
        result = await engine.adaptive_fusion_selection(modal_data, performance_requirements)
        
        assert "selected_strategy" in result
        assert "strategy_scores" in result
        assert "recommendation" in result

    def test_process_modality(self):
        """Test modality processing"""
        from app.services.multi_modal_fusion.fusion_engine import MultiModalFusionEngine

        engine = MultiModalFusionEngine()
        
        # Test text modality
        result = engine.process_modality("sample text", "text")
        assert "features" in result
        assert "embeddings" in result
        assert "confidence" in result
        assert result["confidence"] == 0.85
        
        # Test image modality
        result = engine.process_modality("sample image", "image")
        assert result["confidence"] == 0.80

    def test_weighted_combination(self):
        """Test weighted combination of results"""
        from app.services.multi_modal_fusion.fusion_engine import MultiModalFusionEngine

        engine = MultiModalFusionEngine()
        
        results = {
            "modality1": {
                "result": {"features": {"feature1": 0.5, "feature2": 0.5}},
                "weight": 0.6,
                "confidence": 0.8
            },
            "modality2": {
                "result": {"features": {"feature1": 0.3, "feature2": 0.7}},
                "weight": 0.4,
                "confidence": 0.9
            }
        }
        
        combined = engine.weighted_combination(results)
        
        assert "features" in combined
        assert "confidence" in combined
        assert "feature1" in combined["features"]
        assert "feature2" in combined["features"]

    @patch('app.services.multi_modal_fusion.fusion_engine.Session')
    async def test_create_fusion_model(self, mock_session):
        """Test fusion model creation"""
        from app.services.multi_modal_fusion.fusion_engine import MultiModalFusionEngine
        from app.domain.agent_performance import FusionModel

        engine = MultiModalFusionEngine()
        mock_session_instance = MagicMock()
        
        mock_fusion_model = FusionModel(
            fusion_id="fusion_abc123",
            model_name="Test Fusion Model",
            fusion_type="multi_modal",
            base_models=["model1", "model2"],
            model_weights={"model1": 0.5, "model2": 0.5},
            fusion_strategy="ensemble_fusion",
            input_modalities=["text", "image"],
            modality_weights={"text": 0.6, "image": 0.4},
            computational_complexity="medium",
            memory_requirement=4.0,
            status="training"
        )
        
        mock_session_instance.add.return_value = None
        mock_session_instance.commit.return_value = None
        mock_session_instance.refresh.return_value = mock_fusion_model
        
        result = await engine.create_fusion_model(
            mock_session_instance,
            model_name="Test Fusion Model",
            fusion_type="multi_modal",
            base_models=["model1", "model2"],
            input_modalities=["text", "image"],
            fusion_strategy="ensemble_fusion"
        )
        
        assert result.fusion_id is not None
        assert result.model_name == "Test Fusion Model"
        assert result.status == "training"

    @patch('app.services.multi_modal_fusion.fusion_engine.Session')
    async def test_simulate_fusion_training(self, mock_session):
        """Test fusion training simulation"""
        from app.services.multi_modal_fusion.fusion_engine import MultiModalFusionEngine
        from app.domain.agent_performance import FusionModel

        engine = MultiModalFusionEngine()
        
        mock_fusion_model = FusionModel(
            fusion_id="fusion_abc123",
            model_name="Test Fusion Model",
            fusion_type="multi_modal",
            base_models=["model1", "model2"],
            model_weights={"model1": 0.5, "model2": 0.5},
            fusion_strategy="ensemble_fusion",
            input_modalities=["text", "image"],
            modality_weights={"text": 0.6, "image": 0.4},
            computational_complexity="medium",
            memory_requirement=4.0,
            status="training"
        )
        
        result = await engine.simulate_fusion_training(mock_fusion_model)
        
        assert "performance" in result
        assert "synergy" in result
        assert "robustness" in result
        assert "inference_time" in result
        assert "training_time" in result
