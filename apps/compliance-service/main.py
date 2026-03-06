"""
Production Compliance Service for AITBC
Handles KYC/AML, regulatory compliance, and monitoring
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AITBC Compliance Service",
    description="Regulatory compliance and monitoring for AITBC operations",
    version="1.0.0"
)

# Data models
class KYCRequest(BaseModel):
    user_id: str
    name: str
    email: str
    document_type: str
    document_number: str
    address: Dict[str, str]

class ComplianceReport(BaseModel):
    report_type: str
    description: str
    severity: str  # low, medium, high, critical
    details: Dict[str, Any]

class TransactionMonitoring(BaseModel):
    transaction_id: str
    user_id: str
    amount: float
    currency: str
    counterparty: str
    timestamp: datetime

# In-memory storage (in production, use database)
kyc_records: Dict[str, Dict] = {}
compliance_reports: Dict[str, Dict] = {}
suspicious_transactions: Dict[str, Dict] = {}
compliance_rules: Dict[str, Dict] = {}
risk_scores: Dict[str, Dict] = {}

@app.get("/")
async def root():
    return {
        "service": "AITBC Compliance Service",
        "status": "running",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "kyc_records": len(kyc_records),
        "compliance_reports": len(compliance_reports),
        "suspicious_transactions": len(suspicious_transactions),
        "active_rules": len(compliance_rules)
    }

@app.post("/api/v1/kyc/submit")
async def submit_kyc(kyc_request: KYCRequest):
    """Submit KYC verification request"""
    if kyc_request.user_id in kyc_records:
        raise HTTPException(status_code=400, detail="KYC already submitted for this user")
    
    # Create KYC record
    kyc_record = {
        "user_id": kyc_request.user_id,
        "name": kyc_request.name,
        "email": kyc_request.email,
        "document_type": kyc_request.document_type,
        "document_number": kyc_request.document_number,
        "address": kyc_request.address,
        "status": "pending",
        "submitted_at": datetime.utcnow().isoformat(),
        "reviewed_at": None,
        "approved_at": None,
        "risk_score": "medium",
        "notes": []
    }
    
    kyc_records[kyc_request.user_id] = kyc_record
    
    # Simulate KYC verification process
    await asyncio.sleep(2)  # Simulate verification delay
    
    # Auto-approve for demo (in production, this would involve actual verification)
    kyc_record["status"] = "approved"
    kyc_record["reviewed_at"] = datetime.utcnow().isoformat()
    kyc_record["approved_at"] = datetime.utcnow().isoformat()
    kyc_record["risk_score"] = "low"
    
    logger.info(f"KYC approved for user: {kyc_request.user_id}")
    
    return {
        "user_id": kyc_request.user_id,
        "status": kyc_record["status"],
        "risk_score": kyc_record["risk_score"],
        "approved_at": kyc_record["approved_at"]
    }

@app.get("/api/v1/kyc/{user_id}")
async def get_kyc_status(user_id: str):
    """Get KYC status for a user"""
    if user_id not in kyc_records:
        raise HTTPException(status_code=404, detail="KYC record not found")
    
    return kyc_records[user_id]

@app.get("/api/v1/kyc")
async def list_kyc_records():
    """List all KYC records"""
    return {
        "kyc_records": list(kyc_records.values()),
        "total_records": len(kyc_records),
        "approved": len([r for r in kyc_records.values() if r["status"] == "approved"]),
        "pending": len([r for r in kyc_records.values() if r["status"] == "pending"]),
        "rejected": len([r for r in kyc_records.values() if r["status"] == "rejected"])
    }

@app.post("/api/v1/compliance/report")
async def create_compliance_report(report: ComplianceReport):
    """Create a compliance report"""
    report_id = f"report_{int(datetime.utcnow().timestamp())}"
    
    compliance_record = {
        "report_id": report_id,
        "report_type": report.report_type,
        "description": report.description,
        "severity": report.severity,
        "details": report.details,
        "status": "open",
        "created_at": datetime.utcnow().isoformat(),
        "assigned_to": None,
        "resolved_at": None,
        "resolution": None
    }
    
    compliance_reports[report_id] = compliance_record
    
    logger.info(f"Compliance report created: {report_id} - {report.report_type}")
    
    return {
        "report_id": report_id,
        "status": "created",
        "severity": report.severity,
        "created_at": compliance_record["created_at"]
    }

@app.get("/api/v1/compliance/reports")
async def list_compliance_reports():
    """List all compliance reports"""
    return {
        "reports": list(compliance_reports.values()),
        "total_reports": len(compliance_reports),
        "open": len([r for r in compliance_reports.values() if r["status"] == "open"]),
        "resolved": len([r for r in compliance_reports.values() if r["status"] == "resolved"])
    }

@app.post("/api/v1/monitoring/transaction")
async def monitor_transaction(transaction: TransactionMonitoring):
    """Monitor transaction for compliance"""
    transaction_id = transaction.transaction_id
    
    # Create transaction monitoring record
    monitoring_record = {
        "transaction_id": transaction_id,
        "user_id": transaction.user_id,
        "amount": transaction.amount,
        "currency": transaction.currency,
        "counterparty": transaction.counterparty,
        "timestamp": transaction.timestamp.isoformat(),
        "monitored_at": datetime.utcnow().isoformat(),
        "risk_score": calculate_transaction_risk(transaction),
        "flags": [],
        "status": "monitored"
    }
    
    suspicious_transactions[transaction_id] = monitoring_record
    
    # Check for suspicious patterns
    flags = check_suspicious_patterns(transaction)
    if flags:
        monitoring_record["flags"] = flags
        monitoring_record["status"] = "flagged"
        
        # Create compliance report for suspicious transaction
        await create_suspicious_transaction_report(transaction, flags)
    
    return {
        "transaction_id": transaction_id,
        "risk_score": monitoring_record["risk_score"],
        "flags": flags,
        "status": monitoring_record["status"]
    }

@app.get("/api/v1/monitoring/transactions")
async def list_monitored_transactions():
    """List all monitored transactions"""
    return {
        "transactions": list(suspicious_transactions.values()),
        "total_transactions": len(suspicious_transactions),
        "flagged": len([t for t in suspicious_transactions.values() if t["status"] == "flagged"]),
        "suspicious": len([t for t in suspicious_transactions.values() if t["risk_score"] == "high"])
    }

@app.post("/api/v1/rules/create")
async def create_compliance_rule(rule_data: Dict[str, Any]):
    """Create a new compliance rule"""
    rule_id = f"rule_{int(datetime.utcnow().timestamp())}"
    
    rule = {
        "rule_id": rule_id,
        "name": rule_data.get("name"),
        "description": rule_data.get("description"),
        "type": rule_data.get("type"),
        "conditions": rule_data.get("conditions", {}),
        "actions": rule_data.get("actions", []),
        "severity": rule_data.get("severity", "medium"),
        "active": True,
        "created_at": datetime.utcnow().isoformat(),
        "trigger_count": 0
    }
    
    compliance_rules[rule_id] = rule
    
    logger.info(f"Compliance rule created: {rule_id} - {rule['name']}")
    
    return {
        "rule_id": rule_id,
        "name": rule["name"],
        "status": "created",
        "active": rule["active"]
    }

@app.get("/api/v1/rules")
async def list_compliance_rules():
    """List all compliance rules"""
    return {
        "rules": list(compliance_rules.values()),
        "total_rules": len(compliance_rules),
        "active": len([r for r in compliance_rules.values() if r["active"]])
    }

@app.get("/api/v1/dashboard")
async def compliance_dashboard():
    """Get compliance dashboard data"""
    total_users = len(kyc_records)
    approved_users = len([r for r in kyc_records.values() if r["status"] == "approved"])
    pending_reviews = len([r for r in kyc_records.values() if r["status"] == "pending"])
    
    total_reports = len(compliance_reports)
    open_reports = len([r for r in compliance_reports.values() if r["status"] == "open"])
    
    total_transactions = len(suspicious_transactions)
    flagged_transactions = len([t for t in suspicious_transactions.values() if t["status"] == "flagged"])
    
    return {
        "summary": {
            "total_users": total_users,
            "approved_users": approved_users,
            "pending_reviews": pending_reviews,
            "approval_rate": (approved_users / total_users * 100) if total_users > 0 else 0,
            "total_reports": total_reports,
            "open_reports": open_reports,
            "total_transactions": total_transactions,
            "flagged_transactions": flagged_transactions,
            "flag_rate": (flagged_transactions / total_transactions * 100) if total_transactions > 0 else 0
        },
        "risk_distribution": get_risk_distribution(),
        "recent_activity": get_recent_activity(),
        "generated_at": datetime.utcnow().isoformat()
    }

# Helper functions
def calculate_transaction_risk(transaction: TransactionMonitoring) -> str:
    """Calculate risk score for a transaction"""
    risk_score = 0
    
    # Amount-based risk
    if transaction.amount > 10000:
        risk_score += 3
    elif transaction.amount > 1000:
        risk_score += 2
    elif transaction.amount > 100:
        risk_score += 1
    
    # Time-based risk (transactions outside business hours)
    hour = transaction.timestamp.hour
    if hour < 9 or hour > 17:
        risk_score += 1
    
    # Convert to risk level
    if risk_score >= 4:
        return "high"
    elif risk_score >= 2:
        return "medium"
    else:
        return "low"

def check_suspicious_patterns(transaction: TransactionMonitoring) -> List[str]:
    """Check for suspicious transaction patterns"""
    flags = []
    
    # High value transaction
    if transaction.amount > 50000:
        flags.append("high_value_transaction")
    
    # Rapid transactions (check if user has multiple transactions in short time)
    user_transactions = [t for t in suspicious_transactions.values() 
                        if t["user_id"] == transaction.user_id]
    
    recent_transactions = [t for t in user_transactions 
                         if datetime.fromisoformat(t["monitored_at"]) > 
                         datetime.utcnow() - timedelta(hours=1)]
    
    if len(recent_transactions) > 5:
        flags.append("rapid_transactions")
    
    # Unusual counterparty
    if transaction.counterparty in ["high_risk_entity_1", "high_risk_entity_2"]:
        flags.append("high_risk_counterparty")
    
    return flags

async def create_suspicious_transaction_report(transaction: TransactionMonitoring, flags: List[str]):
    """Create compliance report for suspicious transaction"""
    report_data = ComplianceReport(
        report_type="suspicious_transaction",
        description=f"Suspicious transaction detected: {transaction.transaction_id}",
        severity="high",
        details={
            "transaction_id": transaction.transaction_id,
            "user_id": transaction.user_id,
            "amount": transaction.amount,
            "flags": flags,
            "timestamp": transaction.timestamp.isoformat()
        }
    )
    
    await create_compliance_report(report_data)

def get_risk_distribution() -> Dict[str, int]:
    """Get distribution of risk scores"""
    distribution = {"low": 0, "medium": 0, "high": 0}
    
    for record in kyc_records.values():
        distribution[record["risk_score"]] = distribution.get(record["risk_score"], 0) + 1
    
    for transaction in suspicious_transactions.values():
        distribution[transaction["risk_score"]] = distribution.get(transaction["risk_score"], 0) + 1
    
    return distribution

def get_recent_activity() -> List[Dict]:
    """Get recent compliance activity"""
    activities = []
    
    # Recent KYC approvals
    recent_kyc = [r for r in kyc_records.values() 
                 if r.get("approved_at") and 
                 datetime.fromisoformat(r["approved_at"]) > 
                 datetime.utcnow() - timedelta(hours=24)]
    
    for kyc in recent_kyc[:5]:
        activities.append({
            "type": "kyc_approved",
            "description": f"KYC approved for {kyc['name']}",
            "timestamp": kyc["approved_at"]
        })
    
    # Recent compliance reports
    recent_reports = [r for r in compliance_reports.values() 
                     if datetime.fromisoformat(r["created_at"]) > 
                     datetime.utcnow() - timedelta(hours=24)]
    
    for report in recent_reports[:5]:
        activities.append({
            "type": "compliance_report",
            "description": f"Report: {report['description']}",
            "timestamp": report["created_at"]
        })
    
    # Sort by timestamp
    activities.sort(key=lambda x: x["timestamp"], reverse=True)
    
    return activities[:10]

# Background task for periodic compliance checks
async def periodic_compliance_checks():
    """Background task for periodic compliance monitoring"""
    while True:
        await asyncio.sleep(300)  # Check every 5 minutes
        
        # Check for expired KYC records
        current_time = datetime.utcnow()
        for user_id, kyc_record in kyc_records.items():
            if kyc_record["status"] == "approved":
                approved_time = datetime.fromisoformat(kyc_record["approved_at"])
                if current_time - approved_time > timedelta(days=365):
                    # Flag for re-verification
                    kyc_record["status"] = "reverification_required"
                    logger.info(f"KYC re-verification required for user: {user_id}")

@app.on_event("startup")
async def startup_event():
    logger.info("Starting AITBC Compliance Service")
    # Start background compliance checks
    asyncio.create_task(periodic_compliance_checks())

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down AITBC Compliance Service")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8011, log_level="info")
