"""Scoring Engine Implementation for Pool Hub"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import math


@dataclass
class ScoreComponents:
    """Breakdown of miner score components"""
    reliability: float  # Based on uptime and success rate
    performance: float  # Based on response time and throughput
    capacity: float     # Based on GPU specs and availability
    reputation: float   # Based on historical performance
    total: float


class ScoringEngine:
    """Engine for scoring and ranking miners"""
    
    # Scoring weights
    WEIGHT_RELIABILITY = 0.35
    WEIGHT_PERFORMANCE = 0.30
    WEIGHT_CAPACITY = 0.20
    WEIGHT_REPUTATION = 0.15
    
    # Thresholds
    MIN_JOBS_FOR_RANKING = 10
    DECAY_HALF_LIFE_DAYS = 7
    
    def __init__(self):
        self._score_cache: Dict[str, float] = {}
        self._rank_cache: Dict[str, int] = {}
        self._history: Dict[str, List[Dict]] = {}
    
    async def calculate_score(self, miner) -> float:
        """Calculate overall score for a miner."""
        components = await self.get_score_breakdown(miner)
        return components.total
    
    async def get_score_breakdown(self, miner) -> ScoreComponents:
        """Get detailed score breakdown for a miner."""
        reliability = self._calculate_reliability(miner)
        performance = self._calculate_performance(miner)
        capacity = self._calculate_capacity(miner)
        reputation = self._calculate_reputation(miner)
        
        total = (
            reliability * self.WEIGHT_RELIABILITY +
            performance * self.WEIGHT_PERFORMANCE +
            capacity * self.WEIGHT_CAPACITY +
            reputation * self.WEIGHT_REPUTATION
        )
        
        return ScoreComponents(
            reliability=reliability,
            performance=performance,
            capacity=capacity,
            reputation=reputation,
            total=total
        )
    
    def _calculate_reliability(self, miner) -> float:
        """Calculate reliability score (0-100)."""
        # Uptime component (50%)
        uptime_score = miner.uptime_percent
        
        # Success rate component (50%)
        total_jobs = miner.jobs_completed + miner.jobs_failed
        if total_jobs > 0:
            success_rate = (miner.jobs_completed / total_jobs) * 100
        else:
            success_rate = 100.0  # New miners start with perfect score
        
        # Heartbeat freshness penalty
        heartbeat_age = (datetime.utcnow() - miner.last_heartbeat).total_seconds()
        if heartbeat_age > 300:  # 5 minutes
            freshness_penalty = min(20, heartbeat_age / 60)
        else:
            freshness_penalty = 0
        
        score = (uptime_score * 0.5 + success_rate * 0.5) - freshness_penalty
        return max(0, min(100, score))
    
    def _calculate_performance(self, miner) -> float:
        """Calculate performance score (0-100)."""
        # Base score from GPU utilization efficiency
        if miner.gpu_utilization > 0:
            # Optimal utilization is 60-80%
            if 60 <= miner.gpu_utilization <= 80:
                utilization_score = 100
            elif miner.gpu_utilization < 60:
                utilization_score = 70 + (miner.gpu_utilization / 60) * 30
            else:
                utilization_score = 100 - (miner.gpu_utilization - 80) * 2
        else:
            utilization_score = 50  # Unknown utilization
        
        # Jobs per hour (if we had timing data)
        throughput_score = min(100, miner.jobs_completed / max(1, self._get_hours_active(miner)) * 10)
        
        return (utilization_score * 0.6 + throughput_score * 0.4)
    
    def _calculate_capacity(self, miner) -> float:
        """Calculate capacity score (0-100)."""
        gpu_info = miner.gpu_info or {}
        
        # GPU memory score
        memory_gb = self._parse_memory(gpu_info.get("memory", "0"))
        memory_score = min(100, memory_gb * 4)  # 24GB = 96 points
        
        # Concurrent job capacity
        capacity_score = min(100, miner.max_concurrent_jobs * 25)
        
        # Current availability
        if miner.current_jobs < miner.max_concurrent_jobs:
            availability = ((miner.max_concurrent_jobs - miner.current_jobs) / 
                          miner.max_concurrent_jobs) * 100
        else:
            availability = 0
        
        return (memory_score * 0.4 + capacity_score * 0.3 + availability * 0.3)
    
    def _calculate_reputation(self, miner) -> float:
        """Calculate reputation score (0-100)."""
        # New miners start at 70
        if miner.jobs_completed < self.MIN_JOBS_FOR_RANKING:
            return 70.0
        
        # Historical success with time decay
        history = self._history.get(miner.miner_id, [])
        if not history:
            return miner.score  # Use stored score
        
        weighted_sum = 0
        weight_total = 0
        
        for record in history:
            age_days = (datetime.utcnow() - record["timestamp"]).days
            weight = math.exp(-age_days / self.DECAY_HALF_LIFE_DAYS)
            
            if record["success"]:
                weighted_sum += 100 * weight
            else:
                weighted_sum += 0 * weight
            
            weight_total += weight
        
        if weight_total > 0:
            return weighted_sum / weight_total
        return 70.0
    
    def _get_hours_active(self, miner) -> float:
        """Get hours since miner registered."""
        delta = datetime.utcnow() - miner.registered_at
        return max(1, delta.total_seconds() / 3600)
    
    def _parse_memory(self, memory_str: str) -> float:
        """Parse memory string to GB."""
        try:
            if isinstance(memory_str, (int, float)):
                return float(memory_str)
            memory_str = str(memory_str).upper()
            if "GB" in memory_str:
                return float(memory_str.replace("GB", "").strip())
            if "MB" in memory_str:
                return float(memory_str.replace("MB", "").strip()) / 1024
            return float(memory_str)
        except (ValueError, TypeError):
            return 0.0
    
    async def rank_miners(self, miners: List, job: Any = None) -> List:
        """Rank miners by score, optionally considering job requirements."""
        scored = []
        
        for miner in miners:
            score = await self.calculate_score(miner)
            
            # Bonus for matching capabilities
            if job and hasattr(job, 'model'):
                if job.model in miner.capabilities:
                    score += 5
            
            # Penalty for high current load
            if miner.current_jobs > 0:
                load_ratio = miner.current_jobs / miner.max_concurrent_jobs
                score -= load_ratio * 10
            
            scored.append((miner, score))
        
        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)
        
        return [m for m, s in scored]
    
    async def get_rank(self, miner_id: str) -> int:
        """Get miner's current rank."""
        return self._rank_cache.get(miner_id, 0)
    
    async def record_success(self, miner_id: str, metrics: Dict[str, Any] = None):
        """Record a successful job completion."""
        if miner_id not in self._history:
            self._history[miner_id] = []
        
        self._history[miner_id].append({
            "timestamp": datetime.utcnow(),
            "success": True,
            "metrics": metrics or {}
        })
        
        # Keep last 1000 records
        if len(self._history[miner_id]) > 1000:
            self._history[miner_id] = self._history[miner_id][-1000:]
    
    async def record_failure(self, miner_id: str, error: Optional[str] = None):
        """Record a job failure."""
        if miner_id not in self._history:
            self._history[miner_id] = []
        
        self._history[miner_id].append({
            "timestamp": datetime.utcnow(),
            "success": False,
            "error": error
        })
    
    async def update_rankings(self, miners: List):
        """Update global rankings for all miners."""
        scored = []
        
        for miner in miners:
            score = await self.calculate_score(miner)
            scored.append((miner.miner_id, score))
        
        scored.sort(key=lambda x: x[1], reverse=True)
        
        for rank, (miner_id, score) in enumerate(scored, 1):
            self._rank_cache[miner_id] = rank
            self._score_cache[miner_id] = score
