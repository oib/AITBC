"""
Agent Security and Audit Framework for Verifiable AI Agent Orchestration
Implements comprehensive security, auditing, and trust establishment for agent executions
"""

import hashlib
import json

from aitbc import get_logger

logger = get_logger(__name__)
from datetime import datetime, UTC
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlmodel import JSON, Column, Field, Session, SQLModel, select

from ..domain.agent import AIAgentWorkflow, VerificationLevel


class SecurityLevel(StrEnum):
    """Security classification levels for agent operations"""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class AuditEventType(StrEnum):
    """Types of audit events for agent operations"""

    WORKFLOW_CREATED = "workflow_created"
    WORKFLOW_UPDATED = "workflow_updated"
    WORKFLOW_DELETED = "workflow_deleted"
    EXECUTION_STARTED = "execution_started"
    EXECUTION_COMPLETED = "execution_completed"
    EXECUTION_FAILED = "execution_failed"
    EXECUTION_CANCELLED = "execution_cancelled"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"
    VERIFICATION_COMPLETED = "verification_completed"
    VERIFICATION_FAILED = "verification_failed"
    SECURITY_VIOLATION = "security_violation"
    ACCESS_DENIED = "access_denied"
    SANDBOX_BREACH = "sandbox_breach"


class AgentAuditLog(SQLModel, table=True):
    """Comprehensive audit log for agent operations"""

    __tablename__ = "agent_audit_logs"

    id: str = Field(default_factory=lambda: f"audit_{uuid4().hex[:12]}", primary_key=True)

    # Event information
    event_type: AuditEventType = Field(index=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)

    # Entity references
    workflow_id: str | None = Field(index=True)
    execution_id: str | None = Field(index=True)
    step_id: str | None = Field(index=True)
    user_id: str | None = Field(index=True)

    # Security context
    security_level: SecurityLevel = Field(default=SecurityLevel.PUBLIC)
    ip_address: str | None = Field(default=None)
    user_agent: str | None = Field(default=None)

    # Event data
    event_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    previous_state: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    new_state: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))

    # Security metadata
    risk_score: int = Field(default=0)  # 0-100 risk assessment
    requires_investigation: bool = Field(default=False)
    investigation_notes: str | None = Field(default=None)

    # Verification
    cryptographic_hash: str | None = Field(default=None)
    signature_valid: bool | None = Field(default=None)

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AgentSecurityPolicy(SQLModel, table=True):
    """Security policies for agent operations"""

    __tablename__ = "agent_security_policies"

    id: str = Field(default_factory=lambda: f"policy_{uuid4().hex[:8]}", primary_key=True)

    # Policy definition
    name: str = Field(max_length=100, unique=True)
    description: str = Field(default="")
    security_level: SecurityLevel = Field(default=SecurityLevel.PUBLIC)

    # Policy rules
    allowed_step_types: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    max_execution_time: int = Field(default=3600)  # seconds
    max_memory_usage: int = Field(default=8192)  # MB
    require_verification: bool = Field(default=True)
    allowed_verification_levels: list[VerificationLevel] = Field(
        default_factory=lambda: [VerificationLevel.BASIC], sa_column=Column(JSON)
    )

    # Resource limits
    max_concurrent_executions: int = Field(default=10)
    max_workflow_steps: int = Field(default=100)
    max_data_size: int = Field(default=1024 * 1024 * 1024)  # 1GB

    # Security requirements
    require_sandbox: bool = Field(default=False)
    require_audit_logging: bool = Field(default=True)
    require_encryption: bool = Field(default=False)

    # Compliance
    compliance_standards: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    # Status
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AgentTrustScore(SQLModel, table=True):
    """Trust and reputation scoring for agents and users"""

    __tablename__ = "agent_trust_scores"

    id: str = Field(default_factory=lambda: f"trust_{uuid4().hex[:8]}", primary_key=True)

    # Entity information
    entity_type: str = Field(index=True)  # "agent", "user", "workflow"
    entity_id: str = Field(index=True)

    # Trust metrics
    trust_score: float = Field(default=0.0, index=True)  # 0-100
    reputation_score: float = Field(default=0.0)  # 0-100

    # Performance metrics
    total_executions: int = Field(default=0)
    successful_executions: int = Field(default=0)
    failed_executions: int = Field(default=0)
    verification_success_rate: float = Field(default=0.0)

    # Security metrics
    security_violations: int = Field(default=0)
    policy_violations: int = Field(default=0)
    sandbox_breaches: int = Field(default=0)

    # Time-based metrics
    last_execution: datetime | None = Field(default=None)
    last_violation: datetime | None = Field(default=None)
    average_execution_time: float | None = Field(default=None)

    # Historical data
    execution_history: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    violation_history: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AgentSandboxConfig(SQLModel, table=True):
    """Sandboxing configuration for agent execution"""

    __tablename__ = "agent_sandbox_configs"

    id: str = Field(default_factory=lambda: f"sandbox_{uuid4().hex[:8]}", primary_key=True)

    # Sandbox type
    sandbox_type: str = Field(default="process")  # vm, process, none
    security_level: SecurityLevel = Field(default=SecurityLevel.PUBLIC)

    # Resource limits
    cpu_limit: float = Field(default=1.0)  # CPU cores
    memory_limit: int = Field(default=1024)  # MB
    disk_limit: int = Field(default=10240)  # MB
    network_access: bool = Field(default=False)

    # Security restrictions
    allowed_commands: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    blocked_commands: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    allowed_file_paths: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    blocked_file_paths: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    # Network restrictions
    allowed_domains: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    blocked_domains: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    allowed_ports: list[int] = Field(default_factory=list, sa_column=Column(JSON))

    # Time limits
    max_execution_time: int = Field(default=3600)  # seconds
    idle_timeout: int = Field(default=300)  # seconds

    # Monitoring
    enable_monitoring: bool = Field(default=True)
    log_all_commands: bool = Field(default=False)
    log_file_access: bool = Field(default=True)
    log_network_access: bool = Field(default=True)

    # Status
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AgentAuditor:
    """Comprehensive auditing system for agent operations"""

    def __init__(self, session: Session):
        self.session = session
        self.security_policies = {}
        self.trust_manager = AgentTrustManager(session)
        self.sandbox_manager = AgentSandboxManager(session)

    async def log_event(
        self,
        event_type: AuditEventType,
        workflow_id: str | None = None,
        execution_id: str | None = None,
        step_id: str | None = None,
        user_id: str | None = None,
        security_level: SecurityLevel = SecurityLevel.PUBLIC,
        event_data: dict[str, Any] | None = None,
        previous_state: dict[str, Any] | None = None,
        new_state: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AgentAuditLog:
        """Log an audit event with comprehensive security context"""

        # Calculate risk score
        risk_score = self._calculate_risk_score(event_type, event_data, security_level)

        # Create audit log entry
        audit_log = AgentAuditLog(
            event_type=event_type,
            workflow_id=workflow_id,
            execution_id=execution_id,
            step_id=step_id,
            user_id=user_id,
            security_level=security_level,
            ip_address=ip_address,
            user_agent=user_agent,
            event_data=event_data or {},
            previous_state=previous_state,
            new_state=new_state,
            risk_score=risk_score,
            requires_investigation=risk_score >= 70,
            cryptographic_hash=self._generate_event_hash(event_data),
            signature_valid=self._verify_signature(event_data),
        )

        # Store audit log
        self.session.add(audit_log)
        self.session.commit()
        self.session.refresh(audit_log)

        # Handle high-risk events
        if audit_log.requires_investigation:
            await self._handle_high_risk_event(audit_log)

        logger.info(f"Audit event logged: {event_type.value} for workflow {workflow_id} execution {execution_id}")
        return audit_log

    def _calculate_risk_score(
        self, event_type: AuditEventType, event_data: dict[str, Any], security_level: SecurityLevel
    ) -> int:
        """Calculate risk score for audit event"""

        base_score = 0

        # Event type risk
        event_risk_scores = {
            AuditEventType.SECURITY_VIOLATION: 90,
            AuditEventType.SANDBOX_BREACH: 85,
            AuditEventType.ACCESS_DENIED: 70,
            AuditEventType.VERIFICATION_FAILED: 50,
            AuditEventType.EXECUTION_FAILED: 30,
            AuditEventType.STEP_FAILED: 20,
            AuditEventType.EXECUTION_CANCELLED: 15,
            AuditEventType.WORKFLOW_DELETED: 10,
            AuditEventType.WORKFLOW_CREATED: 5,
            AuditEventType.EXECUTION_STARTED: 3,
            AuditEventType.EXECUTION_COMPLETED: 1,
            AuditEventType.STEP_STARTED: 1,
            AuditEventType.STEP_COMPLETED: 1,
            AuditEventType.VERIFICATION_COMPLETED: 1,
        }

        base_score += event_risk_scores.get(event_type, 0)

        # Security level adjustment
        security_multipliers = {
            SecurityLevel.PUBLIC: 1.0,
            SecurityLevel.INTERNAL: 1.2,
            SecurityLevel.CONFIDENTIAL: 1.5,
            SecurityLevel.RESTRICTED: 2.0,
        }

        base_score = int(base_score * security_multipliers[security_level])

        # Event data analysis
        if event_data:
            # Check for suspicious patterns
            if event_data.get("error_message"):
                base_score += 10
            if event_data.get("execution_time", 0) > 3600:  # > 1 hour
                base_score += 5
            if event_data.get("memory_usage", 0) > 8192:  # > 8GB
                base_score += 5

        return min(base_score, 100)

    def _generate_event_hash(self, event_data: dict[str, Any]) -> str:
        """Generate cryptographic hash for event data"""
        if not event_data:
            return None

        # Create canonical JSON representation
        canonical_json = json.dumps(event_data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical_json.encode()).hexdigest()

    def _verify_signature(self, event_data: dict[str, Any]) -> bool | None:
        """Verify cryptographic signature of event data
        
        Note: Full signature verification requires:
        1. Extract signature from event_data
        2. Verify against expected public key
        3. Use appropriate crypto library (e.g., cryptography, eth_keys)
        Currently returns None (not verified) for compatibility.
        """
        try:
            # Check if signature data exists
            if "signature" not in event_data or "public_key" not in event_data:
                return None
            
            # Placeholder for actual signature verification
            # In production, use cryptography library to verify signature
            # from cryptography.hazmat.primitives import hashes
            # from cryptography.hazmat.primitives.asymmetric import padding
            
            # For now, return None to indicate not verified
            return None
        except Exception as e:
            logger.error(f"Signature verification failed: {e}")
            return False

    async def _handle_high_risk_event(self, audit_log: AgentAuditLog):
        """Handle high-risk audit events requiring investigation"""

        logger.warning(f"High-risk audit event detected: {audit_log.event_type.value} (Score: {audit_log.risk_score})")

        # Create investigation record
        investigation_notes = f"High-risk event detected on {audit_log.timestamp}. "
        investigation_notes += f"Event type: {audit_log.event_type.value}, "
        investigation_notes += f"Risk score: {audit_log.risk_score}. "
        investigation_notes += "Requires manual investigation."

        # Update audit log
        audit_log.investigation_notes = investigation_notes
        audit_log.investigation_status = "pending"
        audit_log.investigation_required = True
        self.session.commit()

        # Send alert to security team (placeholder for actual alerting system)
        # In production, integrate with email, Slack, or other alerting systems
        logger.critical(f"SECURITY ALERT: High-risk event requires investigation - Event ID: {audit_log.id}")

        # Create investigation ticket (placeholder for ticketing system integration)
        # In production, integrate with Jira, GitHub Issues, or other ticketing systems
        logger.info(f"Investigation ticket would be created for event: {audit_log.id}")

        # Temporarily suspend related entities if needed (placeholder for suspension logic)
        # In production, implement suspension logic based on risk level and event type
        if audit_log.risk_score >= 0.9:
            logger.warning(f"Critical risk score ({audit_log.risk_score}) - entity suspension recommended")
            # Placeholder for actual suspension logic
            # await self._suspend_entity_if_needed(audit_log)


class AgentTrustManager:
    """Trust and reputation management for agents and users"""

    def __init__(self, session: Session):
        self.session = session

    async def update_trust_score(
        self,
        entity_type: str,
        entity_id: str,
        execution_success: bool,
        execution_time: float | None = None,
        security_violation: bool = False,
        policy_violation: bool = bool,
    ) -> AgentTrustScore:
        """Update trust score based on execution results"""

        # Get or create trust score record
        trust_score = self.session.execute(
            select(AgentTrustScore).where(
                (AgentTrustScore.entity_type == entity_type) & (AgentTrustScore.entity_id == entity_id)
            )
        ).first()

        if not trust_score:
            trust_score = AgentTrustScore(entity_type=entity_type, entity_id=entity_id)
            self.session.add(trust_score)

        # Update metrics
        trust_score.total_executions += 1

        if execution_success:
            trust_score.successful_executions += 1
        else:
            trust_score.failed_executions += 1

        if security_violation:
            trust_score.security_violations += 1
            trust_score.last_violation = datetime.now(datetime.UTC)
            trust_score.violation_history.append({"timestamp": datetime.now(datetime.UTC).isoformat(), "type": "security_violation"})

        if policy_violation:
            trust_score.policy_violations += 1
            trust_score.last_violation = datetime.now(datetime.UTC)
            trust_score.violation_history.append({"timestamp": datetime.now(datetime.UTC).isoformat(), "type": "policy_violation"})

        # Calculate scores
        trust_score.trust_score = self._calculate_trust_score(trust_score)
        trust_score.reputation_score = self._calculate_reputation_score(trust_score)
        trust_score.verification_success_rate = (
            trust_score.successful_executions / trust_score.total_executions * 100 if trust_score.total_executions > 0 else 0
        )

        # Update execution metrics
        if execution_time:
            if trust_score.average_execution_time is None:
                trust_score.average_execution_time = execution_time
            else:
                trust_score.average_execution_time = (
                    trust_score.average_execution_time * (trust_score.total_executions - 1) + execution_time
                ) / trust_score.total_executions

        trust_score.last_execution = datetime.now(datetime.UTC)
        trust_score.updated_at = datetime.now(datetime.UTC)

        self.session.commit()
        self.session.refresh(trust_score)

        return trust_score

    def _calculate_trust_score(self, trust_score: AgentTrustScore) -> float:
        """Calculate overall trust score"""

        base_score = 50.0  # Start at neutral

        # Success rate impact
        if trust_score.total_executions > 0:
            success_rate = trust_score.successful_executions / trust_score.total_executions
            base_score += (success_rate - 0.5) * 40  # +/- 20 points

        # Security violations penalty
        violation_penalty = trust_score.security_violations * 10
        base_score -= violation_penalty

        # Policy violations penalty
        policy_penalty = trust_score.policy_violations * 5
        base_score -= policy_penalty

        # Recency bonus (recent successful executions)
        if trust_score.last_execution:
            days_since_last = (datetime.now(datetime.UTC) - trust_score.last_execution).days
            if days_since_last < 7:
                base_score += 5  # Recent activity bonus
            elif days_since_last > 30:
                base_score -= 10  # Inactivity penalty

        return max(0.0, min(100.0, base_score))

    def _calculate_reputation_score(self, trust_score: AgentTrustScore) -> float:
        """Calculate reputation score based on long-term performance"""

        base_score = 50.0

        # Long-term success rate
        if trust_score.total_executions >= 10:
            success_rate = trust_score.successful_executions / trust_score.total_executions
            base_score += (success_rate - 0.5) * 30  # +/- 15 points

        # Volume bonus (more executions = more data points)
        volume_bonus = min(trust_score.total_executions / 100, 10)  # Max 10 points
        base_score += volume_bonus

        # Security record
        if trust_score.security_violations == 0 and trust_score.policy_violations == 0:
            base_score += 10  # Clean record bonus
        else:
            violation_penalty = (trust_score.security_violations + trust_score.policy_violations) * 2
            base_score -= violation_penalty

        return max(0.0, min(100.0, base_score))


class AgentSandboxManager:
    """Sandboxing and isolation management for agent execution"""

    def __init__(self, session: Session):
        self.session = session

    async def create_sandbox_environment(
        self,
        execution_id: str,
        security_level: SecurityLevel = SecurityLevel.PUBLIC,
        workflow_requirements: dict[str, Any] | None = None,
    ) -> AgentSandboxConfig:
        """Create sandbox environment for agent execution"""

        # Get appropriate sandbox configuration
        sandbox_config = self._get_sandbox_config(security_level)

        # Customize based on workflow requirements
        if workflow_requirements:
            sandbox_config = self._customize_sandbox(sandbox_config, workflow_requirements)

        # Create sandbox record
        sandbox = AgentSandboxConfig(
            id=f"sandbox_{execution_id}",
            sandbox_type=sandbox_config["type"],
            security_level=security_level,
            cpu_limit=sandbox_config["cpu_limit"],
            memory_limit=sandbox_config["memory_limit"],
            disk_limit=sandbox_config["disk_limit"],
            network_access=sandbox_config["network_access"],
            allowed_commands=sandbox_config["allowed_commands"],
            blocked_commands=sandbox_config["blocked_commands"],
            allowed_file_paths=sandbox_config["allowed_file_paths"],
            blocked_file_paths=sandbox_config["blocked_file_paths"],
            allowed_domains=sandbox_config["allowed_domains"],
            blocked_domains=sandbox_config["blocked_domains"],
            allowed_ports=sandbox_config["allowed_ports"],
            max_execution_time=sandbox_config["max_execution_time"],
            idle_timeout=sandbox_config["idle_timeout"],
            enable_monitoring=sandbox_config["enable_monitoring"],
            log_all_commands=sandbox_config["log_all_commands"],
            log_file_access=sandbox_config["log_file_access"],
            log_network_access=sandbox_config["log_network_access"],
        )

        self.session.add(sandbox)
        self.session.commit()
        self.session.refresh(sandbox)

        # Sandbox environment creation requires integration with:
        # 1. Podman for container isolation
        # 2. Firecracker/gVisor for VM-level isolation
        # 3. Process isolation using seccomp, namespaces
        # 4. Network isolation using virtual networks
        # Currently storing configuration only - actual sandbox creation
        # would be implemented by the execution orchestrator.

        logger.info(f"Created sandbox configuration for execution {execution_id}")
        return sandbox

    def _get_sandbox_config(self, security_level: SecurityLevel) -> dict[str, Any]:
        """Get sandbox configuration based on security level"""

        configs = {
            SecurityLevel.PUBLIC: {
                "type": "process",
                "cpu_limit": 1.0,
                "memory_limit": 1024,
                "disk_limit": 10240,
                "network_access": False,
                "allowed_commands": ["python", "node", "java"],
                "blocked_commands": ["rm", "sudo", "chmod", "chown"],
                "allowed_file_paths": ["/tmp", "/workspace"],
                "blocked_file_paths": ["/etc", "/root", "/home"],
                "allowed_domains": [],
                "blocked_domains": [],
                "allowed_ports": [],
                "max_execution_time": 3600,
                "idle_timeout": 300,
                "enable_monitoring": True,
                "log_all_commands": False,
                "log_file_access": True,
                "log_network_access": True,
            },
            SecurityLevel.INTERNAL: {
                "type": "docker",
                "cpu_limit": 2.0,
                "memory_limit": 2048,
                "disk_limit": 20480,
                "network_access": True,
                "allowed_commands": ["python", "node", "java", "curl", "wget"],
                "blocked_commands": ["rm", "sudo", "chmod", "chown", "iptables"],
                "allowed_file_paths": ["/tmp", "/workspace", "/app"],
                "blocked_file_paths": ["/etc", "/root", "/home", "/var"],
                "allowed_domains": ["*.internal.com", "*.api.internal"],
                "blocked_domains": ["malicious.com", "*.suspicious.net"],
                "allowed_ports": [80, 443, 8000, 8001, 8002, 8003, 8010, 8011, 8012, 8013, 8014, 8015, 8016],
                "max_execution_time": 7200,
                "idle_timeout": 600,
                "enable_monitoring": True,
                "log_all_commands": True,
                "log_file_access": True,
                "log_network_access": True,
            },
            SecurityLevel.CONFIDENTIAL: {
                "type": "docker",
                "cpu_limit": 4.0,
                "memory_limit": 4096,
                "disk_limit": 40960,
                "network_access": True,
                "allowed_commands": ["python", "node", "java", "curl", "wget", "git"],
                "blocked_commands": ["rm", "sudo", "chmod", "chown", "iptables", "systemctl"],
                "allowed_file_paths": ["/tmp", "/workspace", "/app", "/data"],
                "blocked_file_paths": ["/etc", "/root", "/home", "/var", "/sys", "/proc"],
                "allowed_domains": ["*.internal.com", "*.api.internal", "*.trusted.com"],
                "blocked_domains": ["malicious.com", "*.suspicious.net", "*.evil.org"],
                "allowed_ports": [80, 443, 8000, 8001, 8002, 8003, 8010, 8011, 8012, 8013, 8014, 8015, 8016],
                "max_execution_time": 14400,
                "idle_timeout": 1800,
                "enable_monitoring": True,
                "log_all_commands": True,
                "log_file_access": True,
                "log_network_access": True,
            },
            SecurityLevel.RESTRICTED: {
                "type": "vm",
                "cpu_limit": 8.0,
                "memory_limit": 8192,
                "disk_limit": 81920,
                "network_access": True,
                "allowed_commands": ["python", "node", "java", "curl", "wget", "git", "docker"],
                "blocked_commands": ["rm", "sudo", "chmod", "chown", "iptables", "systemctl", "systemd"],
                "allowed_file_paths": ["/tmp", "/workspace", "/app", "/data", "/shared"],
                "blocked_file_paths": ["/etc", "/root", "/home", "/var", "/sys", "/proc", "/boot"],
                "allowed_domains": ["*.internal.com", "*.api.internal", "*.trusted.com", "*.partner.com"],
                "blocked_domains": ["malicious.com", "*.suspicious.net", "*.evil.org"],
                "allowed_ports": [80, 443, 8000, 8001, 8002, 8003, 8010, 8011, 8012, 8013, 8014, 8015, 8016, 22, 25],
                "max_execution_time": 28800,
                "idle_timeout": 3600,
                "enable_monitoring": True,
                "log_all_commands": True,
                "log_file_access": True,
                "log_network_access": True,
            },
        }

        return configs.get(security_level, configs[SecurityLevel.PUBLIC])

    def _customize_sandbox(self, base_config: dict[str, Any], requirements: dict[str, Any]) -> dict[str, Any]:
        """Customize sandbox configuration based on workflow requirements"""

        config = base_config.copy()

        # Adjust resources based on requirements
        if "cpu_cores" in requirements:
            config["cpu_limit"] = max(config["cpu_limit"], requirements["cpu_cores"])

        if "memory_mb" in requirements:
            config["memory_limit"] = max(config["memory_limit"], requirements["memory_mb"])

        if "disk_mb" in requirements:
            config["disk_limit"] = max(config["disk_limit"], requirements["disk_mb"])

        if "max_execution_time" in requirements:
            config["max_execution_time"] = min(config["max_execution_time"], requirements["max_execution_time"])

        # Add custom commands if specified
        if "allowed_commands" in requirements:
            config["allowed_commands"].extend(requirements["allowed_commands"])

        if "blocked_commands" in requirements:
            config["blocked_commands"].extend(requirements["blocked_commands"])

        # Add network access if required
        if "network_access" in requirements:
            config["network_access"] = config["network_access"] or requirements["network_access"]

        return config

    async def monitor_sandbox(self, execution_id: str) -> dict[str, Any]:
        """Monitor sandbox execution for security violations
        
        Note: Actual sandbox monitoring requires integration with:
        1. Container runtime metrics (Docker stats, containerd)
        2. Process monitoring (psutil, /proc filesystem)
        3. Network monitoring (iptables, eBPF)
        4. File system monitoring (inotify, auditd)
        Currently returning placeholder monitoring data.
        """
        # Get sandbox configuration
        sandbox = self.session.execute(
            select(AgentSandboxConfig).where(AgentSandboxConfig.id == f"sandbox_{execution_id}")
        ).first()

        if not sandbox:
            raise ValueError(f"Sandbox not found for execution {execution_id}")

        # Placeholder for actual monitoring implementation
        # In production, integrate with container runtime for real metrics
        monitoring_data = {
            "execution_id": execution_id,
            "sandbox_type": sandbox.sandbox_type,
            "security_level": sandbox.security_level,
            "resource_usage": {"cpu_percent": 0.0, "memory_mb": 0, "disk_mb": 0},
            "security_events": [],
            "command_count": 0,
            "file_access_count": 0,
            "network_access_count": 0,
            "status": "configured",
            "note": "Monitoring requires sandbox runtime integration"
        }

        return monitoring_data

    async def cleanup_sandbox(self, execution_id: str) -> bool:
        """Clean up sandbox environment after execution"""

        try:
            # Get sandbox record
            sandbox = self.session.execute(
                select(AgentSandboxConfig).where(AgentSandboxConfig.id == f"sandbox_{execution_id}")
            ).first()

            if sandbox:
                # Mark as inactive
                sandbox.is_active = False
                sandbox.updated_at = datetime.now(datetime.UTC)
                self.session.commit()

                # Sandbox cleanup requires integration with:
                # 1. Docker/Podman: docker stop/rm, podman stop/rm
                # 2. VM management: Firecracker terminate
                # 3. Process cleanup: kill processes, cleanup namespaces
                # 4. Resource cleanup: remove temp files, network interfaces
                # Currently marking as inactive - actual cleanup would be
                # implemented by the execution orchestrator.
                # Future implementation: await self._cleanup_docker_sandbox(sandbox)

                logger.info(f"Marked sandbox as inactive for execution {execution_id}")
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to cleanup sandbox for execution {execution_id}: {e}")
            return False


class AgentSecurityManager:
    """Main security management interface for agent operations"""

    def __init__(self, session: Session):
        self.session = session
        self.auditor = AgentAuditor(session)
        self.trust_manager = AgentTrustManager(session)
        self.sandbox_manager = AgentSandboxManager(session)

    async def create_security_policy(
        self, name: str, description: str, security_level: SecurityLevel, policy_rules: dict[str, Any]
    ) -> AgentSecurityPolicy:
        """Create a new security policy"""

        policy = AgentSecurityPolicy(name=name, description=description, security_level=security_level, **policy_rules)

        self.session.add(policy)
        self.session.commit()
        self.session.refresh(policy)

        # Log policy creation
        await self.auditor.log_event(
            AuditEventType.WORKFLOW_CREATED,
            user_id="system",
            security_level=SecurityLevel.INTERNAL,
            event_data={"policy_name": name, "policy_id": policy.id},
            new_state={"policy": policy.dict()},
        )

        return policy

    async def validate_workflow_security(self, workflow: AIAgentWorkflow, user_id: str) -> dict[str, Any]:
        """Validate workflow against security policies"""

        validation_result = {
            "valid": True,
            "violations": [],
            "warnings": [],
            "required_security_level": SecurityLevel.PUBLIC,
            "recommendations": [],
        }

        # Check for security-sensitive operations
        security_sensitive_steps = []
        for step_data in workflow.steps.values():
            if step_data.get("step_type") in ["training", "data_processing"]:
                security_sensitive_steps.append(step_data.get("name"))

        if security_sensitive_steps:
            validation_result["warnings"].append(f"Security-sensitive steps detected: {security_sensitive_steps}")
            validation_result["recommendations"].append(
                "Consider using higher security level for workflows with sensitive operations"
            )

        # Check execution time
        if workflow.max_execution_time > 3600:  # > 1 hour
            validation_result["warnings"].append(
                f"Long execution time ({workflow.max_execution_time}s) may require additional security measures"
            )

        # Check verification requirements
        if not workflow.requires_verification:
            validation_result["violations"].append(
                "Workflow does not require verification - this is not recommended for production use"
            )
            validation_result["valid"] = False

        # Determine required security level
        if workflow.requires_verification and workflow.verification_level == VerificationLevel.ZERO_KNOWLEDGE:
            validation_result["required_security_level"] = SecurityLevel.RESTRICTED
        elif workflow.requires_verification and workflow.verification_level == VerificationLevel.FULL:
            validation_result["required_security_level"] = SecurityLevel.CONFIDENTIAL
        elif workflow.requires_verification:
            validation_result["required_security_level"] = SecurityLevel.INTERNAL

        # Log security validation
        await self.auditor.log_event(
            AuditEventType.WORKFLOW_CREATED,
            workflow_id=workflow.id,
            user_id=user_id,
            security_level=validation_result["required_security_level"],
            event_data={"validation_result": validation_result},
        )

        return validation_result

    async def monitor_execution_security(self, execution_id: str, workflow_id: str) -> dict[str, Any]:
        """Monitor execution for security violations"""

        monitoring_result = {
            "execution_id": execution_id,
            "workflow_id": workflow_id,
            "security_status": "monitoring",
            "violations": [],
            "alerts": [],
        }

        try:
            # Monitor sandbox
            sandbox_monitoring = await self.sandbox_manager.monitor_sandbox(execution_id)

            # Check for resource violations
            if sandbox_monitoring["resource_usage"]["cpu_percent"] > 90:
                monitoring_result["violations"].append("High CPU usage detected")
                monitoring_result["alerts"].append("CPU usage exceeded 90%")

            if sandbox_monitoring["resource_usage"]["memory_mb"] > sandbox_monitoring["resource_usage"]["memory_mb"] * 0.9:
                monitoring_result["violations"].append("High memory usage detected")
                monitoring_result["alerts"].append("Memory usage exceeded 90% of limit")

            # Check for security events
            if sandbox_monitoring["security_events"]:
                monitoring_result["violations"].extend(sandbox_monitoring["security_events"])
                monitoring_result["alerts"].extend(
                    f"Security event: {event}" for event in sandbox_monitoring["security_events"]
                )

            # Update security status
            if monitoring_result["violations"]:
                monitoring_result["security_status"] = "violations_detected"
                await self.auditor.log_event(
                    AuditEventType.SECURITY_VIOLATION,
                    execution_id=execution_id,
                    workflow_id=workflow_id,
                    security_level=SecurityLevel.INTERNAL,
                    event_data={"violations": monitoring_result["violations"]},
                    requires_investigation=len(monitoring_result["violations"]) > 0,
                )
            else:
                monitoring_result["security_status"] = "secure"

        except Exception as e:
            monitoring_result["security_status"] = "monitoring_failed"
            monitoring_result["alerts"].append(f"Security monitoring failed: {e}")
            await self.auditor.log_event(
                AuditEventType.SECURITY_VIOLATION,
                execution_id=execution_id,
                workflow_id=workflow_id,
                security_level=SecurityLevel.INTERNAL,
                event_data={"error": str(e)},
                requires_investigation=True,
            )

        return monitoring_result
