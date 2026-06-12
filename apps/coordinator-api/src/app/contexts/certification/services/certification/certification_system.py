"""
Certification System - Agent certification framework and verification system
"""
import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4
from aitbc import get_logger
logger = get_logger(__name__)
from app.domain.certification import AgentCertification, CertificationLevel, CertificationStatus, VerificationType
from app.domain.reputation import AgentReputation
from sqlmodel import Session, and_, select

class CertificationSystem:
    """Agent certification framework and verification system"""

    def __init__(self) -> None:
        self.certification_levels = {CertificationLevel.BASIC: {'requirements': ['identity_verified', 'basic_performance'], 'privileges': ['basic_trading', 'standard_support'], 'validity_days': 365, 'renewal_requirements': ['identity_reverified', 'performance_maintained']}, CertificationLevel.INTERMEDIATE: {'requirements': ['basic', 'reliability_proven', 'community_active'], 'privileges': ['enhanced_trading', 'priority_support', 'analytics_access'], 'validity_days': 365, 'renewal_requirements': ['reliability_maintained', 'community_contribution']}, CertificationLevel.ADVANCED: {'requirements': ['intermediate', 'high_performance', 'security_compliant'], 'privileges': ['premium_trading', 'dedicated_support', 'advanced_analytics'], 'validity_days': 365, 'renewal_requirements': ['performance_excellent', 'security_maintained']}, CertificationLevel.ENTERPRISE: {'requirements': ['advanced', 'enterprise_ready', 'compliance_verified'], 'privileges': ['enterprise_trading', 'white_glove_support', 'custom_analytics'], 'validity_days': 365, 'renewal_requirements': ['enterprise_standards', 'compliance_current']}, CertificationLevel.PREMIUM: {'requirements': ['enterprise', 'excellence_proven', 'innovation_leader'], 'privileges': ['premium_trading', 'vip_support', 'beta_access', 'advisory_role'], 'validity_days': 365, 'renewal_requirements': ['excellence_maintained', 'innovation_continued']}}
        self.verification_methods = {VerificationType.IDENTITY: self.verify_identity, VerificationType.PERFORMANCE: self.verify_performance, VerificationType.RELIABILITY: self.verify_reliability, VerificationType.SECURITY: self.verify_security, VerificationType.COMPLIANCE: self.verify_compliance, VerificationType.CAPABILITY: self.verify_capability}

    async def certify_agent(self, session: Session, agent_id: str, level: CertificationLevel, issued_by: str, certification_type: str='standard') -> tuple[bool, AgentCertification | None, list[str]]:
        """Certify an agent at a specific level"""
        level_config = self.certification_levels.get(level)
        if not level_config:
            return (False, None, [f'Invalid certification level: {level}'])
        requirements = level_config['requirements']
        errors = []
        verification_results = {}
        for requirement in requirements:
            try:
                result = await self.verify_requirement(session, agent_id, requirement)
                verification_results[requirement] = result
                if not result['passed']:
                    errors.append(f"Requirement '{requirement}' failed: {result.get('reason', 'Unknown reason')}")
            except Exception as e:
                logger.error('Error verifying requirement %s for agent %s: %s', requirement, agent_id, str(e))
                errors.append(f"Verification error for '{requirement}': {str(e)}")
        if errors:
            return (False, None, errors)
        certification_id = f'cert_{uuid4().hex[:8]}'
        verification_hash = self.generate_verification_hash(agent_id, level, certification_id)
        expires_at = datetime.now(UTC) + timedelta(days=level_config['validity_days'])
        certification = AgentCertification(certification_id=certification_id, agent_id=agent_id, certification_level=level, certification_type=certification_type, issued_by=issued_by, expires_at=expires_at, verification_hash=verification_hash, status=CertificationStatus.ACTIVE, requirements_met=requirements, verification_results=verification_results, granted_privileges=level_config['privileges'], access_levels=[level.value], special_capabilities=self.get_special_capabilities(level), audit_log=[{'action': 'issued', 'timestamp': datetime.now(UTC).isoformat(), 'performed_by': issued_by, 'details': f'Certification issued at {level.value} level'}])
        session.add(certification)
        session.commit()
        session.refresh(certification)
        logger.info('Agent %s certified at %s level', agent_id, level.value)
        return (True, certification, [])

    async def verify_requirement(self, session: Session, agent_id: str, requirement: str) -> dict[str, Any]:
        """Verify a specific certification requirement"""
        if requirement in ['basic', 'intermediate', 'advanced', 'enterprise']:
            return await self.verify_prerequisite_level(session, agent_id, requirement)
        verification_map = {'identity_verified': VerificationType.IDENTITY, 'basic_performance': VerificationType.PERFORMANCE, 'reliability_proven': VerificationType.RELIABILITY, 'community_active': VerificationType.CAPABILITY, 'high_performance': VerificationType.PERFORMANCE, 'security_compliant': VerificationType.SECURITY, 'enterprise_ready': VerificationType.CAPABILITY, 'compliance_verified': VerificationType.COMPLIANCE, 'excellence_proven': VerificationType.PERFORMANCE, 'innovation_leader': VerificationType.CAPABILITY}
        verification_type = verification_map.get(requirement)
        if verification_type:
            verification_method = self.verification_methods.get(verification_type)
            if verification_method:
                return await verification_method(session, agent_id)
        return {'passed': False, 'reason': f'Unknown requirement: {requirement}', 'score': 0.0, 'details': {}}

    async def verify_prerequisite_level(self, session: Session, agent_id: str, prerequisite_level: str) -> dict[str, Any]:
        """Verify prerequisite certification level"""
        level_map = {'basic': CertificationLevel.BASIC, 'intermediate': CertificationLevel.INTERMEDIATE, 'advanced': CertificationLevel.ADVANCED, 'enterprise': CertificationLevel.ENTERPRISE}
        target_level = level_map.get(prerequisite_level)
        if not target_level:
            return {'passed': False, 'reason': f'Invalid prerequisite level: {prerequisite_level}', 'score': 0.0, 'details': {}}
        certification = session.execute(select(AgentCertification).where(and_(AgentCertification.agent_id == agent_id, AgentCertification.certification_level == target_level, AgentCertification.status == CertificationStatus.ACTIVE, AgentCertification.expires_at > datetime.now(UTC)))).first()
        if certification:
            return {'passed': True, 'reason': f'Prerequisite {prerequisite_level} certification found and active', 'score': 100.0, 'details': {'certification_id': certification.certification_id, 'issued_at': certification.issued_at.isoformat(), 'expires_at': certification.expires_at.isoformat()}}
        else:
            return {'passed': False, 'reason': f'Prerequisite {prerequisite_level} certification not found or expired', 'score': 0.0, 'details': {}}

    async def verify_identity(self, session: Session, agent_id: str) -> dict[str, Any]:
        """Verify agent identity"""
        reputation = session.execute(select(AgentReputation).where(AgentReputation.agent_id == agent_id)).first()
        if reputation:
            return {'passed': True, 'reason': 'Identity verified through reputation system', 'score': 100.0, 'details': {'verification_date': reputation.created_at.isoformat(), 'verification_method': 'reputation_system', 'trust_score': reputation.trust_score}}
        else:
            return {'passed': False, 'reason': 'No identity verification record found', 'score': 0.0, 'details': {}}

    async def verify_performance(self, session: Session, agent_id: str) -> dict[str, Any]:
        """Verify agent performance metrics"""
        reputation = session.execute(select(AgentReputation).where(AgentReputation.agent_id == agent_id)).first()
        if not reputation:
            return {'passed': False, 'reason': 'No performance data available', 'score': 0.0, 'details': {}}
        performance_score = reputation.trust_score
        success_rate = reputation.success_rate
        total_earnings = reputation.total_earnings
        jobs_completed = reputation.jobs_completed
        basic_passed = performance_score >= 400 and success_rate >= 80.0 and (jobs_completed >= 10)
        high_passed = performance_score >= 700 and success_rate >= 90.0 and (jobs_completed >= 50)
        excellence_passed = performance_score >= 850 and success_rate >= 95.0 and (jobs_completed >= 100)
        if excellence_passed:
            return {'passed': True, 'reason': 'Excellent performance metrics', 'score': 95.0, 'details': {'trust_score': performance_score, 'success_rate': success_rate, 'total_earnings': total_earnings, 'jobs_completed': jobs_completed, 'performance_level': 'excellence'}}
        elif high_passed:
            return {'passed': True, 'reason': 'High performance metrics', 'score': 85.0, 'details': {'trust_score': performance_score, 'success_rate': success_rate, 'total_earnings': total_earnings, 'jobs_completed': jobs_completed, 'performance_level': 'high'}}
        elif basic_passed:
            return {'passed': True, 'reason': 'Basic performance requirements met', 'score': 75.0, 'details': {'trust_score': performance_score, 'success_rate': success_rate, 'total_earnings': total_earnings, 'jobs_completed': jobs_completed, 'performance_level': 'basic'}}
        else:
            return {'passed': False, 'reason': 'Performance below minimum requirements', 'score': performance_score / 10.0, 'details': {'trust_score': performance_score, 'success_rate': success_rate, 'total_earnings': total_earnings, 'jobs_completed': jobs_completed, 'performance_level': 'insufficient'}}

    async def verify_reliability(self, session: Session, agent_id: str) -> dict[str, Any]:
        """Verify agent reliability and consistency"""
        reputation = session.execute(select(AgentReputation).where(AgentReputation.agent_id == agent_id)).first()
        if not reputation:
            return {'passed': False, 'reason': 'No reliability data available', 'score': 0.0, 'details': {}}
        reliability_score = reputation.reliability_score
        average_response_time = reputation.average_response_time
        dispute_count = reputation.dispute_count
        total_transactions = reputation.transaction_count
        if total_transactions > 0:
            dispute_rate = dispute_count / total_transactions
        else:
            dispute_rate = 0.0
        reliability_passed = reliability_score >= 80.0 and dispute_rate <= 0.05 and (average_response_time <= 3000.0)
        if reliability_passed:
            return {'passed': True, 'reason': 'Reliability standards met', 'score': reliability_score, 'details': {'reliability_score': reliability_score, 'dispute_rate': dispute_rate, 'average_response_time': average_response_time, 'total_transactions': total_transactions}}
        else:
            return {'passed': False, 'reason': 'Reliability standards not met', 'score': reliability_score, 'details': {'reliability_score': reliability_score, 'dispute_rate': dispute_rate, 'average_response_time': average_response_time, 'total_transactions': total_transactions}}

    async def verify_security(self, session: Session, agent_id: str) -> dict[str, Any]:
        """Verify agent security compliance"""
        reputation = session.execute(select(AgentReputation).where(AgentReputation.agent_id == agent_id)).first()
        if not reputation:
            return {'passed': False, 'reason': 'No security data available', 'score': 0.0, 'details': {}}
        trust_score = reputation.trust_score
        dispute_count = reputation.dispute_count
        security_passed = trust_score >= 600 and dispute_count <= 2
        if security_passed:
            return {'passed': True, 'reason': 'Security compliance verified', 'score': min(100.0, trust_score / 10.0), 'details': {'trust_score': trust_score, 'dispute_count': dispute_count, 'security_level': 'compliant'}}
        else:
            return {'passed': False, 'reason': 'Security compliance not met', 'score': min(100.0, trust_score / 10.0), 'details': {'trust_score': trust_score, 'dispute_count': dispute_count, 'security_level': 'non_compliant'}}

    async def verify_compliance(self, session: Session, agent_id: str) -> dict[str, Any]:
        """Verify agent compliance with regulations"""
        certifications = session.execute(select(AgentCertification).where(and_(AgentCertification.agent_id == agent_id, AgentCertification.status == CertificationStatus.ACTIVE))).all()
        if certifications:
            return {'passed': True, 'reason': 'Compliance verified through existing certifications', 'score': 90.0, 'details': {'active_certifications': len(certifications), 'highest_level': max((cert.certification_level.value for cert in certifications)), 'compliance_status': 'compliant'}}
        else:
            return {'passed': False, 'reason': 'No compliance verification found', 'score': 0.0, 'details': {'active_certifications': 0, 'compliance_status': 'non_compliant'}}

    async def verify_capability(self, session: Session, agent_id: str) -> dict[str, Any]:
        """Verify agent capabilities and specializations"""
        reputation = session.execute(select(AgentReputation).where(AgentReputation.agent_id == agent_id)).first()
        if not reputation:
            return {'passed': False, 'reason': 'No capability data available', 'score': 0.0, 'details': {}}
        trust_score = reputation.trust_score
        specialization_tags = reputation.specialization_tags or []
        certifications = reputation.certifications or []
        capability_score = 0.0
        capability_score += min(50.0, trust_score / 20.0)
        capability_score += min(30.0, len(specialization_tags) * 10.0)
        capability_score += min(20.0, len(certifications) * 5.0)
        capability_passed = capability_score >= 60.0
        if capability_passed:
            return {'passed': True, 'reason': 'Capability requirements met', 'score': capability_score, 'details': {'trust_score': trust_score, 'specializations': specialization_tags, 'certifications': certifications, 'capability_areas': len(specialization_tags)}}
        else:
            return {'passed': False, 'reason': 'Capability requirements not met', 'score': capability_score, 'details': {'trust_score': trust_score, 'specializations': specialization_tags, 'certifications': certifications, 'capability_areas': len(specialization_tags)}}

    def generate_verification_hash(self, agent_id: str, level: CertificationLevel, certification_id: str) -> str:
        """Generate blockchain verification hash for certification"""
        verification_data = {'agent_id': agent_id, 'level': level.value, 'certification_id': certification_id, 'timestamp': datetime.now(UTC).isoformat(), 'nonce': uuid4().hex}
        data_string = json.dumps(verification_data, sort_keys=True)
        hash_object = hashlib.sha256(data_string.encode())
        return hash_object.hexdigest()

    def get_special_capabilities(self, level: CertificationLevel) -> list[str]:
        """Get special capabilities for certification level"""
        capabilities_map = {CertificationLevel.BASIC: ['standard_trading', 'basic_analytics'], CertificationLevel.INTERMEDIATE: ['enhanced_trading', 'priority_support', 'advanced_analytics'], CertificationLevel.ADVANCED: ['premium_trading', 'dedicated_support', 'custom_analytics'], CertificationLevel.ENTERPRISE: ['enterprise_trading', 'white_glove_support', 'beta_access'], CertificationLevel.PREMIUM: ['vip_trading', 'advisory_role', 'innovation_access']}
        return capabilities_map.get(level, [])

    async def renew_certification(self, session: Session, certification_id: str, renewed_by: str) -> tuple[bool, str | None]:
        """Renew an existing certification"""
        certification = session.execute(select(AgentCertification).where(AgentCertification.certification_id == certification_id)).first()
        if not certification:
            return (False, 'Certification not found')
        if certification.status != CertificationStatus.ACTIVE:
            return (False, 'Cannot renew inactive certification')
        level_config = self.certification_levels.get(certification.certification_level)
        if not level_config:
            return (False, 'Invalid certification level')
        renewal_requirements = level_config['renewal_requirements']
        errors = []
        for requirement in renewal_requirements:
            result = await self.verify_requirement(session, certification.agent_id, requirement)
            if not result['passed']:
                errors.append(f"Renewal requirement '{requirement}' failed: {result.get('reason', 'Unknown reason')}")
        if errors:
            return (False, f"Renewal requirements not met: {'; '.join(errors)}")
        certification.expires_at = datetime.now(UTC) + timedelta(days=level_config['validity_days'])
        certification.renewal_count += 1
        certification.last_renewed_at = datetime.now(UTC)
        certification.verification_hash = self.generate_verification_hash(certification.agent_id, certification.certification_level, certification.certification_id)
        certification.audit_log.append({'action': 'renewed', 'timestamp': datetime.now(UTC).isoformat(), 'performed_by': renewed_by, 'details': f"Certification renewed for {level_config['validity_days']} days"})
        session.commit()
        logger.info('Certification %s renewed for agent %s', certification_id, certification.agent_id)
        return (True, 'Certification renewed successfully')