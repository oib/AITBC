"""
Marketplace Analytics Domain Models
Implements SQLModel definitions for analytics, insights, and reporting
"""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlmodel import JSON, Column, Field, SQLModel


class AnalyticsPeriod(StrEnum):
    """Analytics period enumeration"""

    REALTIME = "realtime"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class MetricType(StrEnum):
    """Metric type enumeration"""

    VOLUME = "volume"
    COUNT = "count"
    AVERAGE = "average"
    PERCENTAGE = "percentage"
    RATIO = "ratio"
    RATE = "rate"
    VALUE = "value"


class InsightType(StrEnum):
    """Insight type enumeration"""

    TREND = "trend"
    ANOMALY = "anomaly"
    OPPORTUNITY = "opportunity"
    WARNING = "warning"
    PREDICTION = "prediction"
    RECOMMENDATION = "recommendation"


class ReportType(StrEnum):
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
    previous_value: float | None = None
    change_percentage: float | None = None

    # Contextual data
    unit: str = Field(default="")
    category: str = Field(default="general")
    subcategory: str = Field(default="")

    # Geographic and temporal context
    geographic_region: str | None = None
    agent_tier: str | None = None
    trade_type: str | None = None

    # Metadata
    metric_meta_data: dict[str, Any] = Field(default={}, sa_column=Column(JSON))

    # Timestamps
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    period_start: datetime
    period_end: datetime

    # Additional data
    breakdown: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    comparisons: dict[str, Any] = Field(default={}, sa_column=Column(JSON))


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
    related_metrics: list[str] = Field(default=[], sa_column=Column(JSON))
    affected_entities: list[str] = Field(default=[], sa_column=Column(JSON))
    time_horizon: str = Field(default="short_term")  # immediate, short_term, medium_term, long_term

    # Analysis details
    analysis_method: str = Field(default="statistical")
    data_sources: list[str] = Field(default=[], sa_column=Column(JSON))
    assumptions: list[str] = Field(default=[], sa_column=Column(JSON))

    # Recommendations and actions
    recommendations: list[str] = Field(default=[], sa_column=Column(JSON))
    suggested_actions: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSON))

    # Status and tracking
    status: str = Field(default="active")  # active, resolved, expired
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None
    resolved_by: str | None = None
    resolved_at: datetime | None = None

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None

    # Additional data
    insight_data: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    visualization_config: dict[str, Any] = Field(default={}, sa_column=Column(JSON))


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
    filters: dict[str, Any] = Field(default={}, sa_column=Column(JSON))

    # Report content
    summary: str = Field(default="", max_length=2000)
    key_findings: list[str] = Field(default=[], sa_column=Column(JSON))
    recommendations: list[str] = Field(default=[], sa_column=Column(JSON))

    # Report data
    data_sections: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSON))
    charts: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSON))
    tables: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSON))

    # Generation details
    generated_by: str = Field(default="system")  # system, user, scheduled
    generation_time: float = Field(default=0.0)  # seconds
    data_points_analyzed: int = Field(default=0)

    # Status and delivery
    status: str = Field(default="generated")  # generating, generated, failed, delivered
    delivery_method: str = Field(default="api")  # api, email, dashboard
    recipients: list[str] = Field(default=[], sa_column=Column(JSON))

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    delivered_at: datetime | None = None

    # Additional data
    report_metric_meta_data: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    template_used: str | None = None


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
    layout: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    widgets: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSON))
    filters: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSON))

    # Data sources and refresh
    data_sources: list[str] = Field(default=[], sa_column=Column(JSON))
    refresh_interval: int = Field(default=300)  # seconds
    auto_refresh: bool = Field(default=True)

    # Access and permissions
    owner_id: str = Field(index=True)
    viewers: list[str] = Field(default=[], sa_column=Column(JSON))
    editors: list[str] = Field(default=[], sa_column=Column(JSON))
    is_public: bool = Field(default=False)

    # Status and versioning
    status: str = Field(default="active")  # active, inactive, archived
    version: int = Field(default=1)
    last_modified_by: str | None = None

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_viewed_at: datetime | None = None

    # Additional data
    dashboard_settings: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    theme_config: dict[str, Any] = Field(default={}, sa_column=Column(JSON))


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
    parameters: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    data_sources: list[str] = Field(default=[], sa_column=Column(JSON))
    target_metrics: list[str] = Field(default=[], sa_column=Column(JSON))

    # Schedule and execution
    schedule_type: str = Field(default="manual")  # manual, scheduled, triggered
    cron_expression: str | None = None
    next_run: datetime | None = None

    # Execution details
    status: str = Field(default="pending")  # pending, running, completed, failed, cancelled
    progress: float = Field(default=0.0, ge=0, le=100.0)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Results and output
    records_processed: int = Field(default=0)
    records_generated: int = Field(default=0)
    errors: list[str] = Field(default=[], sa_column=Column(JSON))
    output_files: list[str] = Field(default=[], sa_column=Column(JSON))

    # Performance metrics
    execution_time: float = Field(default=0.0)  # seconds
    memory_usage: float = Field(default=0.0)  # MB
    cpu_usage: float = Field(default=0.0)  # percentage

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Additional data
    job_metric_meta_data: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    execution_log: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSON))


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
    conditions: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSON))
    threshold_value: float | None = None
    comparison_operator: str = Field(default="greater_than")  # greater_than, less_than, equals, contains

    # Target metrics and entities
    target_metrics: list[str] = Field(default=[], sa_column=Column(JSON))
    target_entities: list[str] = Field(default=[], sa_column=Column(JSON))
    geographic_scope: list[str] = Field(default=[], sa_column=Column(JSON))

    # Alert configuration
    severity: str = Field(default="medium")  # low, medium, high, critical
    cooldown_period: int = Field(default=300)  # seconds
    auto_resolve: bool = Field(default=False)
    resolve_conditions: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSON))

    # Notification settings
    notification_channels: list[str] = Field(default=[], sa_column=Column(JSON))
    notification_recipients: list[str] = Field(default=[], sa_column=Column(JSON))
    message_template: str = Field(default="", max_length=1000)

    # Status and scheduling
    status: str = Field(default="active")  # active, inactive, disabled
    created_by: str = Field(index=True)
    last_triggered: datetime | None = None
    trigger_count: int = Field(default=0)

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Additional data
    rule_metric_meta_data: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    test_results: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSON))


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
    trigger_value: float | None = None
    threshold_value: float | None = None
    deviation_percentage: float | None = None
    affected_metrics: list[str] = Field(default=[], sa_column=Column(JSON))

    # Context and entities
    geographic_regions: list[str] = Field(default=[], sa_column=Column(JSON))
    affected_agents: list[str] = Field(default=[], sa_column=Column(JSON))
    time_period: dict[str, Any] = Field(default={}, sa_column=Column(JSON))

    # Status and resolution
    status: str = Field(default="active")  # active, acknowledged, resolved, false_positive
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    resolution_notes: str = Field(default="", max_length=1000)

    # Notifications
    notifications_sent: list[str] = Field(default=[], sa_column=Column(JSON))
    delivery_status: dict[str, str] = Field(default={}, sa_column=Column(JSON))

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None

    # Additional data
    alert_data: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    related_insights: list[str] = Field(default=[], sa_column=Column(JSON))


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
    default_dashboard: str | None = None
    preferred_timezone: str = Field(default="UTC")
    date_format: str = Field(default="YYYY-MM-DD")
    time_format: str = Field(default="24h")

    # Metric preferences
    favorite_metrics: list[str] = Field(default=[], sa_column=Column(JSON))
    metric_units: dict[str, str] = Field(default={}, sa_column=Column(JSON))
    default_period: AnalyticsPeriod = Field(default=AnalyticsPeriod.DAILY)

    # Alert preferences
    alert_severity_threshold: str = Field(default="medium")  # low, medium, high, critical
    quiet_hours: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    alert_channels: list[str] = Field(default=[], sa_column=Column(JSON))

    # Report preferences
    auto_subscribe_reports: list[str] = Field(default=[], sa_column=Column(JSON))
    report_format: str = Field(default="json")  # json, csv, pdf, html
    include_charts: bool = Field(default=True)

    # Privacy and security
    data_retention_days: int = Field(default=90)
    share_analytics: bool = Field(default=False)
    anonymous_usage: bool = Field(default=False)

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_login: datetime | None = None

    # Additional preferences
    custom_settings: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    ui_preferences: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
