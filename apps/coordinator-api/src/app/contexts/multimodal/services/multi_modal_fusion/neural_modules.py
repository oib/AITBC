"""
Neural Network Modules for Multi-Modal Fusion
Contains PyTorch neural network components for multi-modal fusion architectures
"""

import numpy as np  # type: ignore[import-not-found]
import torch
import torch.nn as nn
import torch.nn.functional as F


class CrossModalAttention(nn.Module):  # type: ignore[misc]
    """Cross-modal attention mechanism for multi-modal fusion"""

    def __init__(self, embed_dim: int, num_heads: int = 8):
        super().__init__()
        self.embed_dim = embed_dim
        self.num_heads = num_heads
        self.head_dim = embed_dim // num_heads

        assert self.head_dim * num_heads == embed_dim, "embed_dim must be divisible by num_heads"

        self.query = nn.Linear(embed_dim, embed_dim)
        self.key = nn.Linear(embed_dim, embed_dim)
        self.value = nn.Linear(embed_dim, embed_dim)
        self.dropout = nn.Dropout(0.1)

    def forward(
        self,
        query_modal: torch.Tensor,
        key_modal: torch.Tensor,
        value_modal: torch.Tensor,
        mask: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            query_modal: (batch_size, seq_len_q, embed_dim)
            key_modal: (batch_size, seq_len_k, embed_dim)
            value_modal: (batch_size, seq_len_v, embed_dim)
            mask: (batch_size, seq_len_q, seq_len_k)
        """
        batch_size, seq_len_q, _ = query_modal.size()
        seq_len_k = key_modal.size(1)

        # Linear projections
        Q = self.query(query_modal)  # (batch_size, seq_len_q, embed_dim)
        K = self.key(key_modal)  # (batch_size, seq_len_k, embed_dim)
        V = self.value(value_modal)  # (batch_size, seq_len_v, embed_dim)

        # Reshape for multi-head attention
        Q = Q.view(batch_size, seq_len_q, self.num_heads, self.head_dim).transpose(1, 2)
        K = K.view(batch_size, seq_len_k, self.num_heads, self.head_dim).transpose(1, 2)
        V = V.view(batch_size, seq_len_k, self.num_heads, self.head_dim).transpose(1, 2)

        # Scaled dot-product attention
        scores = torch.matmul(Q, K.transpose(-2, -1)) / np.sqrt(self.head_dim)

        if mask is not None:
            scores = scores.masked_fill(mask == 0, -1e9)

        attention_weights = F.softmax(scores, dim=-1)
        attention_weights = self.dropout(attention_weights)

        # Apply attention to values
        context = torch.matmul(attention_weights, V)

        # Concatenate heads
        context = context.transpose(1, 2).contiguous().view(batch_size, seq_len_q, self.embed_dim)

        return context, attention_weights


class MultiModalTransformer(nn.Module):  # type: ignore[misc]
    """Transformer-based multi-modal fusion architecture"""

    def __init__(self, modality_dims: dict[str, int], embed_dim: int = 512, num_layers: int = 6, num_heads: int = 8):
        super().__init__()
        self.modality_dims = modality_dims
        self.embed_dim = embed_dim

        # Modality-specific encoders
        self.modality_encoders = nn.ModuleDict()
        for modality, dim in modality_dims.items():
            self.modality_encoders[modality] = nn.Sequential(nn.Linear(dim, embed_dim), nn.ReLU(), nn.Dropout(0.1))

        # Cross-modal attention layers
        self.cross_attention_layers = nn.ModuleList([CrossModalAttention(embed_dim, num_heads) for _ in range(num_layers)])

        # Feed-forward networks
        self.feed_forward = nn.ModuleList(
            [
                nn.Sequential(
                    nn.Linear(embed_dim, embed_dim * 4), nn.ReLU(), nn.Dropout(0.1), nn.Linear(embed_dim * 4, embed_dim)
                )
                for _ in range(num_layers)
            ]
        )

        # Layer normalization
        self.layer_norms = nn.ModuleList([nn.LayerNorm(embed_dim) for _ in range(num_layers * 2)])

        # Output projection
        self.output_projection = nn.Sequential(
            nn.Linear(embed_dim, embed_dim), nn.ReLU(), nn.Dropout(0.1), nn.Linear(embed_dim, embed_dim)
        )

    def forward(self, modal_inputs: dict[str, torch.Tensor]) -> torch.Tensor:
        """
        Args:
            modal_inputs: Dict mapping modality names to input tensors
        """
        # Encode each modality
        encoded_modalities = {}
        for modality, input_tensor in modal_inputs.items():
            if modality in self.modality_encoders:
                encoded_modalities[modality] = self.modality_encoders[modality](input_tensor)

        # Cross-modal fusion
        modality_names = list(encoded_modalities.keys())
        fused_features = list(encoded_modalities.values())

        for i, attention_layer in enumerate(self.cross_attention_layers):
            # Apply attention between all modality pairs
            new_features = []

            for j, _modality in enumerate(modality_names):
                # Query from current modality, keys/values from all modalities
                query = fused_features[j]

                # Concatenate all modalities for keys and values
                keys = torch.cat([feat for k, feat in enumerate(fused_features) if k != j], dim=1)
                values = torch.cat([feat for k, feat in enumerate(fused_features) if k != j], dim=1)

                # Apply cross-modal attention
                attended_feat, _ = attention_layer(query, keys, values)
                new_features.append(attended_feat)

            # Residual connection and layer norm
            fused_features = []
            for j, feat in enumerate(new_features):
                residual = encoded_modalities[modality_names[j]]
                fused = self.layer_norms[i * 2](residual + feat)

                # Feed-forward
                ff_output = self.feed_forward[i](fused)
                fused = self.layer_norms[i * 2 + 1](fused + ff_output)
                fused_features.append(fused)

            encoded_modalities = dict(zip(modality_names, fused_features, strict=False))

        # Global fusion - concatenate all modalities
        global_fused = torch.cat(list(encoded_modalities.values()), dim=1)

        # Global attention pooling
        pooled = torch.mean(global_fused, dim=1)  # Global average pooling

        # Output projection
        output = self.output_projection(pooled)

        return output


class AdaptiveModalityWeighting(nn.Module):  # type: ignore[misc]
    """Dynamic modality weighting based on context and performance"""

    def __init__(self, num_modalities: int, embed_dim: int = 256):
        super().__init__()
        self.num_modalities = num_modalities

        # Context encoder
        self.context_encoder = nn.Sequential(
            nn.Linear(embed_dim, embed_dim // 2), nn.ReLU(), nn.Dropout(0.1), nn.Linear(embed_dim // 2, num_modalities)
        )

        # Performance-based weighting
        self.performance_encoder = nn.Sequential(
            nn.Linear(num_modalities, embed_dim // 2), nn.ReLU(), nn.Dropout(0.1), nn.Linear(embed_dim // 2, num_modalities)
        )

        # Weight normalization
        self.weight_normalization = nn.Softmax(dim=-1)

    def forward(
        self, modality_features: torch.Tensor, context: torch.Tensor, performance_scores: torch.Tensor | None = None
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            modality_features: (batch_size, num_modalities, feature_dim)
            context: (batch_size, context_dim)
            performance_scores: (batch_size, num_modalities) - optional performance metrics
        """
        batch_size, num_modalities, feature_dim = modality_features.size()

        # Context-based weights
        context_weights = self.context_encoder(context)  # (batch_size, num_modalities)

        # Combine with performance scores if available
        if performance_scores is not None:
            perf_weights = self.performance_encoder(performance_scores)
            combined_weights = context_weights + perf_weights
        else:
            combined_weights = context_weights

        # Normalize weights
        weights = self.weight_normalization(combined_weights)  # (batch_size, num_modalities)

        # Apply weights to features
        weighted_features = modality_features * weights.unsqueeze(-1)

        # Weighted sum
        fused_features = torch.sum(weighted_features, dim=1)  # (batch_size, feature_dim)

        return fused_features, weights
