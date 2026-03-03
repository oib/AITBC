"""
Marketplace Analytics Domain Models
Implements SQLModel definitions for analytics, insights, and reporting
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from uuid import uuid4
from enum import Enum

from sqlmodel import SQLModel, Field, Column, JSON
from sqlalchemy import DateTime, Float, Integer, Text


class AnalyticsPeriod(str, Enum):
    """Analytics period enumeration"""
    REALTIME = "realtime"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class MetricType(str, Enum):
    """Metric type enumeration"""
    VOLUME = "volume"
    COUNT = "count"
    AVERAGE = "average"
    PERCENTAGE = "percentage"
    RATIO = "ratio"
    RATE = "rate"
    VALUE = "value"


class InsightType(str, Enum):
    """Insight type enumeration"""
    TREND = "trend"
    ANOMALY = "anomaly"
    OPPORTUNITY = "opportunity"
    WARNING = "warning"
    PREDICTION = "prediction"
    RECOMMENDATION = "recommendation"


class ReportType(str, Enum):
    """Report type enumeration"""
    MARKET_OVERVIEW = "market_overview"
    AGENT_PERFORMANCE = "agent_performance"
    ECONOMIC_ANALYSIS = "economic_analysis"
    GEOGRAPHIC_ANALYSIS = "geographic_analysis"
    COMPETITIVE_ANALYSIS = "competitive_analysis"
    RISK_ASSESSMENT = "risk_assessment"


class MarketMetric(SQLModel, table=True):
    """Market metrics and KPIs"""
    
    __tablename__ = "market_metrics"
    __table_args__ = {"extend_existing": True}
    
    id: str = Field(default_factory=lambda: f"metric_{uuid4().hex[:8]}", primary_key=True)
    metric_name: str = Field(index=True)
    metric_type: MetricType
    period_type: AnalyticsPeriod
    
    # Metric values
    value: float = Field(default=0.0)
    previous_value: Optional[float] = None
    change_percentage: Optional[float] = None
    
    # Contextual data
    unit: str = Field(default="")
    category: str = Field(default="general")
    subcategory: str = Field(default="")
    
    # Geographic and temporal context
    geographic_region: Optional[str] = None
    agent_tier: Optional[str] = None
    trade_type: Optional[str] = None
    
    # Metadata
    metric_meta_data: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    
    # Timestamps
    recorded_at: datetime = Field(default_factory=datetime.utcnow)
    period_start: datetime
    period_end: datetime
    
    # Additional data
    breakdown: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    comparisons: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))


class MarketInsight(SQLModel, table=True):
    """Market insights and analysis"""
    
    __tablename__ = "market_insights"
    __table_args__ = {"extend_existing": True}
    
    id: str = Field(default_factory=lambda: f"insight_{uuid4().hex[:8]}", primary_key=True)
    insight_type: InsightType
    title: str = Field(max_length=200)
    description: str = Field(default="", max_length=1000)
    
    # Insight data
    confidence_score: float = Field(default=0.0, ge=0, le=1.0)
    impact_level: str = Field(default="medium")  # low, medium, high, critical
    urgency_level: str = Field(default="normal")  # low, normal, high, urgent
    
    # Related metrics and context
    related_metrics: List[str] = Field(default=[], sa_column=Column(JSON))
    affected_entities: List[str] = Field(default=[], sa_column=Column(JSON))
    time_horizon: str = Field(default="short_term")  # immediate, short_term, medium_term, long_term
    
    # Analysis details
    analysis_method: str = Field(default="statistical")
    data_sources: List[str] = Field(default=[], sa_column=Column(JSON))
    assumptions: List[str] = Field(default=[], sa_column=Column(JSON))
    
    # Recommendations and actions
    recommendations: List[str] = Field(default=[], sa_column=Column(JSON))
    suggested_actions: List[Dict[str, Any]] = Field(default=[], sa_column=Column(JSON))
    
    # Status and tracking
    status: str = Field(default="active")  # active, resolved, expired
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    
    # Additional data
    insight_data: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    visualization_config: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))


class AnalyticsReport(SQLModel, table=True):
    """Generated analytics reports"""
    
    __tablename__ = "analytics_reports"
    __table_args__ = {"extend_existing": True}
    
    id: str = Field(default_factory=lambda: f"report_{uuid4().hex[:8]}", primary_key=True)
    report_id: str = Field(unique=True, index=True)
    
    # Report details
    report_type: ReportType
    title: str = Field(max_length=200)
    description: str = Field(default="", max_length=1000)
    
    # Report parameters
    period_type: AnalyticsPeriod
    start_date: datetime
    end_date: datetime
    filters: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    
    # Report content
    summary: str = Field(default="", max_length=2000)
    key_findings: List[str] = Field(default=[], sa_column=Column(JSON))
    recommendations: List[str] = Field(default=[], sa_column=Column(JSON))
    
    # Report data
    data_sections: List[Dict[str, Any]] = Field(default=[], sa_column=Column(JSON))
    charts: List[Dict[str, Any]] = Field(default=[], sa_column=Column(JSON))
    tables: List[Dict[str, Any]] = Field(default=[], sa_column=Column(JSON))
    
    # Generation details
    generated_by: str = Field(default="system")  # system, user, scheduled
    generation_time: float = Field(default=0.0)  # seconds
    data_points_analyzed: int = Field(default=0)
    
    # Status and delivery
    status: str = Field(default="generated")  # generating, generated, failed, delivered
    delivery_method: str = Field(default="api")  # api, email, dashboard
    recipients: List[str] = Field(default=[], sa_column=Column(JSON))
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    delivered_at: Optional[datetime] = None
    
    # Additional data
    report_metric_meta_data: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    template_used: Optional[str] = None


class DashboardConfig(SQLModel, table=True):
    """Analytics dashboard configurations"""
    
    __tablename__ = "dashboard_configs"
    __table_args__ = {"extend_existing": True}
    
    id: str = Field(default_factory=lambda: f"dashboard_{uuid4().hex[:8]}", primary_key=True)
    dashboard_id: str = Field(unique=True, index=True)
    
    # Dashboard details
    name: str = Field(max_length=100)
    description: str = Field(default="", max_length=500)
    dashboard_type: str = Field(default="custom")  # default, custom, executive, operational
    
    # Layout and configuration
    layout: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    widgets: List[Dict[str, Any]] = Field(default=[], sa_column=Column(JSON))
    filters: List[Dict[str, Any]] = Field(default=[], sa_column=Column(JSON))
    
    # Data sources and refresh
    data_sources: List[str] = Field(default=[], sa_column=Column(JSON))
    refresh_interval: int = Field(default=300)  # seconds
    auto_refresh: bool = Field(default=True)
    
    # Access and permissions
    owner_id: str = Field(index=True)
    viewers: List[str] = Field(default=[], sa_column=Column(JSON))
    editors: List[str] = Field(default=[], sa_column=Column(JSON))
    is_public: bool = Field(default=False)
    
    # Status and versioning
    status: str = Field(default="active")  # active, inactive, archived
    version: int = Field(default=1)
    last_modified_by: Optional[str] = None
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_viewed_at: Optional[datetime] = None
    
    # Additional data
    dashboard_settings: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    theme_config: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))


class DataCollectionJob(SQLModel, table=True):
    """Data collection and processing jobs"""
    
    __tablename__ = "data_collection_jobs"
    __table_args__ = {"extend_existing": True}
    
    id: str = Field(default_factory=lambda: f"job_{uuid4().hex[:8]}", primary_key=True)
    job_id: str = Field(unique=True, index=True)
    
    # Job details
    job_type: str = Field(max_length=50)  # metrics_collection, insight_generation, report_generation
    job_name: str = Field(max_length=100)
    description: str = Field(default="", max_length=500)
    
    # Job parameters
    parameters: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    data_sources: List[str] = Field(default=[], sa_column=Column(JSON))
    target_metrics: List[str] = Field(default=[], sa_column=Column(JSON))
    
    # Schedule and execution
    schedule_type: str = Field(default="manual")  # manual, scheduled, triggered
    cron_expression: Optional[str] = None
    next_run: Optional[datetime] = None
    
    # Execution details
    status: str = Field(default="pending")  # pending, running, completed, failed, cancelled
    progress: float = Field(default=0.0, ge=0, le=100.0)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Results and output
    records_processed: int = Field(default=0)
    records_generated: int = Field(default=0)
    errors: List[str] = Field(default=[], sa_column=Column(JSON))
    output_files: List[str] = Field(default=[], sa_column=Column(JSON))
    
    # Performance metrics
    execution_time: float = Field(default=0.0)  # seconds
    memory_usage: float = Field(default=0.0)  # MB
    cpu_usage: float = Field(default=0.0)  # percentage
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Additional data
    job_metric_meta_data: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    execution_log: List[Dict[str, Any]] = Field(default=[], sa_column=Column(JSON))


class AlertRule(SQLModel, table=True):
    """Analytics alert rules and notifications"""
    
    __tablename__ = "alert_rules"
    __table_args__ = {"extend_existing": True}
    
    id: str = Field(default_factory=lambda: f"alert_{uuid4().hex[:8]}", primary_key=True)
    rule_id: str = Field(unique=True, index=True)
    
    # Rule details
    name: str = Field(max_length=100)
    description: str = Field(default="", max_length=500)
    rule_type: str = Field(default="threshold")  # threshold, anomaly, trend, pattern
    
    # Conditions and triggers
    conditions: List[Dict[str, Any]] = Field(default=[], sa_column=Column(JSON))
    threshold_value: Optional[float] = None
    comparison_operator: str = Field(default="greater_than")  # greater_than, less_than, equals, contains
    
    # Target metrics and entities
    target_metrics: List[str] = Field(default=[], sa_column=Column(JSON))
    target_entities: List[str] = Field(default=[], sa_column=Column(JSON))
    geographic_scope: List[str] = Field(default=[], sa_column=Column(JSON))
    
    # Alert configuration
    severity: str = Field(default="medium")  # low, medium, high, critical
    cooldown_period: int = Field(default=300)  # seconds
    auto_resolve: bool = Field(default=False)
    resolve_conditions: List[Dict[str, Any]] = Field(default=[], sa_column=Column(JSON))
    
    # Notification settings
    notification_channels: List[str] = Field(default=[], sa_column=Column(JSON))
    notification_recipients: List[str] = Field(default=[], sa_column=Column(JSON))
    message_template: str = Field(default="", max_length=1000)
    
    # Status and scheduling
    status: str = Field(default="active")  # active, inactive, disabled
    created_by: str = Field(index=True)
    last_triggered: Optional[datetime] = None
    trigger_count: int = Field(default=0)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Additional data
    rule_metric_meta_data: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    test_results: List[Dict[str, Any]] = Field(default=[], sa_column=Column(JSON))


class AnalyticsAlert(SQLModel, table=True):
    """Generated analytics alerts"""
    
    __tablename__ = "analytics_alerts"
    __table_args__ = {"extend_existing": True}
    
    id: str = Field(default_factory=lambda: f"alert_{uuid4().hex[:8]}", primary_key=True)
    alert_id: str = Field(unique=True, index=True)
    
    # Alert details
    rule_id: str = Field(index=True)
    alert_type: str = Field(max_length=50)
    title: str = Field(max_length=200)
    message: str = Field(default="", max_length=1000)
    
    # Alert data
    severity: str = Field(default="medium")
    confidence: float = Field(default=0.0, ge=0, le=1.0)
    impact_assessment: str = Field(default="", max_length=500)
    
    # Trigger data
    trigger_value: Optional[float] = None
    threshold_value: Optional[float] = None
    deviation_percentage: Optional[float] = None
    affected_metrics: List[str] = Field(default=[], sa_column=Column(JSON))
    
    # Context and entities
    geographic_regions: List[str] = Field(default=[], sa_column=Column(JSON))
    affected_agents: List[str] = Field(default=[], sa_column=Column(JSON))
    time_period: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    
    # Status and resolution
    status: str = Field(default="active")  # active, acknowledged, resolved, false_positive
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolution_notes: str = Field(default="", max_length=1000)
    
    # Notifications
    notifications_sent: List[str] = Field(default=[], sa_column=Column(JSON))
    delivery_status: Dict[str, str] = Field(default={}, sa_column=Column(JSON))
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    
    # Additional data
    alert_data: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    related_insights: List[str] = Field(default=[], sa_column=Column(JSON))


class UserPreference(SQLModel, table=True):
    """User analytics preferences and settings"""
    
    __tablename__ = "user_preferences"
    __table_args__ = {"extend_existing": True}
    
    id: str = Field(default_factory=lambda: f"pref_{uuid4().hex[:8]}", primary_key=True)
    user_id: str = Field(index=True)
    
    # Notification preferences
    email_notifications: bool = Field(default=True)
    alert_notifications: bool = Field(default=True)
    report_notifications: bool = Field(default=False)
    notification_frequency: str = Field(default="daily")  # immediate, daily, weekly, monthly
    
    # Dashboard preferences
    default_dashboard: Optional[str] = None
    preferred_timezone: str = Field(default="UTC")
    date_format: str = Field(default="YYYY-MM-DD")
    time_format: str = Field(default="24h")
    
    # Metric preferences
    favorite_metrics: List[str] = Field(default=[], sa_column=Column(JSON))
    metric_units: Dict[str, str] = Field(default={}, sa_column=Column(JSON))
    default_period: AnalyticsPeriod = Field(default=AnalyticsPeriod.DAILY)
    
    # Alert preferences
    alert_severity_threshold: str = Field(default="medium")  # low, medium, high, critical
    quiet_hours: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    alert_channels: List[str] = Field(default=[], sa_column=Column(JSON))
    
    # Report preferences
    auto_subscribe_reports: List[str] = Field(default=[], sa_column=Column(JSON))
    report_format: str = Field(default="json")  # json, csv, pdf, html
    include_charts: bool = Field(default=True)
    
    # Privacy and security
    data_retention_days: int = Field(default=90)
    share_analytics: bool = Field(default=False)
    anonymous_usage: bool = Field(default=False)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None
    
    # Additional preferences
    custom_settings: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    ui_preferences: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
