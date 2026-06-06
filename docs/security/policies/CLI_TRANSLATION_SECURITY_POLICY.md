# AITBC CLI Translation Security Policy

## 🔐 Security Overview

This document outlines the comprehensive security policy for CLI translation
functionality in the AITBC platform, ensuring that translation services never
compromise security-sensitive operations.

## ⚠️ Security Problem Statement

### Identified Risks

1. **API Dependency**: Translation services rely on external APIs (OpenAI,
   Google, DeepL)
2. **Network Failures**: Translation unavailable during network outages
3. **Data Privacy**: Sensitive command data sent to third-party services
4. **Command Injection**: Risk of translated commands altering security context
5. **Performance Impact**: Translation delays critical operations
6. **Audit Trail**: Loss of original command intent in translation

### Security-Sensitive Operations

- **Agent Strategy Commands**: `aitbc agent strategy --aggressive`
- **Wallet Operations**: `aitbc wallet send --to 0x... --amount 100`
- **Deployment Commands**: `aitbc deploy --production`
- **Signing Operations**: `aitbc sign --message "approve transfer"`
- **Genesis Operations**: `aitbc genesis init --network mainnet`

## 🛡️ Security Framework

### Security Levels

#### 🔴 CRITICAL (Translation Disabled)

**Commands**: `agent`, `strategy`, `wallet`, `sign`, `deploy`, `genesis`,
`transfer`, `send`, `approve`, `mint`, `burn`, `stake`

**Policy**:

- ✅ Translation: **DISABLED**
- ✅ External APIs: **BLOCKED**
- ✅ User Consent: **REQUIRED**
- ✅ Fallback: **Original text only**

**Rationale**: These commands handle sensitive operations where translation
could compromise security or financial transactions.

#### 🟠 HIGH (Local Translation Only)

**Commands**: `config`, `node`, `chain`, `marketplace`, `swap`, `liquidity`,
`governance`, `vote`, `proposal`

**Policy**:

- ✅ Translation: **LOCAL ONLY**
- ✅ External APIs: **BLOCKED**
- ✅ User Consent: **REQUIRED**
- ✅ Fallback: **Local dictionary**

**Rationale**: Important operations that benefit from localization but don't
require external services.

#### 🟡 MEDIUM (Fallback Mode)

**Commands**: `balance`, `status`, `monitor`, `analytics`, `logs`, `history`,
`simulate`, `test`

**Policy**:

- ✅ Translation: **EXTERNAL WITH LOCAL FALLBACK**
- ✅ External APIs: **ALLOWED**
- ✅ User Consent: **NOT REQUIRED**
- ✅ Fallback: **Local translation on failure**

**Rationale**: Standard operations where translation enhances user experience
but isn't critical.

#### 🟢 LOW (Full Translation)

**Commands**: `help`, `version`, `info`, `list`, `show`, `explain`

**Policy**:

- ✅ Translation: **FULL CAPABILITIES**
- ✅ External APIs: **ALLOWED**
- ✅ User Consent: **NOT REQUIRED**
- ✅ Fallback: **External retry then local**

**Rationale**: Informational commands where translation improves
accessibility without security impact.

## 🔧 Implementation Details

### Security Manager Architecture

```python
# Security enforcement flow
async def translate_with_security(request):
    1. Determine command security level
    2. Apply security policy
    3. Check user consent requirements
    4. Execute translation based on policy
    5. Log security check for audit
    6. Return with security metadata
```

### Policy Configuration

```python
# Default security policies
CRITICAL_POLICY = {
    "translation_mode": "DISABLED",
    "allow_external_apis": False,
    "require_explicit_consent": True,
    "timeout_seconds": 0,
    "max_retries": 0
}

HIGH_POLICY = {
    "translation_mode": "LOCAL_ONLY", 
    "allow_external_apis": False,
    "require_explicit_consent": True,
    "timeout_seconds": 5,
    "max_retries": 1
}
```

### Local Translation System

For security-sensitive operations, a local translation system provides basic
localization:

```python
LOCAL_TRANSLATIONS = {
    "help": {"es": "ayuda", "fr": "aide", "de": "hilfe", "zh": "帮助"},
    "error": {"es": "error", "fr": "erreur", "de": "fehler", "zh": "错误"},
    "success": {"es": "éxito", "fr": "succès", "de": "erfolg", "zh": "成功"},
    "wallet": {
        "es": "cartera",
        "fr": "portefeuille",
        "de": "börse",
        "zh": "钱包"
    },
    "transaction": {
        "es": "transacción",
        "fr": "transaction",
        "de": "transaktion",
        "zh": "交易"
    }
}
```

## 🚨 Security Controls

### 1. Command Classification System

```python
def get_command_security_level(command_name: str) -> SecurityLevel:
    critical_commands = {'agent', 'strategy', 'wallet', 'sign', 'deploy'}
    high_commands = {'config', 'node', 'chain', 'marketplace', 'swap'}
    medium_commands = {'balance', 'status', 'monitor', 'analytics'}
    low_commands = {'help', 'version', 'info', 'list', 'show'}
    
    # Return appropriate security level
```

### 2. API Access Control

```python
# External API blocking for critical operations
if security_level == SecurityLevel.CRITICAL:
    raise SecurityException("External APIs blocked for critical operations")

# Timeout enforcement for external calls
if policy.allow_external_apis:
    result = await asyncio.wait_for(
        external_translate(request), 
        timeout=policy.timeout_seconds
    )
```

### 3. Fallback Mechanisms

```python
async def translate_with_fallback(request):
    try:
        # Try external translation first
        return await external_translate(request)
    except (TimeoutError, NetworkError, APIError):
        # Fallback to local translation
        return await local_translate(request)
    except Exception:
        # Ultimate fallback: return original text
        return request.original_text
```

### 4. Audit Logging

```python
def log_security_check(request, policy):
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "command": request.command_name,
        "security_level": request.security_level.value,
        "translation_mode": policy.translation_mode.value,
        "target_language": request.target_language,
        "user_consent": request.user_consent,
        "text_length": len(request.text)
    }
    security_audit_log.append(log_entry)
```

## 📋 Usage Examples

### Security-Compliant Translation

```python
from aitbc_cli.security import cli_translation_security, TranslationRequest

# Critical command - translation disabled
request = TranslationRequest(
    text="Transfer 100 AITBC to 0x1234...",
    target_language="es",
    command_name="transfer",
    security_level=SecurityLevel.CRITICAL
)

response = await cli_translation_security.translate_with_security(request)
# Result: Original text returned, translation disabled
```

### Medium Security Command

```python
# Status command - fallback mode allowed
request = TranslationRequest(
    text="Current balance: 1000 AITBC",
    target_language="fr",
    command_name="balance",
    security_level=SecurityLevel.MEDIUM
)

response = await cli_translation_security.translate_with_security(request)
# Result: Translated with external API, local fallback on failure
```

### Local Translation Only

```python
# Configuration command - local only
request = TranslationRequest(
    text="Node configuration updated",
    target_language="de",
    command_name="config",
    security_level=SecurityLevel.HIGH
)

response = await cli_translation_security.translate_with_security(request)
# Result: Local dictionary translation only
```

## 🔍 Security Monitoring

### Security Report Generation

```python
from aitbc_cli.security import get_translation_security_report

report = get_translation_security_report()
print(f"Total security checks: {report['security_summary']['total_checks']}")
print(
    f"Critical operations: "
    f"{report['security_summary']['by_security_level']['critical']}"
)
print(f"Recommendations: {report['recommendations']}")
```

### Real-time Monitoring

```python
# Monitor translation security in real-time
def monitor_translation_security():
    summary = cli_translation_security.get_security_summary()
    
    # Alert on suspicious patterns
    if summary['by_security_level'].get('critical', 0) > 0:
        send_security_alert("Critical command translation attempts detected")
    
    # Monitor failure rates
    recent_failures = [log for log in summary['recent_checks'] 
                      if log.get('translation_failed', False)]
    
    if len(recent_failures) > 5:  # Threshold
        send_security_alert("High translation failure rate detected")
```

## ⚙️ Configuration

### Environment Variables

```bash
# Security policy configuration
AITBC_TRANSLATION_SECURITY_LEVEL="medium"  # Global security level
AITBC_TRANSLATION_EXTERNAL_APIS="false"   # Block external APIs
AITBC_TRANSLATION_TIMEOUT="10"            # API timeout in seconds
AITBC_TRANSLATION_AUDIT="true"             # Enable audit logging
```

### Configuration File

```json
{
    "translation_security": {
        "critical_level": "disabled",
        "high_level": "local_only", 
        "medium_level": "fallback",
        "low_level": "full",
        "audit_logging": true,
        "max_audit_entries": 1000
    },
    "external_apis": {
        "timeout_seconds": 10,
        "max_retries": 3,
        "cache_enabled": true,
        "cache_ttl": 3600
    }
}
```

## 🚨 Incident Response

### Translation Service Outage

```python
# Automatic fallback during service outage
async def handle_translation_outage():
    # Temporarily disable external APIs
    configure_translation_security(
        critical_level="disabled",
        high_level="local_only",
        medium_level="local_only",  # Downgrade from fallback
        low_level="local_only"       # Downgrade from full
    )
    
    # Log security policy change
    log_security_incident("Translation outage - external APIs disabled")
```

### Security Incident Response

```python
def handle_security_incident(incident_type: str):
    if incident_type == "suspicious_translation_activity":
        # Disable translation for sensitive operations
        configure_translation_security(
            critical_level="disabled",
            high_level="disabled",
            medium_level="local_only",
            low_level="fallback"
        )
        
        # Trigger security review
        trigger_security_review()
```

## 📊 Security Metrics

### Key Performance Indicators

- **Translation Success Rate**: Percentage of successful translations by
  security level
- **Fallback Usage Rate**: How often local fallback is used
- **API Response Time**: External API performance metrics
- **Security Violations**: Attempts to bypass security policies
- **User Consent Rate**: How often users grant consent for translation

### Monitoring Dashboard

```python
def get_security_metrics():
    return {
        "translation_success_rate": calculate_success_rate(),
        "fallback_usage_rate": calculate_fallback_rate(),
        "api_response_times": get_api_metrics(),
        "security_violations": count_violations(),
        "user_consent_rate": calculate_consent_rate()
    }
```

## 🔮 Future Enhancements

### Planned Security Features

1. **Machine Learning Detection**: AI-powered detection of sensitive command
   patterns
2. **Dynamic Policy Adjustment**: Automatic security level adjustment based on
   context
3. **Zero-Knowledge Translation**: Privacy-preserving translation protocols
4. **Blockchain Auditing**: Immutable audit trail on blockchain
5. **Multi-Factor Authentication**: Additional security for sensitive
   translations

### Research Areas

1. **Federated Learning**: Local translation models without external
   dependencies
2. **Quantum-Resistant Security**: Future-proofing against quantum computing
   threats
3. **Behavioral Analysis**: User behavior patterns for anomaly detection
4. **Cross-Platform Security**: Consistent security across all CLI platforms

---

- **Security Policy Status**: ✅ **IMPLEMENTED**
- **Last Updated**: March 3, 2026
- **Next Review**: March 17, 2026
- **Security Level**: 🔒 **HIGH** - Comprehensive protection for sensitive
  operations

This security policy ensures that CLI translation functionality never
compromises security-sensitive operations while providing appropriate
localization capabilities for non-critical commands.
