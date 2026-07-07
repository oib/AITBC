# security

Security — access control, encryption, key management, KYC/AML, quotas, and trading surveillance.

## Domain Models

- None (stub)

## Routes

- POST /policies
- GET /scan
- GET /policies
- GET /policies/{policy_id}
- PUT /policies/{policy_id}
- DELETE /policies/{policy_id}
- POST /validate-workflow/{workflow_id}
- GET /audit-logs
- GET /audit-logs/{audit_id}
- GET /trust-scores
- GET /trust-scores/{entity_type}/{entity_id}
- POST /trust-scores/{entity_type}/{entity_id}/update
- POST /sandbox/{execution_id}/create
- GET /sandbox/{execution_id}/monitor
- POST /sandbox/{execution_id}/cleanup
- POST /executions/{execution_id}/security-monitor
- GET /security-dashboard
- GET /security-stats

## Services

- access_control.py
- encryption.py
- key_management.py
- kyc_aml_providers.py
- quota_enforcement.py
- trading_surveillance.py
