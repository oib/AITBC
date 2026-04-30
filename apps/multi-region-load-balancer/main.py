"""
Multi-Region Load Balancing Service for AITBC
Handles intelligent load distribution across global regions
"""

import asyncio
import json
from datetime import datetime, UTC, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from aitbc import get_logger

logger = get_logger(__name__)

app = FastAPI(
    title="AITBC Multi-Region Load Balancer",
    description="Intelligent load balancing across global regions",
    version="1.0.0"
)

# Data models
class LoadBalancingRule(BaseModel):
    rule_id: str
    name: str
    algorithm: str  # weighted_round_robin, least_connections, geographic, performance_based
    target_regions: List[str]
    weights: Dict[str, float]  # Region weights
    health_check_path: str
    failover_enabled: bool
    session_affinity: bool

class RegionHealth(BaseModel):
    region_id: str
    status: str  # healthy, unhealthy, degraded
    response_time_ms: float
    success_rate: float
    active_connections: int
    last_check: datetime

class LoadBalancingMetrics(BaseModel):
    balancer_id: str
    timestamp: datetime
    total_requests: int
    requests_per_region: Dict[str, int]
    average_response_time: float
    error_rate: float
    throughput: float

class GeographicRule(BaseModel):
    rule_id: str
    source_regions: List[str]
    target_regions: List[str]
    priority: int  # Lower number = higher priority
    latency_threshold_ms: float

# In-memory storage (in production, use database)
load_balancing_rules: Dict[str, Dict] = {}
region_health_status: Dict[str, RegionHealth] = {}
balancing_metrics: Dict[str, List[Dict]] = {}
geographic_rules: Dict[str, Dict] = {}
session_affinity_data: Dict[str, Dict] = {}

@app.get("/")
async def root():
    return {
        "service": "AITBC Multi-Region Load Balancer",
        "status": "running",
        "timestamp": datetime.now(datetime.UTC).isoformat(),
        "version": "1.0.0"
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "total_rules": len(load_balancing_rules),
        "active_rules": len([r for r in load_balancing_rules.values() if r["status"] == "active"]),
        "monitored_regions": len(region_health_status),
        "healthy_regions": len([r for r in region_health_status.values() if r.status == "healthy"])
    }

@app.post("/api/v1/rules/create")
async def create_load_balancing_rule(rule: LoadBalancingRule):
    """Create a new load balancing rule"""
    if rule.rule_id in load_balancing_rules:
        raise HTTPException(status_code=400, detail="Load balancing rule already exists")
    
    # Create rule record
    rule_record = {
        "rule_id": rule.rule_id,
        "name": rule.name,
        "algorithm": rule.algorithm,
        "target_regions": rule.target_regions,
        "weights": rule.weights,
        "health_check_path": rule.health_check_path,
        "failover_enabled": rule.failover_enabled,
        "session_affinity": rule.session_affinity,
        "status": "active",
        "created_at": datetime.now(datetime.UTC).isoformat(),
        "total_requests": 0,
        "failed_requests": 0,
        "last_updated": datetime.now(datetime.UTC).isoformat()
    }
    
    load_balancing_rules[rule.rule_id] = rule_record
    
    # Start health monitoring for target regions
    asyncio.create_task(start_health_monitoring(rule.rule_id))
    
    logger.info(f"Load balancing rule created: {rule.name} ({rule.rule_id})")
    
    return {
        "rule_id": rule.rule_id,
        "status": "created",
        "name": rule.name,
        "algorithm": rule.algorithm,
        "created_at": rule_record["created_at"]
    }

@app.get("/api/v1/rules")
async def list_load_balancing_rules():
    """List all load balancing rules"""
    return {
        "rules": list(load_balancing_rules.values()),
        "total_rules": len(load_balancing_rules),
        "active_rules": len([r for r in load_balancing_rules.values() if r["status"] == "active"])
    }

@app.get("/api/v1/rules/{rule_id}")
async def get_load_balancing_rule(rule_id: str):
    """Get detailed load balancing rule information"""
    if rule_id not in load_balancing_rules:
        raise HTTPException(status_code=404, detail="Load balancing rule not found")
    
    rule = load_balancing_rules[rule_id].copy()
    
    # Add region health status
    rule["region_health"] = {
        region_id: region_health_status.get(region_id)
        for region_id in rule["target_regions"]
        if region_id in region_health_status
    }
    
    # Add performance metrics
    rule["performance_metrics"] = balancing_metrics.get(rule_id, [])
    
    return rule

@app.post("/api/v1/rules/{rule_id}/update-weights")
async def update_rule_weights(rule_id: str, weights: Dict[str, float]):
    """Update weights for a load balancing rule"""
    if rule_id not in load_balancing_rules:
        raise HTTPException(status_code=404, detail="Load balancing rule not found")
    
    rule = load_balancing_rules[rule_id]
    
    # Validate weights
    total_weight = sum(weights.values())
    if total_weight == 0:
        raise HTTPException(status_code=400, detail="Total weight cannot be zero")
    
    # Normalize weights
    normalized_weights = {k: v / total_weight for k, v in weights.items()}
    
    # Update rule weights
    rule["weights"] = normalized_weights
    rule["last_updated"] = datetime.now(datetime.UTC).isoformat()
    
    logger.info(f"Weights updated for rule {rule_id}: {normalized_weights}")
    
    return {
        "rule_id": rule_id,
        "new_weights": normalized_weights,
        "updated_at": rule["last_updated"]
    }

@app.post("/api/v1/health/register")
async def register_region_health(health: RegionHealth):
    """Register or update health status for a region"""
    region_health_status[health.region_id] = health
    
    # Update load balancing rules that use this region
    for rule_id, rule in load_balancing_rules.items():
        if health.region_id in rule["target_regions"]:
            # Update rule based on health status
            if health.status == "unhealthy" and rule["failover_enabled"]:
                logger.warning(f"Region {health.region_id} unhealthy, enabling failover for rule {rule_id}")
                enable_failover(rule_id, health.region_id)
    
    return {
        "region_id": health.region_id,
        "status": health.status,
        "registered_at": datetime.now(datetime.UTC).isoformat()
    }

@app.get("/api/v1/health")
async def get_all_region_health():
    """Get health status for all monitored regions"""
    return {
        "region_health": {
            region_id: health.dict()
            for region_id, health in region_health_status.items()
        },
        "total_regions": len(region_health_status),
        "healthy_regions": len([r for r in region_health_status.values() if r.status == "healthy"]),
        "unhealthy_regions": len([r for r in region_health_status.values() if r.status == "unhealthy"]),
        "degraded_regions": len([r for r in region_health_status.values() if r.status == "degraded"])
    }

@app.post("/api/v1/geographic-rules/create")
async def create_geographic_rule(rule: GeographicRule):
    """Create a geographic routing rule"""
    if rule.rule_id in geographic_rules:
        raise HTTPException(status_code=400, detail="Geographic rule already exists")
    
    # Create geographic rule record
    rule_record = {
        "rule_id": rule.rule_id,
        "source_regions": rule.source_regions,
        "target_regions": rule.target_regions,
        "priority": rule.priority,
        "latency_threshold_ms": rule.latency_threshold_ms,
        "status": "active",
        "created_at": datetime.now(datetime.UTC).isoformat(),
        "usage_count": 0
    }
    
    geographic_rules[rule.rule_id] = rule_record
    
    logger.info(f"Geographic rule created: {rule.rule_id}")
    
    return {
        "rule_id": rule.rule_id,
        "status": "created",
        "priority": rule.priority,
        "created_at": rule_record["created_at"]
    }

@app.get("/api/v1/route/{client_region}")
async def get_optimal_region(client_region: str, rule_id: Optional[str] = None):
    """Get optimal target region for a client region"""
    if rule_id and rule_id not in load_balancing_rules:
        raise HTTPException(status_code=404, detail="Load balancing rule not found")
    
    # Find optimal region based on rules
    if rule_id:
        optimal_region = select_region_by_algorithm(rule_id, client_region)
    else:
        optimal_region = select_region_geographically(client_region)
    
    return {
        "client_region": client_region,
        "optimal_region": optimal_region,
        "rule_id": rule_id,
        "selection_reason": get_selection_reason(optimal_region, client_region, rule_id),
        "timestamp": datetime.now(datetime.UTC).isoformat()
    }

@app.post("/api/v1/metrics/record")
async def record_balancing_metrics(metrics: LoadBalancingMetrics):
    """Record load balancing performance metrics"""
    metrics_record = {
        "metrics_id": f"metrics_{int(datetime.now(datetime.UTC).timestamp())}",
        "balancer_id": metrics.balancer_id,
        "timestamp": metrics.timestamp.isoformat(),
        "total_requests": metrics.total_requests,
        "requests_per_region": metrics.requests_per_region,
        "average_response_time": metrics.average_response_time,
        "error_rate": metrics.error_rate,
        "throughput": metrics.throughput
    }
    
    if metrics.balancer_id not in balancing_metrics:
        balancing_metrics[metrics.balancer_id] = []
    
    balancing_metrics[metrics.balancer_id].append(metrics_record)
    
    # Keep only last 1000 records per balancer
    if len(balancing_metrics[metrics.balancer_id]) > 1000:
        balancing_metrics[metrics.balancer_id] = balancing_metrics[metrics.balancer_id][-1000:]
    
    return {
        "metrics_id": metrics_record["metrics_id"],
        "status": "recorded",
        "timestamp": metrics_record["timestamp"]
    }

@app.get("/api/v1/metrics/{rule_id}")
async def get_balancing_metrics(rule_id: str, hours: int = 24):
    """Get performance metrics for a load balancing rule"""
    if rule_id not in load_balancing_rules:
        raise HTTPException(status_code=404, detail="Load balancing rule not found")
    
    cutoff_time = datetime.now(datetime.UTC) - timedelta(hours=hours)
    recent_metrics = [
        m for m in balancing_metrics.get(rule_id, [])
        if datetime.fromisoformat(m["timestamp"]) > cutoff_time
    ]
    
    # Calculate statistics
    if recent_metrics:
        avg_response_time = sum(m["average_response_time"] for m in recent_metrics) / len(recent_metrics)
        avg_error_rate = sum(m["error_rate"] for m in recent_metrics) / len(recent_metrics)
        avg_throughput = sum(m["throughput"] for m in recent_metrics) / len(recent_metrics)
        total_requests = sum(m["total_requests"] for m in recent_metrics)
    else:
        avg_response_time = avg_error_rate = avg_throughput = total_requests = 0.0
    
    return {
        "rule_id": rule_id,
        "period_hours": hours,
        "metrics": recent_metrics,
        "statistics": {
            "average_response_time_ms": round(avg_response_time, 3),
            "average_error_rate": round(avg_error_rate, 4),
            "average_throughput": round(avg_throughput, 2),
            "total_requests": int(total_requests),
            "total_samples": len(recent_metrics)
        },
        "generated_at": datetime.now(datetime.UTC).isoformat()
    }

@app.get("/api/v1/dashboard")
async def get_load_balancing_dashboard():
    """Get comprehensive load balancing dashboard"""
    # Calculate overall statistics
    total_rules = len(load_balancing_rules)
    active_rules = len([r for r in load_balancing_rules.values() if r["status"] == "active"])
    
    # Region health summary
    health_summary = {
        "total_regions": len(region_health_status),
        "healthy": len([r for r in region_health_status.values() if r.status == "healthy"]),
        "unhealthy": len([r for r in region_health_status.values() if r.status == "unhealthy"]),
        "degraded": len([r for r in region_health_status.values() if r.status == "degraded"])
    }
    
    # Performance summary
    performance_summary = {}
    for rule_id, metrics_list in balancing_metrics.items():
        if metrics_list:
            latest_metrics = metrics_list[-1]
            performance_summary[rule_id] = {
                "total_requests": latest_metrics["total_requests"],
                "average_response_time": latest_metrics["average_response_time"],
                "error_rate": latest_metrics["error_rate"],
                "throughput": latest_metrics["throughput"]
            }
    
    # Algorithm distribution
    algorithm_distribution = {}
    for rule in load_balancing_rules.values():
        algorithm = rule["algorithm"]
        algorithm_distribution[algorithm] = algorithm_distribution.get(algorithm, 0) + 1
    
    return {
        "dashboard": {
            "overview": {
                "total_rules": total_rules,
                "active_rules": active_rules,
                "geographic_rules": len(geographic_rules),
                "algorithm_distribution": algorithm_distribution
            },
            "region_health": health_summary,
            "performance": performance_summary,
            "recent_activity": get_recent_activity()
        },
        "generated_at": datetime.now(datetime.UTC).isoformat()
    }

# Core load balancing functions
def select_region_by_algorithm(rule_id: str, client_region: str) -> Optional[str]:
    """Select optimal region based on load balancing algorithm"""
    if rule_id not in load_balancing_rules:
        return None
    
    rule = load_balancing_rules[rule_id]
    algorithm = rule["algorithm"]
    target_regions = rule["target_regions"]
    
    # Filter healthy regions
    healthy_regions = [
        region for region in target_regions
        if region in region_health_status and region_health_status[region].status == "healthy"
    ]
    
    if not healthy_regions:
        # Fallback to any region if no healthy ones
        healthy_regions = target_regions
    
    if algorithm == "weighted_round_robin":
        return select_weighted_round_robin(rule_id, healthy_regions)
    elif algorithm == "least_connections":
        return select_least_connections(healthy_regions)
    elif algorithm == "geographic":
        return select_geographic_optimal(client_region, healthy_regions)
    elif algorithm == "performance_based":
        return select_performance_optimal(healthy_regions)
    else:
        return healthy_regions[0] if healthy_regions else None

def select_weighted_round_robin(rule_id: str, regions: List[str]) -> str:
    """Select region using weighted round robin"""
    rule = load_balancing_rules[rule_id]
    weights = rule["weights"]
    
    # Filter weights for available regions
    available_weights = {r: weights.get(r, 1.0) for r in regions if r in weights}
    
    if not available_weights:
        return regions[0]
    
    # Simple weighted selection (in production, use proper round robin state)
    import random
    total_weight = sum(available_weights.values())
    rand_val = random.uniform(0, total_weight)
    
    current_weight = 0
    for region, weight in available_weights.items():
        current_weight += weight
        if rand_val <= current_weight:
            return region
    
    return list(available_weights.keys())[-1]

def select_least_connections(regions: List[str]) -> str:
    """Select region with least connections"""
    min_connections = float('inf')
    optimal_region = None
    
    for region in regions:
        if region in region_health_status:
            connections = region_health_status[region].active_connections
            if connections < min_connections:
                min_connections = connections
                optimal_region = region
    
    return optimal_region or regions[0]

def select_geographic_optimal(client_region: str, target_regions: List[str]) -> str:
    """Select region based on geographic proximity"""
    # Simplified geographic mapping (in production, use actual geographic data)
    geographic_proximity = {
        "us-east": ["us-east-1", "us-west-1"],
        "us-west": ["us-west-1", "us-east-1"],
        "europe": ["eu-west-1", "eu-central-1"],
        "asia": ["ap-southeast-1", "ap-northeast-1"]
    }
    
    # Find closest regions
    for geo_area, close_regions in geographic_proximity.items():
        if client_region.lower() in geo_area.lower():
            for close_region in close_regions:
                if close_region in target_regions:
                    return close_region
    
    # Fallback to first healthy region
    return target_regions[0]

def select_performance_optimal(regions: List[str]) -> str:
    """Select region with best performance"""
    best_region = None
    best_score = float('inf')
    
    for region in regions:
        if region in region_health_status:
            health = region_health_status[region]
            # Calculate performance score (lower is better)
            score = health.response_time_ms * (1 - health.success_rate)
            if score < best_score:
                best_score = score
                best_region = region
    
    return best_region or regions[0]

def select_region_geographically(client_region: str) -> Optional[str]:
    """Select region based on geographic rules"""
    # Apply geographic rules
    applicable_rules = [
        rule for rule in geographic_rules.values()
        if client_region in rule["source_regions"] and rule["status"] == "active"
    ]
    
    # Sort by priority (lower number = higher priority)
    applicable_rules.sort(key=lambda x: x["priority"])
    
    for rule in applicable_rules:
        # Find best target region based on latency
        best_target = None
        best_latency = float('inf')
        
        for target_region in rule["target_regions"]:
            if target_region in region_health_status:
                latency = region_health_status[target_region].response_time_ms
                if latency < best_latency and latency < rule["latency_threshold_ms"]:
                    best_latency = latency
                    best_target = target_region
        
        if best_target:
            rule["usage_count"] += 1
            return best_target
    
    # Fallback to any healthy region
    healthy_regions = [
        region for region, health in region_health_status.items()
        if health.status == "healthy"
    ]
    
    return healthy_regions[0] if healthy_regions else None

def get_selection_reason(region: str, client_region: str, rule_id: Optional[str]) -> str:
    """Get reason for region selection"""
    if rule_id and rule_id in load_balancing_rules:
        rule = load_balancing_rules[rule_id]
        return f"Selected by {rule['algorithm']} algorithm using rule {rule['name']}"
    else:
        return f"Selected based on geographic proximity from {client_region}"

def enable_failover(rule_id: str, unhealthy_region: str):
    """Enable failover for unhealthy region"""
    rule = load_balancing_rules[rule_id]
    
    # Remove unhealthy region from rotation temporarily
    if unhealthy_region in rule["target_regions"]:
        rule["target_regions"].remove(unhealthy_region)
        logger.warning(f"Region {unhealthy_region} removed from load balancing rule {rule_id}")

def get_recent_activity() -> List[Dict]:
    """Get recent load balancing activity"""
    activity = []
    
    # Recent health changes
    for region_id, health in region_health_status.items():
        if (datetime.now(datetime.UTC) - health.last_check).total_seconds() < 3600:  # Last hour
            activity.append({
                "type": "health_check",
                "region": region_id,
                "status": health.status,
                "timestamp": health.last_check.isoformat()
            })
    
    # Recent rule updates
    for rule_id, rule in load_balancing_rules.items():
        if (datetime.now(datetime.UTC) - datetime.fromisoformat(rule["last_updated"])).total_seconds() < 3600:
            activity.append({
                "type": "rule_update",
                "rule_id": rule_id,
                "name": rule["name"],
                "timestamp": rule["last_updated"]
            })
    
    # Sort by timestamp (most recent first)
    activity.sort(key=lambda x: x["timestamp"], reverse=True)
    
    return activity[:20]

# Background task for health monitoring
async def start_health_monitoring(rule_id: str):
    """Start health monitoring for a load balancing rule"""
    rule = load_balancing_rules[rule_id]
    
    while rule["status"] == "active":
        try:
            # Check health of all target regions
            for region_id in rule["target_regions"]:
                await check_region_health(region_id)
            
            await asyncio.sleep(30)  # Check every 30 seconds
            
        except Exception as e:
            logger.error(f"Health monitoring error for rule {rule_id}: {str(e)}")
            await asyncio.sleep(10)

async def check_region_health(region_id: str):
    """Check health of a specific region"""
    # Simulate health check (in production, this would be actual health checks)
    import random
    
    # Simulate health metrics
    response_time = random.uniform(20, 200)
    success_rate = random.uniform(0.95, 1.0)
    active_connections = random.randint(100, 1000)
    
    # Determine health status
    if response_time < 100 and success_rate > 0.99:
        status = "healthy"
    elif response_time < 200 and success_rate > 0.95:
        status = "degraded"
    else:
        status = "unhealthy"
    
    health = RegionHealth(
        region_id=region_id,
        status=status,
        response_time_ms=response_time,
        success_rate=success_rate,
        active_connections=active_connections,
        last_check=datetime.now(datetime.UTC)
    )
    
    region_health_status[region_id] = health

# Initialize with some default rules
@app.on_event("startup")
async def startup_event():
    logger.info("Starting AITBC Multi-Region Load Balancer")
    
    # Initialize default load balancing rules
    default_rules = [
        {
            "rule_id": "global-web-rule",
            "name": "Global Web Load Balancer",
            "algorithm": "weighted_round_robin",
            "target_regions": ["us-east-1", "eu-west-1", "ap-southeast-1"],
            "weights": {"us-east-1": 0.4, "eu-west-1": 0.35, "ap-southeast-1": 0.25},
            "health_check_path": "/health",
            "failover_enabled": True,
            "session_affinity": False
        },
        {
            "rule_id": "api-performance-rule",
            "name": "API Performance Optimizer",
            "algorithm": "performance_based",
            "target_regions": ["us-east-1", "eu-west-1"],
            "weights": {"us-east-1": 0.5, "eu-west-1": 0.5},
            "health_check_path": "/api/health",
            "failover_enabled": True,
            "session_affinity": True
        }
    ]
    
    for rule_data in default_rules:
        rule = LoadBalancingRule(**rule_data)
        rule_record = {
            "rule_id": rule.rule_id,
            "name": rule.name,
            "algorithm": rule.algorithm,
            "target_regions": rule.target_regions,
            "weights": rule.weights,
            "health_check_path": rule.health_check_path,
            "failover_enabled": rule.failover_enabled,
            "session_affinity": rule.session_affinity,
            "status": "active",
            "created_at": datetime.now(datetime.UTC).isoformat(),
            "total_requests": 0,
            "failed_requests": 0,
            "last_updated": datetime.now(datetime.UTC).isoformat()
        }
        load_balancing_rules[rule.rule_id] = rule_record
        
        # Start health monitoring
        asyncio.create_task(start_health_monitoring(rule.rule_id))
    
    # Initialize default geographic rules
    default_geo_rules = [
        {
            "rule_id": "us-to-us",
            "source_regions": ["us-east", "us-west", "north-america"],
            "target_regions": ["us-east-1", "us-west-1"],
            "priority": 1,
            "latency_threshold_ms": 50
        },
        {
            "rule_id": "eu-to-eu",
            "source_regions": ["europe", "eu-west", "eu-central"],
            "target_regions": ["eu-west-1", "eu-central-1"],
            "priority": 1,
            "latency_threshold_ms": 30
        }
    ]
    
    for geo_rule_data in default_geo_rules:
        geo_rule = GeographicRule(**geo_rule_data)
        geo_rule_record = {
            "rule_id": geo_rule.rule_id,
            "source_regions": geo_rule.source_regions,
            "target_regions": geo_rule.target_regions,
            "priority": geo_rule.priority,
            "latency_threshold_ms": geo_rule.latency_threshold_ms,
            "status": "active",
            "created_at": datetime.now(datetime.UTC).isoformat(),
            "usage_count": 0
        }
        geographic_rules[geo_rule.rule_id] = geo_rule_record

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down AITBC Multi-Region Load Balancer")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8019, log_level="info")
