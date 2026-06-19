# Secret Rotation Runbook

**Version**: v0.5.0
**Last Updated**: 2026-06-19
**Status**: Ready for implementation

---

## Overview

This runbook provides exact steps for rotating critical secrets with zero-downtime using dual-secret overlap windows. Secrets are loaded at startup, so rotation requires service restart.

---

## Critical Secrets

### 1. JWT_SECRET
- **Location**: `/etc/aitbc/coordinator-api.env`
- **Service**: `aitbc-coordinator-api.service`
- **Impact**: JWT token validation and signing
- **Rotation Window**: 30 minutes (dual-secret overlap)

### 2. API_KEY_HASH_SECRET
- **Location**: `/etc/aitbc/coordinator-api.env`
- **Service**: `aitbc-coordinator-api.service`
- **Impact**: API key hashing and validation
- **Rotation Window**: 30 minutes (dual-secret overlap)

### 3. KEYSTORE_PASSWORD
- **Location**: `/etc/aitbc/blockchain.env`
- **Service**: `aitbc-blockchain-node.service`
- **Impact**: Blockchain keystore encryption
- **Rotation Window**: 60 minutes (dual-secret overlap)

---

## General Rotation Procedure

### Phase 1: Preparation (5 minutes)

1. **Generate new secret**
   ```bash
   # Generate cryptographically secure secret
   openssl rand -hex 32
   ```

2. **Backup current configuration**
   ```bash
   cp /etc/aitbc/coordinator-api.env /etc/aitbc/coordinator-api.env.backup
   cp /etc/aitbc/blockchain.env /etc/aitbc/blockchain.env.backup
   ```

3. **Document rotation in SECRET_ROTATION_LOG.md**
   ```bash
   echo "$(date): Rotating JWT_SECRET - Old: <first_8_chars>... New: <first_8_chars>..." >> docs/operations/SECRET_ROTATION_LOG.md
   ```

### Phase 2: Dual-Secret Overlap (Rotation Window)

#### JWT_SECRET Rotation (30-minute window)

1. **Add new secret as secondary**
   ```bash
   # Add JWT_SECRET_NEW while keeping JWT_SECRET
   echo "JWT_SECRET=<old_secret>" >> /etc/aitbc/coordinator-api.env
   echo "JWT_SECRET_NEW=<new_secret>" >> /etc/aitbc/coordinator-api.env
   ```

2. **Update application to accept both secrets**
   ```python
   # In app/config.py or auth.py
   def validate_jwt(token: str) -> bool:
       # Try old secret first
       try:
           jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
           return True
       except:
           pass

       # Try new secret
       try:
           jwt.decode(token, settings.jwt_secret_new, algorithms=["HS256"])
           return True
       except:
           return False
   ```

3. **Restart service**
   ```bash
   systemctl restart aitbc-coordinator-api.service
   ```

4. **Verify service health**
   ```bash
   curl http://localhost:8203/health
   ```

5. **Wait for overlap period (30 minutes)**
   - Monitor logs for JWT validation errors
   - Verify new tokens are being accepted
   - Check that existing tokens still work

6. **Remove old secret**
   ```bash
   # Remove JWT_SECRET, keep JWT_SECRET_NEW
   sed -i '/^JWT_SECRET=/d' /etc/aitbc/coordinator-api.env
   sed -i 's/JWT_SECRET_NEW/JWT_SECRET/' /etc/aitbc/coordinator-api.env
   ```

7. **Restart service**
   ```bash
   systemctl restart aitbc-coordinator-api.service
   ```

#### API_KEY_HASH_SECRET Rotation (30-minute window)

1. **Add new secret as secondary**
   ```bash
   echo "API_KEY_HASH_SECRET=<old_secret>" >> /etc/aitbc/coordinator-api.env
   echo "API_KEY_HASH_SECRET_NEW=<new_secret>" >> /etc/aitbc/coordinator-api.env
   ```

2. **Update application to accept both secrets**
   ```python
   # In app/auth.py or security module
   def validate_api_key(api_key: str) -> bool:
       # Try old secret first
       try:
           expected_hash = hashlib.sha256(api_key.encode()).hexdigest()
           if hmac.compare_digest(expected_hash, settings.api_key_hash_secret):
               return True
       except:
           pass

       # Try new secret
       try:
           expected_hash = hashlib.sha256(api_key.encode()).hexdigest()
           if hmac.compare_digest(expected_hash, settings.api_key_hash_secret_new):
               return True
       except:
           return False
   ```

3. **Restart service**
   ```bash
   systemctl restart aitbc-coordinator-api.service
   ```

4. **Wait for overlap period (30 minutes)**
   - Monitor API authentication logs
   - Verify new API keys work
   - Check that existing API keys still work

5. **Remove old secret**
   ```bash
   sed -i '/^API_KEY_HASH_SECRET=/d' /etc/aitbc/coordinator-api.env
   sed -i 's/API_KEY_HASH_SECRET_NEW/API_KEY_HASH_SECRET/' /etc/aitbc/coordinator-api.env
   ```

6. **Restart service**
   ```bash
   systemctl restart aitbc-coordinator-api.service
   ```

#### KEYSTORE_PASSWORD Rotation (60-minute window)

**Note**: This requires blockchain keystore re-encryption and is more complex.

1. **Generate new keystore with new password**
   ```bash
   # Backup existing keystore
   cp /var/lib/aitbc/keystore/validator.keystore /var/lib/aitbc/keystore/validator.keystore.backup

   # Generate new keystore with new password
   # (Use blockchain node's keystore management tools)
   ```

2. **Add new password as secondary**
   ```bash
   echo "KEYSTORE_PASSWORD=<old_password>" >> /etc/aitbc/blockchain.env
   echo "KEYSTORE_PASSWORD_NEW=<new_password>" >> /etc/aitbc/blockchain.env
   ```

3. **Update blockchain node to try both passwords**
   ```python
   # In blockchain node keystore loading
   def load_keystore() -> Keystore:
       # Try old password first
       try:
           return Keystore.load("/var/lib/aitbc/keystore/validator.keystore", settings.keystore_password)
       except:
           pass

       # Try new password
       try:
           return Keystore.load("/var/lib/aitbc/keystore/validator.keystore", settings.keystore_password_new)
       except:
           raise KeystoreLoadError("Unable to load keystore with either password")
   ```

4. **Restart blockchain node**
   ```bash
   systemctl restart aitbc-blockchain-node.service
   ```

5. **Wait for overlap period (60 minutes)**
   - Monitor blockchain node logs
   - Verify keystore operations work
   - Check for any decryption errors

6. **Re-encrypt keystore with new password only**
   ```bash
   # Use blockchain node's keystore re-encryption tools
   # This removes the old password dependency
   ```

7. **Remove old password**
   ```bash
   sed -i '/^KEYSTORE_PASSWORD=/d' /etc/aitbc/blockchain.env
   sed -i 's/KEYSTORE_PASSWORD_NEW/KEYSTORE_PASSWORD/' /etc/aitbc/blockchain.env
   ```

8. **Restart blockchain node**
   ```bash
   systemctl restart aitbc-blockchain-node.service
   ```

### Phase 3: Verification (5 minutes)

1. **Verify service health**
   ```bash
   systemctl status aitbc-coordinator-api.service
   systemctl status aitbc-blockchain-node.service
   ```

2. **Verify no errors in logs**
   ```bash
   journalctl -u aitbc-coordinator-api.service -n 100 --no-pager
   journalctl -u aitbc-blockchain-node.service -n 100 --no-pager
   ```

3. **Test authentication**
   ```bash
   # Test JWT authentication
   curl -H "Authorization: Bearer <new_jwt_token>" http://localhost:8203/v1/jobs

   # Test API key authentication
   curl -H "X-API-Key: <new_api_key>" http://localhost:8203/v1/jobs
   ```

4. **Clean up backups**
   ```bash
   rm /etc/aitbc/coordinator-api.env.backup
   rm /etc/aitbc/blockchain.env.backup
   rm /var/lib/aitbc/keystore/validator.keystore.backup
   ```

---

## Emergency Rollback

If rotation causes issues:

1. **Restore from backup**
   ```bash
   cp /etc/aitbc/coordinator-api.env.backup /etc/aitbc/coordinator-api.env
   cp /etc/aitbc/blockchain.env.backup /etc/aitbc/blockchain.env
   ```

2. **Restart services**
   ```bash
   systemctl restart aitbc-coordinator-api.service
   systemctl restart aitbc-blockchain-node.service
   ```

3. **Document rollback**
   ```bash
   echo "$(date): ROLLBACK - JWT_SECRET rotation failed" >> docs/operations/SECRET_ROTATION_LOG.md
   ```

---

## Rotation Schedule

### Recommended Rotation Frequency

- **JWT_SECRET**: Every 90 days
- **API_KEY_HASH_SECRET**: Every 90 days
- **KEYSTORE_PASSWORD**: Every 180 days

### Automated Rotation

Consider implementing automated rotation using:
- HashiCorp Vault with automatic rotation
- AWS Secrets Manager with automatic rotation
- Kubernetes secrets with rotation controllers

---

## Implementation Status

- ✅ Secret rotation runbook documented
- ✅ Zero-downtime rotation procedure defined
- ✅ Dual-secret overlap windows specified
- ✅ Emergency rollback procedure documented
- ⏳ Application code changes needed for dual-secret support
- ⏳ Automated rotation not yet implemented
