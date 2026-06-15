"""
Production Compliance Service for AITBC
Handles KYC/AML, regulatory compliance, and monitoring
"""
import asyncio
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from aitbc import get_logger

logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info('Starting AITBC Compliance Service')
    asyncio.create_task(periodic_compliance_checks())
    yield
    logger.info('Shutting down AITBC Compliance Service')
app = FastAPI(title='AITBC Compliance Service', description='Regulatory compliance and monitoring for AITBC operations', version='1.0.0', lifespan=lifespan)

class KYCRequest(BaseModel):
    user_id: str
    name: str
    email: str
    document_type: str
    document_number: str
    address: dict[str, str]

class ComplianceReport(BaseModel):
    report_type: str
    description: str
    severity: str
    details: dict[str, Any]

class TransactionMonitoring(BaseModel):
    transaction_id: str
    user_id: str
    amount: float
    currency: str
    counterparty: str
    timestamp: datetime
kyc_records: dict[str, dict] = {}
compliance_reports: dict[str, dict] = {}
suspicious_transactions: dict[str, dict] = {}
compliance_rules: dict[str, dict] = {}
risk_scores: dict[str, dict] = {}

@app.get('/')
async def root():
    return {'service': 'AITBC Compliance Service', 'status': 'running', 'timestamp': datetime.now(UTC).isoformat(), 'version': '1.0.0'}

@app.get('/health')
async def health_check():
    return {'status': 'healthy', 'kyc_records': len(kyc_records), 'compliance_reports': len(compliance_reports), 'suspicious_transactions': len(suspicious_transactions), 'active_rules': len(compliance_rules)}

@app.post('/api/v1/kyc/submit')
async def submit_kyc(kyc_request: KYCRequest):
    """Submit KYC verification request"""
    if kyc_request.user_id in kyc_records:
        raise HTTPException(status_code=400, detail='KYC already submitted for this user')
    kyc_record = {'user_id': kyc_request.user_id, 'name': kyc_request.name, 'email': kyc_request.email, 'document_type': kyc_request.document_type, 'document_number': kyc_request.document_number, 'address': kyc_request.address, 'status': 'pending', 'submitted_at': datetime.now(UTC).isoformat(), 'reviewed_at': None, 'approved_at': None, 'risk_score': 'medium', 'notes': []}
    kyc_records[kyc_request.user_id] = kyc_record
    await asyncio.sleep(2)
    kyc_record['status'] = 'approved'
    kyc_record['reviewed_at'] = datetime.now(UTC).isoformat()
    kyc_record['approved_at'] = datetime.now(UTC).isoformat()
    kyc_record['risk_score'] = 'low'
    logger.info('KYC approved for user: %s', kyc_request.user_id)
    return {'user_id': kyc_request.user_id, 'status': kyc_record['status'], 'risk_score': kyc_record['risk_score'], 'approved_at': kyc_record['approved_at']}

@app.get('/api/v1/kyc/{user_id}')
async def get_kyc_status(user_id: str):
    """Get KYC status for a user"""
    if user_id not in kyc_records:
        raise HTTPException(status_code=404, detail='KYC record not found')
    return kyc_records[user_id]

@app.get('/api/v1/kyc')
async def list_kyc_records():
    """List all KYC records"""
    return {'kyc_records': list(kyc_records.values()), 'total_records': len(kyc_records), 'approved': len([r for r in kyc_records.values() if r['status'] == 'approved']), 'pending': len([r for r in kyc_records.values() if r['status'] == 'pending']), 'rejected': len([r for r in kyc_records.values() if r['status'] == 'rejected'])}

@app.post('/api/v1/compliance/report')
async def create_compliance_report(report: ComplianceReport):
    """Create a compliance report"""
    report_id = f'report_{int(datetime.now(UTC).timestamp())}'
    compliance_record = {'report_id': report_id, 'report_type': report.report_type, 'description': report.description, 'severity': report.severity, 'details': report.details, 'status': 'open', 'created_at': datetime.now(UTC).isoformat(), 'assigned_to': None, 'resolved_at': None, 'resolution': None}
    compliance_reports[report_id] = compliance_record
    logger.info('Compliance report created: %s - %s', report_id, report.report_type)
    return {'report_id': report_id, 'status': 'created', 'severity': report.severity, 'created_at': compliance_record['created_at']}

@app.get('/api/v1/compliance/reports')
async def list_compliance_reports():
    """List all compliance reports"""
    return {'reports': list(compliance_reports.values()), 'total_reports': len(compliance_reports), 'open': len([r for r in compliance_reports.values() if r['status'] == 'open']), 'resolved': len([r for r in compliance_reports.values() if r['status'] == 'resolved'])}

@app.post('/api/v1/monitoring/transaction')
async def monitor_transaction(transaction: TransactionMonitoring):
    """Monitor transaction for compliance"""
    transaction_id = transaction.transaction_id
    monitoring_record = {'transaction_id': transaction_id, 'user_id': transaction.user_id, 'amount': transaction.amount, 'currency': transaction.currency, 'counterparty': transaction.counterparty, 'timestamp': transaction.timestamp.isoformat(), 'monitored_at': datetime.now(UTC).isoformat(), 'risk_score': calculate_transaction_risk(transaction), 'flags': [], 'status': 'monitored'}
    suspicious_transactions[transaction_id] = monitoring_record
    flags = check_suspicious_patterns(transaction)
    if flags:
        monitoring_record['flags'] = flags
        monitoring_record['status'] = 'flagged'
        await create_suspicious_transaction_report(transaction, flags)
    return {'transaction_id': transaction_id, 'risk_score': monitoring_record['risk_score'], 'flags': flags, 'status': monitoring_record['status']}

@app.get('/api/v1/monitoring/transactions')
async def list_monitored_transactions():
    """List all monitored transactions"""
    return {'transactions': list(suspicious_transactions.values()), 'total_transactions': len(suspicious_transactions), 'flagged': len([t for t in suspicious_transactions.values() if t['status'] == 'flagged']), 'suspicious': len([t for t in suspicious_transactions.values() if t['risk_score'] == 'high'])}

@app.post('/api/v1/rules/create')
async def create_compliance_rule(rule_data: dict[str, Any]):
    """Create a new compliance rule"""
    rule_id = f'rule_{int(datetime.now(UTC).timestamp())}'
    rule = {'rule_id': rule_id, 'name': rule_data.get('name'), 'description': rule_data.get('description'), 'type': rule_data.get('type'), 'conditions': rule_data.get('conditions', {}), 'actions': rule_data.get('actions', []), 'severity': rule_data.get('severity', 'medium'), 'active': True, 'created_at': datetime.now(UTC).isoformat(), 'trigger_count': 0}
    compliance_rules[rule_id] = rule
    logger.info('Compliance rule created: %s - %s', rule_id, rule['name'])
    return {'rule_id': rule_id, 'name': rule['name'], 'status': 'created', 'active': rule['active']}

@app.get('/api/v1/rules')
async def list_compliance_rules():
    """List all compliance rules"""
    return {'rules': list(compliance_rules.values()), 'total_rules': len(compliance_rules), 'active': len([r for r in compliance_rules.values() if r['active']])}

@app.get('/api/v1/dashboard')
async def compliance_dashboard():
    """Get compliance dashboard data"""
    total_users = len(kyc_records)
    approved_users = len([r for r in kyc_records.values() if r['status'] == 'approved'])
    pending_reviews = len([r for r in kyc_records.values() if r['status'] == 'pending'])
    total_reports = len(compliance_reports)
    open_reports = len([r for r in compliance_reports.values() if r['status'] == 'open'])
    total_transactions = len(suspicious_transactions)
    flagged_transactions = len([t for t in suspicious_transactions.values() if t['status'] == 'flagged'])
    return {'summary': {'total_users': total_users, 'approved_users': approved_users, 'pending_reviews': pending_reviews, 'approval_rate': approved_users / total_users * 100 if total_users > 0 else 0, 'total_reports': total_reports, 'open_reports': open_reports, 'total_transactions': total_transactions, 'flagged_transactions': flagged_transactions, 'flag_rate': flagged_transactions / total_transactions * 100 if total_transactions > 0 else 0}, 'risk_distribution': get_risk_distribution(), 'recent_activity': get_recent_activity(), 'generated_at': datetime.now(UTC).isoformat()}

def calculate_transaction_risk(transaction: TransactionMonitoring) -> str:
    """Calculate risk score for a transaction"""
    risk_score = 0
    if transaction.amount > 10000:
        risk_score += 3
    elif transaction.amount > 1000:
        risk_score += 2
    elif transaction.amount > 100:
        risk_score += 1
    hour = transaction.timestamp.hour
    if hour < 9 or hour > 17:
        risk_score += 1
    if risk_score >= 4:
        return 'high'
    elif risk_score >= 2:
        return 'medium'
    else:
        return 'low'

def check_suspicious_patterns(transaction: TransactionMonitoring) -> list[str]:
    """Check for suspicious transaction patterns"""
    flags = []
    if transaction.amount > 50000:
        flags.append('high_value_transaction')
    user_transactions = [t for t in suspicious_transactions.values() if t['user_id'] == transaction.user_id]
    recent_transactions = [t for t in user_transactions if datetime.fromisoformat(t['monitored_at']) > datetime.now(UTC) - timedelta(hours=1)]
    if len(recent_transactions) > 5:
        flags.append('rapid_transactions')
    if transaction.counterparty in ['high_risk_entity_1', 'high_risk_entity_2']:
        flags.append('high_risk_counterparty')
    return flags

async def create_suspicious_transaction_report(transaction: TransactionMonitoring, flags: list[str]):
    """Create compliance report for suspicious transaction"""
    report_data = ComplianceReport(report_type='suspicious_transaction', description=f'Suspicious transaction detected: {transaction.transaction_id}', severity='high', details={'transaction_id': transaction.transaction_id, 'user_id': transaction.user_id, 'amount': transaction.amount, 'flags': flags, 'timestamp': transaction.timestamp.isoformat()})
    await create_compliance_report(report_data)

def get_risk_distribution() -> dict[str, int]:
    """Get distribution of risk scores"""
    distribution = {'low': 0, 'medium': 0, 'high': 0}
    for record in kyc_records.values():
        distribution[record['risk_score']] = distribution.get(record['risk_score'], 0) + 1
    for transaction in suspicious_transactions.values():
        distribution[transaction['risk_score']] = distribution.get(transaction['risk_score'], 0) + 1
    return distribution

def get_recent_activity() -> list[dict]:
    """Get recent compliance activity"""
    activities = []
    recent_kyc = [r for r in kyc_records.values() if r.get('approved_at') and datetime.fromisoformat(r['approved_at']) > datetime.now(UTC) - timedelta(hours=24)]
    for kyc in recent_kyc[:5]:
        activities.append({'type': 'kyc_approved', 'description': f"KYC approved for {kyc['name']}", 'timestamp': kyc['approved_at']})
    recent_reports = [r for r in compliance_reports.values() if datetime.fromisoformat(r['created_at']) > datetime.now(UTC) - timedelta(hours=24)]
    for report in recent_reports[:5]:
        activities.append({'type': 'compliance_report', 'description': f"Report: {report['description']}", 'timestamp': report['created_at']})
    activities.sort(key=lambda x: x['timestamp'], reverse=True)
    return activities[:10]

async def periodic_compliance_checks():
    """Background task for periodic compliance monitoring"""
    while True:
        await asyncio.sleep(300)
        current_time = datetime.now(UTC)
        for user_id, kyc_record in kyc_records.items():
            if kyc_record['status'] == 'approved':
                approved_time = datetime.fromisoformat(kyc_record['approved_at'])
                if current_time - approved_time > timedelta(days=365):
                    kyc_record['status'] = 'reverification_required'
                    logger.info('KYC re-verification required for user: %s', user_id)
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host=os.getenv('BIND_HOST', '127.0.0.1'), port=8011, log_level='info')
