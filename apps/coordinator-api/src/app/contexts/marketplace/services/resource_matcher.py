"""Resource Matcher Service for ML-based search and recommendations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlmodel import Session, select

from aitbc import get_logger

from ..domain.gpu_marketplace import (
    GPURegistry,
    ResourceEmbedding,
    SearchHistory,
    UserProfile,
)

logger = get_logger(__name__)


class ResourceMatcher:
    """Advanced resource matching with ML-based ranking."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def advanced_search(
        self,
        filters: dict[str, Any],
        user_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Enhanced filtering with ML-based ranking."""
        try:
            # Build base query
            stmt = select(GPURegistry).where(GPURegistry.status == "available")
            
            # Apply filters
            if "gpu_memory_min" in filters:
                stmt = stmt.where(GPURegistry.memory_gb >= filters["gpu_memory_min"])
            if "gpu_memory_max" in filters:
                stmt = stmt.where(GPURegistry.memory_gb <= filters["gpu_memory_max"])
            if "model" in filters:
                stmt = stmt.where(GPURegistry.model.ilike(f"%{filters['model']}%"))
            if "region" in filters:
                stmt = stmt.where(GPURegistry.region == filters["region"])
            if "price_max" in filters:
                stmt = stmt.where(GPURegistry.price_per_hour <= filters["price_max"])
            if "capabilities" in filters:
                for cap in filters["capabilities"]:
                    stmt = stmt.where(GPURegistry.capabilities.contains(cap))
            
            # Execute query
            gpus = self.session.execute(stmt).scalars().all()
            
            # Track search history
            if user_id:
                self._track_search(user_id, filters, len(gpus))
            
            # Apply ML-based ranking
            ranked_gpus = self._rank_resources(gpus, user_id, filters)
            
            # Convert to dict format
            results = [
                {
                    "gpu_id": gpu.id,
                    "model": gpu.model,
                    "memory_gb": gpu.memory_gb,
                    "cuda_version": gpu.cuda_version,
                    "region": gpu.region,
                    "price_per_hour": gpu.price_per_hour,
                    "capabilities": gpu.capabilities,
                    "average_rating": gpu.average_rating,
                    "rank_score": rank,
                }
                for gpu, rank in ranked_gpus[:limit]
            ]
            
            return results
        except Exception as e:
            logger.error(f"Failed to perform advanced search: {e}")
            return []

    def get_recommendations(self, user_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """Get ML-based recommendations for a user."""
        try:
            # Get user profile
            profile = self.session.execute(
                select(UserProfile).where(UserProfile.user_id == user_id)
            ).first()
            
            if not profile:
                # Return popular GPUs if no profile
                return self._get_popular_gpus(limit)
            
            # Build filters from profile
            filters = {
                "gpu_memory_min": profile.min_memory_gb,
                "price_max": profile.price_range_max,
            }
            
            if profile.preferred_gpu_models:
                filters["model"] = profile.preferred_gpu_models[0]  # Use first preferred model
            
            if profile.preferred_regions:
                filters["region"] = profile.preferred_regions[0]
            
            # Perform search with profile filters
            results = self.advanced_search(filters, user_id, limit)
            
            return results
        except Exception as e:
            logger.error(f"Failed to get recommendations: {e}")
            return []

    def generate_embeddings(self, resource_id: str) -> list[float]:
        """Generate vector embeddings for a resource."""
        try:
            # Get resource
            gpu = self.session.execute(
                select(GPURegistry).where(GPURegistry.id == resource_id)
            ).first()
            
            if not gpu:
                return []
            
            # Simple embedding based on features (would use ML model in production)
            embedding = self._create_simple_embedding(gpu)
            
            # Store embedding
            existing = self.session.execute(
                select(ResourceEmbedding).where(ResourceEmbedding.resource_id == resource_id)
            ).first()
            
            if existing:
                existing.embedding = embedding
                existing.updated_at = datetime.now(UTC)
            else:
                new_embedding = ResourceEmbedding(
                    resource_id=resource_id,
                    embedding=embedding,
                )
                self.session.add(new_embedding)
            
            self.session.commit()
            return embedding
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            return []

    def find_similar_resources(self, resource_id: str, limit: int = 5) -> list[dict[str, Any]]:
        """Find similar resources using embedding similarity."""
        try:
            # Get target resource embedding
            target_embedding = self.session.execute(
                select(ResourceEmbedding).where(ResourceEmbedding.resource_id == resource_id)
            ).first()
            
            if not target_embedding:
                return []
            
            # Get all embeddings
            embeddings = self.session.execute(select(ResourceEmbedding)).scalars().all()
            
            # Calculate similarity scores
            similarities = []
            for emb in embeddings:
                if emb.resource_id != resource_id:
                    similarity = self._cosine_similarity(target_embedding.embedding, emb.embedding)
                    similarities.append((emb.resource_id, similarity))
            
            # Sort by similarity
            similarities.sort(key=lambda x: x[1], reverse=True)
            
            # Get similar resources
            similar_ids = [sid for sid, _ in similarities[:limit]]
            similar_gpus = self.session.execute(
                select(GPURegistry).where(GPURegistry.id.in_(similar_ids))
            ).scalars().all()
            
            # Create id to similarity mapping
            similarity_map = {sid: sim for sid, sim in similarities}
            
            results = [
                {
                    "gpu_id": gpu.id,
                    "model": gpu.model,
                    "memory_gb": gpu.memory_gb,
                    "price_per_hour": gpu.price_per_hour,
                    "similarity_score": similarity_map.get(gpu.id, 0.0),
                }
                for gpu in similar_gpus
            ]
            
            return results
        except Exception as e:
            logger.error(f"Failed to find similar resources: {e}")
            return []

    def _track_search(self, user_id: str, filters: dict[str, Any], results_count: int) -> None:
        """Track user search for ML training."""
        try:
            search = SearchHistory(
                user_id=user_id,
                filters=filters,
                results_count=results_count,
            )
            self.session.add(search)
            self.session.commit()
        except Exception as e:
            logger.error(f"Failed to track search: {e}")

    def _rank_resources(
        self, gpus: list[GPURegistry], user_id: str | None, filters: dict[str, Any]
    ) -> list[tuple[GPURegistry, float]]:
        """Rank resources using ML-based scoring."""
        ranked = []
        
        for gpu in gpus:
            # Calculate rank score
            score = 0.0
            
            # Price score (lower is better)
            if gpu.price_per_hour:
                price_score = 1.0 / (1.0 + gpu.price_per_hour)
                score += price_score * 0.3
            
            # Rating score
            if gpu.average_rating:
                rating_score = gpu.average_rating / 5.0
                score += rating_score * 0.3
            
            # Capacity score
            if gpu.capacity:
                capacity_score = gpu.capacity / 100.0
                score += capacity_score * 0.2
            
            # Availability score
            if gpu.status == "available":
                score += 0.2
            
            ranked.append((gpu, score))
        
        # Sort by score
        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked

    def _get_popular_gpus(self, limit: int) -> list[dict[str, Any]]:
        """Get popular GPUs based on rating and bookings."""
        gpus = self.session.execute(
            select(GPURegistry)
            .where(GPURegistry.status == "available")
            .order_by(GPURegistry.average_rating.desc())
            .limit(limit)
        ).scalars().all()
        
        return [
            {
                "gpu_id": gpu.id,
                "model": gpu.model,
                "memory_gb": gpu.memory_gb,
                "cuda_version": gpu.cuda_version,
                "region": gpu.region,
                "price_per_hour": gpu.price_per_hour,
                "capabilities": gpu.capabilities,
                "average_rating": gpu.average_rating,
                "rank_score": gpu.average_rating,
            }
            for gpu in gpus
        ]

    def _create_simple_embedding(self, gpu: GPURegistry) -> list[float]:
        """Create simple embedding based on GPU features."""
        # Normalize features to 0-1 range
        memory_norm = min(1.0, gpu.memory_gb / 80.0)  # Assume 80GB max
        price_norm = min(1.0, gpu.price_per_hour / 10.0)  # Assume $10/hr max
        rating_norm = gpu.average_rating / 5.0
        
        # Create embedding vector
        embedding = [
            memory_norm,
            price_norm,
            rating_norm,
            1.0 if gpu.status == "available" else 0.0,
            len(gpu.capabilities) / 10.0,  # Normalize capabilities count
        ]
        
        return embedding

    def _cosine_similarity(self, vec1: list[float], vec2: list[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = sum(a * a for a in vec1) ** 0.5
        magnitude2 = sum(b * b for b in vec2) ** 0.5
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        return dot_product / (magnitude1 * magnitude2)
