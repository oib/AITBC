"""
Plugin Analytics and Usage Tracking Service for AITBC
Handles plugin analytics, usage tracking, and performance monitoring
"""

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from aitbc import get_logger

logger = get_logger(__name__)

app = FastAPI(
    title="AITBC Plugin Analytics Service",
    description="Plugin analytics, usage tracking, and performance monitoring",
    version="1.0.0"
)

# Data models
class PluginUsage(BaseModel):
    plugin_id: str
    user_id: str
    action: str  # install, uninstall, enable, disable, use
    timestamp: datetime
    metadata: Dict[str, Any] = {}

class PluginPerformance(BaseModel):
    plugin_id: str
    version: str
    cpu_usage: float
    memory_usage: float
    response_time: float
    error_rate: float
    uptime: float
    timestamp: datetime

class PluginRating(BaseModel):
    plugin_id: str
    user_id: str
    rating: int  # 1-5
    review: Optional[str] = None
    timestamp: datetime

class PluginEvent(BaseModel):
    event_type: str
    plugin_id: str
    user_id: Optional[str] = None
    data: Dict[str, Any] = {}
    timestamp: datetime

# In-memory storage (in production, use database)
plugin_usage_data: Dict[str, List[Dict]] = {}
plugin_performance_data: Dict[str, List[Dict]] = {}
plugin_ratings: Dict[str, List[Dict]] = {}
plugin_events: Dict[str, List[Dict]] = {}
analytics_cache: Dict[str, Dict] = {}
usage_trends: Dict[str, Dict] = {}

@app.get("/")
async def root():
    return {
        "service": "AITBC Plugin Analytics Service",
        "status": "running",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "total_usage_records": sum(len(data) for data in plugin_usage_data.values()),
        "total_performance_records": sum(len(data) for data in plugin_performance_data.values()),
        "total_ratings": sum(len(data) for data in plugin_ratings.values()),
        "total_events": sum(len(data) for data in plugin_events.values()),
        "cache_size": len(analytics_cache)
    }

@app.post("/api/v1/analytics/usage")
async def record_plugin_usage(usage: PluginUsage):
    """Record plugin usage event"""
    usage_record = {
        "usage_id": f"usage_{int(datetime.utcnow().timestamp())}",
        "plugin_id": usage.plugin_id,
        "user_id": usage.user_id,
        "action": usage.action,
        "timestamp": usage.timestamp.isoformat(),
        "metadata": usage.metadata
    }
    
    if usage.plugin_id not in plugin_usage_data:
        plugin_usage_data[usage.plugin_id] = []
    
    plugin_usage_data[usage.plugin_id].append(usage_record)
    
    # Update usage trends
    update_usage_trends(usage.plugin_id, usage.action, usage.timestamp)
    
    logger.info(f"Usage recorded: {usage.plugin_id} - {usage.action} by {usage.user_id}")
    
    return {
        "usage_id": usage_record["usage_id"],
        "status": "recorded",
        "timestamp": usage_record["timestamp"]
    }

@app.post("/api/v1/analytics/performance")
async def record_plugin_performance(performance: PluginPerformance):
    """Record plugin performance metrics"""
    performance_record = {
        "performance_id": f"perf_{int(datetime.utcnow().timestamp())}",
        "plugin_id": performance.plugin_id,
        "version": performance.version,
        "cpu_usage": performance.cpu_usage,
        "memory_usage": performance.memory_usage,
        "response_time": performance.response_time,
        "error_rate": performance.error_rate,
        "uptime": performance.uptime,
        "timestamp": performance.timestamp.isoformat()
    }
    
    if performance.plugin_id not in plugin_performance_data:
        plugin_performance_data[performance.plugin_id] = []
    
    plugin_performance_data[performance.plugin_id].append(performance_record)
    
    logger.info(f"Performance recorded: {performance.plugin_id} - CPU: {performance.cpu_usage}%, Memory: {performance.memory_usage}%")
    
    return {
        "performance_id": performance_record["performance_id"],
        "status": "recorded",
        "timestamp": performance_record["timestamp"]
    }

@app.post("/api/v1/analytics/rating")
async def record_plugin_rating(rating: PluginRating):
    """Record plugin rating and review"""
    rating_record = {
        "rating_id": f"rating_{int(datetime.utcnow().timestamp())}",
        "plugin_id": rating.plugin_id,
        "user_id": rating.user_id,
        "rating": rating.rating,
        "review": rating.review,
        "timestamp": rating.timestamp.isoformat()
    }
    
    if rating.plugin_id not in plugin_ratings:
        plugin_ratings[rating.plugin_id] = []
    
    plugin_ratings[rating.plugin_id].append(rating_record)
    
    logger.info(f"Rating recorded: {rating.plugin_id} - {rating.rating} stars by {rating.user_id}")
    
    return {
        "rating_id": rating_record["rating_id"],
        "status": "recorded",
        "timestamp": rating_record["timestamp"]
    }

@app.post("/api/v1/analytics/event")
async def record_plugin_event(event: PluginEvent):
    """Record generic plugin event"""
    event_record = {
        "event_id": f"event_{int(datetime.utcnow().timestamp())}",
        "event_type": event.event_type,
        "plugin_id": event.plugin_id,
        "user_id": event.user_id,
        "data": event.data,
        "timestamp": event.timestamp.isoformat()
    }
    
    if event.plugin_id not in plugin_events:
        plugin_events[event.plugin_id] = []
    
    plugin_events[event.plugin_id].append(event_record)
    
    logger.info(f"Event recorded: {event.event_type} for {event.plugin_id}")
    
    return {
        "event_id": event_record["event_id"],
        "status": "recorded",
        "timestamp": event_record["timestamp"]
    }

@app.get("/api/v1/analytics/usage/{plugin_id}")
async def get_plugin_usage(plugin_id: str, days: int = 30):
    """Get usage analytics for a specific plugin"""
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    usage_records = plugin_usage_data.get(plugin_id, [])
    recent_usage = [r for r in usage_records 
                    if datetime.fromisoformat(r["timestamp"]) > cutoff_date]
    
    # Calculate usage statistics
    usage_stats = calculate_usage_statistics(recent_usage)
    
    return {
        "plugin_id": plugin_id,
        "period_days": days,
        "usage_statistics": usage_stats,
        "total_records": len(recent_usage),
        "generated_at": datetime.utcnow().isoformat()
    }

@app.get("/api/v1/analytics/performance/{plugin_id}")
async def get_plugin_performance(plugin_id: str, hours: int = 24):
    """Get performance analytics for a specific plugin"""
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)
    
    performance_records = plugin_performance_data.get(plugin_id, [])
    recent_performance = [r for r in performance_records 
                        if datetime.fromisoformat(r["timestamp"]) > cutoff_time]
    
    # Calculate performance statistics
    performance_stats = calculate_performance_statistics(recent_performance)
    
    return {
        "plugin_id": plugin_id,
        "period_hours": hours,
        "performance_statistics": performance_stats,
        "total_records": len(recent_performance),
        "generated_at": datetime.utcnow().isoformat()
    }

@app.get("/api/v1/analytics/ratings/{plugin_id}")
async def get_plugin_ratings(plugin_id: str):
    """Get ratings and reviews for a specific plugin"""
    rating_records = plugin_ratings.get(plugin_id, [])
    
    # Calculate rating statistics
    rating_stats = calculate_rating_statistics(rating_records)
    
    return {
        "plugin_id": plugin_id,
        "rating_statistics": rating_stats,
        "total_ratings": len(rating_records),
        "recent_ratings": rating_records[-10:],  # Last 10 ratings
        "generated_at": datetime.utcnow().isoformat()
    }

@app.get("/api/v1/analytics/dashboard")
async def get_analytics_dashboard():
    """Get comprehensive analytics dashboard"""
    dashboard_data = {
        "overview": get_overview_statistics(),
        "trending_plugins": get_trending_plugins(),
        "usage_trends": get_global_usage_trends(),
        "performance_summary": get_performance_summary(),
        "rating_summary": get_rating_summary(),
        "recent_events": get_recent_events()
    }
    
    return {
        "dashboard": dashboard_data,
        "generated_at": datetime.utcnow().isoformat()
    }

@app.get("/api/v1/analytics/trends")
async def get_usage_trends(plugin_id: Optional[str] = None, days: int = 30):
    """Get usage trends data"""
    if plugin_id:
        return get_plugin_trends(plugin_id, days)
    else:
        return get_global_usage_trends(days)

@app.get("/api/v1/analytics/reports")
async def generate_analytics_report(report_type: str, plugin_id: Optional[str] = None):
    """Generate various analytics reports"""
    if report_type == "usage":
        return generate_usage_report(plugin_id)
    elif report_type == "performance":
        return generate_performance_report(plugin_id)
    elif report_type == "ratings":
        return generate_ratings_report(plugin_id)
    elif report_type == "summary":
        return generate_summary_report(plugin_id)
    else:
        raise HTTPException(status_code=400, detail="Invalid report type")

# Analytics calculation functions
def calculate_usage_statistics(usage_records: List[Dict]) -> Dict[str, Any]:
    """Calculate usage statistics from usage records"""
    if not usage_records:
        return {
            "total_actions": 0,
            "unique_users": 0,
            "action_distribution": {},
            "daily_usage": {}
        }
    
    # Basic statistics
    total_actions = len(usage_records)
    unique_users = len(set(r["user_id"] for r in usage_records))
    
    # Action distribution
    action_counts = {}
    for record in usage_records:
        action = record["action"]
        action_counts[action] = action_counts.get(action, 0) + 1
    
    # Daily usage
    daily_usage = {}
    for record in usage_records:
        date = datetime.fromisoformat(record["timestamp"]).date().isoformat()
        daily_usage[date] = daily_usage.get(date, 0) + 1
    
    return {
        "total_actions": total_actions,
        "unique_users": unique_users,
        "action_distribution": action_counts,
        "daily_usage": daily_usage,
        "most_common_action": max(action_counts.items(), key=lambda x: x[1])[0] if action_counts else None
    }

def calculate_performance_statistics(performance_records: List[Dict]) -> Dict[str, Any]:
    """Calculate performance statistics from performance records"""
    if not performance_records:
        return {
            "avg_cpu_usage": 0.0,
            "avg_memory_usage": 0.0,
            "avg_response_time": 0.0,
            "avg_error_rate": 0.0,
            "avg_uptime": 0.0
        }
    
    # Calculate averages
    cpu_usage = sum(r["cpu_usage"] for r in performance_records) / len(performance_records)
    memory_usage = sum(r["memory_usage"] for r in performance_records) / len(performance_records)
    response_time = sum(r["response_time"] for r in performance_records) / len(performance_records)
    error_rate = sum(r["error_rate"] for r in performance_records) / len(performance_records)
    uptime = sum(r["uptime"] for r in performance_records) / len(performance_records)
    
    # Calculate min/max
    min_cpu = min(r["cpu_usage"] for r in performance_records)
    max_cpu = max(r["cpu_usage"] for r in performance_records)
    
    return {
        "avg_cpu_usage": round(cpu_usage, 2),
        "avg_memory_usage": round(memory_usage, 2),
        "avg_response_time": round(response_time, 3),
        "avg_error_rate": round(error_rate, 4),
        "avg_uptime": round(uptime, 2),
        "min_cpu_usage": round(min_cpu, 2),
        "max_cpu_usage": round(max_cpu, 2),
        "total_samples": len(performance_records)
    }

def calculate_rating_statistics(rating_records: List[Dict]) -> Dict[str, Any]:
    """Calculate rating statistics from rating records"""
    if not rating_records:
        return {
            "average_rating": 0.0,
            "total_ratings": 0,
            "rating_distribution": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        }
    
    # Calculate average rating
    total_rating = sum(r["rating"] for r in rating_records)
    average_rating = total_rating / len(rating_records)
    
    # Rating distribution
    rating_distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for record in rating_records:
        rating_distribution[record["rating"]] += 1
    
    return {
        "average_rating": round(average_rating, 2),
        "total_ratings": len(rating_records),
        "rating_distribution": rating_distribution,
        "latest_rating": rating_records[-1]["rating"] if rating_records else 0
    }

def update_usage_trends(plugin_id: str, action: str, timestamp: datetime):
    """Update usage trends data"""
    if plugin_id not in usage_trends:
        usage_trends[plugin_id] = {
            "daily": {},
            "weekly": {},
            "monthly": {}
        }
    
    # Update daily trends
    date_key = timestamp.date().isoformat()
    if date_key not in usage_trends[plugin_id]["daily"]:
        usage_trends[plugin_id]["daily"][date_key] = {}
    
    usage_trends[plugin_id]["daily"][date_key][action] = usage_trends[plugin_id]["daily"][date_key].get(action, 0) + 1

def get_overview_statistics() -> Dict[str, Any]:
    """Get overview statistics for all plugins"""
    total_plugins = len(set(plugin_usage_data.keys()) | set(plugin_performance_data.keys()) | set(plugin_ratings.keys()))
    total_usage = sum(len(data) for data in plugin_usage_data.values())
    total_ratings = sum(len(data) for data in plugin_ratings.values())
    
    # Calculate active plugins (plugins with usage in last 7 days)
    cutoff_date = datetime.utcnow() - timedelta(days=7)
    active_plugins = 0
    
    for plugin_id, usage_records in plugin_usage_data.items():
        recent_usage = [r for r in usage_records 
                       if datetime.fromisoformat(r["timestamp"]) > cutoff_date]
        if recent_usage:
            active_plugins += 1
    
    return {
        "total_plugins": total_plugins,
        "active_plugins": active_plugins,
        "total_usage_events": total_usage,
        "total_ratings": total_ratings,
        "average_ratings_per_plugin": round(total_ratings / total_plugins, 2) if total_plugins > 0 else 0
    }

def get_trending_plugins(limit: int = 10) -> List[Dict]:
    """Get trending plugins based on recent usage"""
    cutoff_date = datetime.utcnow() - timedelta(days=7)
    
    plugin_scores = []
    
    for plugin_id, usage_records in plugin_usage_data.items():
        recent_usage = [r for r in usage_records 
                       if datetime.fromisoformat(r["timestamp"]) > cutoff_date]
        
        if recent_usage:
            # Calculate trend score (simplified)
            score = len(recent_usage) + len(set(r["user_id"] for r in recent_usage))
            
            plugin_scores.append({
                "plugin_id": plugin_id,
                "trend_score": score,
                "recent_usage": len(recent_usage),
                "unique_users": len(set(r["user_id"] for r in recent_usage))
            })
    
    # Sort by trend score
    plugin_scores.sort(key=lambda x: x["trend_score"], reverse=True)
    
    return plugin_scores[:limit]

def get_global_usage_trends(days: int = 30) -> Dict[str, Any]:
    """Get global usage trends"""
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    global_trends = {}
    
    for plugin_id, usage_records in plugin_usage_data.items():
        recent_usage = [r for r in usage_records 
                       if datetime.fromisoformat(r["timestamp"]) > cutoff_date]
        
        if recent_usage:
            daily_counts = {}
            for record in recent_usage:
                date = datetime.fromisoformat(record["timestamp"]).date().isoformat()
                daily_counts[date] = daily_counts.get(date, 0) + 1
            
            global_trends[plugin_id] = daily_counts
    
    return {
        "trends": global_trends,
        "period_days": days,
        "total_plugins": len(global_trends)
    }

def get_performance_summary() -> Dict[str, Any]:
    """Get performance summary for all plugins"""
    all_performance = []
    
    for plugin_id, performance_records in plugin_performance_data.items():
        if performance_records:
            latest_record = performance_records[-1]
            all_performance.append({
                "plugin_id": plugin_id,
                "cpu_usage": latest_record["cpu_usage"],
                "memory_usage": latest_record["memory_usage"],
                "response_time": latest_record["response_time"],
                "error_rate": latest_record["error_rate"]
            })
    
    # Calculate averages
    if all_performance:
        avg_cpu = sum(p["cpu_usage"] for p in all_performance) / len(all_performance)
        avg_memory = sum(p["memory_usage"] for p in all_performance) / len(all_performance)
        avg_response = sum(p["response_time"] for p in all_performance) / len(all_performance)
        avg_error = sum(p["error_rate"] for p in all_performance) / len(all_performance)
    else:
        avg_cpu = avg_memory = avg_response = avg_error = 0.0
    
    return {
        "total_plugins": len(all_performance),
        "average_cpu_usage": round(avg_cpu, 2),
        "average_memory_usage": round(avg_memory, 2),
        "average_response_time": round(avg_response, 3),
        "average_error_rate": round(avg_error, 4),
        "top_cpu_users": sorted(all_performance, key=lambda x: x["cpu_usage"], reverse=True)[:5]
    }

def get_rating_summary() -> Dict[str, Any]:
    """Get rating summary for all plugins"""
    all_ratings = []
    
    for plugin_id, rating_records in plugin_ratings.items():
        if rating_records:
            avg_rating = sum(r["rating"] for r in rating_records) / len(rating_records)
            all_ratings.append({
                "plugin_id": plugin_id,
                "average_rating": round(avg_rating, 2),
                "total_ratings": len(rating_records)
            })
    
    # Sort by rating
    all_ratings.sort(key=lambda x: x["average_rating"], reverse=True)
    
    return {
        "total_plugins": len(all_ratings),
        "top_rated": all_ratings[:10],
        "average_rating_all": round(sum(r["average_rating"] for r in all_ratings) / len(all_ratings), 2) if all_ratings else 0.0
    }

def get_recent_events(limit: int = 20) -> List[Dict]:
    """Get recent plugin events"""
    all_events = []
    
    for plugin_id, events in plugin_events.items():
        for event in events:
            all_events.append({
                "plugin_id": plugin_id,
                "event_type": event["event_type"],
                "timestamp": event["timestamp"],
                "user_id": event.get("user_id")
            })
    
    # Sort by timestamp (most recent first)
    all_events.sort(key=lambda x: x["timestamp"], reverse=True)
    
    return all_events[:limit]

def get_plugin_trends(plugin_id: str, days: int) -> Dict[str, Any]:
    """Get trends for a specific plugin"""
    plugin_trends = usage_trends.get(plugin_id, {})
    
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    date_key = cutoff_date.date().isoformat()
    
    return {
        "plugin_id": plugin_id,
        "trends": plugin_trends,
        "period_days": days,
        "generated_at": datetime.utcnow().isoformat()
    }

# Report generation functions
def generate_usage_report(plugin_id: Optional[str] = None) -> Dict[str, Any]:
    """Generate usage report"""
    if plugin_id:
        return get_plugin_usage(plugin_id, days=30)
    else:
        return get_global_usage_trends(days=30)

def generate_performance_report(plugin_id: Optional[str] = None) -> Dict[str, Any]:
    """Generate performance report"""
    if plugin_id:
        return get_plugin_performance(plugin_id, hours=24)
    else:
        return get_performance_summary()

def generate_ratings_report(plugin_id: Optional[str] = None) -> Dict[str, Any]:
    """Generate ratings report"""
    if plugin_id:
        return get_plugin_ratings(plugin_id)
    else:
        return get_rating_summary()

def generate_summary_report(plugin_id: Optional[str] = None) -> Dict[str, Any]:
    """Generate comprehensive summary report"""
    if plugin_id:
        return {
            "plugin_id": plugin_id,
            "usage": get_plugin_usage(plugin_id, days=30),
            "performance": get_plugin_performance(plugin_id, hours=24),
            "ratings": get_plugin_ratings(plugin_id),
            "generated_at": datetime.utcnow().isoformat()
        }
    else:
        return get_analytics_dashboard()

# Background task for analytics processing
async def process_analytics():
    """Background task to process analytics data"""
    while True:
        await asyncio.sleep(3600)  # Process every hour
        
        # Update analytics cache
        update_analytics_cache()
        
        # Clean old data (older than 90 days)
        cleanup_old_data()
        
        logger.info("Analytics processing completed")

def update_analytics_cache():
    """Update analytics cache with frequently accessed data"""
    # Cache trending plugins
    analytics_cache["trending_plugins"] = get_trending_plugins()
    
    # Cache overview statistics
    analytics_cache["overview"] = get_overview_statistics()
    
    # Cache performance summary
    analytics_cache["performance_summary"] = get_performance_summary()

def cleanup_old_data():
    """Clean up old analytics data"""
    cutoff_date = datetime.utcnow() - timedelta(days=90)
    cutoff_iso = cutoff_date.isoformat()
    
    # Clean usage data
    for plugin_id in plugin_usage_data:
        plugin_usage_data[plugin_id] = [
            r for r in plugin_usage_data[plugin_id] 
            if r["timestamp"] > cutoff_iso
        ]
    
    # Clean performance data
    for plugin_id in plugin_performance_data:
        plugin_performance_data[plugin_id] = [
            r for r in plugin_performance_data[plugin_id] 
            if r["timestamp"] > cutoff_iso
        ]
    
    # Clean events data
    for plugin_id in plugin_events:
        plugin_events[plugin_id] = [
            r for r in plugin_events[plugin_id] 
            if r["timestamp"] > cutoff_iso
        ]

@app.on_event("startup")
async def startup_event():
    logger.info("Starting AITBC Plugin Analytics Service")
    # Initialize analytics cache
    update_analytics_cache()
    # Start analytics processing
    asyncio.create_task(process_analytics())

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down AITBC Plugin Analytics Service")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8016, log_level="info")
