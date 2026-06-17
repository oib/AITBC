"""
Marketplace Adaptive Resource Scaler
Implements predictive and reactive auto-scaling of marketplace resources based on demand.
"""

import asyncio
import math
import time
from datetime import UTC, datetime
from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class ScalingPolicy:
    """Configuration for scaling behavior"""

    def __init__(
        self,
        min_nodes: int = 2,
        max_nodes: int = 100,
        target_utilization: float = 0.75,
        scale_up_threshold: float = 0.85,
        scale_down_threshold: float = 0.4,
        cooldown_period_sec: int = 300,
        predictive_scaling: bool = True,
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

    def __init__(self, policy: ScalingPolicy | None = None):
        self.policy = policy or ScalingPolicy()
        self.current_nodes = self.policy.min_nodes
        self.active_gpu_nodes = 0
        self.active_cpu_nodes = self.policy.min_nodes
        self.last_scaling_action_time = 0
        self.scaling_history: list[dict[str, Any]] = []
        self.historical_demand: dict[int, float] = {}
        self.is_running = False
        self._scaler_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self.is_running:
            return
        self.is_running = True
        self._scaler_task = asyncio.create_task(self._scaling_loop())
        logger.info("Resource Scaler started (Min: %s, Max: %s)", self.policy.min_nodes, self.policy.max_nodes)

    async def stop(self) -> None:
        self.is_running = False
        if self._scaler_task:
            self._scaler_task.cancel()
        logger.info("Resource Scaler stopped")

    def update_historical_demand(self, utilization: float) -> None:
        """Update historical data for predictive scaling"""
        now = datetime.now(UTC)
        hour_of_week = now.weekday() * 24 + now.hour
        if hour_of_week not in self.historical_demand:
            self.historical_demand[hour_of_week] = utilization
        else:
            current_avg = self.historical_demand[hour_of_week]
            self.historical_demand[hour_of_week] = current_avg * 0.9 + utilization * 0.1

    def _predict_demand(self, lookahead_hours: int = 1) -> float:
        """Predict expected utilization based on historical patterns"""
        if not self.policy.predictive_scaling or not self.historical_demand:
            return 0.0
        now = datetime.now(UTC)
        target_hour = (now.weekday() * 24 + now.hour + lookahead_hours) % 168
        if target_hour in self.historical_demand:
            return self.historical_demand[target_hour]
        available_hours = sorted(self.historical_demand.keys())
        if not available_hours:
            return 0.0
        return sum(self.historical_demand.values()) / len(self.historical_demand)

    async def _scaling_loop(self) -> None:
        """Background task that evaluates scaling rules periodically"""
        while self.is_running:
            try:
                current_utilization = self._get_current_utilization()
                current_queue_depth = self._get_queue_depth()
                self.update_historical_demand(current_utilization)
                await self.evaluate_scaling(current_utilization, current_queue_depth)
                await asyncio.sleep(10.0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in scaling loop: %s", e)
                await asyncio.sleep(10.0)

    async def evaluate_scaling(self, current_utilization: float, queue_depth: int) -> dict[str, Any] | None:
        """Evaluate if scaling action is needed and execute if necessary"""
        now = time.time()
        if now - self.last_scaling_action_time < self.policy.cooldown_period_sec:
            return None
        predicted_utilization = self._predict_demand()
        target_nodes = self.current_nodes
        action = None
        reason = ""
        if current_utilization > self.policy.scale_up_threshold or queue_depth > self.current_nodes * 5:
            desired_increase = math.ceil(self.current_nodes * (current_utilization / self.policy.target_utilization - 1.0))
            nodes_to_add = max(1, min(desired_increase, max(1, queue_depth // 2)))
            target_nodes = min(self.policy.max_nodes, self.current_nodes + nodes_to_add)
            if target_nodes > self.current_nodes:
                action = "scale_up"
                reason = f"High utilization ({current_utilization * 100:.1f}%) or queue depth ({queue_depth})"
        elif self.policy.predictive_scaling and predicted_utilization > self.policy.scale_up_threshold:
            target_nodes = min(self.policy.max_nodes, self.current_nodes + 1)
            if target_nodes > self.current_nodes:
                action = "scale_up"
                reason = f"Predictive scaling (expected {predicted_utilization * 100:.1f}% util)"
        elif current_utilization < self.policy.scale_down_threshold and queue_depth == 0:
            if not self.policy.predictive_scaling or predicted_utilization < self.policy.target_utilization:
                nodes_to_remove = max(1, int(self.current_nodes * 0.2))
                target_nodes = max(self.policy.min_nodes, self.current_nodes - nodes_to_remove)
                if target_nodes < self.current_nodes:
                    action = "scale_down"
                    reason = f"Low utilization ({current_utilization * 100:.1f}%)"
        if action and target_nodes != self.current_nodes:
            diff = abs(target_nodes - self.current_nodes)
            await self._execute_scaling(action, diff, target_nodes)
            record = {
                "timestamp": datetime.now(UTC).isoformat(),
                "action": action,
                "nodes_changed": diff,
                "new_total": target_nodes,
                "reason": reason,
                "metrics_at_time": {
                    "utilization": current_utilization,
                    "queue_depth": queue_depth,
                    "predicted_utilization": predicted_utilization,
                },
            }
            self.scaling_history.append(record)
            if len(self.scaling_history) > 1000:
                self.scaling_history = self.scaling_history[-1000:]
            self.last_scaling_action_time = int(now)
            self.current_nodes = target_nodes
            logger.info("Auto-scaler: %s to %s nodes. Reason: %s", action.upper(), target_nodes, reason)
            return record
        return None

    async def _execute_scaling(self, action: str, count: int, new_total: int) -> bool:
        """Execute the actual scaling action (e.g. interacting with Kubernetes/Cloud provider)"""
        logger.debug("Executing %s by %s nodes...", action, count)
        await asyncio.sleep(2.0)
        if action == "scale_up":
            new_gpus = count // 2
            new_cpus = count - new_gpus
            self.active_gpu_nodes += new_gpus
            self.active_cpu_nodes += new_cpus
        elif action == "scale_down":
            remove_cpus = min(count, max(0, self.active_cpu_nodes - self.policy.min_nodes))
            remove_gpus = count - remove_cpus
            self.active_cpu_nodes -= remove_cpus
            self.active_gpu_nodes = max(0, self.active_gpu_nodes - remove_gpus)
        return True

    def _get_current_utilization(self) -> float:
        """Simulate getting current cluster utilization"""
        import random

        base = 0.6
        return max(0.1, min(0.99, base + random.uniform(-0.2, 0.3)))

    def _get_queue_depth(self) -> int:
        """Simulate getting current queue depth"""
        import random

        if random.random() > 0.8:
            return random.randint(10, 50)
        return random.randint(0, 5)

    def get_status(self) -> dict[str, Any]:
        """Get current scaler status"""
        return {
            "status": "running" if self.is_running else "stopped",
            "current_nodes": {
                "total": self.current_nodes,
                "cpu_nodes": self.active_cpu_nodes,
                "gpu_nodes": self.active_gpu_nodes,
            },
            "policy": {
                "min_nodes": self.policy.min_nodes,
                "max_nodes": self.policy.max_nodes,
                "target_utilization": self.policy.target_utilization,
            },
            "last_action": self.scaling_history[-1] if self.scaling_history else None,
            "prediction": {"next_hour_utilization_estimate": round(self._predict_demand(1), 3)},
        }
