"""
Plugin Marketplace Frontend Service for AITBC
Provides web interface and marketplace functionality for plugins
"""

import asyncio
import json
from datetime import datetime, UTC, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from aitbc import get_logger

logger = get_logger(__name__)

app = FastAPI(
    title="AITBC Plugin Marketplace",
    description="Plugin marketplace frontend and community features",
    version="1.0.0"
)

# Data models
class MarketplaceReview(BaseModel):
    plugin_id: str
    user_id: str
    rating: int  # 1-5 stars
    title: str
    content: str
    pros: List[str] = []
    cons: List[str] = []

class PluginPurchase(BaseModel):
    plugin_id: str
    user_id: str
    price: float
    payment_method: str

class DeveloperApplication(BaseModel):
    developer_name: str
    email: str
    company: Optional[str] = None
    experience: str
    portfolio_url: Optional[str] = None
    github_username: Optional[str] = None
    description: str

# In-memory storage (in production, use database)
marketplace_data: Dict[str, Dict] = {}
reviews: Dict[str, List[Dict]] = {}
purchases: Dict[str, List[Dict]] = {}
developer_applications: Dict[str, Dict] = {}
verified_developers: Dict[str, Dict] = {}
revenue_sharing: Dict[str, Dict] = {}

# Static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.get("/")
async def marketplace_home(request: Request):
    """Marketplace homepage"""
    return templates.TemplateResponse("index.html", {
        "request": request,
        "featured_plugins": get_featured_plugins(),
        "popular_plugins": get_popular_plugins(),
        "recent_plugins": get_recent_plugins(),
        "categories": get_categories(),
        "stats": get_marketplace_stats()
    })

@app.get("/plugins")
async def plugins_page(request: Request):
    """Plugin listing page"""
    return templates.TemplateResponse("plugins.html", {
        "request": request,
        "plugins": get_all_plugins(),
        "categories": get_categories(),
        "tags": get_all_tags()
    })

@app.get("/plugins/{plugin_id}")
async def plugin_detail(request: Request, plugin_id: str):
    """Individual plugin detail page"""
    plugin = get_plugin_details(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail="Plugin not found")
    
    return templates.TemplateResponse("plugin_detail.html", {
        "request": request,
        "plugin": plugin,
        "reviews": get_plugin_reviews(plugin_id),
        "related_plugins": get_related_plugins(plugin_id)
    })

@app.get("/developers")
async def developers_page(request: Request):
    """Developer portal page"""
    return templates.TemplateResponse("developers.html", {
        "request": request,
        "verified_developers": get_verified_developers(),
        "developer_stats": get_developer_stats()
    })

@app.get("/submit")
async def submit_plugin_page(request: Request):
    """Plugin submission page"""
    return templates.TemplateResponse("submit.html", {
        "request": request,
        "categories": get_categories(),
        "guidelines": get_submission_guidelines()
    })

# API endpoints
@app.get("/api/v1/marketplace/featured")
async def get_featured_plugins_api():
    """Get featured plugins for marketplace"""
    return {
        "featured_plugins": get_featured_plugins(),
        "generated_at": datetime.now(datetime.UTC).isoformat()
    }

@app.get("/api/v1/marketplace/popular")
async def get_popular_plugins_api(limit: int = 12):
    """Get popular plugins"""
    return {
        "popular_plugins": get_popular_plugins(limit),
        "generated_at": datetime.now(datetime.UTC).isoformat()
    }

@app.get("/api/v1/marketplace/recent")
async def get_recent_plugins_api(limit: int = 12):
    """Get recently added plugins"""
    return {
        "recent_plugins": get_recent_plugins(limit),
        "generated_at": datetime.now(datetime.UTC).isoformat()
    }

@app.get("/api/v1/marketplace/stats")
async def get_marketplace_stats_api():
    """Get marketplace statistics"""
    return {
        "stats": get_marketplace_stats(),
        "generated_at": datetime.now(datetime.UTC).isoformat()
    }

@app.post("/api/v1/reviews")
async def create_review(review: MarketplaceReview):
    """Create a plugin review"""
    review_id = f"review_{int(datetime.now(datetime.UTC).timestamp())}"
    
    review_record = {
        "review_id": review_id,
        "plugin_id": review.plugin_id,
        "user_id": review.user_id,
        "rating": review.rating,
        "title": review.title,
        "content": review.content,
        "pros": review.pros,
        "cons": review.cons,
        "helpful_votes": 0,
        "created_at": datetime.now(datetime.UTC).isoformat(),
        "verified_purchase": False
    }
    
    if review.plugin_id not in reviews:
        reviews[review.plugin_id] = []
    
    reviews[review.plugin_id].append(review_record)
    
    logger.info(f"Review created for plugin {review.plugin_id}: {review.rating} stars")
    
    return {
        "review_id": review_id,
        "status": "created",
        "rating": review.rating,
        "created_at": review_record["created_at"]
    }

@app.get("/api/v1/reviews/{plugin_id}")
async def get_plugin_reviews_api(plugin_id: str):
    """Get all reviews for a plugin"""
    plugin_reviews = reviews.get(plugin_id, [])
    
    # Calculate average rating
    if plugin_reviews:
        avg_rating = sum(r["rating"] for r in plugin_reviews) / len(plugin_reviews)
    else:
        avg_rating = 0.0
    
    return {
        "plugin_id": plugin_id,
        "reviews": plugin_reviews,
        "total_reviews": len(plugin_reviews),
        "average_rating": avg_rating,
        "rating_distribution": get_rating_distribution(plugin_reviews)
    }

@app.post("/api/v1/purchases")
async def create_purchase(purchase: PluginPurchase):
    """Create a plugin purchase"""
    purchase_id = f"purchase_{int(datetime.now(datetime.UTC).timestamp())}"
    
    purchase_record = {
        "purchase_id": purchase_id,
        "plugin_id": purchase.plugin_id,
        "user_id": purchase.user_id,
        "price": purchase.price,
        "payment_method": purchase.payment_method,
        "status": "completed",
        "created_at": datetime.now(datetime.UTC).isoformat(),
        "refund_deadline": (datetime.now(datetime.UTC) + timedelta(days=30)).isoformat()
    }
    
    if purchase.plugin_id not in purchases:
        purchases[purchase.plugin_id] = []
    
    purchases[purchase.plugin_id].append(purchase_record)
    
    # Update revenue sharing
    update_revenue_sharing(purchase.plugin_id, purchase.price)
    
    logger.info(f"Purchase created for plugin {purchase.plugin_id}: ${purchase.price}")
    
    return {
        "purchase_id": purchase_id,
        "status": "completed",
        "price": purchase.price,
        "created_at": purchase_record["created_at"]
    }

@app.post("/api/v1/developers/apply")
async def apply_developer(application: DeveloperApplication):
    """Apply to become a verified developer"""
    application_id = f"dev_app_{int(datetime.now(datetime.UTC).timestamp())}"
    
    application_record = {
        "application_id": application_id,
        "developer_name": application.developer_name,
        "email": application.email,
        "company": application.company,
        "experience": application.experience,
        "portfolio_url": application.portfolio_url,
        "github_username": application.github_username,
        "description": application.description,
        "status": "pending",
        "submitted_at": datetime.now(datetime.UTC).isoformat(),
        "reviewed_at": None,
        "reviewer_notes": None
    }
    
    developer_applications[application_id] = application_record
    
    logger.info(f"Developer application submitted: {application.developer_name}")
    
    return {
        "application_id": application_id,
        "status": "pending",
        "submitted_at": application_record["submitted_at"]
    }

@app.get("/api/v1/developers/verified")
async def get_verified_developers_api():
    """Get list of verified developers"""
    return {
        "verified_developers": get_verified_developers(),
        "total_developers": len(verified_developers),
        "generated_at": datetime.now(datetime.UTC).isoformat()
    }

@app.get("/api/v1/revenue/{developer_id}")
async def get_developer_revenue(developer_id: str):
    """Get revenue information for a developer"""
    developer_revenue = revenue_sharing.get(developer_id, {
        "total_revenue": 0.0,
        "plugin_revenue": {},
        "monthly_revenue": {},
        "last_updated": datetime.now(datetime.UTC).isoformat()
    })
    
    return developer_revenue

# Helper functions
def get_featured_plugins() -> List[Dict]:
    """Get featured plugins"""
    # In production, this would be based on editorial selection or algorithm
    featured_plugins = []
    
    # Mock data for demo
    featured_plugins = [
        {
            "plugin_id": "ai_trading_bot",
            "name": "AI Trading Bot",
            "description": "Advanced AI-powered trading automation",
            "author": "AITBC Labs",
            "category": "ai",
            "rating": 4.8,
            "downloads": 15420,
            "price": 99.99,
            "featured": True
        },
        {
            "plugin_id": "blockchain_analyzer",
            "name": "Blockchain Analyzer",
            "description": "Comprehensive blockchain analytics and monitoring",
            "author": "CryptoTools",
            "category": "blockchain",
            "rating": 4.6,
            "downloads": 12350,
            "price": 149.99,
            "featured": True
        }
    ]
    
    return featured_plugins

def get_popular_plugins(limit: int = 12) -> List[Dict]:
    """Get popular plugins"""
    # Mock data for demo
    popular_plugins = [
        {
            "plugin_id": "cli_enhancer",
            "name": "CLI Enhancer",
            "description": "Enhanced CLI commands and shortcuts",
            "author": "DevTools",
            "category": "cli",
            "rating": 4.7,
            "downloads": 8920,
            "price": 29.99
        },
        {
            "plugin_id": "web_dashboard",
            "name": "Web Dashboard",
            "description": "Beautiful web dashboard for AITBC",
            "author": "WebCraft",
            "category": "web",
            "rating": 4.5,
            "downloads": 7650,
            "price": 79.99
        }
    ]
    
    return popular_plugins[:limit]

def get_recent_plugins(limit: int = 12) -> List[Dict]:
    """Get recently added plugins"""
    # Mock data for demo
    recent_plugins = [
        {
            "plugin_id": "security_scanner",
            "name": "Security Scanner",
            "description": "Advanced security vulnerability scanner",
            "author": "SecureDev",
            "category": "security",
            "rating": 4.9,
            "downloads": 2340,
            "price": 199.99,
            "created_at": (datetime.now(datetime.UTC) - timedelta(days=3)).isoformat()
        },
        {
            "plugin_id": "performance_monitor",
            "name": "Performance Monitor",
            "description": "Real-time performance monitoring and alerts",
            "author": "PerfTools",
            "category": "monitoring",
            "rating": 4.4,
            "downloads": 1890,
            "price": 59.99,
            "created_at": (datetime.now(datetime.UTC) - timedelta(days=7)).isoformat()
        }
    ]
    
    return recent_plugins[:limit]

def get_categories() -> List[Dict]:
    """Get plugin categories"""
    categories = [
        {"name": "ai", "display_name": "AI & Machine Learning", "count": 45},
        {"name": "blockchain", "display_name": "Blockchain", "count": 32},
        {"name": "cli", "display_name": "CLI Tools", "count": 28},
        {"name": "web", "display_name": "Web & UI", "count": 24},
        {"name": "security", "display_name": "Security", "count": 18},
        {"name": "monitoring", "display_name": "Monitoring", "count": 15}
    ]
    
    return categories

def get_all_plugins() -> List[Dict]:
    """Get all plugins"""
    # Mock data for demo
    all_plugins = get_featured_plugins() + get_popular_plugins() + get_recent_plugins()
    return all_plugins

def get_all_tags() -> List[str]:
    """Get all plugin tags"""
    tags = ["automation", "trading", "analytics", "security", "monitoring", "dashboard", "cli", "ai", "blockchain", "web"]
    return tags

def get_plugin_details(plugin_id: str) -> Optional[Dict]:
    """Get detailed plugin information"""
    # Mock data for demo
    plugins = {
        "ai_trading_bot": {
            "plugin_id": "ai_trading_bot",
            "name": "AI Trading Bot",
            "description": "Advanced AI-powered trading automation with machine learning algorithms for optimal trading strategies",
            "author": "AITBC Labs",
            "category": "ai",
            "tags": ["automation", "trading", "ai", "machine-learning"],
            "rating": 4.8,
            "downloads": 15420,
            "price": 99.99,
            "version": "2.1.0",
            "last_updated": (datetime.now(datetime.UTC) - timedelta(days=15)).isoformat(),
            "repository_url": "https://github.com/aitbc-labs/ai-trading-bot",
            "homepage_url": "https://aitbc-trading-bot.com",
            "license": "MIT",
            "screenshots": [
                "/static/screenshots/trading-bot-1.png",
                "/static/screenshots/trading-bot-2.png"
            ],
            "changelog": "Added new ML models, improved performance, bug fixes",
            "compatibility": ["v1.0.0+", "v2.0.0+"]
        }
    }
    
    return plugins.get(plugin_id)

def get_plugin_reviews(plugin_id: str) -> List[Dict]:
    """Get reviews for a plugin"""
    # Mock data for demo
    mock_reviews = [
        {
            "review_id": "review_1",
            "user_id": "user123",
            "rating": 5,
            "title": "Excellent Trading Bot",
            "content": "This plugin has transformed my trading strategy. Highly recommended!",
            "pros": ["Easy to use", "Great performance", "Good documentation"],
            "cons": ["Initial setup complexity"],
            "helpful_votes": 23,
            "created_at": (datetime.now(datetime.UTC) - timedelta(days=10)).isoformat()
        },
        {
            "review_id": "review_2",
            "user_id": "user456",
            "rating": 4,
            "title": "Good but needs improvements",
            "content": "Solid plugin with room for improvement in the UI.",
            "pros": ["Powerful features", "Good support"],
            "cons": ["UI could be better", "Learning curve"],
            "helpful_votes": 15,
            "created_at": (datetime.now(datetime.UTC) - timedelta(days=25)).isoformat()
        }
    ]
    
    return mock_reviews

def get_related_plugins(plugin_id: str) -> List[Dict]:
    """Get related plugins"""
    # Mock data for demo
    related_plugins = [
        {
            "plugin_id": "market_analyzer",
            "name": "Market Analyzer",
            "description": "Advanced market analysis tools",
            "rating": 4.6,
            "price": 79.99
        },
        {
            "plugin_id": "risk_manager",
            "name": "Risk Manager",
            "description": "Comprehensive risk management system",
            "rating": 4.5,
            "price": 89.99
        }
    ]
    
    return related_plugins

def get_verified_developers() -> List[Dict]:
    """Get verified developers"""
    # Mock data for demo
    verified_devs = [
        {
            "developer_id": "aitbc_labs",
            "name": "AITBC Labs",
            "description": "Official AITBC development team",
            "plugins_count": 12,
            "total_downloads": 45680,
            "verified_since": "2025-01-15",
            "avatar": "/static/avatars/aitbc-labs.png"
        },
        {
            "developer_id": "crypto_tools",
            "name": "CryptoTools",
            "description": "Professional blockchain tools provider",
            "plugins_count": 8,
            "total_downloads": 23450,
            "verified_since": "2025-03-01",
            "avatar": "/static/avatars/crypto-tools.png"
        }
    ]
    
    return verified_devs

def get_developer_stats() -> Dict:
    """Get developer statistics"""
    return {
        "total_developers": 156,
        "verified_developers": 23,
        "total_revenue_paid": 1250000.00,
        "active_developers": 89
    }

def get_submission_guidelines() -> Dict:
    """Get plugin submission guidelines"""
    return {
        "requirements": [
            "Plugin must be compatible with AITBC v2.0+",
            "Code must be open source with appropriate license",
            "Comprehensive documentation required",
            "Security scan must pass",
            "Unit tests with 80%+ coverage"
        ],
        "process": [
            "Submit plugin for review",
            "Security and quality assessment",
            "Community review period",
            "Final approval and publication"
        ],
        "benefits": [
            "Revenue sharing (70% to developer)",
            "Featured placement opportunities",
            "Developer support and resources",
            "Community recognition"
        ]
    }

def get_marketplace_stats() -> Dict:
    """Get marketplace statistics"""
    return {
        "total_plugins": 234,
        "total_developers": 156,
        "total_downloads": 1256780,
        "total_revenue": 2345678.90,
        "active_users": 45678,
        "featured_plugins": 12,
        "categories": 8
    }

def get_rating_distribution(reviews: List[Dict]) -> Dict:
    """Get rating distribution"""
    distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for review in reviews:
        distribution[review["rating"]] += 1
    return distribution

def update_revenue_sharing(plugin_id: str, price: float):
    """Update revenue sharing records"""
    # Mock implementation - in production, this would calculate actual revenue sharing
    developer_share = price * 0.7  # 70% to developer
    platform_share = price * 0.3   # 30% to platform
    
    # Update records (simplified for demo)
    if "revenue_sharing" not in revenue_sharing:
        revenue_sharing["revenue_sharing"] = {
            "total_revenue": 0.0,
            "developer_revenue": 0.0,
            "platform_revenue": 0.0
        }
    
    revenue_sharing["revenue_sharing"]["total_revenue"] += price
    revenue_sharing["revenue_sharing"]["developer_revenue"] += developer_share
    revenue_sharing["revenue_sharing"]["platform_revenue"] += platform_share

# Background task for marketplace analytics
async def update_marketplace_analytics():
    """Background task to update marketplace analytics"""
    while True:
        await asyncio.sleep(3600)  # Update every hour
        
        # Update trending plugins
        # Update revenue calculations
        # Update user engagement metrics
        logger.info("Marketplace analytics updated")

@app.on_event("startup")
async def startup_event():
    logger.info("Starting AITBC Plugin Marketplace")
    # Start analytics processing
    asyncio.create_task(update_marketplace_analytics())

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down AITBC Plugin Marketplace")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8014, log_level="info")
