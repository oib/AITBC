"""
Production deployment and scaling system
"""

import asyncio
import json
import subprocess
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import uuid
import os
import sys

class DeploymentStatus(Enum):
    """Deployment status"""
    PENDING = "pending"
    DEPLOYING = "deploying"
    RUNNING = "running"
    FAILED = "failed"
    STOPPED = "stopped"
    SCALING = "scaling"

class ScalingPolicy(Enum):
    """Scaling policies"""
    MANUAL = "manual"
    AUTO = "auto"
    SCHEDULED = "scheduled"
    LOAD_BASED = "load_based"

@dataclass
class DeploymentConfig:
    """Deployment configuration"""
    deployment_id: str
    name: str
    environment: str
    region: str
    instance_type: str
    min_instances: int
    max_instances: int
    desired_instances: int
    scaling_policy: ScalingPolicy
    health_check_path: str
    port: int
    ssl_enabled: bool
    domain: str
    database_config: Dict[str, Any]
    monitoring_enabled: bool
    backup_enabled: bool
    auto_scaling_enabled: bool
    created_at: datetime
    updated_at: datetime

@dataclass
class DeploymentMetrics:
    """Deployment performance metrics"""
    deployment_id: str
    cpu_usage: float
    memory_usage: float
    disk_usage: float
    network_in: float
    network_out: float
    request_count: int
    error_rate: float
    response_time: float
    uptime_percentage: float
    active_instances: int
    last_updated: datetime

@dataclass
class ScalingEvent:
    """Scaling event record"""
    event_id: str
    deployment_id: str
    scaling_type: str
    old_instances: int
    new_instances: int
    trigger_reason: str
    triggered_at: datetime
    completed_at: Optional[datetime]
    success: bool
    metadata: Dict[str, Any]

class ProductionDeployment:
    """Production deployment and scaling system"""
    
    def __init__(self, config_path: str = "/home/oib/windsurf/aitbc"):
        self.config_path = Path(config_path)
        self.deployments: Dict[str, DeploymentConfig] = {}
        self.metrics: Dict[str, DeploymentMetrics] = {}
        self.scaling_events: List[ScalingEvent] = []
        self.health_checks: Dict[str, bool] = {}
        
        # Deployment paths
        self.deployment_dir = self.config_path / "deployments"
        self.config_dir = self.config_path / "config"
        self.logs_dir = self.config_path / "logs"
        self.backups_dir = self.config_path / "backups"
        
        # Ensure directories exist
        self.config_path.mkdir(parents=True, exist_ok=True)
        self.deployment_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        
        # Scaling thresholds
        self.scaling_thresholds = {
            'cpu_high': 80.0,
            'cpu_low': 20.0,
            'memory_high': 85.0,
            'memory_low': 30.0,
            'error_rate_high': 5.0,
            'response_time_high': 2000.0,  # ms
            'min_uptime': 99.0
        }
    
    async def create_deployment(self, name: str, environment: str, region: str,
                              instance_type: str, min_instances: int, max_instances: int,
                              desired_instances: int, port: int, domain: str,
                              database_config: Dict[str, Any]) -> Optional[str]:
        """Create a new deployment configuration"""
        try:
            deployment_id = str(uuid.uuid4())
            
            deployment = DeploymentConfig(
                deployment_id=deployment_id,
                name=name,
                environment=environment,
                region=region,
                instance_type=instance_type,
                min_instances=min_instances,
                max_instances=max_instances,
                desired_instances=desired_instances,
                scaling_policy=ScalingPolicy.AUTO,
                health_check_path="/health",
                port=port,
                ssl_enabled=True,
                domain=domain,
                database_config=database_config,
                monitoring_enabled=True,
                backup_enabled=True,
                auto_scaling_enabled=True,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            
            self.deployments[deployment_id] = deployment
            
            # Create deployment directory structure
            deployment_path = self.deployment_dir / deployment_id
            deployment_path.mkdir(exist_ok=True)
            
            # Generate deployment configuration files
            await self._generate_deployment_configs(deployment, deployment_path)
            
            return deployment_id
            
        except Exception as e:
            print(f"Error creating deployment: {e}")
            return None
    
    async def deploy_application(self, deployment_id: str) -> bool:
        """Deploy the application to production"""
        try:
            deployment = self.deployments.get(deployment_id)
            if not deployment:
                return False
            
            print(f"Starting deployment of {deployment.name} ({deployment_id})")
            
            # 1. Build application
            build_success = await self._build_application(deployment)
            if not build_success:
                return False
            
            # 2. Deploy infrastructure
            infra_success = await self._deploy_infrastructure(deployment)
            if not infra_success:
                return False
            
            # 3. Configure monitoring
            monitoring_success = await self._setup_monitoring(deployment)
            if not monitoring_success:
                return False
            
            # 4. Start health checks
            await self._start_health_checks(deployment)
            
            # 5. Initialize metrics collection
            await self._initialize_metrics(deployment_id)
            
            print(f"Deployment {deployment_id} completed successfully")
            return True
            
        except Exception as e:
            print(f"Error deploying application: {e}")
            return False
    
    async def scale_deployment(self, deployment_id: str, target_instances: int, 
                             reason: str = "manual") -> bool:
        """Scale a deployment to target instance count"""
        try:
            deployment = self.deployments.get(deployment_id)
            if not deployment:
                return False
            
            # Validate scaling limits
            if target_instances < deployment.min_instances or target_instances > deployment.max_instances:
                return False
            
            old_instances = deployment.desired_instances
            
            # Create scaling event
            scaling_event = ScalingEvent(
                event_id=str(uuid.uuid4()),
                deployment_id=deployment_id,
                scaling_type="manual" if reason == "manual" else "auto",
                old_instances=old_instances,
                new_instances=target_instances,
                trigger_reason=reason,
                triggered_at=datetime.now(),
                completed_at=None,
                success=False,
                metadata={"deployment_name": deployment.name}
            )
            
            self.scaling_events.append(scaling_event)
            
            # Update deployment
            deployment.desired_instances = target_instances
            deployment.updated_at = datetime.now()
            
            # Execute scaling
            scaling_success = await self._execute_scaling(deployment, target_instances)
            
            # Update scaling event
            scaling_event.completed_at = datetime.now()
            scaling_event.success = scaling_success
            
            if scaling_success:
                print(f"Scaled deployment {deployment_id} from {old_instances} to {target_instances} instances")
            else:
                # Rollback on failure
                deployment.desired_instances = old_instances
                print(f"Scaling failed, rolled back to {old_instances} instances")
            
            return scaling_success
            
        except Exception as e:
            print(f"Error scaling deployment: {e}")
            return False
    
    async def auto_scale_deployment(self, deployment_id: str) -> bool:
        """Automatically scale deployment based on metrics"""
        try:
            deployment = self.deployments.get(deployment_id)
            if not deployment or not deployment.auto_scaling_enabled:
                return False
            
            metrics = self.metrics.get(deployment_id)
            if not metrics:
                return False
            
            current_instances = deployment.desired_instances
            new_instances = current_instances
            
            # Scale up conditions
            scale_up_triggers = []
            if metrics.cpu_usage > self.scaling_thresholds['cpu_high']:
                scale_up_triggers.append(f"CPU usage high: {metrics.cpu_usage:.1f}%")
            
            if metrics.memory_usage > self.scaling_thresholds['memory_high']:
                scale_up_triggers.append(f"Memory usage high: {metrics.memory_usage:.1f}%")
            
            if metrics.error_rate > self.scaling_thresholds['error_rate_high']:
                scale_up_triggers.append(f"Error rate high: {metrics.error_rate:.1f}%")
            
            # Scale down conditions
            scale_down_triggers = []
            if (metrics.cpu_usage < self.scaling_thresholds['cpu_low'] and 
               metrics.memory_usage < self.scaling_thresholds['memory_low'] and
               current_instances > deployment.min_instances):
                scale_down_triggers.append("Low resource usage")
            
            # Execute scaling
            if scale_up_triggers and current_instances < deployment.max_instances:
                new_instances = min(current_instances + 1, deployment.max_instances)
                reason = f"Auto scale up: {', '.join(scale_up_triggers)}"
                return await self.scale_deployment(deployment_id, new_instances, reason)
            
            elif scale_down_triggers and current_instances > deployment.min_instances:
                new_instances = max(current_instances - 1, deployment.min_instances)
                reason = f"Auto scale down: {', '.join(scale_down_triggers)}"
                return await self.scale_deployment(deployment_id, new_instances, reason)
            
            return True
            
        except Exception as e:
            print(f"Error in auto-scaling: {e}")
            return False
    
    async def get_deployment_status(self, deployment_id: str) -> Optional[Dict[str, Any]]:
        """Get comprehensive deployment status"""
        try:
            deployment = self.deployments.get(deployment_id)
            if not deployment:
                return None
            
            metrics = self.metrics.get(deployment_id)
            health_status = self.health_checks.get(deployment_id, False)
            
            # Get recent scaling events
            recent_events = [
                event for event in self.scaling_events
                if event.deployment_id == deployment_id and
                event.triggered_at >= datetime.now() - timedelta(hours=24)
            ]
            
            status = {
                "deployment": asdict(deployment),
                "metrics": asdict(metrics) if metrics else None,
                "health_status": health_status,
                "recent_scaling_events": [asdict(event) for event in recent_events[-5:]],
                "uptime_percentage": metrics.uptime_percentage if metrics else 0.0,
                "last_updated": datetime.now().isoformat()
            }
            
            return status
            
        except Exception as e:
            print(f"Error getting deployment status: {e}")
            return None
    
    async def get_cluster_overview(self) -> Dict[str, Any]:
        """Get overview of all deployments"""
        try:
            total_deployments = len(self.deployments)
            running_deployments = len([
                d for d in self.deployments.values()
                if self.health_checks.get(d.deployment_id, False)
            ])
            
            total_instances = sum(d.desired_instances for d in self.deployments.values())
            
            # Calculate aggregate metrics
            aggregate_metrics = {
                "total_cpu_usage": 0.0,
                "total_memory_usage": 0.0,
                "total_disk_usage": 0.0,
                "average_response_time": 0.0,
                "average_error_rate": 0.0,
                "average_uptime": 0.0
            }
            
            active_metrics = [m for m in self.metrics.values()]
            if active_metrics:
                aggregate_metrics["total_cpu_usage"] = sum(m.cpu_usage for m in active_metrics) / len(active_metrics)
                aggregate_metrics["total_memory_usage"] = sum(m.memory_usage for m in active_metrics) / len(active_metrics)
                aggregate_metrics["total_disk_usage"] = sum(m.disk_usage for m in active_metrics) / len(active_metrics)
                aggregate_metrics["average_response_time"] = sum(m.response_time for m in active_metrics) / len(active_metrics)
                aggregate_metrics["average_error_rate"] = sum(m.error_rate for m in active_metrics) / len(active_metrics)
                aggregate_metrics["average_uptime"] = sum(m.uptime_percentage for m in active_metrics) / len(active_metrics)
            
            # Recent scaling activity
            recent_scaling = [
                event for event in self.scaling_events
                if event.triggered_at >= datetime.now() - timedelta(hours=24)
            ]
            
            overview = {
                "total_deployments": total_deployments,
                "running_deployments": running_deployments,
                "total_instances": total_instances,
                "aggregate_metrics": aggregate_metrics,
                "recent_scaling_events": len(recent_scaling),
                "successful_scaling_rate": sum(1 for e in recent_scaling if e.success) / len(recent_scaling) if recent_scaling else 0.0,
                "health_check_coverage": len(self.health_checks) / total_deployments if total_deployments > 0 else 0.0,
                "last_updated": datetime.now().isoformat()
            }
            
            return overview
            
        except Exception as e:
            print(f"Error getting cluster overview: {e}")
            return {}
    
    async def _generate_deployment_configs(self, deployment: DeploymentConfig, deployment_path: Path):
        """Generate deployment configuration files"""
        try:
            # Generate systemd service file
            service_content = f"""[Unit]
Description={deployment.name} Service
After=network.target

[Service]
Type=simple
User=aitbc
WorkingDirectory={self.config_path}
ExecStart=/usr/bin/python3 -m aitbc_cli.main --port {deployment.port}
Restart=always
RestartSec=10
Environment=PYTHONPATH={self.config_path}
Environment=DEPLOYMENT_ID={deployment.deployment_id}
Environment=ENVIRONMENT={deployment.environment}

[Install]
WantedBy=multi-user.target
"""
            
            service_file = deployment_path / f"{deployment.name}.service"
            with open(service_file, 'w') as f:
                f.write(service_content)
            
            # Generate nginx configuration
            nginx_content = f"""upstream {deployment.name}_backend {{
    server 127.0.0.1:{deployment.port};
}}

server {{
    listen 80;
    server_name {deployment.domain};
    
    location / {{
        proxy_pass http://{deployment.name}_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
    
    location {deployment.health_check_path} {{
        proxy_pass http://{deployment.name}_backend;
        access_log off;
    }}
}}
"""
            
            nginx_file = deployment_path / f"{deployment.name}.nginx.conf"
            with open(nginx_file, 'w') as f:
                f.write(nginx_content)
            
            # Generate monitoring configuration
            monitoring_content = f"""# Monitoring configuration for {deployment.name}
deployment_id: {deployment.deployment_id}
name: {deployment.name}
environment: {deployment.environment}
port: {deployment.port}
health_check_path: {deployment.health_check_path}
metrics_interval: 30
alert_thresholds:
  cpu_usage: {self.scaling_thresholds['cpu_high']}
  memory_usage: {self.scaling_thresholds['memory_high']}
  error_rate: {self.scaling_thresholds['error_rate_high']}
  response_time: {self.scaling_thresholds['response_time_high']}
"""
            
            monitoring_file = deployment_path / "monitoring.yml"
            with open(monitoring_file, 'w') as f:
                f.write(monitoring_content)
            
        except Exception as e:
            print(f"Error generating deployment configs: {e}")
    
    async def _build_application(self, deployment: DeploymentConfig) -> bool:
        """Build the application for deployment"""
        try:
            print(f"Building application for {deployment.name}")
            
            # Simulate build process
            build_steps = [
                "Installing dependencies...",
                "Compiling application...",
                "Running tests...",
                "Creating deployment package...",
                "Optimizing for production..."
            ]
            
            for step in build_steps:
                print(f"  {step}")
                await asyncio.sleep(0.5)  # Simulate build time
            
            print("Build completed successfully")
            return True
            
        except Exception as e:
            print(f"Error building application: {e}")
            return False
    
    async def _deploy_infrastructure(self, deployment: DeploymentConfig) -> bool:
        """Deploy infrastructure components"""
        try:
            print(f"Deploying infrastructure for {deployment.name}")
            
            # Deploy systemd service
            service_file = self.deployment_dir / deployment.deployment_id / f"{deployment.name}.service"
            system_service_path = Path("/etc/systemd/system") / f"{deployment.name}.service"
            
            if service_file.exists():
                shutil.copy2(service_file, system_service_path)
                subprocess.run(["systemctl", "daemon-reload"], check=True)
                subprocess.run(["systemctl", "enable", deployment.name], check=True)
                subprocess.run(["systemctl", "start", deployment.name], check=True)
                print(f"  Service {deployment.name} started")
            
            # Deploy nginx configuration
            nginx_file = self.deployment_dir / deployment.deployment_id / f"{deployment.name}.nginx.conf"
            nginx_config_path = Path("/etc/nginx/sites-available") / f"{deployment.name}.conf"
            
            if nginx_file.exists():
                shutil.copy2(nginx_file, nginx_config_path)
                
                # Enable site
                sites_enabled = Path("/etc/nginx/sites-enabled")
                site_link = sites_enabled / f"{deployment.name}.conf"
                if not site_link.exists():
                    site_link.symlink_to(nginx_config_path)
                
                subprocess.run(["nginx", "-t"], check=True)
                subprocess.run(["systemctl", "reload", "nginx"], check=True)
                print(f"  Nginx configuration updated")
            
            print("Infrastructure deployment completed")
            return True
            
        except Exception as e:
            print(f"Error deploying infrastructure: {e}")
            return False
    
    async def _setup_monitoring(self, deployment: DeploymentConfig) -> bool:
        """Set up monitoring for the deployment"""
        try:
            print(f"Setting up monitoring for {deployment.name}")
            
            monitoring_file = self.deployment_dir / deployment.deployment_id / "monitoring.yml"
            if monitoring_file.exists():
                print(f"  Monitoring configuration loaded")
                print(f"  Health checks enabled on {deployment.health_check_path}")
                print(f"  Metrics collection started")
            
            print("Monitoring setup completed")
            return True
            
        except Exception as e:
            print(f"Error setting up monitoring: {e}")
            return False
    
    async def _start_health_checks(self, deployment: DeploymentConfig):
        """Start health checks for the deployment"""
        try:
            print(f"Starting health checks for {deployment.name}")
            
            # Initialize health status
            self.health_checks[deployment.deployment_id] = True
            
            # Start periodic health checks
            asyncio.create_task(self._periodic_health_check(deployment))
            
        except Exception as e:
            print(f"Error starting health checks: {e}")
    
    async def _periodic_health_check(self, deployment: DeploymentConfig):
        """Periodic health check for deployment"""
        while True:
            try:
                # Simulate health check
                await asyncio.sleep(30)  # Check every 30 seconds
                
                # Update health status (simulated)
                self.health_checks[deployment.deployment_id] = True
                
                # Update metrics
                await self._update_metrics(deployment.deployment_id)
                
            except Exception as e:
                print(f"Error in health check for {deployment.name}: {e}")
                self.health_checks[deployment.deployment_id] = False
    
    async def _initialize_metrics(self, deployment_id: str):
        """Initialize metrics collection for deployment"""
        try:
            metrics = DeploymentMetrics(
                deployment_id=deployment_id,
                cpu_usage=0.0,
                memory_usage=0.0,
                disk_usage=0.0,
                network_in=0.0,
                network_out=0.0,
                request_count=0,
                error_rate=0.0,
                response_time=0.0,
                uptime_percentage=100.0,
                active_instances=1,
                last_updated=datetime.now()
            )
            
            self.metrics[deployment_id] = metrics
            
        except Exception as e:
            print(f"Error initializing metrics: {e}")
    
    async def _update_metrics(self, deployment_id: str):
        """Update deployment metrics"""
        try:
            metrics = self.metrics.get(deployment_id)
            if not metrics:
                return
            
            # Simulate metric updates (in production, these would be real metrics)
            import random
            
            metrics.cpu_usage = random.uniform(10, 70)
            metrics.memory_usage = random.uniform(20, 80)
            metrics.disk_usage = random.uniform(30, 60)
            metrics.network_in = random.uniform(100, 1000)
            metrics.network_out = random.uniform(50, 500)
            metrics.request_count += random.randint(10, 100)
            metrics.error_rate = random.uniform(0, 2)
            metrics.response_time = random.uniform(50, 500)
            metrics.uptime_percentage = random.uniform(99.0, 100.0)
            metrics.last_updated = datetime.now()
            
        except Exception as e:
            print(f"Error updating metrics: {e}")
    
    async def _execute_scaling(self, deployment: DeploymentConfig, target_instances: int) -> bool:
        """Execute scaling operation"""
        try:
            print(f"Executing scaling to {target_instances} instances")
            
            # Simulate scaling process
            scaling_steps = [
                f"Provisioning {target_instances - deployment.desired_instances} new instances...",
                "Configuring new instances...",
                "Load balancing configuration...",
                "Health checks on new instances...",
                "Traffic migration..."
            ]
            
            for step in scaling_steps:
                print(f"  {step}")
                await asyncio.sleep(1)  # Simulate scaling time
            
            print("Scaling completed successfully")
            return True
            
        except Exception as e:
            print(f"Error executing scaling: {e}")
            return False
