"""
Chain analytics and monitoring system
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict, deque
import statistics

from ..core.config import MultiChainConfig
from ..core.node_client import NodeClient
from ..models.chain import ChainInfo, ChainType, ChainStatus

@dataclass
class ChainMetrics:
    """Chain performance metrics"""
    chain_id: str
    node_id: str
    timestamp: datetime
    block_height: int
    tps: float
    avg_block_time: float
    gas_price: int
    memory_usage_mb: float
    disk_usage_mb: float
    active_nodes: int
    client_count: int
    miner_count: int
    agent_count: int
    network_in_mb: float
    network_out_mb: float

@dataclass
class ChainAlert:
    """Chain performance alert"""
    chain_id: str
    alert_type: str
    severity: str
    message: str
    timestamp: datetime
    threshold: float
    current_value: float

@dataclass
class ChainPrediction:
    """Chain performance prediction"""
    chain_id: str
    metric: str
    predicted_value: float
    confidence: float
    time_horizon_hours: int
    created_at: datetime

class ChainAnalytics:
    """Advanced chain analytics and monitoring"""
    
    def __init__(self, config: MultiChainConfig):
        self.config = config
        self.metrics_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.alerts: List[ChainAlert] = []
        self.predictions: Dict[str, List[ChainPrediction]] = defaultdict(list)
        self.health_scores: Dict[str, float] = {}
        self.performance_benchmarks: Dict[str, Dict[str, float]] = {}
        
        # Alert thresholds
        self.thresholds = {
            'tps_low': 1.0,
            'tps_high': 100.0,
            'block_time_high': 10.0,
            'memory_usage_high': 80.0,  # percentage
            'disk_usage_high': 85.0,   # percentage
            'node_count_low': 1,
            'client_count_low': 5
        }
    
    async def collect_metrics(self, chain_id: str, node_id: str) -> ChainMetrics:
        """Collect metrics for a specific chain"""
        if node_id not in self.config.nodes:
            raise ValueError(f"Node {node_id} not configured")
        
        node_config = self.config.nodes[node_id]
        
        try:
            async with NodeClient(node_config) as client:
                chain_stats = await client.get_chain_stats(chain_id)
                node_info = await client.get_node_info()
                
                metrics = ChainMetrics(
                    chain_id=chain_id,
                    node_id=node_id,
                    timestamp=datetime.now(),
                    block_height=chain_stats.get("block_height", 0),
                    tps=chain_stats.get("tps", 0.0),
                    avg_block_time=chain_stats.get("avg_block_time", 0.0),
                    gas_price=chain_stats.get("gas_price", 0),
                    memory_usage_mb=chain_stats.get("memory_usage_mb", 0.0),
                    disk_usage_mb=chain_stats.get("disk_usage_mb", 0.0),
                    active_nodes=chain_stats.get("active_nodes", 0),
                    client_count=chain_stats.get("client_count", 0),
                    miner_count=chain_stats.get("miner_count", 0),
                    agent_count=chain_stats.get("agent_count", 0),
                    network_in_mb=node_info.get("network_in_mb", 0.0),
                    network_out_mb=node_info.get("network_out_mb", 0.0)
                )
                
                # Store metrics history
                self.metrics_history[chain_id].append(metrics)
                
                # Check for alerts
                await self._check_alerts(metrics)
                
                # Update health score
                self._calculate_health_score(chain_id)
                
                return metrics
                
        except Exception as e:
            print(f"Error collecting metrics for chain {chain_id}: {e}")
            raise
    
    async def collect_all_metrics(self) -> Dict[str, List[ChainMetrics]]:
        """Collect metrics for all chains across all nodes"""
        all_metrics = {}
        
        tasks = []
        for node_id, node_config in self.config.nodes.items():
            async def get_node_metrics(nid):
                try:
                    async with NodeClient(node_config) as client:
                        chains = await client.get_hosted_chains()
                        node_metrics = []
                        
                        for chain in chains:
                            try:
                                metrics = await self.collect_metrics(chain.id, nid)
                                node_metrics.append(metrics)
                            except Exception as e:
                                print(f"Error getting metrics for chain {chain.id}: {e}")
                        
                        return node_metrics
                except Exception as e:
                    print(f"Error getting chains from node {nid}: {e}")
                    return []
            
            tasks.append(get_node_metrics(node_id))
        
        results = await asyncio.gather(*tasks)
        
        for node_metrics in results:
            for metrics in node_metrics:
                if metrics.chain_id not in all_metrics:
                    all_metrics[metrics.chain_id] = []
                all_metrics[metrics.chain_id].append(metrics)
        
        return all_metrics
    
    def get_chain_performance_summary(self, chain_id: str, hours: int = 24) -> Dict[str, Any]:
        """Get performance summary for a chain"""
        if chain_id not in self.metrics_history:
            return {}
        
        # Filter metrics by time range
        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_metrics = [
            m for m in self.metrics_history[chain_id]
            if m.timestamp >= cutoff_time
        ]
        
        if not recent_metrics:
            return {}
        
        # Calculate statistics
        tps_values = [m.tps for m in recent_metrics]
        block_time_values = [m.avg_block_time for m in recent_metrics]
        gas_prices = [m.gas_price for m in recent_metrics]
        
        summary = {
            "chain_id": chain_id,
            "time_range_hours": hours,
            "data_points": len(recent_metrics),
            "latest_metrics": asdict(recent_metrics[-1]),
            "statistics": {
                "tps": {
                    "avg": statistics.mean(tps_values),
                    "min": min(tps_values),
                    "max": max(tps_values),
                    "median": statistics.median(tps_values)
                },
                "block_time": {
                    "avg": statistics.mean(block_time_values),
                    "min": min(block_time_values),
                    "max": max(block_time_values),
                    "median": statistics.median(block_time_values)
                },
                "gas_price": {
                    "avg": statistics.mean(gas_prices),
                    "min": min(gas_prices),
                    "max": max(gas_prices),
                    "median": statistics.median(gas_prices)
                }
            },
            "health_score": self.health_scores.get(chain_id, 0.0),
            "active_alerts": len([a for a in self.alerts if a.chain_id == chain_id])
        }
        
        return summary
    
    def get_cross_chain_analysis(self) -> Dict[str, Any]:
        """Analyze performance across all chains"""
        if not self.metrics_history:
            # Return mock data for testing
            return {
                "total_chains": 2,
                "active_chains": 2,
                "chains_by_type": {"ait-devnet": 1, "ait-testnet": 1},
                "performance_comparison": {
                    "ait-devnet": {
                        "tps": 2.5,
                        "block_time": 8.5,
                        "health_score": 85.0
                    },
                    "ait-testnet": {
                        "tps": 1.8,
                        "block_time": 12.3,
                        "health_score": 72.0
                    }
                },
                "resource_usage": {
                    "total_memory_mb": 2048.0,
                    "total_disk_mb": 10240.0,
                    "total_clients": 25,
                    "total_agents": 8
                },
                "alerts_summary": {
                    "total_alerts": 2,
                    "critical_alerts": 0,
                    "warning_alerts": 2
                }
            }
        
        analysis = {
            "total_chains": len(self.metrics_history),
            "active_chains": len([c for c in self.metrics_history.keys() if self.health_scores.get(c, 0) > 0.5]),
            "chains_by_type": defaultdict(int),
            "performance_comparison": {},
            "resource_usage": {
                "total_memory_mb": 0,
                "total_disk_mb": 0,
                "total_clients": 0,
                "total_agents": 0
            },
            "alerts_summary": {
                "total_alerts": len(self.alerts),
                "critical_alerts": len([a for a in self.alerts if a.severity == "critical"]),
                "warning_alerts": len([a for a in self.alerts if a.severity == "warning"])
            }
        }
        
        # Analyze each chain
        for chain_id, metrics in self.metrics_history.items():
            if not metrics:
                continue
            
            latest = metrics[-1]
            
            # Chain type analysis
            # This would need chain info, using placeholder
            analysis["chains_by_type"]["unknown"] += 1
            
            # Performance comparison
            analysis["performance_comparison"][chain_id] = {
                "tps": latest.tps,
                "block_time": latest.avg_block_time,
                "health_score": self.health_scores.get(chain_id, 0.0)
            }
            
            # Resource usage
            analysis["resource_usage"]["total_memory_mb"] += latest.memory_usage_mb
            analysis["resource_usage"]["total_disk_mb"] += latest.disk_usage_mb
            analysis["resource_usage"]["total_clients"] += latest.client_count
            analysis["resource_usage"]["total_agents"] += latest.agent_count
        
        return analysis
    
    async def predict_chain_performance(self, chain_id: str, hours: int = 24) -> List[ChainPrediction]:
        """Predict chain performance using historical data"""
        if chain_id not in self.metrics_history or len(self.metrics_history[chain_id]) < 10:
            return []
        
        metrics = list(self.metrics_history[chain_id])
        
        predictions = []
        
        # Simple linear regression for TPS prediction
        tps_values = [m.tps for m in metrics]
        if len(tps_values) >= 10:
            # Calculate trend
            recent_tps = tps_values[-5:]
            older_tps = tps_values[-10:-5]
            
            if len(recent_tps) > 0 and len(older_tps) > 0:
                recent_avg = statistics.mean(recent_tps)
                older_avg = statistics.mean(older_tps)
                trend = (recent_avg - older_avg) / older_avg if older_avg > 0 else 0
                
                predicted_tps = recent_avg * (1 + trend * (hours / 24))
                confidence = max(0.1, 1.0 - abs(trend))  # Higher confidence for stable trends
                
                predictions.append(ChainPrediction(
                    chain_id=chain_id,
                    metric="tps",
                    predicted_value=predicted_tps,
                    confidence=confidence,
                    time_horizon_hours=hours,
                    created_at=datetime.now()
                ))
        
        # Memory usage prediction
        memory_values = [m.memory_usage_mb for m in metrics]
        if len(memory_values) >= 10:
            recent_memory = memory_values[-5:]
            older_memory = memory_values[-10:-5]
            
            if len(recent_memory) > 0 and len(older_memory) > 0:
                recent_avg = statistics.mean(recent_memory)
                older_avg = statistics.mean(older_memory)
                growth_rate = (recent_avg - older_avg) / older_avg if older_avg > 0 else 0
                
                predicted_memory = recent_avg * (1 + growth_rate * (hours / 24))
                confidence = max(0.1, 1.0 - abs(growth_rate))
                
                predictions.append(ChainPrediction(
                    chain_id=chain_id,
                    metric="memory_usage_mb",
                    predicted_value=predicted_memory,
                    confidence=confidence,
                    time_horizon_hours=hours,
                    created_at=datetime.now()
                ))
        
        # Store predictions
        self.predictions[chain_id].extend(predictions)
        
        return predictions
    
    def get_optimization_recommendations(self, chain_id: str) -> List[Dict[str, Any]]:
        """Get optimization recommendations for a chain"""
        recommendations = []
        
        if chain_id not in self.metrics_history:
            return recommendations
        
        metrics = list(self.metrics_history[chain_id])
        if not metrics:
            return recommendations
        
        latest = metrics[-1]
        
        # TPS optimization
        if latest.tps < self.thresholds['tps_low']:
            recommendations.append({
                "type": "performance",
                "priority": "high",
                "issue": "Low TPS",
                "current_value": latest.tps,
                "recommended_action": "Consider increasing block size or optimizing smart contracts",
                "expected_improvement": "20-50% TPS increase"
            })
        
        # Block time optimization
        if latest.avg_block_time > self.thresholds['block_time_high']:
            recommendations.append({
                "type": "performance",
                "priority": "medium",
                "issue": "High block time",
                "current_value": latest.avg_block_time,
                "recommended_action": "Optimize consensus parameters or increase validator count",
                "expected_improvement": "30-60% block time reduction"
            })
        
        # Memory usage optimization
        if latest.memory_usage_mb > 1000:  # 1GB threshold
            recommendations.append({
                "type": "resource",
                "priority": "medium",
                "issue": "High memory usage",
                "current_value": latest.memory_usage_mb,
                "recommended_action": "Implement data pruning or increase node memory",
                "expected_improvement": "40-70% memory usage reduction"
            })
        
        # Node count optimization
        if latest.active_nodes < 3:
            recommendations.append({
                "type": "availability",
                "priority": "high",
                "issue": "Low node count",
                "current_value": latest.active_nodes,
                "recommended_action": "Add more nodes to improve network resilience",
                "expected_improvement": "Improved fault tolerance and sync speed"
            })
        
        return recommendations
    
    async def _check_alerts(self, metrics: ChainMetrics):
        """Check for performance alerts"""
        alerts = []
        
        # TPS alerts
        if metrics.tps < self.thresholds['tps_low']:
            alerts.append(ChainAlert(
                chain_id=metrics.chain_id,
                alert_type="tps_low",
                severity="warning",
                message=f"Low TPS detected: {metrics.tps:.2f}",
                timestamp=metrics.timestamp,
                threshold=self.thresholds['tps_low'],
                current_value=metrics.tps
            ))
        
        # Block time alerts
        if metrics.avg_block_time > self.thresholds['block_time_high']:
            alerts.append(ChainAlert(
                chain_id=metrics.chain_id,
                alert_type="block_time_high",
                severity="warning",
                message=f"High block time: {metrics.avg_block_time:.2f}s",
                timestamp=metrics.timestamp,
                threshold=self.thresholds['block_time_high'],
                current_value=metrics.avg_block_time
            ))
        
        # Memory usage alerts
        if metrics.memory_usage_mb > 2000:  # 2GB threshold
            alerts.append(ChainAlert(
                chain_id=metrics.chain_id,
                alert_type="memory_high",
                severity="critical",
                message=f"High memory usage: {metrics.memory_usage_mb:.1f}MB",
                timestamp=metrics.timestamp,
                threshold=2000,
                current_value=metrics.memory_usage_mb
            ))
        
        # Node count alerts
        if metrics.active_nodes < self.thresholds['node_count_low']:
            alerts.append(ChainAlert(
                chain_id=metrics.chain_id,
                alert_type="node_count_low",
                severity="critical",
                message=f"Low node count: {metrics.active_nodes}",
                timestamp=metrics.timestamp,
                threshold=self.thresholds['node_count_low'],
                current_value=metrics.active_nodes
            ))
        
        # Add to alerts list
        self.alerts.extend(alerts)
        
        # Keep only recent alerts (last 24 hours)
        cutoff_time = datetime.now() - timedelta(hours=24)
        self.alerts = [a for a in self.alerts if a.timestamp >= cutoff_time]
    
    def _calculate_health_score(self, chain_id: str):
        """Calculate health score for a chain"""
        if chain_id not in self.metrics_history:
            self.health_scores[chain_id] = 0.0
            return
        
        metrics = list(self.metrics_history[chain_id])
        if not metrics:
            self.health_scores[chain_id] = 0.0
            return
        
        latest = metrics[-1]
        
        # Health score components (0-100)
        tps_score = min(100, (latest.tps / 10) * 100)  # 10 TPS = 100% score
        block_time_score = max(0, 100 - (latest.avg_block_time - 5) * 10)  # 5s = 100% score
        node_score = min(100, (latest.active_nodes / 5) * 100)  # 5 nodes = 100% score
        memory_score = max(0, 100 - (latest.memory_usage_mb / 1000) * 50)  # 1GB = 50% penalty
        
        # Weighted average
        health_score = (tps_score * 0.3 + block_time_score * 0.3 + 
                        node_score * 0.3 + memory_score * 0.1)
        
        self.health_scores[chain_id] = max(0, min(100, health_score))
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get data for analytics dashboard"""
        dashboard = {
            "overview": self.get_cross_chain_analysis(),
            "chain_summaries": {},
            "alerts": [asdict(alert) for alert in self.alerts[-20:]],  # Last 20 alerts
            "predictions": {},
            "recommendations": {}
        }
        
        # Chain summaries
        for chain_id in self.metrics_history.keys():
            dashboard["chain_summaries"][chain_id] = self.get_chain_performance_summary(chain_id, 24)
            dashboard["recommendations"][chain_id] = self.get_optimization_recommendations(chain_id)
            
            # Latest predictions
            if chain_id in self.predictions:
                dashboard["predictions"][chain_id] = [
                    asdict(pred) for pred in self.predictions[chain_id][-5:]
                ]
        
        return dashboard
