"""
AITBC Production Monitoring and Analytics

This module provides comprehensive monitoring and analytics capabilities
for the AITBC production environment, including metrics collection,
alerting, and dashboard generation.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path
import subprocess
import psutil
import aiohttp
import statistics


@dataclass
class SystemMetrics:
    """System performance metrics."""
    timestamp: float
    cpu_percent: float
    memory_percent: float
    disk_usage: float
    network_io: Dict[str, int]
    process_count: int
    load_average: List[float]


@dataclass
class ApplicationMetrics:
    """Application performance metrics."""
    timestamp: float
    active_users: int
    api_requests: int
    response_time_avg: float
    response_time_p95: float
    error_rate: float
    throughput: float
    cache_hit_rate: float


@dataclass
class BlockchainMetrics:
    """Blockchain network metrics."""
    timestamp: float
    block_height: int
    gas_price: float
    transaction_count: int
    network_hashrate: float
    peer_count: int
    sync_status: str


@dataclass
class SecurityMetrics:
    """Security monitoring metrics."""
    timestamp: float
    failed_logins: int
    suspicious_ips: int
    security_events: int
    vulnerability_scans: int
    blocked_requests: int
    audit_log_entries: int


class ProductionMonitor:
    """Production monitoring system."""
    
    def __init__(self, config_path: str = "config/monitoring_config.json"):
        self.config = self._load_config(config_path)
        self.logger = self._setup_logging()
        self.metrics_history = {
            "system": [],
            "application": [],
            "blockchain": [],
            "security": []
        }
        self.alerts = []
        self.dashboards = {}
    
    def _load_config(self, config_path: str) -> Dict:
        """Load monitoring configuration."""
        default_config = {
            "collection_interval": 60,  # seconds
            "retention_days": 30,
            "alert_thresholds": {
                "cpu_percent": 80,
                "memory_percent": 85,
                "disk_usage": 90,
                "error_rate": 5.0,
                "response_time_p95": 2000,  # ms
                "failed_logins": 10,
                "security_events": 5
            },
            "endpoints": {
                "health": "https://api.aitbc.dev/health",
                "metrics": "https://api.aitbc.dev/metrics",
                "blockchain": "https://api.aitbc.dev/blockchain/stats",
                "security": "https://api.aitbc.dev/security/stats"
            },
            "notifications": {
                "slack_webhook": os.getenv("SLACK_WEBHOOK_URL"),
                "email_smtp": os.getenv("SMTP_SERVER"),
                "pagerduty_key": os.getenv("PAGERDUTY_KEY")
            }
        }
        
        config_file = Path(config_path)
        if config_file.exists():
            with open(config_file, 'r') as f:
                user_config = json.load(f)
                default_config.update(user_config)
        
        return default_config
    
    def _setup_logging(self) -> logging.Logger:
        """Setup logging for monitoring system."""
        logger = logging.getLogger("production_monitor")
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    async def collect_system_metrics(self) -> SystemMetrics:
        """Collect system performance metrics."""
        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            load_avg = list(psutil.getloadavg())
            
            # Memory metrics
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            # Disk metrics
            disk = psutil.disk_usage('/')
            disk_usage = (disk.used / disk.total) * 100
            
            # Network metrics
            network = psutil.net_io_counters()
            network_io = {
                "bytes_sent": network.bytes_sent,
                "bytes_recv": network.bytes_recv,
                "packets_sent": network.packets_sent,
                "packets_recv": network.packets_recv
            }
            
            # Process metrics
            process_count = len(psutil.pids())
            
            return SystemMetrics(
                timestamp=time.time(),
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                disk_usage=disk_usage,
                network_io=network_io,
                process_count=process_count,
                load_average=load_avg
            )
            
        except Exception as e:
            self.logger.error(f"Error collecting system metrics: {e}")
            return None
    
    async def collect_application_metrics(self) -> ApplicationMetrics:
        """Collect application performance metrics."""
        try:
            async with aiohttp.ClientSession() as session:
                # Get metrics from application
                async with session.get(self.config["endpoints"]["metrics"]) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        return ApplicationMetrics(
                            timestamp=time.time(),
                            active_users=data.get("active_users", 0),
                            api_requests=data.get("api_requests", 0),
                            response_time_avg=data.get("response_time_avg", 0),
                            response_time_p95=data.get("response_time_p95", 0),
                            error_rate=data.get("error_rate", 0),
                            throughput=data.get("throughput", 0),
                            cache_hit_rate=data.get("cache_hit_rate", 0)
                        )
            
            # Fallback metrics if API is unavailable
            return ApplicationMetrics(
                timestamp=time.time(),
                active_users=0,
                api_requests=0,
                response_time_avg=0,
                response_time_p95=0,
                error_rate=0,
                throughput=0,
                cache_hit_rate=0
            )
            
        except Exception as e:
            self.logger.error(f"Error collecting application metrics: {e}")
            return None
    
    async def collect_blockchain_metrics(self) -> BlockchainMetrics:
        """Collect blockchain network metrics."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.config["endpoints"]["blockchain"]) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        return BlockchainMetrics(
                            timestamp=time.time(),
                            block_height=data.get("block_height", 0),
                            gas_price=data.get("gas_price", 0),
                            transaction_count=data.get("transaction_count", 0),
                            network_hashrate=data.get("network_hashrate", 0),
                            peer_count=data.get("peer_count", 0),
                            sync_status=data.get("sync_status", "unknown")
                        )
            
            return BlockchainMetrics(
                timestamp=time.time(),
                block_height=0,
                gas_price=0,
                transaction_count=0,
                network_hashrate=0,
                peer_count=0,
                sync_status="unknown"
            )
            
        except Exception as e:
            self.logger.error(f"Error collecting blockchain metrics: {e}")
            return None
    
    async def collect_security_metrics(self) -> SecurityMetrics:
        """Collect security monitoring metrics."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.config["endpoints"]["security"]) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        return SecurityMetrics(
                            timestamp=time.time(),
                            failed_logins=data.get("failed_logins", 0),
                            suspicious_ips=data.get("suspicious_ips", 0),
                            security_events=data.get("security_events", 0),
                            vulnerability_scans=data.get("vulnerability_scans", 0),
                            blocked_requests=data.get("blocked_requests", 0),
                            audit_log_entries=data.get("audit_log_entries", 0)
                        )
            
            return SecurityMetrics(
                timestamp=time.time(),
                failed_logins=0,
                suspicious_ips=0,
                security_events=0,
                vulnerability_scans=0,
                blocked_requests=0,
                audit_log_entries=0
            )
            
        except Exception as e:
            self.logger.error(f"Error collecting security metrics: {e}")
            return None
    
    async def collect_all_metrics(self) -> Dict[str, Any]:
        """Collect all metrics."""
        tasks = [
            self.collect_system_metrics(),
            self.collect_application_metrics(),
            self.collect_blockchain_metrics(),
            self.collect_security_metrics()
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return {
            "system": results[0] if not isinstance(results[0], Exception) else None,
            "application": results[1] if not isinstance(results[1], Exception) else None,
            "blockchain": results[2] if not isinstance(results[2], Exception) else None,
            "security": results[3] if not isinstance(results[3], Exception) else None
        }
    
    async def check_alerts(self, metrics: Dict[str, Any]) -> List[Dict]:
        """Check metrics against alert thresholds."""
        alerts = []
        thresholds = self.config["alert_thresholds"]
        
        # System alerts
        if metrics["system"]:
            sys_metrics = metrics["system"]
            
            if sys_metrics.cpu_percent > thresholds["cpu_percent"]:
                alerts.append({
                    "type": "system",
                    "metric": "cpu_percent",
                    "value": sys_metrics.cpu_percent,
                    "threshold": thresholds["cpu_percent"],
                    "severity": "warning" if sys_metrics.cpu_percent < 90 else "critical",
                    "message": f"High CPU usage: {sys_metrics.cpu_percent:.1f}%"
                })
            
            if sys_metrics.memory_percent > thresholds["memory_percent"]:
                alerts.append({
                    "type": "system",
                    "metric": "memory_percent",
                    "value": sys_metrics.memory_percent,
                    "threshold": thresholds["memory_percent"],
                    "severity": "warning" if sys_metrics.memory_percent < 95 else "critical",
                    "message": f"High memory usage: {sys_metrics.memory_percent:.1f}%"
                })
            
            if sys_metrics.disk_usage > thresholds["disk_usage"]:
                alerts.append({
                    "type": "system",
                    "metric": "disk_usage",
                    "value": sys_metrics.disk_usage,
                    "threshold": thresholds["disk_usage"],
                    "severity": "critical",
                    "message": f"High disk usage: {sys_metrics.disk_usage:.1f}%"
                })
        
        # Application alerts
        if metrics["application"]:
            app_metrics = metrics["application"]
            
            if app_metrics.error_rate > thresholds["error_rate"]:
                alerts.append({
                    "type": "application",
                    "metric": "error_rate",
                    "value": app_metrics.error_rate,
                    "threshold": thresholds["error_rate"],
                    "severity": "warning" if app_metrics.error_rate < 10 else "critical",
                    "message": f"High error rate: {app_metrics.error_rate:.1f}%"
                })
            
            if app_metrics.response_time_p95 > thresholds["response_time_p95"]:
                alerts.append({
                    "type": "application",
                    "metric": "response_time_p95",
                    "value": app_metrics.response_time_p95,
                    "threshold": thresholds["response_time_p95"],
                    "severity": "warning",
                    "message": f"High response time: {app_metrics.response_time_p95:.0f}ms"
                })
        
        # Security alerts
        if metrics["security"]:
            sec_metrics = metrics["security"]
            
            if sec_metrics.failed_logins > thresholds["failed_logins"]:
                alerts.append({
                    "type": "security",
                    "metric": "failed_logins",
                    "value": sec_metrics.failed_logins,
                    "threshold": thresholds["failed_logins"],
                    "severity": "warning",
                    "message": f"High failed login count: {sec_metrics.failed_logins}"
                })
            
            if sec_metrics.security_events > thresholds["security_events"]:
                alerts.append({
                    "type": "security",
                    "metric": "security_events",
                    "value": sec_metrics.security_events,
                    "threshold": thresholds["security_events"],
                    "severity": "critical",
                    "message": f"High security events: {sec_metrics.security_events}"
                })
        
        return alerts
    
    async def send_alert(self, alert: Dict) -> bool:
        """Send alert notification."""
        try:
            # Log alert
            self.logger.warning(f"ALERT: {alert['message']}")
            
            # Send to Slack
            if self.config["notifications"]["slack_webhook"]:
                await self._send_slack_alert(alert)
            
            # Send to PagerDuty for critical alerts
            if alert["severity"] == "critical" and self.config["notifications"]["pagerduty_key"]:
                await self._send_pagerduty_alert(alert)
            
            # Store alert
            alert["timestamp"] = time.time()
            self.alerts.append(alert)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error sending alert: {e}")
            return False
    
    async def _send_slack_alert(self, alert: Dict) -> bool:
        """Send alert to Slack."""
        try:
            webhook_url = self.config["notifications"]["slack_webhook"]
            
            color = {
                "warning": "warning",
                "critical": "danger",
                "info": "good"
            }.get(alert["severity"], "warning")
            
            payload = {
                "text": f"AITBC Alert: {alert['message']}",
                "attachments": [{
                    "color": color,
                    "fields": [
                        {"title": "Type", "value": alert["type"], "short": True},
                        {"title": "Metric", "value": alert["metric"], "short": True},
                        {"title": "Value", "value": str(alert["value"]), "short": True},
                        {"title": "Threshold", "value": str(alert["threshold"]), "short": True},
                        {"title": "Severity", "value": alert["severity"], "short": True}
                    ],
                    "timestamp": int(time.time())
                }]
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload) as response:
                    return response.status == 200
            
        except Exception as e:
            self.logger.error(f"Error sending Slack alert: {e}")
            return False
    
    async def _send_pagerduty_alert(self, alert: Dict) -> bool:
        """Send alert to PagerDuty."""
        try:
            api_key = self.config["notifications"]["pagerduty_key"]
            
            payload = {
                "routing_key": api_key,
                "event_action": "trigger",
                "payload": {
                    "summary": f"AITBC Alert: {alert['message']}",
                    "source": "aitbc-monitor",
                    "severity": alert["severity"],
                    "timestamp": datetime.now().isoformat(),
                    "custom_details": alert
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://events.pagerduty.com/v2/enqueue",
                    json=payload
                ) as response:
                    return response.status == 202
            
        except Exception as e:
            self.logger.error(f"Error sending PagerDuty alert: {e}")
            return False
    
    async def generate_dashboard(self) -> Dict:
        """Generate monitoring dashboard data."""
        try:
            # Get recent metrics (last hour)
            cutoff_time = time.time() - 3600
            
            recent_metrics = {
                "system": [m for m in self.metrics_history["system"] if m.timestamp > cutoff_time],
                "application": [m for m in self.metrics_history["application"] if m.timestamp > cutoff_time],
                "blockchain": [m for m in self.metrics_history["blockchain"] if m.timestamp > cutoff_time],
                "security": [m for m in self.metrics_history["security"] if m.timestamp > cutoff_time]
            }
            
            dashboard = {
                "timestamp": time.time(),
                "status": "healthy",
                "alerts": self.alerts[-10:],  # Last 10 alerts
                "metrics": {
                    "current": await self.collect_all_metrics(),
                    "trends": self._calculate_trends(recent_metrics),
                    "summaries": self._calculate_summaries(recent_metrics)
                }
            }
            
            # Determine overall status
            critical_alerts = [a for a in self.alerts if a.get("severity") == "critical"]
            if critical_alerts:
                dashboard["status"] = "critical"
            elif self.alerts:
                dashboard["status"] = "warning"
            
            return dashboard
            
        except Exception as e:
            self.logger.error(f"Error generating dashboard: {e}")
            return {"status": "error", "error": str(e)}
    
    def _calculate_trends(self, recent_metrics: Dict) -> Dict:
        """Calculate metric trends."""
        trends = {}
        
        for metric_type, metrics in recent_metrics.items():
            if not metrics:
                continue
            
            # Calculate trend for each numeric field
            if metric_type == "system" and metrics:
                trends["system"] = {
                    "cpu_trend": self._calculate_trend([m.cpu_percent for m in metrics]),
                    "memory_trend": self._calculate_trend([m.memory_percent for m in metrics]),
                    "disk_trend": self._calculate_trend([m.disk_usage for m in metrics])
                }
            
            elif metric_type == "application" and metrics:
                trends["application"] = {
                    "response_time_trend": self._calculate_trend([m.response_time_avg for m in metrics]),
                    "error_rate_trend": self._calculate_trend([m.error_rate for m in metrics]),
                    "throughput_trend": self._calculate_trend([m.throughput for m in metrics])
                }
        
        return trends
    
    def _calculate_trend(self, values: List[float]) -> str:
        """Calculate trend direction."""
        if len(values) < 2:
            return "stable"
        
        # Simple linear regression to determine trend
        n = len(values)
        x = list(range(n))
        
        x_mean = sum(x) / n
        y_mean = sum(values) / n
        
        numerator = sum((x[i] - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
        
        if denominator == 0:
            return "stable"
        
        slope = numerator / denominator
        
        if slope > 0.1:
            return "increasing"
        elif slope < -0.1:
            return "decreasing"
        else:
            return "stable"
    
    def _calculate_summaries(self, recent_metrics: Dict) -> Dict:
        """Calculate metric summaries."""
        summaries = {}
        
        for metric_type, metrics in recent_metrics.items():
            if not metrics:
                continue
            
            if metric_type == "system" and metrics:
                summaries["system"] = {
                    "avg_cpu": statistics.mean([m.cpu_percent for m in metrics]),
                    "max_cpu": max([m.cpu_percent for m in metrics]),
                    "avg_memory": statistics.mean([m.memory_percent for m in metrics]),
                    "max_memory": max([m.memory_percent for m in metrics]),
                    "avg_disk": statistics.mean([m.disk_usage for m in metrics])
                }
            
            elif metric_type == "application" and metrics:
                summaries["application"] = {
                    "avg_response_time": statistics.mean([m.response_time_avg for m in metrics]),
                    "max_response_time": max([m.response_time_p95 for m in metrics]),
                    "avg_error_rate": statistics.mean([m.error_rate for m in metrics]),
                    "total_requests": sum([m.api_requests for m in metrics]),
                    "avg_throughput": statistics.mean([m.throughput for m in metrics])
                }
        
        return summaries
    
    async def store_metrics(self, metrics: Dict) -> None:
        """Store metrics in history."""
        try:
            timestamp = time.time()
            
            # Add to history
            if metrics["system"]:
                self.metrics_history["system"].append(metrics["system"])
            if metrics["application"]:
                self.metrics_history["application"].append(metrics["application"])
            if metrics["blockchain"]:
                self.metrics_history["blockchain"].append(metrics["blockchain"])
            if metrics["security"]:
                self.metrics_history["security"].append(metrics["security"])
            
            # Cleanup old metrics
            cutoff_time = timestamp - (self.config["retention_days"] * 24 * 3600)
            
            for metric_type in self.metrics_history:
                self.metrics_history[metric_type] = [
                    m for m in self.metrics_history[metric_type] 
                    if m.timestamp > cutoff_time
                ]
            
            # Save to file
            await self._save_metrics_to_file()
            
        except Exception as e:
            self.logger.error(f"Error storing metrics: {e}")
    
    async def _save_metrics_to_file(self) -> None:
        """Save metrics to file."""
        try:
            metrics_file = Path("data/metrics_history.json")
            metrics_file.parent.mkdir(exist_ok=True)
            
            # Convert dataclasses to dicts for JSON serialization
            serializable_history = {}
            for metric_type, metrics in self.metrics_history.items():
                serializable_history[metric_type] = [
                    asdict(m) if hasattr(m, '__dict__') else m 
                    for m in metrics
                ]
            
            with open(metrics_file, 'w') as f:
                json.dump(serializable_history, f, indent=2)
            
        except Exception as e:
            self.logger.error(f"Error saving metrics to file: {e}")
    
    async def run_monitoring_cycle(self) -> None:
        """Run a complete monitoring cycle."""
        try:
            # Collect metrics
            metrics = await self.collect_all_metrics()
            
            # Store metrics
            await self.store_metrics(metrics)
            
            # Check alerts
            alerts = await self.check_alerts(metrics)
            
            # Send alerts
            for alert in alerts:
                await self.send_alert(alert)
            
            # Generate dashboard
            dashboard = await self.generate_dashboard()
            
            # Log summary
            self.logger.info(f"Monitoring cycle completed. Status: {dashboard['status']}")
            if alerts:
                self.logger.warning(f"Generated {len(alerts)} alerts")
            
        except Exception as e:
            self.logger.error(f"Error in monitoring cycle: {e}")
    
    async def start_monitoring(self) -> None:
        """Start continuous monitoring."""
        self.logger.info("Starting production monitoring")
        
        while True:
            try:
                await self.run_monitoring_cycle()
                await asyncio.sleep(self.config["collection_interval"])
                
            except KeyboardInterrupt:
                self.logger.info("Monitoring stopped by user")
                break
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(60)  # Wait before retrying


# CLI interface
async def main():
    """Main CLI interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description="AITBC Production Monitoring")
    parser.add_argument("--start", action="store_true", help="Start monitoring")
    parser.add_argument("--collect", action="store_true", help="Collect metrics once")
    parser.add_argument("--dashboard", action="store_true", help="Generate dashboard")
    parser.add_argument("--alerts", action="store_true", help="Check alerts")
    
    args = parser.parse_args()
    
    monitor = ProductionMonitor()
    
    if args.start:
        await monitor.start_monitoring()
    
    elif args.collect:
        metrics = await monitor.collect_all_metrics()
        print(json.dumps(metrics, indent=2, default=str))
    
    elif args.dashboard:
        dashboard = await monitor.generate_dashboard()
        print(json.dumps(dashboard, indent=2, default=str))
    
    elif args.alerts:
        metrics = await monitor.collect_all_metrics()
        alerts = await monitor.check_alerts(metrics)
        print(json.dumps(alerts, indent=2, default=str))
    
    else:
        print("Use --help to see available options")


if __name__ == "__main__":
    asyncio.run(main())
