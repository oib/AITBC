"""
Alerting System for AITBC Agent Coordinator
Implements comprehensive alerting with multiple channels and SLA monitoring
"""

import asyncio
import smtplib
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import json

from aitbc import get_logger

# Try to import email modules, handle gracefully if not available
try:
    from email.mime.text import MimeText
    from email.mime.multipart import MimeMultipart
    EMAIL_AVAILABLE = True
except ImportError:
    EMAIL_AVAILABLE = False
    MimeText = None
    MimeMultipart = None

import requests

logger = get_logger(__name__)

class AlertSeverity(Enum):
    """Alert severity levels"""
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"
    DEBUG = "debug"

class AlertStatus(Enum):
    """Alert status"""
    ACTIVE = "active"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"

class NotificationChannel(Enum):
    """Notification channels"""
    EMAIL = "email"
    SLACK = "slack"
    WEBHOOK = "webhook"
    LOG = "log"

@dataclass
class Alert:
    """Alert definition"""
    alert_id: str
    name: str
    description: str
    severity: AlertSeverity
    status: AlertStatus
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime] = None
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)
    source: str = "aitbc-agent-coordinator"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert alert to dictionary"""
        return {
            "alert_id": self.alert_id,
            "name": self.name,
            "description": self.description,
            "severity": self.severity.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "labels": self.labels,
            "annotations": self.annotations,
            "source": self.source
        }

@dataclass
class AlertRule:
    """Alert rule definition"""
    rule_id: str
    name: str
    description: str
    severity: AlertSeverity
    condition: str  # Expression language
    threshold: float
    duration: timedelta  # How long condition must be met
    enabled: bool = True
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)
    notification_channels: List[NotificationChannel] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert rule to dictionary"""
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "description": self.description,
            "severity": self.severity.value,
            "condition": self.condition,
            "threshold": self.threshold,
            "duration_seconds": self.duration.total_seconds(),
            "enabled": self.enabled,
            "labels": self.labels,
            "annotations": self.annotations,
            "notification_channels": [ch.value for ch in self.notification_channels]
        }

class SLAMonitor:
    """SLA monitoring and compliance tracking"""
    
    def __init__(self):
        self.sla_rules = {}  # {sla_id: SLARule}
        self.sla_metrics = {}  # {sla_id: [compliance_data]}
        self.violations = {}  # {sla_id: [violations]}
    
    def add_sla_rule(self, sla_id: str, name: str, target: float, window: timedelta, metric: str):
        """Add SLA rule"""
        self.sla_rules[sla_id] = {
            "name": name,
            "target": target,
            "window": window,
            "metric": metric
        }
        self.sla_metrics[sla_id] = []
        self.violations[sla_id] = []
    
    def record_metric(self, sla_id: str, value: float, timestamp: datetime = None):
        """Record SLA metric value"""
        if sla_id not in self.sla_rules:
            return
        
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        
        rule = self.sla_rules[sla_id]
        
        # Check if SLA is violated
        is_violation = value > rule["target"]  # Assuming lower is better
        
        if is_violation:
            self.violations[sla_id].append({
                "timestamp": timestamp,
                "value": value,
                "target": rule["target"]
            })
        
        self.sla_metrics[sla_id].append({
            "timestamp": timestamp,
            "value": value,
            "violation": is_violation
        })
        
        # Keep only recent data
        cutoff = timestamp - rule["window"]
        self.sla_metrics[sla_id] = [
            m for m in self.sla_metrics[sla_id] 
            if m["timestamp"] > cutoff
        ]
    
    def get_sla_compliance(self, sla_id: str) -> Dict[str, Any]:
        """Get SLA compliance status"""
        if sla_id not in self.sla_rules:
            return {"status": "error", "message": "SLA rule not found"}
        
        rule = self.sla_rules[sla_id]
        metrics = self.sla_metrics[sla_id]
        
        if not metrics:
            return {
                "status": "success",
                "sla_id": sla_id,
                "name": rule["name"],
                "target": rule["target"],
                "compliance_percentage": 100.0,
                "total_measurements": 0,
                "violations_count": 0,
                "recent_violations": []
            }
        
        total_measurements = len(metrics)
        violations_count = sum(1 for m in metrics if m["violation"])
        compliance_percentage = ((total_measurements - violations_count) / total_measurements) * 100
        
        # Get recent violations
        recent_violations = [
            v for v in self.violations[sla_id]
            if v["timestamp"] > datetime.now(timezone.utc) - timedelta(hours=24)
        ]
        
        return {
            "status": "success",
            "sla_id": sla_id,
            "name": rule["name"],
            "target": rule["target"],
            "compliance_percentage": compliance_percentage,
            "total_measurements": total_measurements,
            "violations_count": violations_count,
            "recent_violations": recent_violations
        }
    
    def get_all_sla_status(self) -> Dict[str, Any]:
        """Get status of all SLAs"""
        status = {}
        for sla_id in self.sla_rules:
            status[sla_id] = self.get_sla_compliance(sla_id)
        
        return {
            "status": "success",
            "total_slas": len(self.sla_rules),
            "sla_status": status,
            "overall_compliance": self._calculate_overall_compliance()
        }
    
    def _calculate_overall_compliance(self) -> float:
        """Calculate overall SLA compliance"""
        if not self.sla_metrics:
            return 100.0
        
        total_measurements = 0
        total_violations = 0
        
        for sla_id, metrics in self.sla_metrics.items():
            total_measurements += len(metrics)
            total_violations += sum(1 for m in metrics if m["violation"])
        
        if total_measurements == 0:
            return 100.0
        
        return ((total_measurements - total_violations) / total_measurements) * 100

class NotificationManager:
    """Manages notifications across different channels"""
    
    def __init__(self):
        self.email_config = {}
        self.slack_config = {}
        self.webhook_configs = {}
    
    def configure_email(self, smtp_server: str, smtp_port: int, username: str, password: str, from_email: str):
        """Configure email notifications"""
        self.email_config = {
            "smtp_server": smtp_server,
            "smtp_port": smtp_port,
            "username": username,
            "password": password,
            "from_email": from_email
        }
    
    def configure_slack(self, webhook_url: str, channel: str):
        """Configure Slack notifications"""
        self.slack_config = {
            "webhook_url": webhook_url,
            "channel": channel
        }
    
    def add_webhook(self, name: str, url: str, headers: Dict[str, str] = None):
        """Add webhook configuration"""
        self.webhook_configs[name] = {
            "url": url,
            "headers": headers or {}
        }
    
    async def send_notification(self, channel: NotificationChannel, alert: Alert, message: str):
        """Send notification through specified channel"""
        try:
            if channel == NotificationChannel.EMAIL:
                await self._send_email(alert, message)
            elif channel == NotificationChannel.SLACK:
                await self._send_slack(alert, message)
            elif channel == NotificationChannel.WEBHOOK:
                await self._send_webhook(alert, message)
            elif channel == NotificationChannel.LOG:
                self._send_log(alert, message)
            
            logger.info(f"Notification sent via {channel.value} for alert {alert.alert_id}")
            
        except Exception as e:
            logger.error(f"Failed to send notification via {channel.value}: {e}")
    
    async def _send_email(self, alert: Alert, message: str):
        """Send email notification"""
        if not EMAIL_AVAILABLE:
            logger.warning("Email functionality not available")
            return
        
        if not self.email_config:
            logger.warning("Email not configured")
            return
        
        try:
            msg = MimeMultipart()
            msg['From'] = self.email_config['from_email']
            msg['To'] = 'admin@aitbc.local'  # Default recipient
            msg['Subject'] = f"[{alert.severity.value.upper()}] {alert.name}"
            
            body = f"""
Alert: {alert.name}
Severity: {alert.severity.value}
Status: {alert.status.value}
Description: {alert.description}
Created: {alert.created_at}
Source: {alert.source}

{message}

Labels: {json.dumps(alert.labels, indent=2)}
Annotations: {json.dumps(alert.annotations, indent=2)}
            """
            
            msg.attach(MimeText(body, 'plain'))
            
            server = smtplib.SMTP(self.email_config['smtp_server'], self.email_config['smtp_port'])
            server.starttls()
            server.login(self.email_config['username'], self.email_config['password'])
            server.send_message(msg)
            server.quit()
            
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
    
    async def _send_slack(self, alert: Alert, message: str):
        """Send Slack notification"""
        if not self.slack_config:
            logger.warning("Slack not configured")
            return
        
        try:
            color = {
                AlertSeverity.CRITICAL: "danger",
                AlertSeverity.WARNING: "warning",
                AlertSeverity.INFO: "good",
                AlertSeverity.DEBUG: "gray"
            }.get(alert.severity, "gray")
            
            payload = {
                "channel": self.slack_config["channel"],
                "username": "AITBC Alert Manager",
                "icon_emoji": ":warning:",
                "attachments": [{
                    "color": color,
                    "title": alert.name,
                    "text": alert.description,
                    "fields": [
                        {"title": "Severity", "value": alert.severity.value, "short": True},
                        {"title": "Status", "value": alert.status.value, "short": True},
                        {"title": "Source", "value": alert.source, "short": True},
                        {"title": "Created", "value": alert.created_at.strftime("%Y-%m-%d %H:%M:%S"), "short": True}
                    ],
                    "text": message,
                    "footer": "AITBC Agent Coordinator",
                    "ts": int(alert.created_at.timestamp())
                }]
            }
            
            response = requests.post(
                self.slack_config["webhook_url"],
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            
        except Exception as e:
            logger.error(f"Failed to send Slack notification: {e}")
    
    async def _send_webhook(self, alert: Alert, message: str):
        """Send webhook notification"""
        webhook_configs = self.webhook_configs
        
        for name, config in webhook_configs.items():
            try:
                payload = {
                    "alert": alert.to_dict(),
                    "message": message,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
                response = requests.post(
                    config["url"],
                    json=payload,
                    headers=config["headers"],
                    timeout=10
                )
                response.raise_for_status()
                
            except Exception as e:
                logger.error(f"Failed to send webhook to {name}: {e}")
    
    def _send_log(self, alert: Alert, message: str):
        """Send log notification"""
        log_level = {
            AlertSeverity.CRITICAL: logging.CRITICAL,
            AlertSeverity.WARNING: logging.WARNING,
            AlertSeverity.INFO: logging.INFO,
            AlertSeverity.DEBUG: logging.DEBUG
        }.get(alert.severity, logging.INFO)
        
        logger.log(
            log_level,
            f"ALERT [{alert.severity.value.upper()}] {alert.name}: {alert.description} - {message}"
        )

class AlertManager:
    """Main alert management system"""
    
    def __init__(self):
        self.alerts = {}  # {alert_id: Alert}
        self.rules = {}  # {rule_id: AlertRule}
        self.notification_manager = NotificationManager()
        self.sla_monitor = SLAMonitor()
        self.active_conditions = {}  # {rule_id: start_time}
        
        # Initialize default rules
        self._initialize_default_rules()
    
    def _initialize_default_rules(self):
        """Initialize default alert rules"""
        default_rules = [
            AlertRule(
                rule_id="high_error_rate",
                name="High Error Rate",
                description="Error rate exceeds threshold",
                severity=AlertSeverity.WARNING,
                condition="error_rate > threshold",
                threshold=0.05,  # 5% error rate
                duration=timedelta(minutes=5),
                labels={"component": "api"},
                annotations={"runbook_url": "https://docs.aitbc.local/runbooks/error_rate"},
                notification_channels=[NotificationChannel.LOG, NotificationChannel.EMAIL]
            ),
            AlertRule(
                rule_id="high_response_time",
                name="High Response Time",
                description="Response time exceeds threshold",
                severity=AlertSeverity.WARNING,
                condition="response_time > threshold",
                threshold=2.0,  # 2 seconds
                duration=timedelta(minutes=3),
                labels={"component": "api"},
                notification_channels=[NotificationChannel.LOG]
            ),
            AlertRule(
                rule_id="agent_count_low",
                name="Low Agent Count",
                description="Number of active agents is below threshold",
                severity=AlertSeverity.CRITICAL,
                condition="agent_count < threshold",
                threshold=3,  # Minimum 3 agents
                duration=timedelta(minutes=2),
                labels={"component": "agents"},
                notification_channels=[NotificationChannel.LOG, NotificationChannel.EMAIL]
            ),
            AlertRule(
                rule_id="memory_usage_high",
                name="High Memory Usage",
                description="Memory usage exceeds threshold",
                severity=AlertSeverity.WARNING,
                condition="memory_usage > threshold",
                threshold=0.85,  # 85% memory usage
                duration=timedelta(minutes=5),
                labels={"component": "system"},
                notification_channels=[NotificationChannel.LOG]
            ),
            AlertRule(
                rule_id="cpu_usage_high",
                name="High CPU Usage",
                description="CPU usage exceeds threshold",
                severity=AlertSeverity.WARNING,
                condition="cpu_usage > threshold",
                threshold=0.80,  # 80% CPU usage
                duration=timedelta(minutes=5),
                labels={"component": "system"},
                notification_channels=[NotificationChannel.LOG]
            )
        ]
        
        for rule in default_rules:
            self.rules[rule.rule_id] = rule
    
    def add_rule(self, rule: AlertRule):
        """Add alert rule"""
        self.rules[rule.rule_id] = rule
    
    def remove_rule(self, rule_id: str):
        """Remove alert rule"""
        if rule_id in self.rules:
            del self.rules[rule_id]
        if rule_id in self.active_conditions:
            del self.active_conditions[rule_id]
    
    def evaluate_rules(self, metrics: Dict[str, Any]):
        """Evaluate all alert rules against current metrics"""
        for rule_id, rule in self.rules.items():
            if not rule.enabled:
                continue
            
            try:
                condition_met = self._evaluate_condition(rule.condition, metrics, rule.threshold)
                current_time = datetime.now(timezone.utc)
                
                if condition_met:
                    # Check if condition has been met for required duration
                    if rule_id not in self.active_conditions:
                        self.active_conditions[rule_id] = current_time
                    elif current_time - self.active_conditions[rule_id] >= rule.duration:
                        # Trigger alert
                        self._trigger_alert(rule, metrics)
                        # Reset to avoid duplicate alerts
                        self.active_conditions[rule_id] = current_time
                else:
                    # Clear condition if not met
                    if rule_id in self.active_conditions:
                        del self.active_conditions[rule_id]
                
            except Exception as e:
                logger.error(f"Error evaluating rule {rule_id}: {e}")
    
    def _evaluate_condition(self, condition: str, metrics: Dict[str, Any], threshold: float) -> bool:
        """Evaluate alert condition"""
        # Simple condition evaluation for demo
        # In production, use a proper expression parser
        
        if "error_rate" in condition:
            error_rate = metrics.get("error_rate", 0)
            return error_rate > threshold
        elif "response_time" in condition:
            response_time = metrics.get("avg_response_time", 0)
            return response_time > threshold
        elif "agent_count" in condition:
            agent_count = metrics.get("active_agents", 0)
            return agent_count < threshold
        elif "memory_usage" in condition:
            memory_usage = metrics.get("memory_usage_percent", 0)
            return memory_usage > threshold
        elif "cpu_usage" in condition:
            cpu_usage = metrics.get("cpu_usage_percent", 0)
            return cpu_usage > threshold
        
        return False
    
    def _trigger_alert(self, rule: AlertRule, metrics: Dict[str, Any]):
        """Trigger an alert"""
        alert_id = f"{rule.rule_id}_{int(datetime.now(timezone.utc).timestamp())}"
        
        # Check if similar alert is already active
        existing_alert = self._find_similar_active_alert(rule)
        if existing_alert:
            return  # Don't duplicate active alerts
        
        alert = Alert(
            alert_id=alert_id,
            name=rule.name,
            description=rule.description,
            severity=rule.severity,
            status=AlertStatus.ACTIVE,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            labels=rule.labels.copy(),
            annotations=rule.annotations.copy()
        )
        
        # Add metric values to annotations
        alert.annotations.update({
            "error_rate": str(metrics.get("error_rate", "N/A")),
            "response_time": str(metrics.get("avg_response_time", "N/A")),
            "agent_count": str(metrics.get("active_agents", "N/A")),
            "memory_usage": str(metrics.get("memory_usage_percent", "N/A")),
            "cpu_usage": str(metrics.get("cpu_usage_percent", "N/A"))
        })
        
        self.alerts[alert_id] = alert
        
        # Send notifications
        message = self._generate_alert_message(alert, metrics)
        for channel in rule.notification_channels:
            asyncio.create_task(self.notification_manager.send_notification(channel, alert, message))
    
    def _find_similar_active_alert(self, rule: AlertRule) -> Optional[Alert]:
        """Find similar active alert"""
        for alert in self.alerts.values():
            if (alert.status == AlertStatus.ACTIVE and 
                alert.name == rule.name and
                alert.labels == rule.labels):
                return alert
        return None
    
    def _generate_alert_message(self, alert: Alert, metrics: Dict[str, Any]) -> str:
        """Generate alert message"""
        message_parts = [
            f"Alert triggered for {alert.name}",
            f"Current metrics:"
        ]
        
        for key, value in metrics.items():
            if isinstance(value, (int, float)):
                message_parts.append(f"  {key}: {value:.2f}")
        
        return "\n".join(message_parts)
    
    def resolve_alert(self, alert_id: str) -> Dict[str, Any]:
        """Resolve an alert"""
        if alert_id not in self.alerts:
            return {"status": "error", "message": "Alert not found"}
        
        alert = self.alerts[alert_id]
        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.now(timezone.utc)
        alert.updated_at = datetime.now(timezone.utc)
        
        return {"status": "success", "alert": alert.to_dict()}
    
    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get all active alerts"""
        return [
            alert.to_dict() for alert in self.alerts.values()
            if alert.status == AlertStatus.ACTIVE
        ]
    
    def get_alert_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get alert history"""
        sorted_alerts = sorted(
            self.alerts.values(),
            key=lambda a: a.created_at,
            reverse=True
        )
        
        return [alert.to_dict() for alert in sorted_alerts[:limit]]
    
    def get_alert_stats(self) -> Dict[str, Any]:
        """Get alert statistics"""
        total_alerts = len(self.alerts)
        active_alerts = len([a for a in self.alerts.values() if a.status == AlertStatus.ACTIVE])
        
        severity_counts = {}
        for severity in AlertSeverity:
            severity_counts[severity.value] = len([
                a for a in self.alerts.values() 
                if a.severity == severity
            ])
        
        return {
            "total_alerts": total_alerts,
            "active_alerts": active_alerts,
            "severity_breakdown": severity_counts,
            "total_rules": len(self.rules),
            "enabled_rules": len([r for r in self.rules.values() if r.enabled])
        }

# Global alert manager instance
alert_manager = AlertManager()
