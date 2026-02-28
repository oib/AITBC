"""
Agent Certification and Partnership Service
Implements certification framework, partnership programs, and badge system
"""

import asyncio
import hashlib
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from uuid import uuid4
from aitbc.logging import get_logger

from sqlmodel import Session, select, update, delete, and_, or_, func
from sqlalchemy.exc import SQLAlchemyError

from ..domain.certification import (
    AgentCertification, CertificationRequirement, VerificationRecord,
    PartnershipProgram, AgentPartnership, AchievementBadge, AgentBadge,
    CertificationAudit, CertificationLevel, CertificationStatus, VerificationType,
    PartnershipType, BadgeType
)
from ..domain.reputation import AgentReputation
from ..domain.rewards import AgentRewardProfile

logger = get_logger(__name__)


class CertificationSystem:
    """Agent certification framework and verification system"""
    
    def __init__(self):
        self.certification_levels = {
            CertificationLevel.BASIC: {
                'requirements': ['identity_verified', 'basic_performance'],
                'privileges': ['basic_trading', 'standard_support'],
                'validity_days': 365,
                'renewal_requirements': ['identity_reverified', 'performance_maintained']
            },
            CertificationLevel.INTERMEDIATE: {
                'requirements': ['basic', 'reliability_proven', 'community_active'],
                'privileges': ['enhanced_trading', 'priority_support', 'analytics_access'],
                'validity_days': 365,
                'renewal_requirements': ['reliability_maintained', 'community_contribution']
            },
            CertificationLevel.ADVANCED: {
                'requirements': ['intermediate', 'high_performance', 'security_compliant'],
                'privileges': ['premium_trading', 'dedicated_support', 'advanced_analytics'],
                'validity_days': 365,
                'renewal_requirements': ['performance_excellent', 'security_maintained']
            },
            CertificationLevel.ENTERPRISE: {
                'requirements': ['advanced', 'enterprise_ready', 'compliance_verified'],
                'privileges': ['enterprise_trading', 'white_glove_support', 'custom_analytics'],
                'validity_days': 365,
                'renewal_requirements': ['enterprise_standards', 'compliance_current']
            },
            CertificationLevel.PREMIUM: {
                'requirements': ['enterprise', 'excellence_proven', 'innovation_leader'],
                'privileges': ['premium_trading', 'vip_support', 'beta_access', 'advisory_role'],
                'validity_days': 365,
                'renewal_requirements': ['excellence_maintained', 'innovation_continued']
            }
        }
        
        self.verification_methods = {
            VerificationType.IDENTITY: self.verify_identity,
            VerificationType.PERFORMANCE: self.verify_performance,
            VerificationType.RELIABILITY: self.verify_reliability,
            VerificationType.SECURITY: self.verify_security,
            VerificationType.COMPLIANCE: self.verify_compliance,
            VerificationType.CAPABILITY: self.verify_capability
        }
    
    async def certify_agent(
        self, 
        session: Session,
        agent_id: str,
        level: CertificationLevel,
        issued_by: str,
        certification_type: str = "standard"
    ) -> Tuple[bool, Optional[AgentCertification], List[str]]:
        """Certify an agent at a specific level"""
        
        # Get certification requirements
        level_config = self.certification_levels.get(level)
        if not level_config:
            return False, None, [f"Invalid certification level: {level}"]
        
        requirements = level_config['requirements']
        errors = []
        
        # Verify all requirements
        verification_results = {}
        for requirement in requirements:
            try:
                result = await self.verify_requirement(session, agent_id, requirement)
                verification_results[requirement] = result
                
                if not result['passed']:
                    errors.append(f"Requirement '{requirement}' failed: {result.get('reason', 'Unknown reason')}")
            except Exception as e:
                logger.error(f"Error verifying requirement {requirement} for agent {agent_id}: {str(e)}")
                errors.append(f"Verification error for '{requirement}': {str(e)}")
        
        # Check if all requirements passed
        if errors:
            return False, None, errors
        
        # Create certification
        certification_id = f"cert_{uuid4().hex[:8]}"
        verification_hash = self.generate_verification_hash(agent_id, level, certification_id)
        
        expires_at = datetime.utcnow() + timedelta(days=level_config['validity_days'])
        
        certification = AgentCertification(
            certification_id=certification_id,
            agent_id=agent_id,
            certification_level=level,
            certification_type=certification_type,
            issued_by=issued_by,
            expires_at=expires_at,
            verification_hash=verification_hash,
            status=CertificationStatus.ACTIVE,
            requirements_met=requirements,
            verification_results=verification_results,
            granted_privileges=level_config['privileges'],
            access_levels=[level.value],
            special_capabilities=self.get_special_capabilities(level),
            audit_log=[{
                'action': 'issued',
                'timestamp': datetime.utcnow().isoformat(),
                'performed_by': issued_by,
                'details': f"Certification issued at {level.value} level"
            }]
        )
        
        session.add(certification)
        session.commit()
        session.refresh(certification)
        
        logger.info(f"Agent {agent_id} certified at {level.value} level")
        return True, certification, []
    
    async def verify_requirement(
        self, 
        session: Session,
        agent_id: str,
        requirement: str
    ) -> Dict[str, Any]:
        """Verify a specific certification requirement"""
        
        # Handle prerequisite requirements
        if requirement in ['basic', 'intermediate', 'advanced', 'enterprise']:
            return await self.verify_prerequisite_level(session, agent_id, requirement)
        
        # Handle specific verification types
        verification_map = {
            'identity_verified': VerificationType.IDENTITY,
            'basic_performance': VerificationType.PERFORMANCE,
            'reliability_proven': VerificationType.RELIABILITY,
            'community_active': VerificationType.CAPABILITY,
            'high_performance': VerificationType.PERFORMANCE,
            'security_compliant': VerificationType.SECURITY,
            'enterprise_ready': VerificationType.CAPABILITY,
            'compliance_verified': VerificationType.COMPLIANCE,
            'excellence_proven': VerificationType.PERFORMANCE,
            'innovation_leader': VerificationType.CAPABILITY
        }
        
        verification_type = verification_map.get(requirement)
        if verification_type:
            verification_method = self.verification_methods.get(verification_type)
            if verification_method:
                return await verification_method(session, agent_id)
        
        return {
            'passed': False,
            'reason': f"Unknown requirement: {requirement}",
            'score': 0.0,
            'details': {}
        }
    
    async def verify_prerequisite_level(
        self, 
        session: Session,
        agent_id: str,
        prerequisite_level: str
    ) -> Dict[str, Any]:
        """Verify prerequisite certification level"""
        
        # Map prerequisite to certification level
        level_map = {
            'basic': CertificationLevel.BASIC,
            'intermediate': CertificationLevel.INTERMEDIATE,
            'advanced': CertificationLevel.ADVANCED,
            'enterprise': CertificationLevel.ENTERPRISE
        }
        
        target_level = level_map.get(prerequisite_level)
        if not target_level:
            return {
                'passed': False,
                'reason': f"Invalid prerequisite level: {prerequisite_level}",
                'score': 0.0,
                'details': {}
            }
        
        # Check if agent has the prerequisite certification
        certification = session.exec(
            select(AgentCertification).where(
                and_(
                    AgentCertification.agent_id == agent_id,
                    AgentCertification.certification_level == target_level,
                    AgentCertification.status == CertificationStatus.ACTIVE,
                    AgentCertification.expires_at > datetime.utcnow()
                )
            )
        ).first()
        
        if certification:
            return {
                'passed': True,
                'reason': f"Prerequisite {prerequisite_level} certification found and active",
                'score': 100.0,
                'details': {
                    'certification_id': certification.certification_id,
                    'issued_at': certification.issued_at.isoformat(),
                    'expires_at': certification.expires_at.isoformat()
                }
            }
        else:
            return {
                'passed': False,
                'reason': f"Prerequisite {prerequisite_level} certification not found or expired",
                'score': 0.0,
                'details': {}
            }
    
    async def verify_identity(self, session: Session, agent_id: str) -> Dict[str, Any]:
        """Verify agent identity"""
        
        # Mock identity verification - in real system would check KYC/AML
        # For now, assume all agents have basic identity verification
        
        # Check if agent has any reputation record (indicates identity verification)
        reputation = session.exec(
            select(AgentReputation).where(AgentReputation.agent_id == agent_id)
        ).first()
        
        if reputation:
            return {
                'passed': True,
                'reason': "Identity verified through reputation system",
                'score': 100.0,
                'details': {
                    'verification_date': reputation.created_at.isoformat(),
                    'verification_method': 'reputation_system',
                    'trust_score': reputation.trust_score
                }
            }
        else:
            return {
                'passed': False,
                'reason': "No identity verification record found",
                'score': 0.0,
                'details': {}
            }
    
    async def verify_performance(self, session: Session, agent_id: str) -> Dict[str, Any]:
        """Verify agent performance metrics"""
        
        # Get agent reputation for performance metrics
        reputation = session.exec(
            select(AgentReputation).where(AgentReputation.agent_id == agent_id)
        ).first()
        
        if not reputation:
            return {
                'passed': False,
                'reason': "No performance data available",
                'score': 0.0,
                'details': {}
            }
        
        # Performance criteria
        performance_score = reputation.trust_score
        success_rate = reputation.success_rate
        total_earnings = reputation.total_earnings
        jobs_completed = reputation.jobs_completed
        
        # Basic performance requirements
        basic_passed = (
            performance_score >= 400 and  # Minimum trust score
            success_rate >= 80.0 and     # Minimum success rate
            jobs_completed >= 10         # Minimum job experience
        )
        
        # High performance requirements
        high_passed = (
            performance_score >= 700 and  # High trust score
            success_rate >= 90.0 and     # High success rate
            jobs_completed >= 50         # Significant experience
        )
        
        # Excellence requirements
        excellence_passed = (
            performance_score >= 850 and  # Excellent trust score
            success_rate >= 95.0 and     # Excellent success rate
            jobs_completed >= 100         # Extensive experience
        )
        
        if excellence_passed:
            return {
                'passed': True,
                'reason': "Excellent performance metrics",
                'score': 95.0,
                'details': {
                    'trust_score': performance_score,
                    'success_rate': success_rate,
                    'total_earnings': total_earnings,
                    'jobs_completed': jobs_completed,
                    'performance_level': 'excellence'
                }
            }
        elif high_passed:
            return {
                'passed': True,
                'reason': "High performance metrics",
                'score': 85.0,
                'details': {
                    'trust_score': performance_score,
                    'success_rate': success_rate,
                    'total_earnings': total_earnings,
                    'jobs_completed': jobs_completed,
                    'performance_level': 'high'
                }
            }
        elif basic_passed:
            return {
                'passed': True,
                'reason': "Basic performance requirements met",
                'score': 75.0,
                'details': {
                    'trust_score': performance_score,
                    'success_rate': success_rate,
                    'total_earnings': total_earnings,
                    'jobs_completed': jobs_completed,
                    'performance_level': 'basic'
                }
            }
        else:
            return {
                'passed': False,
                'reason': "Performance below minimum requirements",
                'score': performance_score / 10.0,  # Convert to 0-100 scale
                'details': {
                    'trust_score': performance_score,
                    'success_rate': success_rate,
                    'total_earnings': total_earnings,
                    'jobs_completed': jobs_completed,
                    'performance_level': 'insufficient'
                }
            }
    
    async def verify_reliability(self, session: Session, agent_id: str) -> Dict[str, Any]:
        """Verify agent reliability and consistency"""
        
        reputation = session.exec(
            select(AgentReputation).where(AgentReputation.agent_id == agent_id)
        ).first()
        
        if not reputation:
            return {
                'passed': False,
                'reason': "No reliability data available",
                'score': 0.0,
                'details': {}
            }
        
        # Reliability metrics
        reliability_score = reputation.reliability_score
        average_response_time = reputation.average_response_time
        dispute_count = reputation.dispute_count
        total_transactions = reputation.transaction_count
        
        # Calculate reliability score
        if total_transactions > 0:
            dispute_rate = dispute_count / total_transactions
        else:
            dispute_rate = 0.0
        
        # Reliability requirements
        reliability_passed = (
            reliability_score >= 80.0 and      # High reliability score
            dispute_rate <= 0.05 and         # Low dispute rate (5% or less)
            average_response_time <= 3000.0  # Fast response time (3 seconds or less)
        )
        
        if reliability_passed:
            return {
                'passed': True,
                'reason': "Reliability standards met",
                'score': reliability_score,
                'details': {
                    'reliability_score': reliability_score,
                    'dispute_rate': dispute_rate,
                    'average_response_time': average_response_time,
                    'total_transactions': total_transactions
                }
            }
        else:
            return {
                'passed': False,
                'reason': "Reliability standards not met",
                'score': reliability_score,
                'details': {
                    'reliability_score': reliability_score,
                    'dispute_rate': dispute_rate,
                    'average_response_time': average_response_time,
                    'total_transactions': total_transactions
                }
            }
    
    async def verify_security(self, session: Session, agent_id: str) -> Dict[str, Any]:
        """Verify agent security compliance"""
        
        # Mock security verification - in real system would check security audits
        # For now, assume agents with high trust scores have basic security
        
        reputation = session.exec(
            select(AgentReputation).where(AgentReputation.agent_id == agent_id)
        ).first()
        
        if not reputation:
            return {
                'passed': False,
                'reason': "No security data available",
                'score': 0.0,
                'details': {}
            }
        
        # Security criteria based on trust score and dispute history
        trust_score = reputation.trust_score
        dispute_count = reputation.dispute_count
        
        # Security requirements
        security_passed = (
            trust_score >= 600 and      # High trust score
            dispute_count <= 2         # Low dispute count
        )
        
        if security_passed:
            return {
                'passed': True,
                'reason': "Security compliance verified",
                'score': min(100.0, trust_score / 10.0),
                'details': {
                    'trust_score': trust_score,
                    'dispute_count': dispute_count,
                    'security_level': 'compliant'
                }
            }
        else:
            return {
                'passed': False,
                'reason': "Security compliance not met",
                'score': min(100.0, trust_score / 10.0),
                'details': {
                    'trust_score': trust_score,
                    'dispute_count': dispute_count,
                    'security_level': 'non_compliant'
                }
            }
    
    async def verify_compliance(self, session: Session, agent_id: str) -> Dict[str, Any]:
        """Verify agent compliance with regulations"""
        
        # Mock compliance verification - in real system would check regulatory compliance
        # For now, assume agents with certifications are compliant
        
        certifications = session.exec(
            select(AgentCertification).where(
                and_(
                    AgentCertification.agent_id == agent_id,
                    AgentCertification.status == CertificationStatus.ACTIVE
                )
            )
        ).all()
        
        if certifications:
            return {
                'passed': True,
                'reason': "Compliance verified through existing certifications",
                'score': 90.0,
                'details': {
                    'active_certifications': len(certifications),
                    'highest_level': max(cert.certification_level.value for cert in certifications),
                    'compliance_status': 'compliant'
                }
            }
        else:
            return {
                'passed': False,
                'reason': "No compliance verification found",
                'score': 0.0,
                'details': {
                    'active_certifications': 0,
                    'compliance_status': 'non_compliant'
                }
            }
    
    async def verify_capability(self, session: Session, agent_id: str) -> Dict[str, Any]:
        """Verify agent capabilities and specializations"""
        
        reputation = session.exec(
            select(AgentReputation).where(AgentReputation.agent_id == agent_id)
        ).first()
        
        if not reputation:
            return {
                'passed': False,
                'reason': "No capability data available",
                'score': 0.0,
                'details': {}
            }
        
        # Capability metrics
        trust_score = reputation.trust_score
        specialization_tags = reputation.specialization_tags or []
        certifications = reputation.certifications or []
        
        # Capability assessment
        capability_score = 0.0
        
        # Base score from trust score
        capability_score += min(50.0, trust_score / 20.0)
        
        # Specialization bonus
        capability_score += min(30.0, len(specialization_tags) * 10.0)
        
        # Certification bonus
        capability_score += min(20.0, len(certifications) * 5.0)
        
        capability_passed = capability_score >= 60.0
        
        if capability_passed:
            return {
                'passed': True,
                'reason': "Capability requirements met",
                'score': capability_score,
                'details': {
                    'trust_score': trust_score,
                    'specializations': specialization_tags,
                    'certifications': certifications,
                    'capability_areas': len(specialization_tags)
                }
            }
        else:
            return {
                'passed': False,
                'reason': "Capability requirements not met",
                'score': capability_score,
                'details': {
                    'trust_score': trust_score,
                    'specializations': specialization_tags,
                    'certifications': certifications,
                    'capability_areas': len(specialization_tags)
                }
            }
    
    def generate_verification_hash(self, agent_id: str, level: CertificationLevel, certification_id: str) -> str:
        """Generate blockchain verification hash for certification"""
        
        # Create verification data
        verification_data = {
            'agent_id': agent_id,
            'level': level.value,
            'certification_id': certification_id,
            'timestamp': datetime.utcnow().isoformat(),
            'nonce': uuid4().hex
        }
        
        # Generate hash
        data_string = json.dumps(verification_data, sort_keys=True)
        hash_object = hashlib.sha256(data_string.encode())
        
        return hash_object.hexdigest()
    
    def get_special_capabilities(self, level: CertificationLevel) -> List[str]:
        """Get special capabilities for certification level"""
        
        capabilities_map = {
            CertificationLevel.BASIC: ['standard_trading', 'basic_analytics'],
            CertificationLevel.INTERMEDIATE: ['enhanced_trading', 'priority_support', 'advanced_analytics'],
            CertificationLevel.ADVANCED: ['premium_trading', 'dedicated_support', 'custom_analytics'],
            CertificationLevel.ENTERPRISE: ['enterprise_trading', 'white_glove_support', 'beta_access'],
            CertificationLevel.PREMIUM: ['vip_trading', 'advisory_role', 'innovation_access']
        }
        
        return capabilities_map.get(level, [])
    
    async def renew_certification(
        self, 
        session: Session,
        certification_id: str,
        renewed_by: str
    ) -> Tuple[bool, Optional[str]]:
        """Renew an existing certification"""
        
        certification = session.exec(
            select(AgentCertification).where(AgentCertification.certification_id == certification_id)
        ).first()
        
        if not certification:
            return False, "Certification not found"
        
        if certification.status != CertificationStatus.ACTIVE:
            return False, "Cannot renew inactive certification"
        
        # Check renewal requirements
        level_config = self.certification_levels.get(certification.certification_level)
        if not level_config:
            return False, "Invalid certification level"
        
        renewal_requirements = level_config['renewal_requirements']
        errors = []
        
        for requirement in renewal_requirements:
            result = await self.verify_requirement(session, certification.agent_id, requirement)
            if not result['passed']:
                errors.append(f"Renewal requirement '{requirement}' failed: {result.get('reason', 'Unknown reason')}")
        
        if errors:
            return False, f"Renewal requirements not met: {'; '.join(errors)}"
        
        # Update certification
        certification.expires_at = datetime.utcnow() + timedelta(days=level_config['validity_days'])
        certification.renewal_count += 1
        certification.last_renewed_at = datetime.utcnow()
        certification.verification_hash = self.generate_verification_hash(
            certification.agent_id, certification.certification_level, certification.certification_id
        )
        
        # Add to audit log
        certification.audit_log.append({
            'action': 'renewed',
            'timestamp': datetime.utcnow().isoformat(),
            'performed_by': renewed_by,
            'details': f"Certification renewed for {level_config['validity_days']} days"
        })
        
        session.commit()
        
        logger.info(f"Certification {certification_id} renewed for agent {certification.agent_id}")
        return True, "Certification renewed successfully"


class PartnershipManager:
    """Partnership program management system"""
    
    def __init__(self):
        self.partnership_types = {
            PartnershipType.TECHNOLOGY: {
                'benefits': ['api_access', 'technical_support', 'co_marketing'],
                'requirements': ['technical_capability', 'integration_ready'],
                'commission_structure': {'type': 'revenue_share', 'rate': 0.15}
            },
            PartnershipType.SERVICE: {
                'benefits': ['service_listings', 'customer_referrals', 'branding'],
                'requirements': ['service_quality', 'customer_support'],
                'commission_structure': {'type': 'referral_fee', 'rate': 0.10}
            },
            PartnershipType.RESELLER: {
                'benefits': ['reseller_pricing', 'sales_tools', 'training'],
                'requirements': ['sales_capability', 'market_presence'],
                'commission_structure': {'type': 'margin', 'rate': 0.20}
            },
            PartnershipType.INTEGRATION: {
                'benefits': ['integration_support', 'joint_development', 'co_branding'],
                'requirements': ['technical_expertise', 'development_resources'],
                'commission_structure': {'type': 'project_share', 'rate': 0.25}
            },
            PartnershipType.STRATEGIC: {
                'benefits': ['strategic_input', 'exclusive_access', 'joint_planning'],
                'requirements': ['market_leader', 'vision_alignment'],
                'commission_structure': {'type': 'equity', 'rate': 0.05}
            },
            PartnershipType.AFFILIATE: {
                'benefits': ['affiliate_links', 'marketing_materials', 'tracking'],
                'requirements': ['marketing_capability', 'audience_reach'],
                'commission_structure': {'type': 'affiliate', 'rate': 0.08}
            }
        }
    
    async def create_partnership_program(
        self, 
        session: Session,
        program_name: str,
        program_type: PartnershipType,
        description: str,
        created_by: str,
        **kwargs
    ) -> PartnershipProgram:
        """Create a new partnership program"""
        
        program_id = f"prog_{uuid4().hex[:8]}"
        
        # Get default configuration for partnership type
        type_config = self.partnership_types.get(program_type, {})
        
        program = PartnershipProgram(
            program_id=program_id,
            program_name=program_name,
            program_type=program_type,
            description=description,
            tier_levels=kwargs.get('tier_levels', ['basic', 'premium']),
            benefits_by_tier=kwargs.get('benefits_by_tier', {
                'basic': type_config.get('benefits', []),
                'premium': type_config.get('benefits', []) + ['enhanced_support']
            }),
            requirements_by_tier=kwargs.get('requirements_by_tier', {
                'basic': type_config.get('requirements', []),
                'premium': type_config.get('requirements', []) + ['advanced_criteria']
            }),
            eligibility_requirements=kwargs.get('eligibility_requirements', type_config.get('requirements', [])),
            minimum_criteria=kwargs.get('minimum_criteria', {}),
            exclusion_criteria=kwargs.get('exclusion_criteria', []),
            financial_benefits=kwargs.get('financial_benefits', type_config.get('commission_structure', {})),
            non_financial_benefits=kwargs.get('non_financial_benefits', type_config.get('benefits', [])),
            exclusive_access=kwargs.get('exclusive_access', []),
            agreement_terms=kwargs.get('agreement_terms', {}),
            commission_structure=kwargs.get('commission_structure', type_config.get('commission_structure', {})),
            performance_metrics=kwargs.get('performance_metrics', ['sales_volume', 'customer_satisfaction']),
            max_participants=kwargs.get('max_participants'),
            launched_at=datetime.utcnow() if kwargs.get('launch_immediately', False) else None
        )
        
        session.add(program)
        session.commit()
        session.refresh(program)
        
        logger.info(f"Partnership program {program_id} created: {program_name}")
        return program
    
    async def apply_for_partnership(
        self, 
        session: Session,
        agent_id: str,
        program_id: str,
        application_data: Dict[str, Any]
    ) -> Tuple[bool, Optional[AgentPartnership], List[str]]:
        """Apply for partnership program"""
        
        # Get program details
        program = session.exec(
            select(PartnershipProgram).where(PartnershipProgram.program_id == program_id)
        ).first()
        
        if not program:
            return False, None, ["Partnership program not found"]
        
        if program.status != "active":
            return False, None, ["Partnership program is not currently accepting applications"]
        
        if program.max_participants and program.current_participants >= program.max_participants:
            return False, None, ["Partnership program is full"]
        
        # Check eligibility requirements
        errors = []
        eligibility_results = {}
        
        for requirement in program.eligibility_requirements:
            result = await self.check_eligibility_requirement(session, agent_id, requirement)
            eligibility_results[requirement] = result
            
            if not result['eligible']:
                errors.append(f"Eligibility requirement '{requirement}' not met: {result.get('reason', 'Unknown reason')}")
        
        if errors:
            return False, None, errors
        
        # Create partnership record
        partnership_id = f"agent_partner_{uuid4().hex[:8]}"
        
        partnership = AgentPartnership(
            partnership_id=partnership_id,
            agent_id=agent_id,
            program_id=program_id,
            partnership_type=program.program_type,
            current_tier="basic",
            applied_at=datetime.utcnow(),
            status="pending_approval",
            partnership_metadata={
                'application_data': application_data,
                'eligibility_results': eligibility_results
            }
        )
        
        session.add(partnership)
        session.commit()
        session.refresh(partnership)
        
        # Update program participant count
        program.current_participants += 1
        session.commit()
        
        logger.info(f"Agent {agent_id} applied for partnership program {program_id}")
        return True, partnership, []
    
    async def check_eligibility_requirement(
        self, 
        session: Session,
        agent_id: str,
        requirement: str
    ) -> Dict[str, Any]:
        """Check specific eligibility requirement"""
        
        # Mock eligibility checking - in real system would have specific validation logic
        requirement_checks = {
            'technical_capability': self.check_technical_capability,
            'integration_ready': self.check_integration_readiness,
            'service_quality': self.check_service_quality,
            'customer_support': self.check_customer_support,
            'sales_capability': self.check_sales_capability,
            'market_presence': self.check_market_presence,
            'technical_expertise': self.check_technical_expertise,
            'development_resources': self.check_development_resources,
            'market_leader': self.check_market_leader,
            'vision_alignment': self.check_vision_alignment,
            'marketing_capability': self.check_marketing_capability,
            'audience_reach': self.check_audience_reach
        }
        
        check_method = requirement_checks.get(requirement)
        if check_method:
            return await check_method(session, agent_id)
        
        return {
            'eligible': False,
            'reason': f"Unknown eligibility requirement: {requirement}",
            'score': 0.0,
            'details': {}
        }
    
    async def check_technical_capability(self, session: Session, agent_id: str) -> Dict[str, Any]:
        """Check technical capability requirement"""
        
        reputation = session.exec(
            select(AgentReputation).where(AgentReputation.agent_id == agent_id)
        ).first()
        
        if not reputation:
            return {
                'eligible': False,
                'reason': "No technical capability data available",
                'score': 0.0,
                'details': {}
            }
        
        # Technical capability based on trust score and specializations
        trust_score = reputation.trust_score
        specializations = reputation.specialization_tags or []
        
        technical_score = min(100.0, trust_score / 10.0)
        technical_score += len(specializations) * 5.0
        
        eligible = technical_score >= 60.0
        
        return {
            'eligible': eligible,
            'reason': "Technical capability assessed" if eligible else "Technical capability insufficient",
            'score': technical_score,
            'details': {
                'trust_score': trust_score,
                'specializations': specializations,
                'technical_areas': len(specializations)
            }
        }
    
    async def check_integration_readiness(self, session: Session, agent_id: str) -> Dict[str, Any]:
        """Check integration readiness requirement"""
        
        # Mock integration readiness check
        # In real system would check API integration capabilities, technical infrastructure
        
        reputation = session.exec(
            select(AgentReputation).where(AgentReputation.agent_id == agent_id)
        ).first()
        
        if not reputation:
            return {
                'eligible': False,
                'reason': "No integration data available",
                'score': 0.0,
                'details': {}
            }
        
        # Integration readiness based on reliability and performance
        reliability_score = reputation.reliability_score
        success_rate = reputation.success_rate
        
        integration_score = (reliability_score + success_rate) / 2
        eligible = integration_score >= 80.0
        
        return {
            'eligible': eligible,
            'reason': "Integration ready" if eligible else "Integration not ready",
            'score': integration_score,
            'details': {
                'reliability_score': reliability_score,
                'success_rate': success_rate
            }
        }
    
    async def check_service_quality(self, session: Session, agent_id: str) -> Dict[str, Any]:
        """Check service quality requirement"""
        
        reputation = session.exec(
            select(AgentReputation).where(AgentReputation.agent_id == agent_id)
        ).first()
        
        if not reputation:
            return {
                'eligible': False,
                'reason': "No service quality data available",
                'score': 0.0,
                'details': {}
            }
        
        # Service quality based on performance rating and success rate
        performance_rating = reputation.performance_rating
        success_rate = reputation.success_rate
        
        quality_score = (performance_rating * 20) + (success_rate * 0.8)  # Scale to 0-100
        eligible = quality_score >= 75.0
        
        return {
            'eligible': eligible,
            'reason': "Service quality acceptable" if eligible else "Service quality insufficient",
            'score': quality_score,
            'details': {
                'performance_rating': performance_rating,
                'success_rate': success_rate
            }
        }
    
    async def check_customer_support(self, session: Session, agent_id: str) -> Dict[str, Any]:
        """Check customer support capability"""
        
        # Mock customer support check
        # In real system would check support response times, customer satisfaction
        
        reputation = session.exec(
            select(AgentReputation).where(AgentReputation.agent_id == agent_id)
        ).first()
        
        if not reputation:
            return {
                'eligible': False,
                'reason': "No customer support data available",
                'score': 0.0,
                'details': {}
            }
        
        # Customer support based on response time and reliability
        response_time = reputation.average_response_time
        reliability_score = reputation.reliability_score
        
        support_score = max(0, 100 - (response_time / 100)) + reliability_score / 2
        eligible = support_score >= 70.0
        
        return {
            'eligible': eligible,
            'reason': "Customer support adequate" if eligible else "Customer support inadequate",
            'score': support_score,
            'details': {
                'average_response_time': response_time,
                'reliability_score': reliability_score
            }
        }
    
    async def check_sales_capability(self, session: Session, agent_id: str) -> Dict[str, Any]:
        """Check sales capability requirement"""
        
        # Mock sales capability check
        # In real system would check sales history, customer acquisition, revenue
        
        reputation = session.exec(
            select(AgentReputation).where(AgentReputation.agent_id == agent_id)
        ).first()
        
        if not reputation:
            return {
                'eligible': False,
                'reason': "No sales capability data available",
                'score': 0.0,
                'details': {}
            }
        
        # Sales capability based on earnings and transaction volume
        total_earnings = reputation.total_earnings
        transaction_count = reputation.transaction_count
        
        sales_score = min(100.0, (total_earnings / 10) + (transaction_count / 5))
        eligible = sales_score >= 60.0
        
        return {
            'eligible': eligible,
            'reason': "Sales capability adequate" if eligible else "Sales capability insufficient",
            'score': sales_score,
            'details': {
                'total_earnings': total_earnings,
                'transaction_count': transaction_count
            }
        }
    
    async def check_market_presence(self, session: Session, agent_id: str) -> Dict[str, Any]:
        """Check market presence requirement"""
        
        # Mock market presence check
        # In real system would check market share, brand recognition, geographic reach
        
        reputation = session.exec(
            select(AgentReputation).where(AgentReputation.agent_id == agent_id)
        ).first()
        
        if not reputation:
            return {
                'eligible': False,
                'reason': "No market presence data available",
                'score': 0.0,
                'details': {}
            }
        
        # Market presence based on transaction count and geographic distribution
        transaction_count = reputation.transaction_count
        geographic_region = reputation.geographic_region
        
        presence_score = min(100.0, (transaction_count / 10) + 20)  # Base score for any activity
        eligible = presence_score >= 50.0
        
        return {
            'eligible': eligible,
            'reason': "Market presence adequate" if eligible else "Market presence insufficient",
            'score': presence_score,
            'details': {
                'transaction_count': transaction_count,
                'geographic_region': geographic_region
            }
        }
    
    async def check_technical_expertise(self, session: Session, agent_id: str) -> Dict[str, Any]:
        """Check technical expertise requirement"""
        
        # Similar to technical capability but with higher standards
        return await self.check_technical_capability(session, agent_id)
    
    async def check_development_resources(self, session: Session, agent_id: str) -> Dict[str, Any]:
        """Check development resources requirement"""
        
        # Mock development resources check
        # In real system would check team size, technical infrastructure, development capacity
        
        reputation = session.exec(
            select(AgentReputation).where(AgentReputation.agent_id == agent_id)
        ).first()
        
        if not reputation:
            return {
                'eligible': False,
                'reason': "No development resources data available",
                'score': 0.0,
                'details': {}
            }
        
        # Development resources based on trust score and specializations
        trust_score = reputation.trust_score
        specializations = reputation.specialization_tags or []
        
        dev_score = min(100.0, (trust_score / 8) + (len(specializations) * 8))
        eligible = dev_score >= 70.0
        
        return {
            'eligible': eligible,
            'reason': "Development resources adequate" if eligible else "Development resources insufficient",
            'score': dev_score,
            'details': {
                'trust_score': trust_score,
                'specializations': specializations,
                'technical_depth': len(specializations)
            }
        }
    
    async def check_market_leader(self, session: Session, agent_id: str) -> Dict[str, Any]:
        """Check market leader requirement"""
        
        # Mock market leader check
        # In real system would check market share, industry influence, thought leadership
        
        reputation = session.exec(
            select(AgentReputation).where(AgentReputation.agent_id == agent_id)
        ).first()
        
        if not reputation:
            return {
                'eligible': False,
                'reason': "No market leadership data available",
                'score': 0.0,
                'details': {}
            }
        
        # Market leader based on top performance metrics
        trust_score = reputation.trust_score
        total_earnings = reputation.total_earnings
        
        leader_score = min(100.0, (trust_score / 5) + (total_earnings / 20))
        eligible = leader_score >= 85.0
        
        return {
            'eligible': eligible,
            'reason': "Market leader status confirmed" if eligible else "Market leader status not met",
            'score': leader_score,
            'details': {
                'trust_score': trust_score,
                'total_earnings': total_earnings,
                'market_position': 'leader' if eligible else 'follower'
            }
        }
    
    async def check_vision_alignment(self, session: Session, agent_id: str) -> Dict[str, Any]:
        """Check vision alignment requirement"""
        
        # Mock vision alignment check
        # In real system would check strategic alignment, values compatibility
        
        # For now, assume all agents have basic vision alignment
        return {
            'eligible': True,
            'reason': "Vision alignment confirmed",
            'score': 80.0,
            'details': {
                'alignment_score': 80.0,
                'strategic_fit': 'good'
            }
        }
    
    async def check_marketing_capability(self, session: Session, agent_id: str) -> Dict[str, Any]:
        """Check marketing capability requirement"""
        
        # Mock marketing capability check
        # In real system would check marketing materials, brand presence, outreach capabilities
        
        reputation = session.exec(
            select(AgentReputation).where(AgentReputation.agent_id == agent_id)
        ).first()
        
        if not reputation:
            return {
                'eligible': False,
                'reason': "No marketing capability data available",
                'score': 0.0,
                'details': {}
            }
        
        # Marketing capability based on transaction volume and geographic reach
        transaction_count = reputation.transaction_count
        geographic_region = reputation.geographic_region
        
        marketing_score = min(100.0, (transaction_count / 8) + 25)
        eligible = marketing_score >= 55.0
        
        return {
            'eligible': eligible,
            'reason': "Marketing capability adequate" if eligible else "Marketing capability insufficient",
            'score': marketing_score,
            'details': {
                'transaction_count': transaction_count,
                'geographic_region': geographic_region,
                'market_reach': 'broad' if transaction_count > 50 else 'limited'
            }
        }
    
    async def check_audience_reach(self, session: Session, agent_id: str) -> Dict[str, Any]:
        """Check audience reach requirement"""
        
        # Mock audience reach check
        # In real system would check audience size, engagement metrics, reach demographics
        
        reputation = session.exec(
            select(AgentReputation).where(AgentReputation.agent_id == agent_id)
        ).first()
        
        if not reputation:
            return {
                'eligible': False,
                'reason': "No audience reach data available",
                'score': 0.0,
                'details': {}
            }
        
        # Audience reach based on transaction count and success rate
        transaction_count = reputation.transaction_count
        success_rate = reputation.success_rate
        
        reach_score = min(100.0, (transaction_count / 5) + (success_rate * 0.5))
        eligible = reach_score >= 60.0
        
        return {
            'eligible': eligible,
            'reason': "Audience reach adequate" if eligible else "Audience reach insufficient",
            'score': reach_score,
            'details': {
                'transaction_count': transaction_count,
                'success_rate': success_rate,
                'audience_size': 'large' if transaction_count > 100 else 'medium' if transaction_count > 50 else 'small'
            }
        }


class BadgeSystem:
    """Achievement and recognition badge system"""
    
    def __init__(self):
        self.badge_categories = {
            'performance': {
                'early_adopter': {'threshold': 1, 'metric': 'jobs_completed'},
                'consistent_performer': {'threshold': 50, 'metric': 'jobs_completed'},
                'top_performer': {'threshold': 100, 'metric': 'jobs_completed'},
                'excellence_achiever': {'threshold': 500, 'metric': 'jobs_completed'}
            },
            'reliability': {
                'reliable_start': {'threshold': 10, 'metric': 'successful_transactions'},
                'dependable_partner': {'threshold': 50, 'metric': 'successful_transactions'},
                'trusted_provider': {'threshold': 100, 'metric': 'successful_transactions'},
                'rock_star': {'threshold': 500, 'metric': 'successful_transactions'}
            },
            'financial': {
                'first_earning': {'threshold': 0.01, 'metric': 'total_earnings'},
                'growing_income': {'threshold': 10, 'metric': 'total_earnings'},
                'successful_earner': {'threshold': 100, 'metric': 'total_earnings'},
                'top_earner': {'threshold': 1000, 'metric': 'total_earnings'}
            },
            'community': {
                'community_starter': {'threshold': 1, 'metric': 'community_contributions'},
                'active_contributor': {'threshold': 10, 'metric': 'community_contributions'},
                'community_leader': {'threshold': 50, 'metric': 'community_contributions'},
                'community_icon': {'threshold': 100, 'metric': 'community_contributions'}
            }
        }
    
    async def create_badge(
        self, 
        session: Session,
        badge_name: str,
        badge_type: BadgeType,
        description: str,
        criteria: Dict[str, Any],
        created_by: str
    ) -> AchievementBadge:
        """Create a new achievement badge"""
        
        badge_id = f"badge_{uuid4().hex[:8]}"
        
        badge = AchievementBadge(
            badge_id=badge_id,
            badge_name=badge_name,
            badge_type=badge_type,
            description=description,
            achievement_criteria=criteria,
            required_metrics=criteria.get('required_metrics', []),
            threshold_values=criteria.get('threshold_values', {}),
            rarity=criteria.get('rarity', 'common'),
            point_value=criteria.get('point_value', 10),
            category=criteria.get('category', 'general'),
            color_scheme=criteria.get('color_scheme', {}),
            display_properties=criteria.get('display_properties', {}),
            is_limited=criteria.get('is_limited', False),
            max_awards=criteria.get('max_awards'),
            available_from=datetime.utcnow(),
            available_until=criteria.get('available_until')
        )
        
        session.add(badge)
        session.commit()
        session.refresh(badge)
        
        logger.info(f"Badge {badge_id} created: {badge_name}")
        return badge
    
    async def award_badge(
        self, 
        session: Session,
        agent_id: str,
        badge_id: str,
        awarded_by: str,
        award_reason: str = "",
        context: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, Optional[AgentBadge], str]:
        """Award a badge to an agent"""
        
        # Get badge details
        badge = session.exec(
            select(AchievementBadge).where(AchievementBadge.badge_id == badge_id)
        ).first()
        
        if not badge:
            return False, None, "Badge not found"
        
        if not badge.is_active:
            return False, None, "Badge is not active"
        
        if badge.is_limited and badge.current_awards >= badge.max_awards:
            return False, None, "Badge has reached maximum awards"
        
        # Check if agent already has this badge
        existing_badge = session.exec(
            select(AgentBadge).where(
                and_(
                    AgentBadge.agent_id == agent_id,
                    AgentBadge.badge_id == badge_id
                )
            )
        ).first()
        
        if existing_badge:
            return False, None, "Agent already has this badge"
        
        # Verify eligibility criteria
        eligibility_result = await self.verify_badge_eligibility(session, agent_id, badge)
        if not eligibility_result['eligible']:
            return False, None, f"Agent not eligible: {eligibility_result['reason']}"
        
        # Create agent badge record
        agent_badge = AgentBadge(
            agent_id=agent_id,
            badge_id=badge_id,
            awarded_by=awarded_by,
            award_reason=award_reason or f"Awarded for meeting {badge.badge_name} criteria",
            achievement_context=context or eligibility_result.get('context', {}),
            metrics_at_award=eligibility_result.get('metrics', {}),
            supporting_evidence=eligibility_result.get('evidence', [])
        )
        
        session.add(agent_badge)
        session.commit()
        session.refresh(agent_badge)
        
        # Update badge award count
        badge.current_awards += 1
        session.commit()
        
        logger.info(f"Badge {badge_id} awarded to agent {agent_id}")
        return True, agent_badge, "Badge awarded successfully"
    
    async def verify_badge_eligibility(
        self, 
        session: Session,
        agent_id: str,
        badge: AchievementBadge
    ) -> Dict[str, Any]:
        """Verify if agent is eligible for a badge"""
        
        # Get agent reputation data
        reputation = session.exec(
            select(AgentReputation).where(AgentReputation.agent_id == agent_id)
        ).first()
        
        if not reputation:
            return {
                'eligible': False,
                'reason': "No agent data available",
                'metrics': {},
                'evidence': []
            }
        
        # Check badge criteria
        criteria = badge.achievement_criteria
        required_metrics = badge.required_metrics
        threshold_values = badge.threshold_values
        
        eligibility_results = []
        metrics_data = {}
        evidence = []
        
        for metric in required_metrics:
            threshold = threshold_values.get(metric, 0)
            
            # Get metric value from reputation
            metric_value = self.get_metric_value(reputation, metric)
            metrics_data[metric] = metric_value
            
            # Check if threshold is met
            if metric_value >= threshold:
                eligibility_results.append(True)
                evidence.append({
                    'metric': metric,
                    'value': metric_value,
                    'threshold': threshold,
                    'met': True
                })
            else:
                eligibility_results.append(False)
                evidence.append({
                    'metric': metric,
                    'value': metric_value,
                    'threshold': threshold,
                    'met': False
                })
        
        # Check if all criteria are met
        all_met = all(eligibility_results)
        
        return {
            'eligible': all_met,
            'reason': "All criteria met" if all_met else "Some criteria not met",
            'metrics': metrics_data,
            'evidence': evidence,
            'context': {
                'badge_name': badge.badge_name,
                'badge_type': badge.badge_type.value,
                'verification_date': datetime.utcnow().isoformat()
            }
        }
    
    def get_metric_value(self, reputation: AgentReputation, metric: str) -> float:
        """Get metric value from reputation data"""
        
        metric_map = {
            'jobs_completed': float(reputation.jobs_completed),
            'successful_transactions': float(reputation.jobs_completed * (reputation.success_rate / 100)),
            'total_earnings': reputation.total_earnings,
            'community_contributions': float(reputation.community_contributions or 0),
            'trust_score': reputation.trust_score,
            'reliability_score': reputation.reliability_score,
            'performance_rating': reputation.performance_rating,
            'transaction_count': float(reputation.transaction_count)
        }
        
        return metric_map.get(metric, 0.0)
    
    async def check_and_award_automatic_badges(
        self, 
        session: Session,
        agent_id: str
    ) -> List[Dict[str, Any]]:
        """Check and award automatic badges for an agent"""
        
        awarded_badges = []
        
        # Get all active automatic badges
        automatic_badges = session.exec(
            select(AchievementBadge).where(
                and_(
                    AchievementBadge.is_active == True,
                    AchievementBadge.badge_type.in_([BadgeType.ACHIEVEMENT, BadgeType.MILESTONE])
                )
            )
        ).all()
        
        for badge in automatic_badges:
            # Check eligibility
            eligibility_result = await self.verify_badge_eligibility(session, agent_id, badge)
            
            if eligibility_result['eligible']:
                # Check if already awarded
                existing = session.exec(
                    select(AgentBadge).where(
                        and_(
                            AgentBadge.agent_id == agent_id,
                            AgentBadge.badge_id == badge.badge_id
                        )
                    )
                ).first()
                
                if not existing:
                    # Award the badge
                    success, agent_badge, message = await self.award_badge(
                        session, agent_id, badge.badge_id, "system", 
                        "Automatic badge award", eligibility_result.get('context')
                    )
                    
                    if success:
                        awarded_badges.append({
                            'badge_id': badge.badge_id,
                            'badge_name': badge.badge_name,
                            'badge_type': badge.badge_type.value,
                            'awarded_at': agent_badge.awarded_at.isoformat(),
                            'reason': message
                        })
        
        return awarded_badges


class CertificationAndPartnershipService:
    """Main service for certification and partnership management"""
    
    def __init__(self, session: Session):
        self.session = session
        self.certification_system = CertificationSystem()
        self.partnership_manager = PartnershipManager()
        self.badge_system = BadgeSystem()
    
    async def get_agent_certification_summary(self, agent_id: str) -> Dict[str, Any]:
        """Get comprehensive certification summary for an agent"""
        
        # Get certifications
        certifications = self.session.exec(
            select(AgentCertification).where(AgentCertification.agent_id == agent_id)
        ).all()
        
        # Get partnerships
        partnerships = self.session.exec(
            select(AgentPartnership).where(AgentPartnership.agent_id == agent_id)
        ).all()
        
        # Get badges
        badges = self.session.exec(
            select(AgentBadge).where(AgentBadge.agent_id == agent_id)
        ).all()
        
        # Get verification records
        verifications = self.session.exec(
            select(VerificationRecord).where(VerificationRecord.agent_id == agent_id)
        ).all()
        
        return {
            'agent_id': agent_id,
            'certifications': {
                'total': len(certifications),
                'active': len([c for c in certifications if c.status == CertificationStatus.ACTIVE]),
                'highest_level': max([c.certification_level.value for c in certifications]) if certifications else None,
                'details': [
                    {
                        'certification_id': c.certification_id,
                        'level': c.certification_level.value,
                        'status': c.status.value,
                        'issued_at': c.issued_at.isoformat(),
                        'expires_at': c.expires_at.isoformat() if c.expires_at else None,
                        'privileges': c.granted_privileges
                    }
                    for c in certifications
                ]
            },
            'partnerships': {
                'total': len(partnerships),
                'active': len([p for p in partnerships if p.status == 'active']),
                'programs': [p.program_id for p in partnerships],
                'details': [
                    {
                        'partnership_id': p.partnership_id,
                        'program_type': p.partnership_type.value,
                        'current_tier': p.current_tier,
                        'status': p.status,
                        'performance_score': p.performance_score,
                        'total_earnings': p.total_earnings
                    }
                    for p in partnerships
                ]
            },
            'badges': {
                'total': len(badges),
                'featured': len([b for b in badges if b.is_featured]),
                'categories': {},
                'details': [
                    {
                        'badge_id': b.badge_id,
                        'badge_name': b.badge_name,
                        'badge_type': b.badge_type.value,
                        'awarded_at': b.awarded_at.isoformat(),
                        'is_featured': b.is_featured,
                        'point_value': self.get_badge_point_value(b.badge_id)
                    }
                    for b in badges
                ]
            },
            'verifications': {
                'total': len(verifications),
                'passed': len([v for v in verifications if v.status == 'passed']),
                'failed': len([v for v in verifications if v.status == 'failed']),
                'pending': len([v for v in verifications if v.status == 'pending'])
            }
        }
    
    def get_badge_point_value(self, badge_id: str) -> int:
        """Get point value for a badge"""
        
        badge = self.session.exec(
            select(AchievementBadge).where(AchievementBadge.badge_id == badge_id)
        ).first()
        
        return badge.point_value if badge else 0
