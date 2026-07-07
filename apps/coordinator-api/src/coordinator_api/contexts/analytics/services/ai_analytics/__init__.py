"""
AI Analytics services (merged from the former ai_analytics context in v0.5.14).
Provides AI-driven analytics, insights, and advanced learning services that
consume the analytics context's domain models.
"""

from .advanced_learning import AdvancedLearningService
from .analytics import AnalyticsEngine, DashboardManager, MarketplaceAnalytics

__all__ = [
    "AdvancedLearningService",
    "AnalyticsEngine",
    "DashboardManager",
    "MarketplaceAnalytics",
]
