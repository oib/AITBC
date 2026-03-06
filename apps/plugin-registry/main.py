"""
Production Plugin Registry Service for AITBC
Handles plugin registration, discovery, versioning, and security validation
"""

import asyncio
import json
import logging
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AITBC Plugin Registry",
    description="Production plugin registry for AITBC ecosystem",
    version="1.0.0"
)

# Data models
class PluginRegistration(BaseModel):
    name: str
    version: str
    description: str
    author: str
    category: str
    tags: List[str]
    repository_url: str
    homepage_url: Optional[str] = None
    license: str
    dependencies: List[str] = []
    aitbc_version: str
    plugin_type: str  # cli, blockchain, ai, web, etc.

class PluginVersion(BaseModel):
    version: str
    changelog: str
    download_url: str
    checksum: str
    aitbc_compatibility: List[str]
    release_date: datetime

class SecurityScan(BaseModel):
    scan_id: str
    plugin_id: str
    version: str
    scan_date: datetime
    vulnerabilities: List[Dict[str, Any]]
    risk_score: str  # low, medium, high, critical
    passed: bool

# In-memory storage (in production, use database)
plugins: Dict[str, Dict] = {}
plugin_versions: Dict[str, List[Dict]] = {}
security_scans: Dict[str, Dict] = {}
analytics: Dict[str, Dict] = {}
downloads: Dict[str, List[Dict]] = {}

@app.get("/")
async def root():
    return {
        "service": "AITBC Plugin Registry",
        "status": "running",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "total_plugins": len(plugins),
        "total_versions": sum(len(versions) for versions in plugin_versions.values()),
        "security_scans": len(security_scans),
        "downloads_today": len([d for downloads_list in downloads.values() 
                              for d in downloads_list 
                              if datetime.fromisoformat(d["timestamp"]).date() == datetime.utcnow().date()])
    }

@app.post("/api/v1/plugins/register")
async def register_plugin(plugin: PluginRegistration):
    """Register a new plugin"""
    plugin_id = f"{plugin.name.lower().replace(' ', '_')}"
    
    if plugin_id in plugins:
        raise HTTPException(status_code=400, detail="Plugin already registered")
    
    # Create plugin record
    plugin_record = {
        "plugin_id": plugin_id,
        "name": plugin.name,
        "description": plugin.description,
        "author": plugin.author,
        "category": plugin.category,
        "tags": plugin.tags,
        "repository_url": plugin.repository_url,
        "homepage_url": plugin.homepage_url,
        "license": plugin.license,
        "dependencies": plugin.dependencies,
        "aitbc_version": plugin.aitbc_version,
        "plugin_type": plugin.plugin_type,
        "status": "active",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "verified": False,
        "featured": False,
        "download_count": 0,
        "rating": 0.0,
        "rating_count": 0,
        "latest_version": plugin.version
    }
    
    plugins[plugin_id] = plugin_record
    plugin_versions[plugin_id] = []
    
    # Initialize analytics
    analytics[plugin_id] = {
        "downloads": [],
        "views": [],
        "ratings": [],
        "daily_stats": {}
    }
    
    logger.info(f"Plugin registered: {plugin.name}")
    
    return {
        "plugin_id": plugin_id,
        "status": "registered",
        "name": plugin.name,
        "created_at": plugin_record["created_at"]
    }

@app.post("/api/v1/plugins/{plugin_id}/versions")
async def add_plugin_version(plugin_id: str, version: PluginVersion):
    """Add a new version to an existing plugin"""
    if plugin_id not in plugins:
        raise HTTPException(status_code=404, detail="Plugin not found")
    
    # Check if version already exists
    for existing_version in plugin_versions[plugin_id]:
        if existing_version["version"] == version.version:
            raise HTTPException(status_code=400, detail="Version already exists")
    
    # Create version record
    version_record = {
        "version_id": f"{plugin_id}_v_{version.version}",
        "plugin_id": plugin_id,
        "version": version.version,
        "changelog": version.changelog,
        "download_url": version.download_url,
        "checksum": version.checksum,
        "aitbc_compatibility": version.aitbc_compatibility,
        "release_date": version.release_date.isoformat(),
        "downloads": 0,
        "security_scan_passed": False,
        "created_at": datetime.utcnow().isoformat()
    }
    
    plugin_versions[plugin_id].append(version_record)
    
    # Update plugin's latest version
    plugins[plugin_id]["latest_version"] = version.version
    plugins[plugin_id]["updated_at"] = datetime.utcnow().isoformat()
    
    # Sort versions by version number (semantic versioning)
    plugin_versions[plugin_id].sort(key=lambda x: x["version"], reverse=True)
    
    logger.info(f"Version added to plugin {plugin_id}: {version.version}")
    
    return {
        "plugin_id": plugin_id,
        "version": version.version,
        "status": "added",
        "created_at": version_record["created_at"]
    }

@app.get("/api/v1/plugins")
async def list_plugins(category: Optional[str] = None, tag: Optional[str] = None, 
                     search: Optional[str] = None, sort_by: str = "created_at"):
    """List all plugins with filtering and sorting"""
    filtered_plugins = []
    
    for plugin in plugins.values():
        # Apply filters
        if category and plugin["category"] != category:
            continue
        if tag and tag not in plugin["tags"]:
            continue
        if search and search.lower() not in plugin["name"].lower() and search.lower() not in plugin["description"].lower():
            continue
        
        filtered_plugins.append(plugin.copy())
    
    # Sort plugins
    if sort_by == "created_at":
        filtered_plugins.sort(key=lambda x: x["created_at"], reverse=True)
    elif sort_by == "updated_at":
        filtered_plugins.sort(key=lambda x: x["updated_at"], reverse=True)
    elif sort_by == "name":
        filtered_plugins.sort(key=lambda x: x["name"])
    elif sort_by == "downloads":
        filtered_plugins.sort(key=lambda x: x["download_count"], reverse=True)
    elif sort_by == "rating":
        filtered_plugins.sort(key=lambda x: x["rating"], reverse=True)
    
    return {
        "plugins": filtered_plugins,
        "total_plugins": len(filtered_plugins),
        "filters": {
            "category": category,
            "tag": tag,
            "search": search,
            "sort_by": sort_by
        }
    }

@app.get("/api/v1/plugins/{plugin_id}")
async def get_plugin(plugin_id: str):
    """Get detailed plugin information"""
    if plugin_id not in plugins:
        raise HTTPException(status_code=404, detail="Plugin not found")
    
    plugin = plugins[plugin_id].copy()
    
    # Add version information
    plugin["versions"] = plugin_versions.get(plugin_id, [])
    
    # Add analytics
    plugin_analytics = analytics.get(plugin_id, {})
    plugin["analytics"] = {
        "total_downloads": len(plugin_analytics.get("downloads", [])),
        "total_views": len(plugin_analytics.get("views", [])),
        "average_rating": sum(plugin_analytics.get("ratings", [])) / len(plugin_analytics.get("ratings", [])) if plugin_analytics.get("ratings") else 0.0,
        "rating_count": len(plugin_analytics.get("ratings", []))
    }
    
    return plugin

@app.get("/api/v1/plugins/{plugin_id}/versions")
async def get_plugin_versions(plugin_id: str):
    """Get all versions of a plugin"""
    if plugin_id not in plugins:
        raise HTTPException(status_code=404, detail="Plugin not found")
    
    return {
        "plugin_id": plugin_id,
        "versions": plugin_versions.get(plugin_id, []),
        "total_versions": len(plugin_versions.get(plugin_id, []))
    }

@app.get("/api/v1/plugins/{plugin_id}/download/{version}")
async def download_plugin(plugin_id: str, version: str):
    """Download a specific plugin version"""
    if plugin_id not in plugins:
        raise HTTPException(status_code=404, detail="Plugin not found")
    
    # Find the version
    version_record = None
    for v in plugin_versions.get(plugin_id, []):
        if v["version"] == version:
            version_record = v
            break
    
    if not version_record:
        raise HTTPException(status_code=404, detail="Version not found")
    
    # Record download
    download_record = {
        "version": version,
        "timestamp": datetime.utcnow().isoformat(),
        "ip_address": "client_ip",  # In production, get actual IP
        "user_agent": "user_agent"   # In production, get actual user agent
    }
    
    if plugin_id not in downloads:
        downloads[plugin_id] = []
    downloads[plugin_id].append(download_record)
    
    # Update analytics
    if plugin_id not in analytics:
        analytics[plugin_id] = {"downloads": [], "views": [], "ratings": []}
    analytics[plugin_id]["downloads"].append(datetime.utcnow().timestamp())
    
    # Update plugin download count
    plugins[plugin_id]["download_count"] += 1
    version_record["downloads"] += 1
    
    # In production, this would return the actual file
    return {
        "plugin_id": plugin_id,
        "version": version,
        "download_url": version_record["download_url"],
        "checksum": version_record["checksum"],
        "download_count": version_record["downloads"]
    }

@app.post("/api/v1/plugins/{plugin_id}/security-scan")
async def create_security_scan(plugin_id: str, scan: SecurityScan):
    """Create a security scan record for a plugin version"""
    if plugin_id not in plugins:
        raise HTTPException(status_code=404, detail="Plugin not found")
    
    # Verify version exists
    version_exists = any(v["version"] == scan.version for v in plugin_versions.get(plugin_id, []))
    if not version_exists:
        raise HTTPException(status_code=404, detail="Version not found")
    
    # Create security scan record
    security_scans[scan.scan_id] = {
        "scan_id": scan.scan_id,
        "plugin_id": plugin_id,
        "version": scan.version,
        "scan_date": scan.scan_date.isoformat(),
        "vulnerabilities": scan.vulnerabilities,
        "risk_score": scan.risk_score,
        "passed": scan.passed,
        "created_at": datetime.utcnow().isoformat()
    }
    
    # Update version security status
    for version_record in plugin_versions.get(plugin_id, []):
        if version_record["version"] == scan.version:
            version_record["security_scan_passed"] = scan.passed
            break
    
    logger.info(f"Security scan created for {plugin_id} v{scan.version}: {scan.risk_score}")
    
    return {
        "scan_id": scan.scan_id,
        "plugin_id": plugin_id,
        "version": scan.version,
        "risk_score": scan.risk_score,
        "passed": scan.passed,
        "scan_date": scan.scan_date.isoformat()
    }

@app.get("/api/v1/plugins/{plugin_id}/security")
async def get_plugin_security(plugin_id: str):
    """Get security information for a plugin"""
    if plugin_id not in plugins:
        raise HTTPException(status_code=404, detail="Plugin not found")
    
    plugin_scans = []
    for scan_id, scan in security_scans.items():
        if scan["plugin_id"] == plugin_id:
            plugin_scans.append(scan)
    
    # Sort by scan date
    plugin_scans.sort(key=lambda x: x["scan_date"], reverse=True)
    
    return {
        "plugin_id": plugin_id,
        "security_scans": plugin_scans,
        "total_scans": len(plugin_scans),
        "latest_scan": plugin_scans[0] if plugin_scans else None
    }

@app.get("/api/v1/categories")
async def get_categories():
    """Get all plugin categories"""
    categories = {}
    for plugin in plugins.values():
        category = plugin["category"]
        if category not in categories:
            categories[category] = {
                "name": category,
                "plugin_count": 0,
                "description": f"Plugins in {category} category"
            }
        categories[category]["plugin_count"] += 1
    
    return {
        "categories": list(categories.values()),
        "total_categories": len(categories)
    }

@app.get("/api/v1/tags")
async def get_tags():
    """Get all plugin tags"""
    tag_counts = {}
    for plugin in plugins.values():
        for tag in plugin["tags"]:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    
    return {
        "tags": [{"tag": tag, "count": count} for tag, count in sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)],
        "total_tags": len(tag_counts)
    }

@app.get("/api/v1/analytics/popular")
async def get_popular_plugins(limit: int = 10):
    """Get most popular plugins by downloads"""
    popular_plugins = sorted(plugins.values(), key=lambda x: x["download_count"], reverse=True)[:limit]
    
    return {
        "popular_plugins": popular_plugins,
        "limit": limit,
        "generated_at": datetime.utcnow().isoformat()
    }

@app.get("/api/v1/analytics/recent")
async def get_recent_plugins(limit: int = 10):
    """Get recently updated plugins"""
    recent_plugins = sorted(plugins.values(), key=lambda x: x["updated_at"], reverse=True)[:limit]
    
    return {
        "recent_plugins": recent_plugins,
        "limit": limit,
        "generated_at": datetime.utcnow().isoformat()
    }

@app.get("/api/v1/analytics/dashboard")
async def get_analytics_dashboard():
    """Get registry analytics dashboard"""
    total_plugins = len(plugins)
    total_versions = sum(len(versions) for versions in plugin_versions.values())
    total_downloads = sum(plugin["download_count"] for plugin in plugins.values())
    
    # Category distribution
    category_stats = {}
    for plugin in plugins.values():
        category = plugin["category"]
        category_stats[category] = category_stats.get(category, 0) + 1
    
    # Recent activity
    recent_downloads = 0
    today = datetime.utcnow().date()
    for download_list in downloads.values():
        recent_downloads += len([d for d in download_list 
                               if datetime.fromisoformat(d["timestamp"]).date() == today])
    
    return {
        "dashboard": {
            "total_plugins": total_plugins,
            "total_versions": total_versions,
            "total_downloads": total_downloads,
            "recent_downloads_today": recent_downloads,
            "categories": category_stats,
            "security_scans": len(security_scans),
            "passed_scans": len([s for s in security_scans.values() if s["passed"]])
        },
        "generated_at": datetime.utcnow().isoformat()
    }

# Background task for analytics processing
async def process_analytics():
    """Background task to process analytics data"""
    while True:
        await asyncio.sleep(3600)  # Process every hour
        
        # Update daily statistics
        current_date = datetime.utcnow().date()
        
        for plugin_id, plugin_analytics in analytics.items():
            daily_key = current_date.isoformat()
            
            if daily_key not in plugin_analytics["daily_stats"]:
                plugin_analytics["daily_stats"][daily_key] = {
                    "downloads": len([d for d in plugin_analytics.get("downloads", []) 
                                   if datetime.fromtimestamp(d).date() == current_date]),
                    "views": len([v for v in plugin_analytics.get("views", []) 
                                 if datetime.fromtimestamp(v).date() == current_date]),
                    "ratings": len([r for r in plugin_analytics.get("ratings", []) 
                                   if datetime.fromtimestamp(r).date() == current_date])
                }

@app.on_event("startup")
async def startup_event():
    logger.info("Starting AITBC Plugin Registry")
    # Start analytics processing
    asyncio.create_task(process_analytics())

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down AITBC Plugin Registry")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8013, log_level="info")
