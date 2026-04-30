"""
Marketplace Adaptive Resource Scaler
Implements predictive and reactive auto-scaling of marketplace resources based on demand.
"""

import time
import asyncio
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, UTC, timedelta
import math

from aitbc import get_logger

logger = get_logger(__name__)

class ScalingPolicy:
    """Configuration for scaling behavior"""
    def __init__(
        self,
        min_nodes: int = 2,
        max_nodes: int = 100,
        target_utilization: float = 0.75,
        scale_up_threshold: float = 0.85,
        scale_down_threshold: float = 0.40,
        cooldown_period_sec: int = 300, # 5 minutes between scaling actions
        predictive_scaling: bool = True
    ):
        self.min_nodes = min_nodes
        self.max_nodes = max_nodes
        self.target_utilization = target_utilization
        self.scale_up_threshold = scale_up_threshold
        self.scale_down_threshold = scale_down_threshold
        self.cooldown_period_sec = cooldown_period_sec
        self.predictive_scaling = predictive_scaling

class ResourceScaler:
    """Adaptive resource scaling engine for the AITBC marketplace"""
    
    def __init__(self, policy: Optional[ScalingPolicy] = None):
        self.policy = policy or ScalingPolicy()
        
        # Current state
        self.current_nodes = self.policy.min_nodes
        self.active_gpu_nodes = 0
        self.active_cpu_nodes = self.policy.min_nodes
        
        self.last_scaling_action_time = 0
        self.scaling_history = []
        
        # Historical demand tracking for predictive scaling
        # Format: hour_of_week (0-167) -> avg_utilization
        self.historical_demand = {}
        
        self.is_running = False
        self._scaler_task = None
        
    async def start(self):
        if self.is_running:
            return
        self.is_running = True
        self._scaler_task = asyncio.create_task(self._scaling_loop())
        logger.info(f"Resource Scaler started (Min: {self.policy.min_nodes}, Max: {self.policy.max_nodes})")
        
    async def stop(self):
        self.is_running = False
        if self._scaler_task:
            self._scaler_task.cancel()
        logger.info("Resource Scaler stopped")
        
    def update_historical_demand(self, utilization: float):
        """Update historical data for predictive scaling"""
        now = datetime.now(datetime.UTC)
        hour_of_week = now.weekday() * 24 + now.hour
        
        if hour_of_week not in self.historical_demand:
            self.historical_demand[hour_of_week] = utilization
        else:
            # Exponential moving average (favor recent data)
            current_avg = self.historical_demand[hour_of_week]
            self.historical_demand[hour_of_week] = (current_avg * 0.9) + (utilization * 0.1)

    def _predict_demand(self, lookahead_hours: int = 1) -> float:
        """Predict expected utilization based on historical patterns"""
        if not self.policy.predictive_scaling or not self.historical_demand:
            return 0.0
            
        now = datetime.now(datetime.UTC)
        target_hour = (now.weekday() * 24 + now.hour + lookahead_hours) % 168
        
        # If we have exact data for that hour
        if target_hour in self.historical_demand:
            return self.historical_demand[target_hour]
            
        # Find nearest available data points
        available_hours = sorted(self.historical_demand.keys())
        if not available_hours:
            return 0.0
            
        # Simplistic interpolation
        return sum(self.historical_demand.values()) / len(self.historical_demand)
        
    async def _scaling_loop(self):
        """Background task that evaluates scaling rules periodically"""
        while self.is_running:
            try:
                # In a real system, we'd fetch this from the Monitor or Coordinator
                # Here we simulate fetching current metrics
                current_utilization = self._get_current_utilization()
                current_queue_depth = self._get_queue_depth()
                
                self.update_historical_demand(current_utilization)
                
                await self.evaluate_scaling(current_utilization, current_queue_depth)
                
                # Check every 10 seconds
                await asyncio.sleep(10.0)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in scaling loop: {e}")
                await asyncio.sleep(10.0)

    async def evaluate_scaling(self, current_utilization: float, queue_depth: int) -> Optional[Dict[str, Any]]:
        """Evaluate if scaling action is needed and execute if necessary"""
        now = time.time()
        
        # Check cooldown
        if now - self.last_scaling_action_time < self.policy.cooldown_period_sec:
            return None
            
        predicted_utilization = self._predict_demand()
        
        # Determine target node count
        target_nodes = self.current_nodes
        action = None
        reason = ""
        
        # Scale UP conditions
        if current_utilization > self.policy.scale_up_threshold or queue_depth > self.current_nodes * 5:
            # Reactive scale up
            desired_increase = math.ceil(self.current_nodes * (current_utilization / self.policy.target_utilization - 1.0))
            # Ensure we add at least 1, but bounded by queue depth and max_nodes
            nodes_to_add = max(1, min(desired_increase, max(1, queue_depth // 2)))
            
            target_nodes = min(self.policy.max_nodes, self.current_nodes + nodes_to_add)
            
            if target_nodes > self.current_nodes:
                action = "scale_up"
                reason = f"High utilization ({current_utilization*100:.1f}%) or queue depth ({queue_depth})"
                
        elif self.policy.predictive_scaling and predicted_utilization > self.policy.scale_up_threshold:
            # Predictive scale up (proactive)
            # Add nodes more conservatively for predictive scaling
            target_nodes = min(self.policy.max_nodes, self.current_nodes + 1)
            
            if target_nodes > self.current_nodes:
                action = "scale_up"
                reason = f"Predictive scaling (expected {predicted_utilization*100:.1f}% util)"
                
        # Scale DOWN conditions
        elif current_utilization < self.policy.scale_down_threshold and queue_depth == 0:
            # Only scale down if predicted utilization is also low
            if not self.policy.predictive_scaling or predicted_utilization < self.policy.target_utilization:
                # Remove nodes conservatively
                nodes_to_remove = max(1, int(self.current_nodes * 0.2))
                target_nodes = max(self.policy.min_nodes, self.current_nodes - nodes_to_remove)
                
                if target_nodes < self.current_nodes:
                    action = "scale_down"
                    reason = f"Low utilization ({current_utilization*100:.1f}%)"
                    
        # Execute scaling if needed
        if action and target_nodes != self.current_nodes:
            diff = abs(target_nodes - self.current_nodes)
            
            result = await self._execute_scaling(action, diff, target_nodes)
            
            record = {
                "timestamp": datetime.now(datetime.UTC).isoformat(),
                "action": action,
                "nodes_changed": diff,
                "new_total": target_nodes,
                "reason": reason,
                "metrics_at_time": {
                    "utilization": current_utilization,
                    "queue_depth": queue_depth,
                    "predicted_utilization": predicted_utilization
                }
            }
            
            self.scaling_history.append(record)
            # Keep history manageable
            if len(self.scaling_history) > 1000:
                self.scaling_history = self.scaling_history[-1000:]
                
            self.last_scaling_action_time = now
            self.current_nodes = target_nodes
            
            logger.info(f"Auto-scaler: {action.upper()} to {target_nodes} nodes. Reason: {reason}")
            return record
            
        return None

    async def _execute_scaling(self, action: str, count: int, new_total: int) -> bool:
        """Execute the actual scaling action (e.g. interacting with Kubernetes/Cloud provider)"""
        # In this implementation, we simulate the scaling delay
        # In production, this would call cloud APIs (AWS AutoScaling, K8s Scale, etc.)
        logger.debug(f"Executing {action} by {count} nodes...")
        
        # Simulate API delay
        await asyncio.sleep(2.0)
        
        if action == "scale_up":
            # Simulate provisioning new instances
            # We assume a mix of CPU and GPU instances based on demand
            new_gpus = count // 2
            new_cpus = count - new_gpus
            self.active_gpu_nodes += new_gpus
            self.active_cpu_nodes += new_cpus
        elif action == "scale_down":
            # Simulate de-provisioning
            # Prefer removing CPU nodes first if we have GPU ones
            remove_cpus = min(count, max(0, self.active_cpu_nodes - self.policy.min_nodes))
            remove_gpus = count - remove_cpus
            
            self.active_cpu_nodes -= remove_cpus
            self.active_gpu_nodes = max(0, self.active_gpu_nodes - remove_gpus)
            
        return True

    # --- Simulation helpers ---
    def _get_current_utilization(self) -> float:
        """Simulate getting current cluster utilization"""
        # In reality, fetch from MarketplaceMonitor or Coordinator
        import random
        # Base utilization with some noise
        base = 0.6
        return max(0.1, min(0.99, base + random.uniform(-0.2, 0.3)))
        
    def _get_queue_depth(self) -> int:
        """Simulate getting current queue depth"""
        import random
        if random.random() > 0.8:
            return random.randint(10, 50)
        return random.randint(0, 5)

    def get_status(self) -> Dict[str, Any]:
        """Get current scaler status"""
        return {
            "status": "running" if self.is_running else "stopped",
            "current_nodes": {
                "total": self.current_nodes,
                "cpu_nodes": self.active_cpu_nodes,
                "gpu_nodes": self.active_gpu_nodes
            },
            "policy": {
                "min_nodes": self.policy.min_nodes,
                "max_nodes": self.policy.max_nodes,
                "target_utilization": self.policy.target_utilization
            },
            "last_action": self.scaling_history[-1] if self.scaling_history else None,
            "prediction": {
                "next_hour_utilization_estimate": round(self._predict_demand(1), 3)
            }
        }
