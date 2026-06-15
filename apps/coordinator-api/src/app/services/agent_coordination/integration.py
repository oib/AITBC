"""
Agent Integration and Deployment Framework for Verifiable AI Agent Orchestration
Integrates agent orchestration with existing ML ZK proof system and provides deployment tools

MIGRATION IN PROGRESS: This file is being migrated to use shared AgentIntegrationService
from aitbc-agent-core package. See agent_integration_factory.py for the factory pattern.
After migration is complete, duplicated code will be removed.
"""
import asyncio
import os
import subprocess

from aitbc import get_logger

logger = get_logger(__name__)
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlmodel import JSON, Column, Field, Session, SQLModel, select

from ...domain.agent import AgentExecution, AgentStepExecution, VerificationLevel
from .agent_service import AIAgentOrchestrator
from .security import AgentAuditor, AgentSecurityManager, AuditEventType, SecurityLevel


class ZKProofService:
    """Mock ZK proof service for testing"""

    def __init__(self, session: Any) -> None:
        self.session = session

    async def generate_zk_proof(self, circuit_name: str, inputs: dict[str, Any]) -> dict[str, Any]:
        """Mock ZK proof generation"""
        return {'proof_id': f'proof_{uuid4().hex[:8]}', 'circuit_name': circuit_name, 'inputs': inputs, 'proof_size': 1024, 'generation_time': 0.1}

    async def verify_proof(self, proof_id: str) -> dict[str, Any]:
        """Mock ZK proof verification"""
        return {'verified': True, 'verification_time': 0.05, 'details': {'mock': True}}

class DeploymentStatus(StrEnum):
    """Deployment status enumeration"""
    PENDING = 'pending'
    DEPLOYING = 'deploying'
    DEPLOYED = 'deployed'
    FAILED = 'failed'
    RETRYING = 'retrying'
    TERMINATED = 'terminated'

class AgentDeploymentConfig(SQLModel, table=True):
    """Configuration for agent deployment"""
    __tablename__ = 'agent_deployment_configs'
    id: str = Field(default_factory=lambda: f'deploy_{uuid4().hex[:8]}', primary_key=True)
    workflow_id: str = Field(index=True)
    deployment_name: str = Field(max_length=100)
    description: str = Field(default='')
    version: str = Field(default='1.0.0')
    target_environments: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    deployment_regions: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    min_cpu_cores: float = Field(default=1.0)
    min_memory_mb: int = Field(default=1024)
    min_storage_gb: int = Field(default=10)
    requires_gpu: bool = Field(default=False)
    gpu_memory_mb: int | None = Field(default=None)
    min_instances: int = Field(default=1)
    max_instances: int = Field(default=5)
    auto_scaling: bool = Field(default=True)
    scaling_policy: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    health_check_endpoint: str = Field(default='/health')
    health_check_interval: int = Field(default=30)
    health_check_timeout: int = Field(default=10)
    max_failures: int = Field(default=3)
    rollout_strategy: str = Field(default='rolling')
    rollback_enabled: bool = Field(default=True)
    deployment_timeout: int = Field(default=1800)
    enable_metrics: bool = Field(default=True)
    enable_logging: bool = Field(default=True)
    enable_tracing: bool = Field(default=False)
    log_level: str = Field(default='INFO')
    status: DeploymentStatus = Field(default=DeploymentStatus.PENDING)
    deployment_time: datetime | None = Field(default=None)
    last_health_check: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class AgentDeploymentInstance(SQLModel, table=True):
    """Individual deployment instance tracking"""
    __tablename__ = 'agent_deployment_instances'
    id: str = Field(default_factory=lambda: f'instance_{uuid4().hex[:10]}', primary_key=True)
    deployment_id: str = Field(index=True)
    instance_id: str = Field(index=True)
    environment: str = Field(index=True)
    region: str = Field(index=True)
    status: DeploymentStatus = Field(default=DeploymentStatus.PENDING)
    health_status: str = Field(default='unknown')
    endpoint_url: str | None = Field(default=None)
    internal_ip: str | None = Field(default=None)
    external_ip: str | None = Field(default=None)
    port: int | None = Field(default=None)
    cpu_usage: float | None = Field(default=None)
    memory_usage: int | None = Field(default=None)
    disk_usage: int | None = Field(default=None)
    gpu_usage: float | None = Field(default=None)
    request_count: int = Field(default=0)
    error_count: int = Field(default=0)
    average_response_time: float | None = Field(default=None)
    uptime_percentage: float | None = Field(default=None)
    last_health_check: datetime | None = Field(default=None)
    consecutive_failures: int = Field(default=0)
    health_check_history: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class AgentIntegrationManager:
    """Manages integration between agent orchestration and existing systems"""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.zk_service = ZKProofService(session)
        self.orchestrator = AIAgentOrchestrator(session, None)  # type: ignore[arg-type]
        self.security_manager = AgentSecurityManager(session)
        self.auditor = AgentAuditor(session)

    async def integrate_with_zk_system(self, execution_id: str, verification_level: VerificationLevel=VerificationLevel.BASIC) -> dict[str, Any]:
        """Integrate agent execution with ZK proof system"""
        try:
            execution = self.session.scalars(select(AgentExecution).where(AgentExecution.id == execution_id)).first()
            if not execution:
                raise ValueError(f'Execution not found: {execution_id}')
            step_executions = self.session.scalars(select(AgentStepExecution).where(AgentStepExecution.execution_id == execution_id)).all()
            integration_result: dict[str, Any] = {'execution_id': execution_id, 'integration_status': 'in_progress', 'zk_proofs_generated': [], 'verification_results': [], 'integration_errors': []}
            for step_execution in step_executions:
                if getattr(step_execution, 'requires_proof', False):
                    try:
                        proof_result = await self._generate_step_zk_proof(step_execution, verification_level)
                        integration_result['zk_proofs_generated'].append({'step_id': step_execution.step_id, 'proof_id': proof_result['proof_id'], 'verification_level': verification_level, 'proof_size': proof_result['proof_size']})
                        verification_result = await self._verify_zk_proof(proof_result['proof_id'])
                        integration_result['verification_results'].append({'step_id': step_execution.step_id, 'verification_status': verification_result['verified'], 'verification_time': verification_result['verification_time']})
                    except Exception as e:
                        integration_result['integration_errors'].append({'step_id': step_execution.step_id, 'error': str(e), 'error_type': 'zk_proof_generation'})
            try:
                workflow_proof = await self._generate_workflow_zk_proof(execution, list(step_executions), verification_level)
                integration_result['workflow_proof'] = {'proof_id': workflow_proof['proof_id'], 'verification_level': verification_level, 'proof_size': workflow_proof['proof_size']}
                workflow_verification = await self._verify_zk_proof(workflow_proof['proof_id'])
                integration_result['workflow_verification'] = {'verified': workflow_verification['verified'], 'verification_time': workflow_verification['verification_time']}
            except Exception as e:
                integration_result['integration_errors'].append({'error': str(e), 'error_type': 'workflow_proof_generation'})
            if integration_result['integration_errors']:
                integration_result['integration_status'] = 'partial_success'
            else:
                integration_result['integration_status'] = 'success'
            await self.auditor.log_event(AuditEventType.VERIFICATION_COMPLETED, execution_id=execution_id, security_level=SecurityLevel.INTERNAL, event_data={'integration_result': integration_result, 'verification_level': verification_level})
            return integration_result
        except Exception as e:
            logger.error('ZK integration failed: %s', e)
            await self.auditor.log_event(AuditEventType.VERIFICATION_FAILED, execution_id=execution_id, security_level=SecurityLevel.INTERNAL, event_data={'error': str(e)})
            raise

    async def _generate_step_zk_proof(self, step_execution: AgentStepExecution, verification_level: VerificationLevel) -> dict[str, Any]:
        """Generate ZK proof for individual step execution"""
        proof_inputs = {'step_id': step_execution.step_id, 'execution_id': step_execution.execution_id, 'step_type': 'inference', 'input_data': step_execution.input_data, 'output_data': step_execution.output_data, 'execution_time': step_execution.execution_time, 'timestamp': step_execution.completed_at.isoformat() if step_execution.completed_at else None}
        if verification_level == VerificationLevel.ZERO_KNOWLEDGE:
            proof_result = await self.zk_service.generate_zk_proof(circuit_name='agent_step_verification', inputs=proof_inputs)
        elif verification_level == VerificationLevel.FULL:
            proof_result = await self.zk_service.generate_zk_proof(circuit_name='agent_step_full_verification', inputs=proof_inputs)
        else:
            proof_result = await self.zk_service.generate_zk_proof(circuit_name='agent_step_basic_verification', inputs=proof_inputs)
        return proof_result

    async def _generate_workflow_zk_proof(self, execution: AgentExecution, step_executions: list[AgentStepExecution], verification_level: VerificationLevel) -> dict[str, Any]:
        """Generate ZK proof for entire workflow execution"""
        step_proofs = []
        for step_execution in step_executions:
            if step_execution.step_proof:
                step_proofs.append(step_execution.step_proof)
        proof_inputs = {'execution_id': execution.id, 'workflow_id': execution.workflow_id, 'step_proofs': step_proofs, 'final_result': execution.final_result, 'total_execution_time': execution.total_execution_time, 'started_at': execution.started_at.isoformat() if execution.started_at else None, 'completed_at': execution.completed_at.isoformat() if execution.completed_at else None}
        circuit_name = f'agent_workflow_{verification_level.value}_verification'
        proof_result = await self.zk_service.generate_zk_proof(circuit_name=circuit_name, inputs=proof_inputs)
        return proof_result

    async def _verify_zk_proof(self, proof_id: str) -> dict[str, Any]:
        """Verify ZK proof"""
        verification_result = await self.zk_service.verify_proof(proof_id)
        return {'verified': verification_result['verified'], 'verification_time': verification_result['verification_time'], 'verification_details': verification_result.get('details', {})}

class AgentDeploymentManager:
    """Manages deployment of agent workflows to production environments"""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.integration_manager = AgentIntegrationManager(session)
        self.auditor = AgentAuditor(session)

    async def create_deployment_config(self, workflow_id: str, deployment_name: str, deployment_config: dict[str, Any]) -> AgentDeploymentConfig:
        """Create deployment configuration for agent workflow"""
        config = AgentDeploymentConfig(workflow_id=workflow_id, deployment_name=deployment_name, **deployment_config)
        self.session.add(config)
        self.session.commit()
        self.session.refresh(config)
        await self.auditor.log_event(AuditEventType.WORKFLOW_CREATED, workflow_id=workflow_id, security_level=SecurityLevel.INTERNAL, event_data={'deployment_config_id': config.id, 'deployment_name': deployment_name})
        logger.info('Created deployment config: %s for workflow %s', config.id, workflow_id)
        return config

    async def deploy_agent_workflow(self, deployment_config_id: str, target_environment: str='production') -> dict[str, Any]:
        """Deploy agent workflow to target environment"""
        try:
            config = self.session.get(AgentDeploymentConfig, deployment_config_id)
            if not config:
                raise ValueError(f'Deployment config not found: {deployment_config_id}')
            config.status = DeploymentStatus.DEPLOYING
            config.deployment_time = datetime.now(UTC)
            self.session.commit()
            deployment_result: dict[str, Any] = {'deployment_id': deployment_config_id, 'environment': target_environment, 'status': 'deploying', 'instances': [], 'deployment_errors': []}
            for i in range(config.min_instances):
                instance = await self._create_deployment_instance(config, target_environment, i)
                deployment_result['instances'].append(instance)
            if deployment_result['deployment_errors']:
                config.status = DeploymentStatus.FAILED
            else:
                config.status = DeploymentStatus.DEPLOYED
            self.session.commit()
            await self.auditor.log_event(AuditEventType.EXECUTION_STARTED, workflow_id=config.workflow_id, security_level=SecurityLevel.INTERNAL, event_data={'deployment_id': deployment_config_id, 'environment': target_environment, 'deployment_result': deployment_result})
            logger.info('Deployed agent workflow: %s to %s', deployment_config_id, target_environment)
            return deployment_result
        except Exception as e:
            logger.error('Deployment failed for %s: %s', deployment_config_id, e)
            config = self.session.get(AgentDeploymentConfig, deployment_config_id)
            if config:
                config.status = DeploymentStatus.FAILED
                self.session.commit()
            await self.auditor.log_event(AuditEventType.EXECUTION_FAILED, workflow_id=config.workflow_id if config else None, security_level=SecurityLevel.INTERNAL, event_data={'error': str(e)})
            raise

    async def _create_deployment_instance(self, config: AgentDeploymentConfig, environment: str, instance_number: int) -> dict[str, Any]:
        """Create individual deployment instance"""
        try:
            instance_id = f'{config.deployment_name}-{environment}-{instance_number}'
            instance = AgentDeploymentInstance(deployment_id=config.id, instance_id=instance_id, environment=environment, region=config.deployment_regions[0] if config.deployment_regions else 'default', status=DeploymentStatus.DEPLOYING, port=8000 + instance_number)
            self.session.add(instance)
            self.session.commit()
            self.session.refresh(instance)
            try:
                await self._deploy_agent_systemd(instance, config)
                instance.status = DeploymentStatus.DEPLOYED
                instance.health_status = 'healthy'
                instance.endpoint_url = f'http://localhost:{instance.port}'
                instance.last_health_check = datetime.now(UTC)
            except Exception as deploy_error:
                logger.error('Systemd deployment failed for %s: %s', instance_id, deploy_error)
                instance.status = DeploymentStatus.FAILED
                instance.health_status = 'unhealthy'
            self.session.commit()
            return {'instance_id': instance_id, 'status': 'deployed', 'endpoint_url': instance.endpoint_url, 'port': instance.port}
        except Exception as e:
            logger.error('Failed to create instance %s: %s', instance_number, e)
            return {'instance_id': f'{config.deployment_name}-{environment}-{instance_number}', 'status': 'failed', 'error': str(e)}

    async def monitor_deployment_health(self, deployment_config_id: str) -> dict[str, Any]:
        """Monitor health of deployment instances"""
        try:
            config = self.session.get(AgentDeploymentConfig, deployment_config_id)
            if not config:
                raise ValueError(f'Deployment config not found: {deployment_config_id}')
            instances = self.session.scalars(select(AgentDeploymentInstance).where(AgentDeploymentInstance.deployment_id == deployment_config_id)).all()
            health_result: dict[str, Any] = {'deployment_id': deployment_config_id, 'total_instances': len(instances), 'healthy_instances': 0, 'unhealthy_instances': 0, 'unknown_instances': 0, 'instance_health': []}
            for instance in instances:
                instance_health = await self._check_instance_health(instance)
                health_result['instance_health'].append(instance_health)
                if instance_health['status'] == 'healthy':
                    health_result['healthy_instances'] += 1
                elif instance_health['status'] == 'unhealthy':
                    health_result['unhealthy_instances'] += 1
                else:
                    health_result['unknown_instances'] += 1
            overall_health = 'healthy'
            if health_result['unhealthy_instances'] > 0:
                overall_health = 'unhealthy'
            elif health_result['unknown_instances'] > 0:
                overall_health = 'degraded'
            health_result['overall_health'] = overall_health
            return health_result
        except Exception as e:
            logger.error('Health monitoring failed for %s: %s', deployment_config_id, e)
            raise

    async def _deploy_agent_systemd(self, instance: AgentDeploymentInstance, config: AgentDeploymentConfig) -> None:
        """Deploy agent instance using systemd service"""
        service_name = f'aitbc-agent-{instance.instance_id}'
        service_file = f'/etc/systemd/system/{service_name}.service'
        service_content = f'[Unit]\nDescription=AITBC Agent Instance {instance.instance_id}\nDocumentation=https://github.com/aitbc/blockchain\nAfter=network.target aitbc-blockchain-node.service\nRequires=aitbc-blockchain-node.service\n\n[Service]\nType=simple\nUser=root\nGroup=root\nWorkingDirectory=/opt/aitbc\nEnvironmentFile=/etc/aitbc/.env\nEnvironment="AGENT_ID={instance.instance_id}"\nEnvironment="AGENT_PORT={instance.port}"\nEnvironment="PYTHONPATH=/opt/aitbc/packages/py/aitbc-agent-sdk/src:/opt/aitbc"\nEnvironment="PATH=/opt/aitbc/venv/bin:/usr/local/bin:/usr/bin:/bin"\nExecStart=/opt/aitbc/venv/bin/python /opt/aitbc/apps/agent-daemon/aitbc-agent-daemon-wrapper.py\n\nRestart=always\nRestartSec=10\nStandardOutput=journal\nStandardError=journal\nSyslogIdentifier=AgentInstance-{instance.instance_id}\n\n# Security settings\nNoNewPrivileges=true\nPrivateTmp=true\nProtectHome=true\n\n[Install]\nWantedBy=multi-user.target\n'
        try:
            with open(service_file, 'w') as f:
                f.write(service_content)
            os.chmod(service_file, 420)
            subprocess.run(['systemctl', 'daemon-reload'], check=True, capture_output=True)
            subprocess.run(['systemctl', 'enable', service_name], check=True, capture_output=True)
            subprocess.run(['systemctl', 'start', service_name], check=True, capture_output=True)
            max_wait = 30
            for i in range(max_wait):
                result = subprocess.run(['systemctl', 'is-active', service_name], capture_output=True, text=True)
                if result.stdout.strip() == 'active':
                    logger.info('Service %s is active', service_name)
                    break
                await asyncio.sleep(1)
            else:
                raise RuntimeError(f'Service {service_name} did not become active within {max_wait}s')
            logger.info('Successfully deployed agent instance %s via systemd', instance.instance_id)
        except subprocess.CalledProcessError as e:
            logger.error('Failed to deploy systemd service %s: %s', service_name, e.stderr)
            raise RuntimeError(f'Systemd deployment failed: {e.stderr}')
        except Exception as e:
            logger.error('Error deploying systemd service: %s', e)
            raise

    async def _check_instance_health(self, instance: AgentDeploymentInstance) -> dict[str, Any]:
        """Check health of individual instance"""
        try:
            service_name = f'aitbc-agent-{instance.instance_id}'
            result = subprocess.run(['systemctl', 'is-active', service_name], capture_output=True, text=True)
            service_active = result.stdout.strip() == 'active'
            health_status = 'unhealthy'
            response_time = 0.0
            if service_active and instance.endpoint_url:
                try:
                    import httpx
                    start_time = datetime.now(UTC)
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        response = await client.get(f'{instance.endpoint_url}/health')
                        end_time = datetime.now(UTC)
                        response_time = (end_time - start_time).total_seconds()
                        if response.status_code == 200:
                            health_data = response.json()
                            if health_data.get('status') == 'healthy':
                                health_status = 'healthy'
                            else:
                                health_status = 'degraded'
                        else:
                            health_status = 'unhealthy'
                except Exception as http_error:
                    logger.warning('HTTP health check failed for %s: %s', instance.instance_id, http_error)
                    health_status = 'degraded' if service_active else 'unhealthy'
            else:
                health_status = 'healthy' if service_active else 'unhealthy'
            instance.health_status = health_status
            instance.last_health_check = datetime.now(UTC)
            health_check_record = {'timestamp': datetime.now(UTC).isoformat(), 'status': health_status, 'response_time': response_time, 'service_active': service_active}
            instance.health_check_history.append(health_check_record)
            if len(instance.health_check_history) > 100:
                instance.health_check_history = instance.health_check_history[-100:]
            self.session.commit()
            return {'instance_id': instance.instance_id, 'status': health_status, 'response_time': response_time, 'last_check': instance.last_health_check.isoformat()}
        except Exception as e:
            logger.error('Health check failed for instance %s: %s', instance.id, e)
            instance.health_status = 'unhealthy'
            instance.last_health_check = datetime.now(UTC)
            instance.consecutive_failures += 1
            self.session.commit()
            return {'instance_id': instance.instance_id, 'status': 'unhealthy', 'error': str(e), 'consecutive_failures': instance.consecutive_failures}

    async def scale_deployment(self, deployment_config_id: str, target_instances: int) -> dict[str, Any]:
        """Scale deployment to target number of instances"""
        try:
            config = self.session.get(AgentDeploymentConfig, deployment_config_id)
            if not config:
                raise ValueError(f'Deployment config not found: {deployment_config_id}')
            current_instances = self.session.scalars(select(AgentDeploymentInstance).where(AgentDeploymentInstance.deployment_id == deployment_config_id)).all()
            current_count = len(current_instances)
            scaling_result: dict[str, Any] = {'deployment_id': deployment_config_id, 'current_instances': current_count, 'target_instances': target_instances, 'scaling_action': None, 'scaled_instances': [], 'scaling_errors': []}
            if target_instances > current_count:
                scaling_result['scaling_action'] = 'scale_up'
                instances_to_add = target_instances - current_count
                for i in range(instances_to_add):
                    instance = await self._create_deployment_instance(config, 'production', current_count + i)
                    scaling_result['scaled_instances'].append(instance)
            elif target_instances < current_count:
                scaling_result['scaling_action'] = 'scale_down'
                instances_to_remove = current_count - target_instances
                if instances_to_remove > 0:
                    instances_to_remove_list = current_instances[-instances_to_remove:]
                    for inst_to_remove in instances_to_remove_list:
                        await self._remove_deployment_instance(inst_to_remove.id)
                        scaling_result['scaled_instances'].append({'instance_id': inst_to_remove.instance_id, 'status': 'removed'})
            else:
                scaling_result['scaling_action'] = 'no_change'
            return scaling_result
        except Exception as e:
            logger.error('Scaling failed for %s: %s', deployment_config_id, e)
            raise

    async def _remove_deployment_instance(self, instance_id: str) -> None:
        """Remove deployment instance"""
        try:
            instance = self.session.get(AgentDeploymentInstance, instance_id)
            if instance:
                service_name = f'aitbc-agent-{instance.instance_id}'
                service_file = f'/etc/systemd/system/{service_name}.service'
                try:
                    subprocess.run(['systemctl', 'stop', service_name], check=True, capture_output=True)
                    subprocess.run(['systemctl', 'disable', service_name], check=True, capture_output=True)
                    if os.path.exists(service_file):
                        os.remove(service_file)
                    subprocess.run(['systemctl', 'daemon-reload'], check=True, capture_output=True)
                    logger.info('Removed systemd service: %s', service_name)
                except subprocess.CalledProcessError as e:
                    logger.warning('Failed to remove systemd service %s: %s', service_name, e.stderr)
                except Exception as e:
                    logger.warning('Error removing systemd service: %s', e)
                instance.status = DeploymentStatus.TERMINATED
                self.session.commit()
                logger.info('Removed deployment instance: %s', instance_id)
        except Exception as e:
            logger.error('Failed to remove instance %s: %s', instance_id, e)
            raise

    async def rollback_deployment(self, deployment_config_id: str) -> dict[str, Any]:
        """Rollback deployment to previous version"""
        try:
            config = self.session.get(AgentDeploymentConfig, deployment_config_id)
            if not config:
                raise ValueError(f'Deployment config not found: {deployment_config_id}')
            if not config.rollback_enabled:
                raise ValueError('Rollback not enabled for this deployment')
            rollback_result: dict[str, Any] = {'deployment_id': deployment_config_id, 'rollback_status': 'in_progress', 'rolled_back_instances': [], 'rollback_errors': []}
            current_instances = self.session.scalars(select(AgentDeploymentInstance).where(AgentDeploymentInstance.deployment_id == deployment_config_id)).all()
            for instance in current_instances:
                try:
                    if getattr(config, 'previous_version', None):
                        await self._remove_deployment_instance(instance.id)
                        previous_config = config
                        previous_config.agent_version = getattr(config, 'previous_version', getattr(config, 'agent_version', ''))
                        instance_number = int(instance.instance_id.split('-')[-1])
                        await self._create_deployment_instance(previous_config, instance.environment, instance_number)
                        rollback_result['rolled_back_instances'].append({'instance_id': instance.instance_id, 'status': 'rolled_back'})
                    else:
                        logger.warning('No previous version available for %s', instance.instance_id)
                        rollback_result['rollback_errors'].append({'instance_id': instance.instance_id, 'error': 'No previous version available'})
                except Exception as e:
                    rollback_result['rollback_errors'].append({'instance_id': instance.instance_id, 'error': str(e)})
            if rollback_result['rollback_errors']:
                config.status = DeploymentStatus.FAILED
            else:
                config.status = DeploymentStatus.TERMINATED
            self.session.commit()
            await self.auditor.log_event(AuditEventType.EXECUTION_CANCELLED, workflow_id=config.workflow_id, security_level=SecurityLevel.INTERNAL, event_data={'deployment_id': deployment_config_id, 'rollback_result': rollback_result})
            logger.info('Rolled back deployment: %s', deployment_config_id)
            return rollback_result
        except Exception as e:
            logger.error('Rollback failed for %s: %s', deployment_config_id, e)
            raise

class AgentMonitoringManager:
    """Manages monitoring and metrics for deployed agents"""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.deployment_manager = AgentDeploymentManager(session)
        self.auditor = AgentAuditor(session)

    async def get_deployment_metrics(self, deployment_config_id: str, time_range: str='1h') -> dict[str, Any]:
        """Get metrics for deployment over time range"""
        try:
            config = self.session.get(AgentDeploymentConfig, deployment_config_id)
            if not config:
                raise ValueError(f'Deployment config not found: {deployment_config_id}')
            instances = self.session.scalars(select(AgentDeploymentInstance).where(AgentDeploymentInstance.deployment_id == deployment_config_id)).all()
            metrics: dict[str, Any] = {'deployment_id': deployment_config_id, 'time_range': time_range, 'total_instances': len(instances), 'instance_metrics': [], 'aggregated_metrics': {'total_requests': 0, 'total_errors': 0, 'average_response_time': 0, 'average_cpu_usage': 0, 'average_memory_usage': 0, 'uptime_percentage': 0}}
            total_requests = 0
            total_errors = 0
            total_response_time = 0
            total_cpu = 0
            total_memory = 0
            total_uptime = 0
            for instance in instances:
                instance_metrics = await self._collect_instance_metrics(instance)
                metrics['instance_metrics'].append(instance_metrics)
            for instance_metrics in metrics['instance_metrics']:
                total_requests += instance_metrics.get('request_count', 0)
                total_errors += instance_metrics.get('error_count', 0)
                avg_response_time = instance_metrics.get('average_response_time', 0)
                request_count = instance_metrics.get('request_count', 1)
                if avg_response_time is not None:
                    total_response_time += avg_response_time * request_count
                cpu_usage = instance_metrics.get('cpu_usage', 0)
                if cpu_usage is not None:
                    total_cpu += cpu_usage
                memory_usage = instance_metrics.get('memory_usage', 0)
                if memory_usage is not None:
                    total_memory += memory_usage
                uptime_percentage = instance_metrics.get('uptime_percentage', 0)
                if uptime_percentage is not None:
                    total_uptime += uptime_percentage
            if len(instances) > 0:
                metrics['aggregated_metrics']['total_requests'] = total_requests
                metrics['aggregated_metrics']['total_errors'] = total_errors
                metrics['aggregated_metrics']['average_response_time'] = total_response_time / total_requests if total_requests > 0 else 0
                metrics['aggregated_metrics']['average_cpu_usage'] = total_cpu / len(instances)
                metrics['aggregated_metrics']['average_memory_usage'] = total_memory / len(instances)
                metrics['aggregated_metrics']['uptime_percentage'] = total_uptime / len(instances)
            return metrics
        except Exception as e:
            logger.error('Metrics collection failed for %s: %s', deployment_config_id, e)
            raise

    async def _collect_instance_metrics(self, instance: AgentDeploymentInstance) -> dict[str, Any]:
        """Collect metrics from individual instance"""
        try:
            metrics_data: dict[str, Any] = {'instance_id': instance.instance_id, 'status': instance.status, 'health_status': instance.health_status, 'timestamp': datetime.now(UTC).isoformat()}
            if instance.endpoint_url:
                try:
                    import httpx
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        response = await client.get(f'{instance.endpoint_url}/metrics')
                        if response.status_code == 200:
                            agent_metrics = response.json()
                            metrics_data.update({'cpu_usage': agent_metrics.get('cpu_usage', instance.cpu_usage), 'memory_usage': agent_metrics.get('memory_usage', instance.memory_usage), 'request_count': agent_metrics.get('request_count', instance.request_count), 'error_count': agent_metrics.get('error_count', instance.error_count), 'average_response_time': agent_metrics.get('average_response_time', instance.average_response_time), 'uptime_percentage': agent_metrics.get('uptime_percentage', instance.uptime_percentage)})
                        else:
                            metrics_data.update({'cpu_usage': instance.cpu_usage, 'memory_usage': instance.memory_usage, 'request_count': instance.request_count, 'error_count': instance.error_count, 'average_response_time': instance.average_response_time, 'uptime_percentage': instance.uptime_percentage})
                except Exception as http_error:
                    logger.warning('Failed to fetch metrics from %s: %s', instance.instance_id, http_error)
                    metrics_data.update({'cpu_usage': instance.cpu_usage, 'memory_usage': instance.memory_usage, 'request_count': instance.request_count, 'error_count': instance.error_count, 'average_response_time': instance.average_response_time, 'uptime_percentage': instance.uptime_percentage})
            else:
                metrics_data.update({'cpu_usage': instance.cpu_usage, 'memory_usage': instance.memory_usage, 'request_count': instance.request_count, 'error_count': instance.error_count, 'average_response_time': instance.average_response_time, 'uptime_percentage': instance.uptime_percentage})
            metrics_data['last_health_check'] = instance.last_health_check.isoformat() if instance.last_health_check else None
            return metrics_data
        except Exception as e:
            logger.error('Metrics collection failed for instance %s: %s', instance.id, e)
            return {'instance_id': instance.instance_id, 'error': str(e)}

    async def create_alerting_rules(self, deployment_config_id: str, alerting_rules: dict[str, Any]) -> dict[str, Any]:
        """Create alerting rules for deployment monitoring"""
        try:
            config = self.session.get(AgentDeploymentConfig, deployment_config_id)
            if not config:
                raise ValueError(f'Deployment config not found: {deployment_config_id}')
            config.alerting_rules = alerting_rules
            self.session.commit()
            thresholds = alerting_rules.get('thresholds', {'cpu_usage_warning': 80.0, 'cpu_usage_critical': 90.0, 'memory_usage_warning': 85.0, 'memory_usage_critical': 95.0, 'error_rate_warning': 0.05, 'error_rate_critical': 0.1, 'response_time_warning': 2.0, 'response_time_critical': 5.0})
            alert_channels = alerting_rules.get('channels', ['log'])
            alerting_result = {'deployment_id': deployment_config_id, 'alerting_rules': alerting_rules, 'rules_created': len(alerting_rules.get('rules', [])), 'thresholds_configured': thresholds, 'alert_channels': alert_channels, 'status': 'created'}
            logger.info('Created alerting rules for deployment %s', deployment_config_id)
            return alerting_result
        except Exception as e:
            logger.error('Failed to create alerting rules for %s: %s', deployment_config_id, e)
            raise

class AgentProductionManager:
    """Main production management interface for agent orchestration"""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.integration_manager = AgentIntegrationManager(session)
        self.deployment_manager = AgentDeploymentManager(session)
        self.monitoring_manager = AgentMonitoringManager(session)
        self.auditor = AgentAuditor(session)

    async def deploy_to_production(self, workflow_id: str, deployment_config: dict[str, Any], integration_config: dict[str, Any] | None=None) -> dict[str, Any]:
        """Deploy agent workflow to production with full integration"""
        try:
            production_result: dict[str, Any] = {'workflow_id': workflow_id, 'deployment_status': 'in_progress', 'integration_status': 'pending', 'monitoring_status': 'pending', 'deployment_id': None, 'errors': []}
            deployment = await self.deployment_manager.create_deployment_config(workflow_id=workflow_id, deployment_name=deployment_config.get('name', f'production-{workflow_id}'), deployment_config=deployment_config)
            production_result['deployment_id'] = deployment.id
            deployment_result = await self.deployment_manager.deploy_agent_workflow(deployment_config_id=deployment.id, target_environment='production')
            production_result['deployment_status'] = deployment_result['status']
            production_result['deployment_errors'] = deployment_result.get('deployment_errors', [])
            if integration_config:
                production_result['integration_status'] = 'configured'
            else:
                production_result['integration_status'] = 'skipped'
            try:
                monitoring_setup = await self.monitoring_manager.create_alerting_rules(deployment_config_id=deployment.id, alerting_rules=deployment_config.get('alerting_rules', {}))
                production_result['monitoring_status'] = monitoring_setup['status']
            except Exception as e:
                production_result['monitoring_status'] = 'failed'
                production_result['errors'].append(f'Monitoring setup failed: {e}')
            if production_result['errors']:
                production_result['overall_status'] = 'partial_success'
            else:
                production_result['overall_status'] = 'success'
            await self.auditor.log_event(AuditEventType.EXECUTION_COMPLETED, workflow_id=workflow_id, security_level=SecurityLevel.INTERNAL, event_data={'production_deployment': production_result})
            logger.info('Production deployment completed for workflow %s', workflow_id)
            return production_result
        except Exception as e:
            logger.error('Production deployment failed for workflow %s: %s', workflow_id, e)
            await self.auditor.log_event(AuditEventType.EXECUTION_FAILED, workflow_id=workflow_id, security_level=SecurityLevel.INTERNAL, event_data={'error': str(e)})
            raise
