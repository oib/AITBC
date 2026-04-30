"""
Performance Monitoring and Analytics Service - Phase 5.2
Real-time performance tracking and optimization recommendations
"""

import json
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, UTC, timedelta
from typing import Any

import psutil
import torch

from aitbc import get_logger

logger = get_logger(__name__)


@dataclass
class PerformanceMetric:
    """Performance metric data structure"""

    timestamp: datetime
    metric_name: str
    value: float
    unit: str
    tags: dict[str, str]
    threshold: float | None = None


@dataclass
class SystemResource:
    """System resource utilization"""

    cpu_percent: float
    memory_percent: float
    gpu_utilization: float | None = None
    gpu_memory_percent: float | None = None
    disk_io_read_mb_s: float = 0.0
    disk_io_write_mb_s: float = 0.0
    network_io_recv_mb_s: float = 0.0
    network_io_sent_mb_s: float = 0.0


@dataclass
class AIModelPerformance:
    """AI model performance metrics"""

    model_id: str
    model_type: str
    inference_time_ms: float
    throughput_requests_per_second: float
    accuracy: float | None = None
    memory_usage_mb: float = 0.0
    gpu_utilization: float | None = None


class PerformanceMonitor:
    """Real-time performance monitoring system"""

    def __init__(self, max_history_hours: int = 24):
        self.max_history_hours = max_history_hours
        self.metrics_history = defaultdict(lambda: deque(maxlen=3600))  # 1 hour per metric
        self.system_resources = deque(maxlen=60)  # Last 60 seconds
        self.model_performance = defaultdict(lambda: deque(maxlen=1000))  # Last 1000 requests per model
        self.alert_thresholds = self._initialize_thresholds()
        self.performance_baseline = {}
        self.optimization_recommendations = []

    def _initialize_thresholds(self) -> dict[str, dict[str, float]]:
        """Initialize performance alert thresholds"""
        return {
            "system": {"cpu_percent": 80.0, "memory_percent": 85.0, "gpu_utilization": 90.0, "gpu_memory_percent": 85.0},
            "ai_models": {"inference_time_ms": 100.0, "throughput_requests_per_second": 10.0, "accuracy": 0.8},
            "services": {"response_time_ms": 200.0, "error_rate_percent": 5.0, "availability_percent": 99.0},
        }

    async def collect_system_metrics(self) -> SystemResource:
        """Collect system resource metrics"""

        # CPU metrics
        cpu_percent = psutil.cpu_percent(interval=1)

        # Memory metrics
        memory = psutil.virtual_memory()
        memory_percent = memory.percent

        # GPU metrics (if available)
        gpu_utilization = None
        gpu_memory_percent = None

        if torch.cuda.is_available():
            try:
                # GPU utilization (simplified - in production use nvidia-ml-py)
                gpu_memory_allocated = torch.cuda.memory_allocated()
                gpu_memory_total = torch.cuda.get_device_properties(0).total_memory
                gpu_memory_percent = (gpu_memory_allocated / gpu_memory_total) * 100

                # Simulate GPU utilization (in production use actual GPU monitoring)
                gpu_utilization = min(95.0, gpu_memory_percent * 1.2)
            except Exception as e:
                logger.warning(f"Failed to collect GPU metrics: {e}")

        # Disk I/O metrics
        disk_io = psutil.disk_io_counters()
        disk_io_read_mb_s = disk_io.read_bytes / (1024 * 1024) if disk_io else 0.0
        disk_io_write_mb_s = disk_io.write_bytes / (1024 * 1024) if disk_io else 0.0

        # Network I/O metrics
        network_io = psutil.net_io_counters()
        network_io_recv_mb_s = network_io.bytes_recv / (1024 * 1024) if network_io else 0.0
        network_io_sent_mb_s = network_io.bytes_sent / (1024 * 1024) if network_io else 0.0

        system_resource = SystemResource(
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            gpu_utilization=gpu_utilization,
            gpu_memory_percent=gpu_memory_percent,
            disk_io_read_mb_s=disk_io_read_mb_s,
            disk_io_write_mb_s=disk_io_write_mb_s,
            network_io_recv_mb_s=network_io_recv_mb_s,
            network_io_sent_mb_s=network_io_sent_mb_s,
        )

        # Store in history
        self.system_resources.append({"timestamp": datetime.now(datetime.UTC), "data": system_resource})

        return system_resource

    async def record_model_performance(
        self,
        model_id: str,
        model_type: str,
        inference_time_ms: float,
        throughput: float,
        accuracy: float | None = None,
        memory_usage_mb: float = 0.0,
        gpu_utilization: float | None = None,
    ):
        """Record AI model performance metrics"""

        performance = AIModelPerformance(
            model_id=model_id,
            model_type=model_type,
            inference_time_ms=inference_time_ms,
            throughput_requests_per_second=throughput,
            accuracy=accuracy,
            memory_usage_mb=memory_usage_mb,
            gpu_utilization=gpu_utilization,
        )

        # Store in history
        self.model_performance[model_id].append({"timestamp": datetime.now(datetime.UTC), "data": performance})

        # Check for performance alerts
        await self._check_model_alerts(model_id, performance)

    async def _check_model_alerts(self, model_id: str, performance: AIModelPerformance):
        """Check for performance alerts and generate recommendations"""

        alerts = []
        recommendations = []

        # Check inference time
        if performance.inference_time_ms > self.alert_thresholds["ai_models"]["inference_time_ms"]:
            alerts.append(
                {
                    "type": "performance_degradation",
                    "model_id": model_id,
                    "metric": "inference_time_ms",
                    "value": performance.inference_time_ms,
                    "threshold": self.alert_thresholds["ai_models"]["inference_time_ms"],
                    "severity": "warning",
                }
            )
            recommendations.append(
                {
                    "model_id": model_id,
                    "type": "optimization",
                    "action": "consider_model_optimization",
                    "description": "Model inference time exceeds threshold, consider quantization or pruning",
                }
            )

        # Check throughput
        if performance.throughput_requests_per_second < self.alert_thresholds["ai_models"]["throughput_requests_per_second"]:
            alerts.append(
                {
                    "type": "low_throughput",
                    "model_id": model_id,
                    "metric": "throughput_requests_per_second",
                    "value": performance.throughput_requests_per_second,
                    "threshold": self.alert_thresholds["ai_models"]["throughput_requests_per_second"],
                    "severity": "warning",
                }
            )
            recommendations.append(
                {
                    "model_id": model_id,
                    "type": "scaling",
                    "action": "increase_model_replicas",
                    "description": "Model throughput below threshold, consider scaling or load balancing",
                }
            )

        # Check accuracy
        if performance.accuracy and performance.accuracy < self.alert_thresholds["ai_models"]["accuracy"]:
            alerts.append(
                {
                    "type": "accuracy_degradation",
                    "model_id": model_id,
                    "metric": "accuracy",
                    "value": performance.accuracy,
                    "threshold": self.alert_thresholds["ai_models"]["accuracy"],
                    "severity": "critical",
                }
            )
            recommendations.append(
                {
                    "model_id": model_id,
                    "type": "retraining",
                    "action": "retrain_model",
                    "description": "Model accuracy degraded significantly, consider retraining with fresh data",
                }
            )

        # Store alerts and recommendations
        if alerts:
            logger.warning(f"Performance alerts for model {model_id}: {alerts}")
            self.optimization_recommendations.extend(recommendations)

    async def get_performance_summary(self, hours: int = 1) -> dict[str, Any]:
        """Get performance summary for specified time period"""

        cutoff_time = datetime.now(datetime.UTC) - timedelta(hours=hours)

        # System metrics summary
        system_metrics = []
        for entry in self.system_resources:
            if entry["timestamp"] > cutoff_time:
                system_metrics.append(entry["data"])

        if system_metrics:
            avg_cpu = sum(m.cpu_percent for m in system_metrics) / len(system_metrics)
            avg_memory = sum(m.memory_percent for m in system_metrics) / len(system_metrics)
            avg_gpu_util = None
            avg_gpu_mem = None

            gpu_utils = [m.gpu_utilization for m in system_metrics if m.gpu_utilization is not None]
            gpu_mems = [m.gpu_memory_percent for m in system_metrics if m.gpu_memory_percent is not None]

            if gpu_utils:
                avg_gpu_util = sum(gpu_utils) / len(gpu_utils)
            if gpu_mems:
                avg_gpu_mem = sum(gpu_mems) / len(gpu_mems)
        else:
            avg_cpu = avg_memory = avg_gpu_util = avg_gpu_mem = 0.0

        # Model performance summary
        model_summary = {}
        for model_id, entries in self.model_performance.items():
            recent_entries = [e for e in entries if e["timestamp"] > cutoff_time]

            if recent_entries:
                performances = [e["data"] for e in recent_entries]
                avg_inference_time = sum(p.inference_time_ms for p in performances) / len(performances)
                avg_throughput = sum(p.throughput_requests_per_second for p in performances) / len(performances)
                avg_accuracy = None
                avg_memory = sum(p.memory_usage_mb for p in performances) / len(performances)

                accuracies = [p.accuracy for p in performances if p.accuracy is not None]
                if accuracies:
                    avg_accuracy = sum(accuracies) / len(accuracies)

                model_summary[model_id] = {
                    "avg_inference_time_ms": avg_inference_time,
                    "avg_throughput_rps": avg_throughput,
                    "avg_accuracy": avg_accuracy,
                    "avg_memory_usage_mb": avg_memory,
                    "request_count": len(recent_entries),
                }

        return {
            "time_period_hours": hours,
            "timestamp": datetime.now(datetime.UTC).isoformat(),
            "system_metrics": {
                "avg_cpu_percent": avg_cpu,
                "avg_memory_percent": avg_memory,
                "avg_gpu_utilization": avg_gpu_util,
                "avg_gpu_memory_percent": avg_gpu_mem,
            },
            "model_performance": model_summary,
            "total_requests": sum(
                len([e for e in entries if e["timestamp"] > cutoff_time]) for entries in self.model_performance.values()
            ),
        }

    async def get_optimization_recommendations(self) -> list[dict[str, Any]]:
        """Get current optimization recommendations"""

        # Filter recent recommendations (last hour)
        cutoff_time = datetime.now(datetime.UTC) - timedelta(hours=1)
        recent_recommendations = [
            rec for rec in self.optimization_recommendations if rec.get("timestamp", datetime.now(datetime.UTC)) > cutoff_time
        ]

        return recent_recommendations

    async def analyze_performance_trends(self, model_id: str, hours: int = 24) -> dict[str, Any]:
        """Analyze performance trends for a specific model"""

        if model_id not in self.model_performance:
            return {"error": f"Model {model_id} not found"}

        cutoff_time = datetime.now(datetime.UTC) - timedelta(hours=hours)
        entries = [e for e in self.model_performance[model_id] if e["timestamp"] > cutoff_time]

        if not entries:
            return {"error": f"No data available for model {model_id} in the last {hours} hours"}

        performances = [e["data"] for e in entries]

        # Calculate trends
        inference_times = [p.inference_time_ms for p in performances]
        throughputs = [p.throughput_requests_per_second for p in performances]

        # Simple linear regression for trend
        def calculate_trend(values):
            if len(values) < 2:
                return 0.0

            n = len(values)
            x = list(range(n))
            sum_x = sum(x)
            sum_y = sum(values)
            sum_xy = sum(x[i] * values[i] for i in range(n))
            sum_x2 = sum(x[i] * x[i] for i in range(n))

            slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
            return slope

        inference_trend = calculate_trend(inference_times)
        throughput_trend = calculate_trend(throughputs)

        # Performance classification
        avg_inference = sum(inference_times) / len(inference_times)
        avg_throughput = sum(throughputs) / len(throughputs)

        performance_rating = "excellent"
        if avg_inference > 100 or avg_throughput < 10:
            performance_rating = "poor"
        elif avg_inference > 50 or avg_throughput < 20:
            performance_rating = "fair"
        elif avg_inference > 25 or avg_throughput < 50:
            performance_rating = "good"

        return {
            "model_id": model_id,
            "analysis_period_hours": hours,
            "performance_rating": performance_rating,
            "trends": {
                "inference_time_trend": inference_trend,  # ms per hour
                "throughput_trend": throughput_trend,  # requests per second per hour
            },
            "averages": {"avg_inference_time_ms": avg_inference, "avg_throughput_rps": avg_throughput},
            "sample_count": len(performances),
            "timestamp": datetime.now(datetime.UTC).isoformat(),
        }

    async def export_metrics(self, format: str = "json", hours: int = 24) -> Union[str, dict[str, Any]]:
        """Export metrics in specified format"""

        summary = await self.get_performance_summary(hours)

        if format.lower() == "json":
            return json.dumps(summary, indent=2, default=str)
        elif format.lower() == "csv":
            # Convert to CSV format (simplified)
            csv_lines = ["timestamp,model_id,inference_time_ms,throughput_rps,accuracy,memory_usage_mb"]

            for model_id, entries in self.model_performance.items():
                cutoff_time = datetime.now(datetime.UTC) - timedelta(hours=hours)
                recent_entries = [e for e in entries if e["timestamp"] > cutoff_time]

                for entry in recent_entries:
                    perf = entry["data"]
                    csv_lines.append(
                        f"{entry['timestamp'].isoformat()},{model_id},{perf.inference_time_ms},{perf.throughput_requests_per_second},{perf.accuracy or ''},{perf.memory_usage_mb}"
                    )

            return "\n".join(csv_lines)
        else:
            return summary


class AutoOptimizer:
    """Automatic performance optimization system"""

    def __init__(self, performance_monitor: PerformanceMonitor):
        self.monitor = performance_monitor
        self.optimization_history = []
        self.optimization_enabled = True

    async def run_optimization_cycle(self):
        """Run automatic optimization cycle"""

        if not self.optimization_enabled:
            return

        try:
            # Get current performance summary
            summary = await self.monitor.get_performance_summary(hours=1)

            # Identify optimization opportunities
            optimizations = await self._identify_optimizations(summary)

            # Apply optimizations
            for optimization in optimizations:
                success = await self._apply_optimization(optimization)

                self.optimization_history.append(
                    {"timestamp": datetime.now(datetime.UTC), "optimization": optimization, "success": success, "impact": "pending"}
                )

        except Exception as e:
            logger.error(f"Auto-optimization cycle failed: {e}")

    async def _identify_optimizations(self, summary: dict[str, Any]) -> list[dict[str, Any]]:
        """Identify optimization opportunities"""

        optimizations = []

        # System-level optimizations
        if summary["system_metrics"]["avg_cpu_percent"] > 80:
            optimizations.append(
                {"type": "system", "action": "scale_horizontal", "target": "cpu", "reason": "High CPU utilization detected"}
            )

        if summary["system_metrics"]["avg_memory_percent"] > 85:
            optimizations.append(
                {
                    "type": "system",
                    "action": "optimize_memory",
                    "target": "memory",
                    "reason": "High memory utilization detected",
                }
            )

        # Model-level optimizations
        for model_id, metrics in summary["model_performance"].items():
            if metrics["avg_inference_time_ms"] > 100:
                optimizations.append(
                    {"type": "model", "action": "quantize_model", "target": model_id, "reason": "High inference latency"}
                )

            if metrics["avg_throughput_rps"] < 10:
                optimizations.append(
                    {"type": "model", "action": "scale_model", "target": model_id, "reason": "Low throughput"}
                )

        return optimizations

    async def _apply_optimization(self, optimization: dict[str, Any]) -> bool:
        """Apply optimization (simulated)"""

        try:
            optimization_type = optimization["type"]
            action = optimization["action"]

            if optimization_type == "system":
                if action == "scale_horizontal":
                    logger.info(f"Scaling horizontally due to high {optimization['target']}")
                    # In production, implement actual scaling logic
                    return True
                elif action == "optimize_memory":
                    logger.info("Optimizing memory usage")
                    # In production, implement memory optimization
                    return True

            elif optimization_type == "model":
                target = optimization["target"]
                if action == "quantize_model":
                    logger.info(f"Quantizing model {target}")
                    # In production, implement model quantization
                    return True
                elif action == "scale_model":
                    logger.info(f"Scaling model {target}")
                    # In production, implement model scaling
                    return True

            return False

        except Exception as e:
            logger.error(f"Failed to apply optimization {optimization}: {e}")
            return False
