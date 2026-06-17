"""
Agent Security and Audit Framework for Verifiable AI Agent Orchestration
Implements comprehensive security, auditing, and trust establishment for agent executions
"""

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlmodel import JSON, Column, Field, Session, SQLModel, select

from aitbc.aitbc_logging import get_logger
from app.domain.agent import AIAgentWorkflow, VerificationLevel

logger = get_logger(__name__)


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
    event_type: AuditEventType = Field(index=True)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    workflow_id: str | None = Field(index=True)
    execution_id: str | None = Field(index=True)
    step_id: str | None = Field(index=True)
    user_id: str | None = Field(index=True)
    security_level: SecurityLevel = Field(default=SecurityLevel.PUBLIC)
    ip_address: str | None = Field(default=None)
    user_agent: str | None = Field(default=None)
    event_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    previous_state: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    new_state: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    risk_score: int = Field(default=0)
    requires_investigation: bool = Field(default=False)
    investigation_notes: str | None = Field(default=None)
    cryptographic_hash: str | None = Field(default=None)
    signature_valid: bool | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AgentSecurityPolicy(SQLModel, table=True):
    """Security policies for agent operations"""

    __tablename__ = "agent_security_policies"
    id: str = Field(default_factory=lambda: f"policy_{uuid4().hex[:8]}", primary_key=True)
    name: str = Field(max_length=100, unique=True)
    description: str = Field(default="")
    security_level: SecurityLevel = Field(default=SecurityLevel.PUBLIC)
    allowed_step_types: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    max_execution_time: int = Field(default=3600)
    max_memory_usage: int = Field(default=8192)
    require_verification: bool = Field(default=True)
    allowed_verification_levels: list[VerificationLevel] = Field(
        default_factory=lambda: [VerificationLevel.BASIC], sa_column=Column(JSON)
    )
    max_concurrent_executions: int = Field(default=10)
    max_workflow_steps: int = Field(default=100)
    max_data_size: int = Field(default=1024 * 1024 * 1024)
    require_sandbox: bool = Field(default=False)
    require_audit_logging: bool = Field(default=True)
    require_encryption: bool = Field(default=False)
    compliance_standards: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AgentTrustScore(SQLModel, table=True):
    """Trust and reputation scoring for agents and users"""

    __tablename__ = "agent_trust_scores"
    id: str = Field(default_factory=lambda: f"trust_{uuid4().hex[:8]}", primary_key=True)
    entity_type: str = Field(index=True)
    entity_id: str = Field(index=True)
    trust_score: float = Field(default=0.0, index=True)
    reputation_score: float = Field(default=0.0)
    total_executions: int = Field(default=0)
    successful_executions: int = Field(default=0)
    failed_executions: int = Field(default=0)
    verification_success_rate: float = Field(default=0.0)
    security_violations: int = Field(default=0)
    policy_violations: int = Field(default=0)
    sandbox_breaches: int = Field(default=0)
    last_execution: datetime | None = Field(default=None)
    last_violation: datetime | None = Field(default=None)
    average_execution_time: float | None = Field(default=None)
    execution_history: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    violation_history: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AgentSandboxConfig(SQLModel, table=True):
    """Sandboxing configuration for agent execution"""

    __tablename__ = "agent_sandbox_configs"
    id: str = Field(default_factory=lambda: f"sandbox_{uuid4().hex[:8]}", primary_key=True)
    sandbox_type: str = Field(default="process")
    security_level: SecurityLevel = Field(default=SecurityLevel.PUBLIC)
    cpu_limit: float = Field(default=1.0)
    memory_limit: int = Field(default=1024)
    disk_limit: int = Field(default=10240)
    network_access: bool = Field(default=False)
    allowed_commands: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    blocked_commands: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    allowed_file_paths: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    blocked_file_paths: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    allowed_domains: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    blocked_domains: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    allowed_ports: list[int] = Field(default_factory=list, sa_column=Column(JSON))
    max_execution_time: int = Field(default=3600)
    idle_timeout: int = Field(default=300)
    enable_monitoring: bool = Field(default=True)
    log_all_commands: bool = Field(default=False)
    log_file_access: bool = Field(default=True)
    log_network_access: bool = Field(default=True)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AgentAuditor:
    """Comprehensive auditing system for agent operations"""

    def __init__(self, session: Session):
        self.session = session
        self.security_policies: dict[str, Any] = {}
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
        risk_score = self._calculate_risk_score(event_type, event_data or {}, security_level)
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
            cryptographic_hash=self._generate_event_hash(event_data or {}),
            signature_valid=self._verify_signature(event_data or {}),
        )
        self.session.add(audit_log)
        self.session.commit()
        self.session.refresh(audit_log)
        if audit_log.requires_investigation:
            await self._handle_high_risk_event(audit_log)
        logger.info("Audit event logged: %s for workflow %s execution %s", event_type.value, workflow_id, execution_id)
        return audit_log

    def _calculate_risk_score(
        self, event_type: AuditEventType, event_data: dict[str, Any], security_level: SecurityLevel
    ) -> int:
        """Calculate risk score for audit event"""
        base_score = 0
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
        security_multipliers = {
            SecurityLevel.PUBLIC: 1.0,
            SecurityLevel.INTERNAL: 1.2,
            SecurityLevel.CONFIDENTIAL: 1.5,
            SecurityLevel.RESTRICTED: 2.0,
        }
        base_score = int(base_score * security_multipliers[security_level])
        if event_data:
            if event_data.get("error_message"):
                base_score += 10
            if event_data.get("execution_time", 0) > 3600:
                base_score += 5
            if event_data.get("memory_usage", 0) > 8192:
                base_score += 5
        return min(base_score, 100)

    def _generate_event_hash(self, event_data: dict[str, Any]) -> str | None:
        """Generate cryptographic hash for event data"""
        if not event_data:
            return None
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
            if "signature" not in event_data or "public_key" not in event_data:
                return None
            return None
        except Exception as e:
            logger.error("Signature verification failed: %s", e)
            return False

    async def _handle_high_risk_event(self, audit_log: AgentAuditLog) -> None:
        """Handle high-risk audit events requiring investigation"""
        logger.warning("High-risk audit event detected: %s (Score: %s)", audit_log.event_type.value, audit_log.risk_score)
        investigation_notes = f"High-risk event detected on {audit_log.timestamp}. "
        investigation_notes += f"Event type: {audit_log.event_type.value}, "
        investigation_notes += f"Risk score: {audit_log.risk_score}. "
        investigation_notes += "Requires manual investigation."
        audit_log.investigation_notes = investigation_notes
        audit_log.investigation_status = "pending"
        audit_log.investigation_required = True
        self.session.commit()
        logger.critical("SECURITY ALERT: High-risk event requires investigation - Event ID: %s", audit_log.id)
        logger.info("Investigation ticket would be created for event: %s", audit_log.id)
        if audit_log.risk_score >= 0.9:
            logger.warning("Critical risk score (%s) - entity suspension recommended", audit_log.risk_score)


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
        policy_violation: bool = False,
    ) -> AgentTrustScore:
        """Update trust score based on execution results"""
        trust_score = self.session.exec(
            select(AgentTrustScore).where(
                (AgentTrustScore.entity_type == entity_type) & (AgentTrustScore.entity_id == entity_id)
            )
        ).first()
        if not trust_score:
            trust_score = AgentTrustScore(entity_type=entity_type, entity_id=entity_id)
            self.session.add(trust_score)
        trust_score.total_executions += 1
        if execution_success:
            trust_score.successful_executions += 1
        else:
            trust_score.failed_executions += 1
        if security_violation:
            trust_score.security_violations += 1
            trust_score.last_violation = datetime.now(UTC)
            trust_score.violation_history.append({"timestamp": datetime.now(UTC).isoformat(), "type": "security_violation"})
        if policy_violation:
            trust_score.policy_violations += 1
            trust_score.last_violation = datetime.now(UTC)
            trust_score.violation_history.append({"timestamp": datetime.now(UTC).isoformat(), "type": "policy_violation"})
        trust_score.trust_score = self._calculate_trust_score(trust_score)
        trust_score.reputation_score = self._calculate_reputation_score(trust_score)
        trust_score.verification_success_rate = (
            trust_score.successful_executions / trust_score.total_executions * 100 if trust_score.total_executions > 0 else 0
        )
        if execution_time:
            if trust_score.average_execution_time is None:
                trust_score.average_execution_time = execution_time
            else:
                trust_score.average_execution_time = (
                    trust_score.average_execution_time * (trust_score.total_executions - 1) + execution_time
                ) / trust_score.total_executions
        trust_score.last_execution = datetime.now(UTC)
        trust_score.updated_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(trust_score)
        return trust_score

    def _calculate_trust_score(self, trust_score: AgentTrustScore) -> float:
        """Calculate overall trust score"""
        base_score = 50.0
        if trust_score.total_executions > 0:
            success_rate = trust_score.successful_executions / trust_score.total_executions
            base_score += (success_rate - 0.5) * 40
        violation_penalty = trust_score.security_violations * 10
        base_score -= violation_penalty
        policy_penalty = trust_score.policy_violations * 5
        base_score -= policy_penalty
        if trust_score.last_execution:
            days_since_last = (datetime.now(UTC) - trust_score.last_execution).days
            if days_since_last < 7:
                base_score += 5
            elif days_since_last > 30:
                base_score -= 10
        return max(0.0, min(100.0, base_score))

    def _calculate_reputation_score(self, trust_score: AgentTrustScore) -> float:
        """Calculate reputation score based on long-term performance"""
        base_score = 50.0
        if trust_score.total_executions >= 10:
            success_rate = trust_score.successful_executions / trust_score.total_executions
            base_score += (success_rate - 0.5) * 30
        volume_bonus = min(trust_score.total_executions / 100, 10)
        base_score += volume_bonus
        if trust_score.security_violations == 0 and trust_score.policy_violations == 0:
            base_score += 10
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
        sandbox_config = self._get_sandbox_config(security_level)
        if workflow_requirements:
            sandbox_config = self._customize_sandbox(sandbox_config, workflow_requirements)
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
        logger.info("Created sandbox configuration for execution %s", execution_id)
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
        if "cpu_cores" in requirements:
            config["cpu_limit"] = max(config["cpu_limit"], requirements["cpu_cores"])
        if "memory_mb" in requirements:
            config["memory_limit"] = max(config["memory_limit"], requirements["memory_mb"])
        if "disk_mb" in requirements:
            config["disk_limit"] = max(config["disk_limit"], requirements["disk_mb"])
        if "max_execution_time" in requirements:
            config["max_execution_time"] = min(config["max_execution_time"], requirements["max_execution_time"])
        if "allowed_commands" in requirements:
            config["allowed_commands"].extend(requirements["allowed_commands"])
        if "blocked_commands" in requirements:
            config["blocked_commands"].extend(requirements["blocked_commands"])
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
        sandbox = self.session.execute(
            select(AgentSandboxConfig).where(AgentSandboxConfig.id == f"sandbox_{execution_id}")
        ).first()
        if not sandbox:
            raise ValueError(f"Sandbox not found for execution {execution_id}")
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
            "note": "Monitoring requires sandbox runtime integration",
        }
        return monitoring_data

    async def cleanup_sandbox(self, execution_id: str) -> bool:
        """Clean up sandbox environment after execution"""
        try:
            sandbox = self.session.execute(
                select(AgentSandboxConfig).where(AgentSandboxConfig.id == f"sandbox_{execution_id}")
            ).first()
            if sandbox:
                sandbox.is_active = False
                sandbox.updated_at = datetime.now(UTC)
                self.session.commit()
                logger.info("Marked sandbox as inactive for execution %s", execution_id)
                return True
            return False
        except Exception as e:
            logger.error("Failed to cleanup sandbox for execution %s: %s", execution_id, e)
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
        validation_result: dict[str, Any] = {
            "valid": True,
            "violations": [],
            "warnings": [],
            "required_security_level": SecurityLevel.PUBLIC,
            "recommendations": [],
        }
        security_sensitive_steps = []
        for step_data in workflow.steps.values():
            if step_data.get("step_type") in ["training", "data_processing"]:
                security_sensitive_steps.append(step_data.get("name"))
        if security_sensitive_steps:
            validation_result["warnings"].append(f"Security-sensitive steps detected: {security_sensitive_steps}")
            validation_result["recommendations"].append(
                "Consider using higher security level for workflows with sensitive operations"
            )
        if workflow.max_execution_time > 3600:
            validation_result["warnings"].append(
                f"Long execution time ({workflow.max_execution_time}s) may require additional security measures"
            )
        if not workflow.requires_verification:
            validation_result["violations"].append(
                "Workflow does not require verification - this is not recommended for production use"
            )
            validation_result["valid"] = False
        if workflow.requires_verification and workflow.verification_level == VerificationLevel.ZERO_KNOWLEDGE:
            validation_result["required_security_level"] = SecurityLevel.RESTRICTED
        elif workflow.requires_verification and workflow.verification_level == VerificationLevel.FULL:
            validation_result["required_security_level"] = SecurityLevel.CONFIDENTIAL
        elif workflow.requires_verification:
            validation_result["required_security_level"] = SecurityLevel.INTERNAL
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
        monitoring_result: dict[str, Any] = {
            "execution_id": execution_id,
            "workflow_id": workflow_id,
            "security_status": "monitoring",
            "violations": [],
            "alerts": [],
        }
        try:
            sandbox_monitoring = await self.sandbox_manager.monitor_sandbox(execution_id)
            if sandbox_monitoring["resource_usage"]["cpu_percent"] > 90:
                monitoring_result["violations"].append("High CPU usage detected")
                monitoring_result["alerts"].append("CPU usage exceeded 90%")
            if sandbox_monitoring["resource_usage"]["memory_mb"] > sandbox_monitoring["resource_usage"]["memory_mb"] * 0.9:
                monitoring_result["violations"].append("High memory usage detected")
                monitoring_result["alerts"].append("Memory usage exceeded 90% of limit")
            if sandbox_monitoring["security_events"]:
                monitoring_result["violations"].extend(sandbox_monitoring["security_events"])
                monitoring_result["alerts"].extend(
                    f"Security event: {event}" for event in sandbox_monitoring["security_events"]
                )
            if monitoring_result["violations"]:
                monitoring_result["security_status"] = "violations_detected"
                await self.auditor.log_event(
                    AuditEventType.SECURITY_VIOLATION,
                    execution_id=execution_id,
                    workflow_id=workflow_id,
                    security_level=SecurityLevel.INTERNAL,
                    event_data={"violations": monitoring_result["violations"]},
                    requires_investigation=len(monitoring_result["violations"]) > 0,
                )  # type: ignore
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
            )  # type: ignore
        return monitoring_result
