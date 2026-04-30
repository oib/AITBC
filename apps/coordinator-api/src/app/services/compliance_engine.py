"""
Enterprise Compliance Engine - Phase 6.2 Implementation
GDPR, CCPA, SOC 2, and regulatory compliance automation
"""

from dataclasses import dataclass, field
from datetime import datetime, UTC, timedelta
from enum import StrEnum
from typing import Any
from uuid import uuid4

from aitbc import get_logger

logger = get_logger(__name__)


class ComplianceFramework(StrEnum):
    """Compliance frameworks"""

    GDPR = "gdpr"
    CCPA = "ccpa"
    SOC2 = "soc2"
    HIPAA = "hipaa"
    PCI_DSS = "pci_dss"
    ISO27001 = "iso27001"
    AML_KYC = "aml_kyc"


class ComplianceStatus(StrEnum):
    """Compliance status"""

    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    PENDING = "pending"
    EXEMPT = "exempt"
    UNKNOWN = "unknown"


class DataCategory(StrEnum):
    """Data categories for compliance"""

    PERSONAL_DATA = "personal_data"
    SENSITIVE_DATA = "sensitive_data"
    FINANCIAL_DATA = "financial_data"
    HEALTH_DATA = "health_data"
    BIOMETRIC_DATA = "biometric_data"
    PUBLIC_DATA = "public_data"


class ConsentStatus(StrEnum):
    """Consent status"""

    GRANTED = "granted"
    DENIED = "denied"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


@dataclass
class ComplianceRule:
    """Compliance rule definition"""

    rule_id: str
    framework: ComplianceFramework
    name: str
    description: str
    data_categories: list[DataCategory]
    requirements: dict[str, Any]
    validation_logic: str
    severity: str = "medium"
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ConsentRecord:
    """User consent record"""

    consent_id: str
    user_id: str
    data_category: DataCategory
    purpose: str
    status: ConsentStatus
    granted_at: datetime | None = None
    withdrawn_at: datetime | None = None
    expires_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ComplianceAudit:
    """Compliance audit record"""

    audit_id: str
    framework: ComplianceFramework
    entity_id: str
    entity_type: str
    status: ComplianceStatus
    score: float
    findings: list[dict[str, Any]]
    recommendations: list[str]
    auditor: str
    audit_date: datetime = field(default_factory=datetime.utcnow)
    next_review_date: datetime | None = None


class GDPRCompliance:
    """GDPR compliance implementation"""

    def __init__(self):
        self.consent_records = {}
        self.data_subject_requests = {}
        self.breach_notifications = {}
        self.logger = get_logger("gdpr_compliance")

    async def check_consent_validity(self, user_id: str, data_category: DataCategory, purpose: str) -> bool:
        """Check if consent is valid for data processing"""

        try:
            # Find active consent record
            consent = self._find_active_consent(user_id, data_category, purpose)

            if not consent:
                return False

            # Check if consent is still valid
            if consent.status != ConsentStatus.GRANTED:
                return False

            # Check if consent has expired
            if consent.expires_at and datetime.now(datetime.UTC) > consent.expires_at:
                return False

            # Check if consent has been withdrawn
            if consent.status == ConsentStatus.WITHDRAWN:
                return False

            return True

        except Exception as e:
            self.logger.error(f"Consent validity check failed: {e}")
            return False

    def _find_active_consent(self, user_id: str, data_category: DataCategory, purpose: str) -> ConsentRecord | None:
        """Find active consent record"""

        user_consents = self.consent_records.get(user_id, [])

        for consent in user_consents:
            if (
                consent.data_category == data_category
                and consent.purpose == purpose
                and consent.status == ConsentStatus.GRANTED
            ):
                return consent

        return None

    async def record_consent(
        self, user_id: str, data_category: DataCategory, purpose: str, granted: bool, expires_days: int | None = None
    ) -> str:
        """Record user consent"""

        consent_id = str(uuid4())

        status = ConsentStatus.GRANTED if granted else ConsentStatus.DENIED
        granted_at = datetime.now(datetime.UTC) if granted else None
        expires_at = None

        if granted and expires_days:
            expires_at = datetime.now(datetime.UTC) + timedelta(days=expires_days)

        consent = ConsentRecord(
            consent_id=consent_id,
            user_id=user_id,
            data_category=data_category,
            purpose=purpose,
            status=status,
            granted_at=granted_at,
            expires_at=expires_at,
        )

        # Store consent record
        if user_id not in self.consent_records:
            self.consent_records[user_id] = []

        self.consent_records[user_id].append(consent)

        self.logger.info(f"Consent recorded: {user_id} - {data_category.value} - {purpose} - {status.value}")

        return consent_id

    async def withdraw_consent(self, consent_id: str) -> bool:
        """Withdraw user consent"""

        for _user_id, consents in self.consent_records.items():
            for consent in consents:
                if consent.consent_id == consent_id:
                    consent.status = ConsentStatus.WITHDRAWN
                    consent.withdrawn_at = datetime.now(datetime.UTC)

                    self.logger.info(f"Consent withdrawn: {consent_id}")
                    return True

        return False

    async def handle_data_subject_request(self, request_type: str, user_id: str, details: dict[str, Any]) -> str:
        """Handle data subject request (DSAR)"""

        request_id = str(uuid4())

        request_data = {
            "request_id": request_id,
            "request_type": request_type,
            "user_id": user_id,
            "details": details,
            "status": "pending",
            "created_at": datetime.now(datetime.UTC),
            "due_date": datetime.now(datetime.UTC) + timedelta(days=30),  # GDPR 30-day deadline
        }

        self.data_subject_requests[request_id] = request_data

        self.logger.info(f"Data subject request created: {request_id} - {request_type}")

        return request_id

    async def check_data_breach_notification(self, breach_data: dict[str, Any]) -> bool:
        """Check if data breach notification is required"""

        try:
            # Check if personal data is affected
            affected_data = breach_data.get("affected_data_categories", [])
            has_personal_data = any(
                category
                in [
                    DataCategory.PERSONAL_DATA,
                    DataCategory.SENSITIVE_DATA,
                    DataCategory.HEALTH_DATA,
                    DataCategory.BIOMETRIC_DATA,
                ]
                for category in affected_data
            )

            if not has_personal_data:
                return False

            # Check if notification threshold is met
            affected_individuals = breach_data.get("affected_individuals", 0)

            # GDPR requires notification within 72 hours if likely to affect rights/freedoms
            high_risk = breach_data.get("high_risk", False)

            return (affected_individuals > 0 and high_risk) or affected_individuals >= 500

        except Exception as e:
            self.logger.error(f"Breach notification check failed: {e}")
            return False

    async def create_breach_notification(self, breach_data: dict[str, Any]) -> str:
        """Create data breach notification"""

        notification_id = str(uuid4())

        notification = {
            "notification_id": notification_id,
            "breach_data": breach_data,
            "notification_required": await self.check_data_breach_notification(breach_data),
            "created_at": datetime.now(datetime.UTC),
            "deadline": datetime.now(datetime.UTC) + timedelta(hours=72),  # 72-hour deadline
            "status": "pending",
        }

        self.breach_notifications[notification_id] = notification

        self.logger.info(f"Breach notification created: {notification_id}")

        return notification_id


class SOC2Compliance:
    """SOC 2 Type II compliance implementation"""

    def __init__(self):
        self.security_controls = {}
        self.audit_logs = {}
        self.control_evidence = {}
        self.logger = get_logger("soc2_compliance")

    async def implement_security_control(self, control_id: str, control_config: dict[str, Any]) -> bool:
        """Implement SOC 2 security control"""

        try:
            control = {
                "control_id": control_id,
                "name": control_config["name"],
                "category": control_config["category"],
                "description": control_config["description"],
                "implementation": control_config["implementation"],
                "evidence_requirements": control_config.get("evidence_requirements", []),
                "testing_procedures": control_config.get("testing_procedures", []),
                "status": "implemented",
                "implemented_at": datetime.now(datetime.UTC),
                "last_tested": None,
                "test_results": [],
            }

            self.security_controls[control_id] = control

            self.logger.info(f"SOC 2 control implemented: {control_id}")
            return True

        except Exception as e:
            self.logger.error(f"Control implementation failed: {e}")
            return False

    async def test_control(self, control_id: str, test_data: dict[str, Any]) -> dict[str, Any]:
        """Test security control effectiveness"""

        control = self.security_controls.get(control_id)
        if not control:
            return {"error": f"Control not found: {control_id}"}

        try:
            # Execute control test based on control type
            test_result = await self._execute_control_test(control, test_data)

            # Record test result
            control["test_results"].append(
                {"test_id": str(uuid4()), "timestamp": datetime.now(datetime.UTC), "result": test_result, "tester": "automated"}
            )

            control["last_tested"] = datetime.now(datetime.UTC)

            return test_result

        except Exception as e:
            self.logger.error(f"Control test failed: {e}")
            return {"error": str(e)}

    async def _execute_control_test(self, control: dict[str, Any], test_data: dict[str, Any]) -> dict[str, Any]:
        """Execute specific control test"""

        category = control["category"]

        if category == "access_control":
            return await self._test_access_control(control, test_data)
        elif category == "encryption":
            return await self._test_encryption(control, test_data)
        elif category == "monitoring":
            return await self._test_monitoring(control, test_data)
        elif category == "incident_response":
            return await self._test_incident_response(control, test_data)
        else:
            return {"status": "skipped", "reason": f"Test not implemented for category: {category}"}

    async def _test_access_control(self, control: dict[str, Any], test_data: dict[str, Any]) -> dict[str, Any]:
        """Test access control"""

        # Simulate access control test
        test_attempts = test_data.get("test_attempts", 10)
        failed_attempts = 0

        for i in range(test_attempts):
            # Simulate access attempt
            if i < 2:  # Simulate 2 failed attempts
                failed_attempts += 1

        success_rate = (test_attempts - failed_attempts) / test_attempts

        return {
            "status": "passed" if success_rate >= 0.9 else "failed",
            "success_rate": success_rate,
            "test_attempts": test_attempts,
            "failed_attempts": failed_attempts,
            "threshold_met": success_rate >= 0.9,
        }

    async def _test_encryption(self, control: dict[str, Any], test_data: dict[str, Any]) -> dict[str, Any]:
        """Test encryption controls"""

        # Simulate encryption test
        encryption_strength = test_data.get("encryption_strength", "aes_256")
        key_rotation_days = test_data.get("key_rotation_days", 90)

        # Check if encryption meets requirements
        strong_encryption = encryption_strength in ["aes_256", "chacha20_poly1305"]
        proper_rotation = key_rotation_days <= 90

        return {
            "status": "passed" if strong_encryption and proper_rotation else "failed",
            "encryption_strength": encryption_strength,
            "key_rotation_days": key_rotation_days,
            "strong_encryption": strong_encryption,
            "proper_rotation": proper_rotation,
        }

    async def _test_monitoring(self, control: dict[str, Any], test_data: dict[str, Any]) -> dict[str, Any]:
        """Test monitoring controls"""

        # Simulate monitoring test
        alert_coverage = test_data.get("alert_coverage", 0.95)
        log_retention_days = test_data.get("log_retention_days", 90)

        # Check monitoring requirements
        adequate_coverage = alert_coverage >= 0.9
        sufficient_retention = log_retention_days >= 90

        return {
            "status": "passed" if adequate_coverage and sufficient_retention else "failed",
            "alert_coverage": alert_coverage,
            "log_retention_days": log_retention_days,
            "adequate_coverage": adequate_coverage,
            "sufficient_retention": sufficient_retention,
        }

    async def _test_incident_response(self, control: dict[str, Any], test_data: dict[str, Any]) -> dict[str, Any]:
        """Test incident response controls"""

        # Simulate incident response test
        response_time_hours = test_data.get("response_time_hours", 4)
        has_procedure = test_data.get("has_procedure", True)

        # Check response requirements
        timely_response = response_time_hours <= 24  # SOC 2 requires timely response
        procedure_exists = has_procedure

        return {
            "status": "passed" if timely_response and procedure_exists else "failed",
            "response_time_hours": response_time_hours,
            "has_procedure": has_procedure,
            "timely_response": timely_response,
            "procedure_exists": procedure_exists,
        }

    async def generate_compliance_report(self) -> dict[str, Any]:
        """Generate SOC 2 compliance report"""

        total_controls = len(self.security_controls)
        tested_controls = len([c for c in self.security_controls.values() if c["last_tested"]])
        passed_controls = 0

        for control in self.security_controls.values():
            if control["test_results"]:
                latest_test = control["test_results"][-1]
                if latest_test["result"].get("status") == "passed":
                    passed_controls += 1

        compliance_score = (passed_controls / total_controls) if total_controls > 0 else 0.0

        return {
            "framework": "SOC 2 Type II",
            "total_controls": total_controls,
            "tested_controls": tested_controls,
            "passed_controls": passed_controls,
            "compliance_score": compliance_score,
            "compliance_status": "compliant" if compliance_score >= 0.9 else "non_compliant",
            "report_date": datetime.now(datetime.UTC).isoformat(),
            "controls": self.security_controls,
        }


class AMLKYCCompliance:
    """AML/KYC compliance implementation"""

    def __init__(self):
        self.customer_records = {}
        self.transaction_monitoring = {}
        self.suspicious_activity_reports = {}
        self.logger = get_logger("aml_kyc_compliance")

    async def perform_kyc_check(self, customer_id: str, customer_data: dict[str, Any]) -> dict[str, Any]:
        """Perform KYC check on customer"""

        try:
            kyc_score = 0.0
            risk_factors = []

            # Check identity verification
            identity_verified = await self._verify_identity(customer_data)
            if identity_verified:
                kyc_score += 0.4
            else:
                risk_factors.append("identity_not_verified")

            # Check address verification
            address_verified = await self._verify_address(customer_data)
            if address_verified:
                kyc_score += 0.3
            else:
                risk_factors.append("address_not_verified")

            # Check document verification
            documents_verified = await self._verify_documents(customer_data)
            if documents_verified:
                kyc_score += 0.3
            else:
                risk_factors.append("documents_not_verified")

            # Determine risk level
            if kyc_score >= 0.8:
                risk_level = "low"
                status = "approved"
            elif kyc_score >= 0.6:
                risk_level = "medium"
                status = "approved_with_conditions"
            else:
                risk_level = "high"
                status = "rejected"

            kyc_result = {
                "customer_id": customer_id,
                "kyc_score": kyc_score,
                "risk_level": risk_level,
                "status": status,
                "risk_factors": risk_factors,
                "checked_at": datetime.now(datetime.UTC),
                "next_review": datetime.now(datetime.UTC) + timedelta(days=365),
            }

            self.customer_records[customer_id] = kyc_result

            self.logger.info(f"KYC check completed: {customer_id} - {risk_level} - {status}")

            return kyc_result

        except Exception as e:
            self.logger.error(f"KYC check failed: {e}")
            return {"error": str(e)}

    async def _verify_identity(self, customer_data: dict[str, Any]) -> bool:
        """Verify customer identity"""

        # Simulate identity verification
        required_fields = ["first_name", "last_name", "date_of_birth", "national_id"]

        for field in required_fields:
            if field not in customer_data or not customer_data[field]:
                return False

        # Simulate verification check
        return True

    async def _verify_address(self, customer_data: dict[str, Any]) -> bool:
        """Verify customer address"""

        # Check address fields
        address_fields = ["street", "city", "country", "postal_code"]

        for field in address_fields:
            if field not in customer_data.get("address", {}):
                return False

        # Simulate address verification
        return True

    async def _verify_documents(self, customer_data: dict[str, Any]) -> bool:
        """Verify customer documents"""

        documents = customer_data.get("documents", [])

        # Check for required documents
        required_docs = ["id_document", "proof_of_address"]

        for doc_type in required_docs:
            if not any(doc.get("type") == doc_type for doc in documents):
                return False

        # Simulate document verification
        return True

    async def monitor_transaction(self, transaction_data: dict[str, Any]) -> dict[str, Any]:
        """Monitor transaction for suspicious activity"""

        try:
            transaction_id = transaction_data.get("transaction_id")
            customer_id = transaction_data.get("customer_id")
            transaction_data.get("amount", 0)
            transaction_data.get("currency")

            # Get customer risk profile
            customer_record = self.customer_records.get(customer_id, {})
            risk_level = customer_record.get("risk_level", "medium")

            # Calculate transaction risk score
            risk_score = await self._calculate_transaction_risk(transaction_data, risk_level)

            # Check if transaction is suspicious
            suspicious = risk_score >= 0.7

            result = {
                "transaction_id": transaction_id,
                "customer_id": customer_id,
                "risk_score": risk_score,
                "suspicious": suspicious,
                "monitored_at": datetime.now(datetime.UTC),
            }

            if suspicious:
                # Create suspicious activity report
                await self._create_sar(transaction_data, risk_score, risk_level)
                result["sar_created"] = True

            # Store monitoring record
            if customer_id not in self.transaction_monitoring:
                self.transaction_monitoring[customer_id] = []

            self.transaction_monitoring[customer_id].append(result)

            return result

        except Exception as e:
            self.logger.error(f"Transaction monitoring failed: {e}")
            return {"error": str(e)}

    async def _calculate_transaction_risk(self, transaction_data: dict[str, Any], customer_risk_level: str) -> float:
        """Calculate transaction risk score"""

        risk_score = 0.0
        amount = transaction_data.get("amount", 0)

        # Amount-based risk
        if amount > 10000:
            risk_score += 0.3
        elif amount > 5000:
            risk_score += 0.2
        elif amount > 1000:
            risk_score += 0.1

        # Customer risk level
        risk_multipliers = {"low": 0.5, "medium": 1.0, "high": 1.5}

        risk_score *= risk_multipliers.get(customer_risk_level, 1.0)

        # Additional risk factors
        if transaction_data.get("cross_border", False):
            risk_score += 0.2

        if transaction_data.get("high_frequency", False):
            risk_score += 0.1

        return min(risk_score, 1.0)

    async def _create_sar(self, transaction_data: dict[str, Any], risk_score: float, customer_risk_level: str):
        """Create Suspicious Activity Report (SAR)"""

        sar_id = str(uuid4())

        sar = {
            "sar_id": sar_id,
            "transaction_id": transaction_data.get("transaction_id"),
            "customer_id": transaction_data.get("customer_id"),
            "risk_score": risk_score,
            "customer_risk_level": customer_risk_level,
            "transaction_details": transaction_data,
            "created_at": datetime.now(datetime.UTC),
            "status": "pending_review",
            "reported_to_authorities": False,
        }

        self.suspicious_activity_reports[sar_id] = sar

        self.logger.warning(f"SAR created: {sar_id} - risk_score: {risk_score}")

    async def generate_aml_report(self) -> dict[str, Any]:
        """Generate AML compliance report"""

        total_customers = len(self.customer_records)
        high_risk_customers = len([c for c in self.customer_records.values() if c.get("risk_level") == "high"])

        total_transactions = sum(len(transactions) for transactions in self.transaction_monitoring.values())

        suspicious_transactions = sum(
            len([t for t in transactions if t.get("suspicious", False)])
            for transactions in self.transaction_monitoring.values()
        )

        pending_sars = len([sar for sar in self.suspicious_activity_reports.values() if sar.get("status") == "pending_review"])

        return {
            "framework": "AML/KYC",
            "total_customers": total_customers,
            "high_risk_customers": high_risk_customers,
            "total_transactions": total_transactions,
            "suspicious_transactions": suspicious_transactions,
            "pending_sars": pending_sars,
            "suspicious_rate": (suspicious_transactions / total_transactions) if total_transactions > 0 else 0,
            "report_date": datetime.now(datetime.UTC).isoformat(),
        }


class EnterpriseComplianceEngine:
    """Main enterprise compliance engine"""

    def __init__(self):
        self.gdpr = GDPRCompliance()
        self.soc2 = SOC2Compliance()
        self.aml_kyc = AMLKYCCompliance()
        self.compliance_rules = {}
        self.audit_records = {}
        self.logger = get_logger("compliance_engine")

    async def initialize(self) -> bool:
        """Initialize compliance engine"""

        try:
            # Load default compliance rules
            await self._load_default_rules()

            # Implement default SOC 2 controls
            await self._implement_default_soc2_controls()

            self.logger.info("Enterprise compliance engine initialized")
            return True

        except Exception as e:
            self.logger.error(f"Compliance engine initialization failed: {e}")
            return False

    async def _load_default_rules(self):
        """Load default compliance rules"""

        default_rules = [
            ComplianceRule(
                rule_id="gdpr_consent_001",
                framework=ComplianceFramework.GDPR,
                name="Valid Consent Required",
                description="Valid consent must be obtained before processing personal data",
                data_categories=[DataCategory.PERSONAL_DATA, DataCategory.SENSITIVE_DATA],
                requirements={"consent_required": True, "consent_documented": True, "withdrawal_allowed": True},
                validation_logic="check_consent_validity",
            ),
            ComplianceRule(
                rule_id="soc2_access_001",
                framework=ComplianceFramework.SOC2,
                name="Access Control",
                description="Logical access controls must be implemented",
                data_categories=[DataCategory.SENSITIVE_DATA, DataCategory.FINANCIAL_DATA],
                requirements={"authentication_required": True, "authorization_required": True, "access_logged": True},
                validation_logic="check_access_control",
            ),
            ComplianceRule(
                rule_id="aml_kyc_001",
                framework=ComplianceFramework.AML_KYC,
                name="Customer Due Diligence",
                description="KYC checks must be performed on all customers",
                data_categories=[DataCategory.PERSONAL_DATA, DataCategory.FINANCIAL_DATA],
                requirements={"identity_verification": True, "address_verification": True, "risk_assessment": True},
                validation_logic="check_kyc_compliance",
            ),
        ]

        for rule in default_rules:
            self.compliance_rules[rule.rule_id] = rule

    async def _implement_default_soc2_controls(self):
        """Implement default SOC 2 controls"""

        default_controls = [
            {
                "name": "Logical Access Control",
                "category": "access_control",
                "description": "Logical access controls safeguard information",
                "implementation": "Role-based access control with MFA",
                "evidence_requirements": ["access_logs", "mfa_logs"],
                "testing_procedures": ["access_review", "penetration_testing"],
            },
            {
                "name": "Encryption",
                "category": "encryption",
                "description": "Encryption of sensitive information",
                "implementation": "AES-256 encryption for data at rest and in transit",
                "evidence_requirements": ["encryption_keys", "encryption_policies"],
                "testing_procedures": ["encryption_verification", "key_rotation_test"],
            },
            {
                "name": "Security Monitoring",
                "category": "monitoring",
                "description": "Security monitoring and incident detection",
                "implementation": "24/7 security monitoring with SIEM",
                "evidence_requirements": ["monitoring_logs", "alert_logs"],
                "testing_procedures": ["monitoring_test", "alert_verification"],
            },
        ]

        for i, control_config in enumerate(default_controls):
            await self.soc2.implement_security_control(f"control_{i+1}", control_config)

    async def check_compliance(self, framework: ComplianceFramework, entity_data: dict[str, Any]) -> dict[str, Any]:
        """Check compliance against specific framework"""

        try:
            if framework == ComplianceFramework.GDPR:
                return await self._check_gdpr_compliance(entity_data)
            elif framework == ComplianceFramework.SOC2:
                return await self._check_soc2_compliance(entity_data)
            elif framework == ComplianceFramework.AML_KYC:
                return await self._check_aml_kyc_compliance(entity_data)
            else:
                return {"error": f"Unsupported framework: {framework}"}

        except Exception as e:
            self.logger.error(f"Compliance check failed: {e}")
            return {"error": str(e)}

    async def _check_gdpr_compliance(self, entity_data: dict[str, Any]) -> dict[str, Any]:
        """Check GDPR compliance"""

        user_id = entity_data.get("user_id")
        data_category = DataCategory(entity_data.get("data_category", "personal_data"))
        purpose = entity_data.get("purpose", "data_processing")

        # Check consent
        consent_valid = await self.gdpr.check_consent_validity(user_id, data_category, purpose)

        # Check data retention
        retention_compliant = await self._check_data_retention(entity_data)

        # Check data protection
        protection_compliant = await self._check_data_protection(entity_data)

        overall_compliant = consent_valid and retention_compliant and protection_compliant

        return {
            "framework": "GDPR",
            "compliant": overall_compliant,
            "consent_valid": consent_valid,
            "retention_compliant": retention_compliant,
            "protection_compliant": protection_compliant,
            "checked_at": datetime.now(datetime.UTC).isoformat(),
        }

    async def _check_soc2_compliance(self, entity_data: dict[str, Any]) -> dict[str, Any]:
        """Check SOC 2 compliance"""

        # Generate SOC 2 report
        soc2_report = await self.soc2.generate_compliance_report()

        return {
            "framework": "SOC 2 Type II",
            "compliant": soc2_report["compliance_status"] == "compliant",
            "compliance_score": soc2_report["compliance_score"],
            "total_controls": soc2_report["total_controls"],
            "passed_controls": soc2_report["passed_controls"],
            "report": soc2_report,
        }

    async def _check_aml_kyc_compliance(self, entity_data: dict[str, Any]) -> dict[str, Any]:
        """Check AML/KYC compliance"""

        # Generate AML report
        aml_report = await self.aml_kyc.generate_aml_report()

        # Check if suspicious rate is acceptable (<1%)
        suspicious_rate_acceptable = aml_report["suspicious_rate"] < 0.01

        return {
            "framework": "AML/KYC",
            "compliant": suspicious_rate_acceptable,
            "suspicious_rate": aml_report["suspicious_rate"],
            "pending_sars": aml_report["pending_sars"],
            "report": aml_report,
        }

    async def _check_data_retention(self, entity_data: dict[str, Any]) -> bool:
        """Check data retention compliance"""

        # Simulate retention check
        created_at = entity_data.get("created_at")
        if created_at:
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at)

            # Check if data is older than retention period
            retention_days = entity_data.get("retention_days", 2555)  # 7 years default
            expiry_date = created_at + timedelta(days=retention_days)

            return datetime.now(datetime.UTC) <= expiry_date

        return True

    async def _check_data_protection(self, entity_data: dict[str, Any]) -> bool:
        """Check data protection measures"""

        # Simulate protection check
        encryption_enabled = entity_data.get("encryption_enabled", False)
        access_controls = entity_data.get("access_controls", False)

        return encryption_enabled and access_controls

    async def generate_compliance_dashboard(self) -> dict[str, Any]:
        """Generate comprehensive compliance dashboard"""

        try:
            # Get compliance reports for all frameworks
            gdpr_compliance = await self._check_gdpr_compliance({})
            soc2_compliance = await self._check_soc2_compliance({})
            aml_compliance = await self._check_aml_kyc_compliance({})

            # Calculate overall compliance score
            frameworks = [gdpr_compliance, soc2_compliance, aml_compliance]
            compliant_frameworks = sum(1 for f in frameworks if f.get("compliant", False))
            overall_score = (compliant_frameworks / len(frameworks)) * 100

            return {
                "overall_compliance_score": overall_score,
                "frameworks": {"GDPR": gdpr_compliance, "SOC 2": soc2_compliance, "AML/KYC": aml_compliance},
                "total_rules": len(self.compliance_rules),
                "last_updated": datetime.now(datetime.UTC).isoformat(),
                "status": "compliant" if overall_score >= 80 else "needs_attention",
            }

        except Exception as e:
            self.logger.error(f"Compliance dashboard generation failed: {e}")
            return {"error": str(e)}

    async def create_compliance_audit(self, framework: ComplianceFramework, entity_id: str, entity_type: str) -> str:
        """Create compliance audit"""

        audit_id = str(uuid4())

        audit = ComplianceAudit(
            audit_id=audit_id,
            framework=framework,
            entity_id=entity_id,
            entity_type=entity_type,
            status=ComplianceStatus.PENDING,
            score=0.0,
            findings=[],
            recommendations=[],
            auditor="automated",
        )

        self.audit_records[audit_id] = audit

        self.logger.info(f"Compliance audit created: {audit_id} - {framework.value}")

        return audit_id


# Global compliance engine instance
compliance_engine = None


async def get_compliance_engine() -> EnterpriseComplianceEngine:
    """Get or create global compliance engine"""

    global compliance_engine
    if compliance_engine is None:
        compliance_engine = EnterpriseComplianceEngine()
        await compliance_engine.initialize()

    return compliance_engine
