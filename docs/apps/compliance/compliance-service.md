# Compliance Service

## Status
✅ Operational

## Overview
Compliance checking and regulatory services for ensuring AITBC operations meet regulatory requirements and industry standards.

## Architecture

### Core Components
- **Compliance Checker**: Validates operations against compliance rules
- **Rule Engine**: Manages and executes compliance rules
- **Audit Logger**: Logs compliance-related events
- **Report Generator**: Generates compliance reports
- **Policy Manager**: Manages compliance policies

## Quick Start (End Users)

### Prerequisites
- Python 3.13+
- PostgreSQL database for audit logs
- Compliance rule definitions

### Installation
```bash
cd /opt/aitbc/apps/compliance-service
.venv/bin/pip install -r requirements.txt
```

### Configuration
Set environment variables in `.env`:
```bash
DATABASE_URL=postgresql://user:pass@localhost/compliance
RULES_PATH=/opt/aitbc/compliance/rules
AUDIT_LOG_ENABLED=true
REPORT_INTERVAL=86400
```

### Running the Service
```bash
.venv/bin/python main.py
```

## Developer Guide

### Development Setup
1. Clone the repository
2. Create virtual environment: `python -m venv .venv`
3. Install dependencies: `pip install -r requirements.txt`
4. Set up database
5. Configure compliance rules
6. Run tests: `pytest tests/`

### Project Structure
```
compliance-service/
├── src/
│   ├── compliance_checker/   # Compliance checking
│   ├── rule_engine/         # Rule management
│   ├── audit_logger/        # Audit logging
│   ├── report_generator/    # Report generation
│   └── policy_manager/     # Policy management
├── rules/                   # Compliance rules
├── tests/                   # Test suite
└── pyproject.toml           # Project configuration
```

### Testing
```bash
# Run all tests
pytest tests/

# Run compliance checker tests
pytest tests/test_compliance.py

# Run rule engine tests
pytest tests/test_rules.py
```

## API Reference

### Compliance Checking

#### Check Compliance
```http
POST /api/v1/compliance/check
Content-Type: application/json

{
  "entity_type": "agent|transaction|user",
  "entity_id": "string",
  "action": "string",
  "context": {}
}
```

#### Get Compliance Status
```http
GET /api/v1/compliance/status/{entity_id}
```

#### Batch Compliance Check
```http
POST /api/v1/compliance/check/batch
Content-Type: application/json

{
  "checks": [
    {"entity_type": "string", "entity_id": "string", "action": "string"}
  ]
}
```

### Rule Management

#### Add Rule
```http
POST /api/v1/compliance/rules
Content-Type: application/json

{
  "rule_id": "string",
  "name": "string",
  "description": "string",
  "conditions": {},
  "severity": "high|medium|low"
}
```

#### Update Rule
```http
PUT /api/v1/compliance/rules/{rule_id}
Content-Type: application/json

{
  "conditions": {},
  "severity": "high|medium|low"
}
```

#### List Rules
```http
GET /api/v1/compliance/rules?category=kyc|aml
```

### Audit Logging

#### Get Audit Logs
```http
GET /api/v1/compliance/audit?entity_id=string&limit=100
```

#### Search Audit Logs
```http
POST /api/v1/compliance/audit/search
Content-Type: application/json

{
  "filters": {
    "entity_type": "string",
    "action": "string",
    "date_range": {"start": "2024-01-01", "end": "2024-12-31"}
  }
}
```

### Reporting

#### Generate Compliance Report
```http
POST /api/v1/compliance/reports/generate
Content-Type: application/json

{
  "report_type": "summary|detailed",
  "period": "daily|weekly|monthly",
  "scope": {}
}
```

#### Get Report
```http
GET /api/v1/compliance/reports/{report_id}
```

#### List Reports
```http
GET /api/v1/compliance/reports?period=monthly
```

### Policy Management

#### Get Policy
```http
GET /api/v1/compliance/policies/{policy_id}
```

#### Update Policy
```http
PUT /api/v1/compliance/policies/{policy_id}
Content-Type: application/json

{
  "policy": {}
}
```

## Configuration

### Environment Variables
- `DATABASE_URL`: PostgreSQL connection string
- `RULES_PATH`: Path to compliance rules
- `AUDIT_LOG_ENABLED`: Enable audit logging
- `REPORT_INTERVAL`: Report generation interval (default: 86400s)

### Compliance Categories
- **KYC**: Know Your Customer verification
- **AML**: Anti-Money Laundering checks
- **Data Privacy**: Data protection compliance
- **Financial**: Financial regulations

### Rule Parameters
- **Conditions**: Rule conditions and logic
- **Severity**: Rule severity level
- **Actions**: Actions to take on rule violation

## Troubleshooting

**Compliance check failed**: Review rule conditions and entity data.

**Rule not executing**: Verify rule syntax and configuration.

**Audit logs not appearing**: Check audit log configuration and database connectivity.

**Report generation failed**: Verify report parameters and data availability.

## Security Notes

- Encrypt audit log data
- Implement access controls for compliance data
- Regularly review and update compliance rules
- Monitor for compliance violations
- Implement secure policy management
- Regularly audit compliance service access
