#!/usr/bin/env python3
"""
Regulatory Reporting System
Automated generation of regulatory reports and compliance filings
"""

import asyncio
import csv
import io
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ReportType(StrEnum):
    """Types of regulatory reports"""

    SAR = "sar"  # Suspicious Activity Report
    CTR = "ctr"  # Currency Transaction Report
    AML_REPORT = "aml_report"
    COMPLIANCE_SUMMARY = "compliance_summary"
    TRADING_ACTIVITY = "trading_activity"
    VOLUME_REPORT = "volume_report"
    INCIDENT_REPORT = "incident_report"


class RegulatoryBody(StrEnum):
    """Regulatory bodies"""

    FINCEN = "fincen"
    SEC = "sec"
    FINRA = "finra"
    CFTC = "cftc"
    OFAC = "ofac"
    EU_REGULATOR = "eu_regulator"


class ReportStatus(StrEnum):
    """Report status"""

    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class RegulatoryReport:
    """Regulatory report data structure"""

    report_id: str
    report_type: ReportType
    regulatory_body: RegulatoryBody
    status: ReportStatus
    generated_at: datetime
    submitted_at: datetime | None = None
    accepted_at: datetime | None = None
    expires_at: datetime | None = None
    content: dict[str, Any] = field(default_factory=dict)
    attachments: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SuspiciousActivity:
    """Suspicious activity data for SAR reports"""

    activity_id: str
    timestamp: datetime
    user_id: str
    activity_type: str
    description: str
    amount: float
    currency: str
    risk_score: float
    indicators: list[str]
    evidence: dict[str, Any]


class RegulatoryReporter:
    """Main regulatory reporting system"""

    def __init__(self):
        self.reports: list[RegulatoryReport] = []
        self.templates = self._load_report_templates()
        self.submission_endpoints = {
            RegulatoryBody.FINCEN: "https://bsaenfiling.fincen.treas.gov",
            RegulatoryBody.SEC: "https://edgar.sec.gov",
            RegulatoryBody.FINRA: "https://reporting.finra.org",
            RegulatoryBody.CFTC: "https://report.cftc.gov",
            RegulatoryBody.OFAC: "https://ofac.treasury.gov",
            RegulatoryBody.EU_REGULATOR: "https://eu-regulatory-reporting.eu",
        }

    def _load_report_templates(self) -> dict[str, dict[str, Any]]:
        """Load report templates"""
        return {
            "sar": {
                "required_fields": [
                    "filing_institution",
                    "reporting_date",
                    "suspicious_activity_date",
                    "suspicious_activity_type",
                    "amount_involved",
                    "currency",
                    "subject_information",
                    "suspicion_reason",
                    "supporting_evidence",
                ],
                "format": "json",
                "schema": "fincen_sar_v2",
            },
            "ctr": {
                "required_fields": [
                    "filing_institution",
                    "transaction_date",
                    "transaction_amount",
                    "currency",
                    "transaction_type",
                    "subject_information",
                    "location",
                ],
                "format": "json",
                "schema": "fincen_ctr_v1",
            },
            "aml_report": {
                "required_fields": [
                    "reporting_period",
                    "total_transactions",
                    "suspicious_transactions",
                    "high_risk_customers",
                    "compliance_metrics",
                    "risk_assessment",
                ],
                "format": "json",
                "schema": "internal_aml_v1",
            },
            "compliance_summary": {
                "required_fields": [
                    "reporting_period",
                    "kyc_compliance",
                    "aml_compliance",
                    "surveillance_metrics",
                    "audit_results",
                    "risk_indicators",
                    "recommendations",
                ],
                "format": "json",
                "schema": "internal_compliance_v1",
            },
        }

    async def generate_sar_report(self, activities: list[SuspiciousActivity]) -> RegulatoryReport:
        """Generate Suspicious Activity Report"""
        try:
            report_id = f"sar_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # Aggregate suspicious activities
            total_amount = sum(activity.amount for activity in activities)
            unique_users = list({activity.user_id for activity in activities})

            # Categorize suspicious activities
            activity_types = {}
            for activity in activities:
                if activity.activity_type not in activity_types:
                    activity_types[activity.activity_type] = []
                activity_types[activity.activity_type].append(activity)

            # Generate SAR content
            sar_content = {
                "filing_institution": "AITBC Exchange",
                "reporting_date": datetime.now().isoformat(),
                "suspicious_activity_date": min(activity.timestamp for activity in activities).isoformat(),
                "suspicious_activity_type": list(activity_types.keys()),
                "amount_involved": total_amount,
                "currency": activities[0].currency if activities else "USD",
                "number_of_suspicious_activities": len(activities),
                "unique_subjects": len(unique_users),
                "subject_information": [
                    {
                        "user_id": user_id,
                        "activities": [a for a in activities if a.user_id == user_id],
                        "total_amount": sum(a.amount for a in activities if a.user_id == user_id),
                        "risk_score": max(a.risk_score for a in activities if a.user_id == user_id),
                    }
                    for user_id in unique_users
                ],
                "suspicion_reason": self._generate_suspicion_reason(activity_types),
                "supporting_evidence": {
                    "transaction_patterns": self._analyze_transaction_patterns(activities),
                    "timing_analysis": self._analyze_timing_patterns(activities),
                    "risk_indicators": self._extract_risk_indicators(activities),
                },
                "regulatory_references": {
                    "bank_secrecy_act": "31 USC 5311",
                    "patriot_act": "31 USC 5318",
                    "aml_regulations": "31 CFR 1030",
                },
            }

            report = RegulatoryReport(
                report_id=report_id,
                report_type=ReportType.SAR,
                regulatory_body=RegulatoryBody.FINCEN,
                status=ReportStatus.DRAFT,
                generated_at=datetime.now(),
                expires_at=datetime.now() + timedelta(days=30),
                content=sar_content,
                metadata={
                    "total_activities": len(activities),
                    "total_amount": total_amount,
                    "unique_subjects": len(unique_users),
                    "generation_time": datetime.now().isoformat(),
                },
            )

            self.reports.append(report)
            logger.info(f"✅ SAR report generated: {report_id}")
            return report

        except Exception as e:
            logger.error(f"❌ SAR report generation failed: {e}")
            raise

    async def generate_ctr_report(self, transactions: list[dict[str, Any]]) -> RegulatoryReport:
        """Generate Currency Transaction Report"""
        try:
            report_id = f"ctr_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # Filter transactions over $10,000 (CTR threshold)
            threshold_transactions = [tx for tx in transactions if tx.get("amount", 0) >= 10000]

            if not threshold_transactions:
                logger.info("ℹ️  No transactions over $10,000 threshold for CTR")
                return None

            total_amount = sum(tx["amount"] for tx in threshold_transactions)
            unique_customers = list({tx.get("customer_id") for tx in threshold_transactions})

            ctr_content = {
                "filing_institution": "AITBC Exchange",
                "reporting_period": {
                    "start_date": min(tx["timestamp"] for tx in threshold_transactions).isoformat(),
                    "end_date": max(tx["timestamp"] for tx in threshold_transactions).isoformat(),
                },
                "total_transactions": len(threshold_transactions),
                "total_amount": total_amount,
                "currency": "USD",
                "transaction_types": list({tx.get("transaction_type") for tx in threshold_transactions}),
                "subject_information": [
                    {
                        "customer_id": customer_id,
                        "transaction_count": len(
                            [tx for tx in threshold_transactions if tx.get("customer_id") == customer_id]
                        ),
                        "total_amount": sum(
                            tx["amount"] for tx in threshold_transactions if tx.get("customer_id") == customer_id
                        ),
                        "average_transaction": sum(
                            tx["amount"] for tx in threshold_transactions if tx.get("customer_id") == customer_id
                        )
                        / len([tx for tx in threshold_transactions if tx.get("customer_id") == customer_id]),
                    }
                    for customer_id in unique_customers
                ],
                "location_data": self._aggregate_location_data(threshold_transactions),
                "compliance_notes": {
                    "threshold_met": True,
                    "threshold_amount": 10000,
                    "reporting_requirement": "31 CFR 1030.311",
                },
            }

            report = RegulatoryReport(
                report_id=report_id,
                report_type=ReportType.CTR,
                regulatory_body=RegulatoryBody.FINCEN,
                status=ReportStatus.DRAFT,
                generated_at=datetime.now(),
                expires_at=datetime.now() + timedelta(days=15),
                content=ctr_content,
                metadata={
                    "threshold_transactions": len(threshold_transactions),
                    "total_amount": total_amount,
                    "unique_customers": len(unique_customers),
                },
            )

            self.reports.append(report)
            logger.info(f"✅ CTR report generated: {report_id}")
            return report

        except Exception as e:
            logger.error(f"❌ CTR report generation failed: {e}")
            raise

    async def generate_aml_report(self, period_start: datetime, period_end: datetime) -> RegulatoryReport:
        """Generate AML compliance report"""
        try:
            report_id = f"aml_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # Mock AML data - in production would fetch from database
            aml_data = await self._get_aml_data(period_start, period_end)

            aml_content = {
                "reporting_period": {
                    "start_date": period_start.isoformat(),
                    "end_date": period_end.isoformat(),
                    "duration_days": (period_end - period_start).days,
                },
                "transaction_monitoring": {
                    "total_transactions": aml_data["total_transactions"],
                    "monitored_transactions": aml_data["monitored_transactions"],
                    "flagged_transactions": aml_data["flagged_transactions"],
                    "false_positives": aml_data["false_positives"],
                },
                "customer_risk_assessment": {
                    "total_customers": aml_data["total_customers"],
                    "high_risk_customers": aml_data["high_risk_customers"],
                    "medium_risk_customers": aml_data["medium_risk_customers"],
                    "low_risk_customers": aml_data["low_risk_customers"],
                    "new_customer_onboarding": aml_data["new_customers"],
                },
                "suspicious_activity_reporting": {
                    "sars_filed": aml_data["sars_filed"],
                    "pending_investigations": aml_data["pending_investigations"],
                    "closed_investigations": aml_data["closed_investigations"],
                    "law_enforcement_requests": aml_data["law_enforcement_requests"],
                },
                "compliance_metrics": {
                    "kyc_completion_rate": aml_data["kyc_completion_rate"],
                    "transaction_monitoring_coverage": aml_data["monitoring_coverage"],
                    "alert_response_time": aml_data["avg_response_time"],
                    "investigation_resolution_rate": aml_data["resolution_rate"],
                },
                "risk_indicators": {
                    "high_volume_transactions": aml_data["high_volume_tx"],
                    "cross_border_transactions": aml_data["cross_border_tx"],
                    "new_customer_large_transactions": aml_data["new_customer_large_tx"],
                    "unusual_patterns": aml_data["unusual_patterns"],
                },
                "recommendations": self._generate_aml_recommendations(aml_data),
            }

            report = RegulatoryReport(
                report_id=report_id,
                report_type=ReportType.AML_REPORT,
                regulatory_body=RegulatoryBody.FINCEN,
                status=ReportStatus.DRAFT,
                generated_at=datetime.now(),
                expires_at=datetime.now() + timedelta(days=90),
                content=aml_content,
                metadata={
                    "period_start": period_start.isoformat(),
                    "period_end": period_end.isoformat(),
                    "reporting_days": (period_end - period_start).days,
                },
            )

            self.reports.append(report)
            logger.info(f"✅ AML report generated: {report_id}")
            return report

        except Exception as e:
            logger.error(f"❌ AML report generation failed: {e}")
            raise

    async def generate_compliance_summary(self, period_start: datetime, period_end: datetime) -> RegulatoryReport:
        """Generate comprehensive compliance summary"""
        try:
            report_id = f"compliance_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # Aggregate compliance data
            compliance_data = await self._get_compliance_data(period_start, period_end)

            summary_content = {
                "executive_summary": {
                    "reporting_period": f"{period_start.strftime('%Y-%m-%d')} to {period_end.strftime('%Y-%m-%d')}",
                    "overall_compliance_score": compliance_data["overall_score"],
                    "critical_issues": compliance_data["critical_issues"],
                    "regulatory_filings": compliance_data["total_filings"],
                },
                "kyc_compliance": {
                    "total_customers": compliance_data["total_customers"],
                    "verified_customers": compliance_data["verified_customers"],
                    "pending_verifications": compliance_data["pending_verifications"],
                    "rejected_verifications": compliance_data["rejected_verifications"],
                    "completion_rate": compliance_data["kyc_completion_rate"],
                },
                "aml_compliance": {
                    "transaction_monitoring": compliance_data["transaction_monitoring"],
                    "suspicious_activity_reports": compliance_data["sar_filings"],
                    "currency_transaction_reports": compliance_data["ctr_filings"],
                    "risk_assessments": compliance_data["risk_assessments"],
                },
                "trading_surveillance": {
                    "active_monitoring": compliance_data["surveillance_active"],
                    "alerts_generated": compliance_data["total_alerts"],
                    "alerts_resolved": compliance_data["resolved_alerts"],
                    "false_positive_rate": compliance_data["false_positive_rate"],
                },
                "regulatory_filings": {
                    "sars_filed": compliance_data.get("sar_filings", 0),
                    "ctrs_filed": compliance_data.get("ctr_filings", 0),
                    "other_filings": compliance_data.get("other_filings", 0),
                    "submission_success_rate": compliance_data["submission_success_rate"],
                },
                "audit_trail": {
                    "internal_audits": compliance_data["internal_audits"],
                    "external_audits": compliance_data["external_audits"],
                    "findings": compliance_data["audit_findings"],
                    "remediation_status": compliance_data["remediation_status"],
                },
                "risk_assessment": {
                    "high_risk_areas": compliance_data["high_risk_areas"],
                    "mitigation_strategies": compliance_data["mitigation_strategies"],
                    "risk_trends": compliance_data["risk_trends"],
                },
                "recommendations": compliance_data["recommendations"],
                "next_steps": compliance_data["next_steps"],
            }

            report = RegulatoryReport(
                report_id=report_id,
                report_type=ReportType.COMPLIANCE_SUMMARY,
                regulatory_body=RegulatoryBody.SEC,  # Multi-regulatory summary
                status=ReportStatus.DRAFT,
                generated_at=datetime.now(),
                expires_at=datetime.now() + timedelta(days=30),
                content=summary_content,
                metadata={
                    "period_start": period_start.isoformat(),
                    "period_end": period_end.isoformat(),
                    "overall_score": compliance_data["overall_score"],
                },
            )

            self.reports.append(report)
            logger.info(f"✅ Compliance summary generated: {report_id}")
            return report

        except Exception as e:
            logger.error(f"❌ Compliance summary generation failed: {e}")
            raise

    async def submit_report(self, report_id: str) -> bool:
        """Submit report to regulatory body"""
        try:
            report = self._find_report(report_id)
            if not report:
                logger.error(f"❌ Report {report_id} not found")
                return False

            if report.status != ReportStatus.DRAFT:
                logger.warning(f"⚠️  Report {report_id} already submitted")
                return False

            # Mock submission - in production would call real API
            await asyncio.sleep(2)  # Simulate network call

            report.status = ReportStatus.SUBMITTED
            report.submitted_at = datetime.now()

            logger.info(f"✅ Report {report_id} submitted to {report.regulatory_body.value}")
            return True

        except Exception as e:
            logger.error(f"❌ Report submission failed: {e}")
            return False

    def export_report(self, report_id: str, format_type: str = "json") -> str:
        """Export report in specified format"""
        try:
            report = self._find_report(report_id)
            if not report:
                raise ValueError(f"Report {report_id} not found")

            if format_type == "json":
                return json.dumps(report.content, indent=2, default=str)
            elif format_type == "csv":
                return self._export_to_csv(report)
            elif format_type == "xml":
                return self._export_to_xml(report)
            else:
                raise ValueError(f"Unsupported format: {format_type}")

        except Exception as e:
            logger.error(f"❌ Report export failed: {e}")
            raise

    def get_report_status(self, report_id: str) -> dict[str, Any] | None:
        """Get report status"""
        report = self._find_report(report_id)
        if not report:
            return None

        return {
            "report_id": report.report_id,
            "report_type": report.report_type.value,
            "regulatory_body": report.regulatory_body.value,
            "status": report.status.value,
            "generated_at": report.generated_at.isoformat(),
            "submitted_at": report.submitted_at.isoformat() if report.submitted_at else None,
            "expires_at": report.expires_at.isoformat() if report.expires_at else None,
        }

    def list_reports(
        self, report_type: ReportType | None = None, status: ReportStatus | None = None
    ) -> list[dict[str, Any]]:
        """List reports with optional filters"""
        filtered_reports = self.reports

        if report_type:
            filtered_reports = [r for r in filtered_reports if r.report_type == report_type]

        if status:
            filtered_reports = [r for r in filtered_reports if r.status == status]

        return [
            {
                "report_id": r.report_id,
                "report_type": r.report_type.value,
                "regulatory_body": r.regulatory_body.value,
                "status": r.status.value,
                "generated_at": r.generated_at.isoformat(),
            }
            for r in sorted(filtered_reports, key=lambda x: x.generated_at, reverse=True)
        ]

    # Helper methods
    def _find_report(self, report_id: str) -> RegulatoryReport | None:
        """Find report by ID"""
        for report in self.reports:
            if report.report_id == report_id:
                return report
        return None

    def _generate_suspicion_reason(self, activity_types: dict[str, list]) -> str:
        """Generate consolidated suspicion reason"""
        reasons = []

        type_mapping = {
            "unusual_volume": "Unusually high trading volume detected",
            "rapid_price_movement": "Rapid price movements inconsistent with market trends",
            "concentrated_trading": "Trading concentrated among few participants",
            "timing_anomaly": "Suspicious timing patterns in trading activity",
            "cross_market_arbitrage": "Unusual cross-market trading patterns",
        }

        for activity_type, _activities in activity_types.items():
            if activity_type in type_mapping:
                reasons.append(type_mapping[activity_type])

        return "; ".join(reasons) if reasons else "Suspicious trading activity detected"

    def _analyze_transaction_patterns(self, activities: list[SuspiciousActivity]) -> dict[str, Any]:
        """Analyze transaction patterns"""
        return {
            "frequency_analysis": len(activities),
            "amount_distribution": {
                "min": min(a.amount for a in activities),
                "max": max(a.amount for a in activities),
                "avg": sum(a.amount for a in activities) / len(activities),
            },
            "temporal_patterns": "Irregular timing patterns detected",
        }

    def _analyze_timing_patterns(self, activities: list[SuspiciousActivity]) -> dict[str, Any]:
        """Analyze timing patterns"""
        timestamps = [a.timestamp for a in activities]
        time_span = (max(timestamps) - min(timestamps)).total_seconds()

        # Avoid division by zero
        activity_density = len(activities) / (time_span / 3600) if time_span > 0 else 0

        return {
            "time_span": time_span,
            "activity_density": activity_density,
            "peak_hours": "Off-hours activity detected" if activity_density > 10 else "Normal activity pattern",
        }

    def _extract_risk_indicators(self, activities: list[SuspiciousActivity]) -> list[str]:
        """Extract risk indicators"""
        indicators = set()
        for activity in activities:
            indicators.update(activity.indicators)
        return list(indicators)

    def _aggregate_location_data(self, transactions: list[dict[str, Any]]) -> dict[str, Any]:
        """Aggregate location data for CTR"""
        locations = {}
        for tx in transactions:
            location = tx.get("location", "Unknown")
            if location not in locations:
                locations[location] = {"count": 0, "amount": 0}
            locations[location]["count"] += 1
            locations[location]["amount"] += tx.get("amount", 0)

        return locations

    async def _get_aml_data(self, start: datetime, end: datetime) -> dict[str, Any]:
        """Get AML data for reporting period"""
        # Mock data - in production would fetch from database
        return {
            "total_transactions": 150000,
            "monitored_transactions": 145000,
            "flagged_transactions": 1250,
            "false_positives": 320,
            "total_customers": 25000,
            "high_risk_customers": 150,
            "medium_risk_customers": 1250,
            "low_risk_customers": 23600,
            "new_customers": 850,
            "sars_filed": 45,
            "pending_investigations": 12,
            "closed_investigations": 33,
            "law_enforcement_requests": 8,
            "kyc_completion_rate": 0.96,
            "monitoring_coverage": 0.98,
            "avg_response_time": 2.5,  # hours
            "resolution_rate": 0.87,
        }

    async def _get_compliance_data(self, start: datetime, end: datetime) -> dict[str, Any]:
        """Get compliance data for summary"""
        return {
            "overall_score": 0.92,
            "critical_issues": 2,
            "total_filings": 67,
            "total_customers": 25000,
            "verified_customers": 24000,
            "pending_verifications": 800,
            "rejected_verifications": 200,
            "kyc_completion_rate": 0.96,
            "transaction_monitoring": True,
            "sar_filings": 45,
            "ctr_filings": 22,
            "risk_assessments": 156,
            "surveillance_active": True,
            "total_alerts": 156,
            "resolved_alerts": 134,
            "false_positive_rate": 0.14,
            "submission_success_rate": 0.98,
            "internal_audits": 4,
            "external_audits": 2,
            "audit_findings": 8,
            "remediation_status": "In Progress",
            "high_risk_areas": ["Cross-border transactions", "High-value customers"],
            "mitigation_strategies": ["Enhanced monitoring", "Additional verification"],
            "risk_trends": "Stable",
            "recommendations": ["Increase monitoring frequency", "Enhance customer due diligence"],
            "next_steps": ["Implement enhanced monitoring", "Schedule external audit"],
        }

    def _generate_aml_recommendations(self, aml_data: dict[str, Any]) -> list[str]:
        """Generate AML recommendations"""
        recommendations = []

        if aml_data["false_positives"] / aml_data["flagged_transactions"] > 0.3:
            recommendations.append("Review and refine transaction monitoring rules to reduce false positives")

        if aml_data["high_risk_customers"] / aml_data["total_customers"] > 0.01:
            recommendations.append("Implement enhanced due diligence for high-risk customers")

        if aml_data["avg_response_time"] > 4:
            recommendations.append("Improve alert response time to meet regulatory requirements")

        return recommendations

    def _export_to_csv(self, report: RegulatoryReport) -> str:
        """Export report to CSV format"""
        output = io.StringIO()

        if report.report_type == ReportType.SAR:
            writer = csv.writer(output)
            writer.writerow(["Field", "Value"])

            for key, value in report.content.items():
                if isinstance(value, (str, int, float)):
                    writer.writerow([key, value])
                elif isinstance(value, list):
                    writer.writerow([key, f"List with {len(value)} items"])
                elif isinstance(value, dict):
                    writer.writerow([key, f"Object with {len(value)} fields"])

        return output.getvalue()

    def _export_to_xml(self, report: RegulatoryReport) -> str:
        """Export report to XML format"""
        # Simple XML export - in production would use proper XML library
        xml_lines = ['<?xml version="1.0" encoding="UTF-8"?>']
        xml_lines.append(f'<report type="{report.report_type.value}" id="{report.report_id}">')

        def dict_to_xml(data, indent=1):
            indent_str = "  " * indent
            for key, value in data.items():
                if isinstance(value, (str, int, float)):
                    xml_lines.append(f"{indent_str}<{key}>{value}</{key}>")
                elif isinstance(value, dict):
                    xml_lines.append(f"{indent_str}<{key}>")
                    dict_to_xml(value, indent + 1)
                    xml_lines.append(f"{indent_str}</{key}>")

        dict_to_xml(report.content)
        xml_lines.append("</report>")

        return "\n".join(xml_lines)


# Global instance
regulatory_reporter = RegulatoryReporter()


# CLI Interface Functions
async def generate_sar(activities: list[dict[str, Any]]) -> dict[str, Any]:
    """Generate SAR report"""
    suspicious_activities = [
        SuspiciousActivity(
            activity_id=activity["id"],
            timestamp=datetime.fromisoformat(activity["timestamp"]),
            user_id=activity["user_id"],
            activity_type=activity["type"],
            description=activity["description"],
            amount=activity["amount"],
            currency=activity["currency"],
            risk_score=activity["risk_score"],
            indicators=activity["indicators"],
            evidence=activity.get("evidence", {}),
        )
        for activity in activities
    ]

    report = await regulatory_reporter.generate_sar_report(suspicious_activities)

    return {
        "report_id": report.report_id,
        "report_type": report.report_type.value,
        "status": report.status.value,
        "generated_at": report.generated_at.isoformat(),
    }


async def generate_compliance_summary(period_start: str, period_end: str) -> dict[str, Any]:
    """Generate compliance summary"""
    start_date = datetime.fromisoformat(period_start)
    end_date = datetime.fromisoformat(period_end)

    report = await regulatory_reporter.generate_compliance_summary(start_date, end_date)

    return {
        "report_id": report.report_id,
        "report_type": report.report_type.value,
        "status": report.status.value,
        "generated_at": report.generated_at.isoformat(),
        "overall_score": report.content.get("executive_summary", {}).get("overall_compliance_score", 0),
    }


def list_reports(report_type: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
    """List regulatory reports"""
    rt = ReportType(report_type) if report_type else None
    st = ReportStatus(status) if status else None

    return regulatory_reporter.list_reports(rt, st)


# Test function
async def test_regulatory_reporting():
    """Test regulatory reporting system"""
    print("🧪 Testing Regulatory Reporting System...")

    # Test SAR generation
    activities = [
        {
            "id": "act_001",
            "timestamp": datetime.now().isoformat(),
            "user_id": "user123",
            "type": "unusual_volume",
            "description": "Unusual trading volume detected",
            "amount": 50000,
            "currency": "USD",
            "risk_score": 0.85,
            "indicators": ["volume_spike", "timing_anomaly"],
            "evidence": {},
        }
    ]

    sar_result = await generate_sar(activities)
    print(f"✅ SAR Report Generated: {sar_result['report_id']}")

    # Test compliance summary
    compliance_result = await generate_compliance_summary("2026-01-01T00:00:00", "2026-01-31T23:59:59")
    print(f"✅ Compliance Summary Generated: {compliance_result['report_id']}")

    # List reports
    reports = list_reports()
    print(f"📋 Total Reports: {len(reports)}")

    print("🎉 Regulatory reporting test complete!")


if __name__ == "__main__":
    asyncio.run(test_regulatory_reporting())
