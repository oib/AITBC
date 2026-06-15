"""
Tests for multi-modal fusion neural modules
"""

import pytest
import torch


@pytest.mark.unit
class TestCrossModalAttention:
    """Test Cross Modal Attention neural network"""

    def test_cross_modal_attention_initialization(self):
        """Test cross-modal attention initialization"""
        from app.services.multi_modal_fusion.neural_modules import CrossModalAttention

        attention = CrossModalAttention(embed_dim=512, num_heads=8)

        assert attention.embed_dim == 512
        assert attention.num_heads == 8
        assert attention.head_dim == 64

    def test_cross_modal_attention_forward(self):
        """Test cross-modal attention forward pass"""
        from app.services.multi_modal_fusion.neural_modules import CrossModalAttention

        attention = CrossModalAttention(embed_dim=512, num_heads=8)

        batch_size = 4
        seq_len_q = 10
        seq_len_k = 15

        query_modal = torch.randn(batch_size, seq_len_q, 512)
        key_modal = torch.randn(batch_size, seq_len_k, 512)
        value_modal = torch.randn(batch_size, seq_len_k, 512)

        context, attention_weights = attention(query_modal, key_modal, value_modal)

        assert context.shape == (batch_size, seq_len_q, 512)
        assert attention_weights.shape == (batch_size, 8, seq_len_q, seq_len_k)


@pytest.mark.unit
class TestMultiModalTransformer:
    """Test Multi-Modal Transformer neural network"""

    def test_multimodal_transformer_initialization(self):
        """Test multi-modal transformer initialization"""
        from app.services.multi_modal_fusion.neural_modules import MultiModalTransformer

        modality_dims = {"text": 768, "image": 2048, "audio": 1024}
        transformer = MultiModalTransformer(modality_dims=modality_dims, embed_dim=512, num_layers=6, num_heads=8)

        assert transformer.modality_dims == modality_dims
        assert transformer.embed_dim == 512
        assert len(transformer.modality_encoders) == 3

    def test_multimodal_transformer_forward(self):
        """Test multi-modal transformer forward pass"""
        from app.services.multi_modal_fusion.neural_modules import MultiModalTransformer

        modality_dims = {"text": 768, "image": 2048}
        transformer = MultiModalTransformer(modality_dims=modality_dims, embed_dim=512, num_layers=2, num_heads=4)

        batch_size = 4
        seq_len = 10

        modal_inputs = {"text": torch.randn(batch_size, seq_len, 768), "image": torch.randn(batch_size, seq_len, 2048)}

        output = transformer(modal_inputs)

        assert output.shape == (batch_size, 512)


@pytest.mark.unit
class TestAdaptiveModalityWeighting:
    """Test Adaptive Modality Weighting neural network"""

    def test_adaptive_weighting_initialization(self):
        """Test adaptive weighting initialization"""
        from app.services.multi_modal_fusion.neural_modules import AdaptiveModalityWeighting

        weighting = AdaptiveModalityWeighting(num_modalities=3, embed_dim=256)

        assert weighting.num_modalities == 3
        assert weighting.context_encoder is not None
        assert weighting.performance_encoder is not None

    def test_adaptive_weighting_forward(self):
        """Test adaptive weighting forward pass"""
        from app.services.multi_modal_fusion.neural_modules import AdaptiveModalityWeighting

        weighting = AdaptiveModalityWeighting(num_modalities=3, embed_dim=256)

        batch_size = 4
        feature_dim = 128

        modality_features = torch.randn(batch_size, 3, feature_dim)
        context = torch.randn(batch_size, 256)

        fused_features, weights = weighting(modality_features, context)

        assert fused_features.shape == (batch_size, feature_dim)
        assert weights.shape == (batch_size, 3)
        assert torch.allclose(weights.sum(dim=1), torch.ones(batch_size), atol=1e-5)  # Weights sum to 1

    def test_adaptive_weighting_with_performance_scores(self):
        """Test adaptive weighting with performance scores"""
        from app.services.multi_modal_fusion.neural_modules import AdaptiveModalityWeighting

        weighting = AdaptiveModalityWeighting(num_modalities=3, embed_dim=256)

        batch_size = 4
        feature_dim = 128

        modality_features = torch.randn(batch_size, 3, feature_dim)
        context = torch.randn(batch_size, 256)
        performance_scores = torch.randn(batch_size, 3)

        fused_features, weights = weighting(modality_features, context, performance_scores)

        assert fused_features.shape == (batch_size, feature_dim)
        assert weights.shape == (batch_size, 3)
