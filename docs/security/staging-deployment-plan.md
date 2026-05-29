# Staging Deployment Plan for Security Remediations

**Date:** 2026-05-11  
**Purpose:** Deploy completed security fixes to staging environment for integration testing

## Deployment Scope

### Components to Deploy

**1. Circom Circuits (3 circuits)**
- `ml_training_verification.circom` - Compiled with bit size fix
- `ml_inference_verification.circom` - Compiled successfully
- `modular_ml_components.circom` - Compiled with bit size fix
- Note: `receipt.circom` has pre-existing compilation issue, not deployed

**2. ZK Proof Service Python Code (3 services)**
- `apps/coordinator-api/src/app/services/zk_proofs.py` - Groth16 verification
- `apps/coordinator-api/src/app/services/zk_memory_verification.py` - Enabled flag
- `apps/coordinator-api/src/app/routers/zk_applications.py` - DEMO_MODE_ENABLED flag

**3. Smart Contract (1 contract)**
- `contracts/contracts/AIToken.sol` - Supply cap and cooldown

## Staging Environment Setup

### Prerequisites

**System Requirements:**
- Linux server (Ubuntu/Debian/CentOS/RHEL)
- Python 3.13+
- Node.js and npm (for Circom)
- PostgreSQL
- Redis
- systemd

**Environment Configuration:**
- Create `/etc/aitbc/.env.staging` based on `examples/env.example`
- Set `NODE_ENV=staging`
- Set `APP_ENV=staging`
- Configure staging-specific database and Redis
- Use testnet blockchain configuration

### Configuration Changes

**Staging Environment Variables:**
```bash
NODE_ENV=staging
APP_ENV=staging
DEBUG=true
LOG_LEVEL=DEBUG

# Staging database
DATABASE_URL=postgresql://aitbc:staging_password@localhost:5432/aitbc_staging
REDIS_URL=redis://localhost:6379/1

# Staging blockchain
chain_id=ait-testnet
NETWORK_ID=1337

# Staging API keys (use test values)
SECRET_KEY=staging-secret-key
JWT_SECRET=staging-jwt-secret-32-chars-long
COORDINATOR_API_KEY=staging_admin_key
```

**Feature Flags for Testing:**
```bash
# Enable services for testing
DEMO_MODE_ENABLED=true  # Test demo endpoints
ZK_PROOF_ENABLED=true   # Test ZK proof service
```

## Deployment Steps

### Phase 1: Environment Preparation

**1. Create staging environment file**
```bash
mkdir -p /etc/aitbc
cp /opt/aitbc/examples/env.example /etc/aitbc/.env.staging
vim /etc/aitbc/.env.staging
# Update with staging-specific values
```

**2. Create staging database**
```bash
-u postgres psql
CREATE DATABASE aitbc_staging;
CREATE USER aitbc_staging WITH PASSWORD 'staging_password';
GRANT ALL PRIVILEGES ON DATABASE aitbc_staging TO aitbc_staging;
\q
```

**3. Setup Python virtual environment**
```bash
cd /opt/aitbc
python3 -m venv venv_staging
source venv_staging/bin/activate
pip install -r requirements.txt
```

### Phase 2: Deploy Python Services

**1. Deploy coordinator-api with security fixes**
```bash
cd /opt/aitbc/apps/coordinator-api

# Install dependencies
pip install -r requirements.txt

# Run migrations
alembic upgrade head --env-file /etc/aitbc/.env.staging

# Restart service (if using systemd)
systemctl restart aitbc-coordinator-api
```

**2. Verify ZK proof services**
```bash
# Test that services start correctly
curl http://localhost:8001/health
curl http://localhost:8001/zk/status
```

### Phase 3: Deploy Smart Contract

**1. Compile AIToken.sol**
```bash
cd /opt/aitbc/contracts
npx hardhat compile
```

**2. Deploy to testnet**
```bash
# Create deployment script
cat > scripts/deploy_aitoken_staging.js << 'EOF'
const hre = require("hardhat");

async function main() {
  const AIToken = await hre.ethers.getContractFactory("AIToken");
  const initialSupply = hre.ethers.parseEther("1000000"); // 1 million for staging
  const token = await AIToken.deploy(initialSupply);
  await token.waitForDeployment();
  
  console.log("AIToken deployed to:", await token.getAddress());
  
  // Verify supply cap
  const MAX_SUPPLY = await token.MAX_SUPPLY();
  console.log("MAX_SUPPLY:", hre.ethers.formatEther(MAX_SUPPLY));
  
  // Verify cooldown
  const COOLDOWN = await token.MINTING_COOLDOWN();
  console.log("MINTING_COOLDOWN:", COOLDOWN.toString());
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
EOF

# Deploy
npx hardhat run scripts/deploy_aitoken_staging.js --network testnet
```

**3. Test contract functions**
```bash
# Create test script
cat > scripts/test_aitoken_staging.js << 'EOF'
const hre = require("hardhat");

async function main() {
  const [owner] = await hre.ethers.getSigners();
  const tokenAddress = process.env.TOKEN_ADDRESS;
  const token = await hre.ethers.getContractAt("AIToken", tokenAddress);
  
  // Test supply cap
  const MAX_SUPPLY = hre.ethers.parseEther("1000000000");
  const totalSupply = await token.totalSupply();
  
  console.log("Total Supply:", hre.ethers.formatEther(totalSupply));
  console.log("MAX_SUPPLY:", hre.ethers.formatEther(MAX_SUPPLY));
  
  // Test minting within cap
  await token.mint(owner.address, hre.ethers.parseEther("1000"));
  console.log("Minted 1000 tokens successfully");
  
  // Test cooldown
  try {
    await token.mint(owner.address, hre.ethers.parseEther("100"));
    console.log("ERROR: Should have failed due to cooldown");
  } catch (error) {
    console.log("Cooldown working correctly");
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1);
});
EOF

npx hardhat run scripts/test_aitoken_staging.js --network testnet
```

### Phase 4: Deploy Circom Circuits

**1. Copy compiled circuits to staging**
```bash
cd /opt/aitbc/apps/zk-circuits

# Copy compiled files to staging circuits directory
mkdir -p /var/lib/aitbc/circuits_staging
cp ml_training_verification.r1cs /var/lib/aitbc/circuits_staging/
cp ml_training_verification_js/ /var/lib/aitbc/circuits_staging/ -r
cp ml_inference_verification.r1cs /var/lib/aitbc/circuits_staging/
cp ml_inference_verification_js/ /var/lib/aitbc/circuits_staging/ -r
cp modular_ml_components.r1cs /var/lib/aitbc/circuits_staging/
cp modular_ml_components_js/ /var/lib/aitbc/circuits_staging/ -r
```

**2. Update ZK proof service configuration**
```bash
# Update service config to point to staging circuits
vim /etc/aitbc/coordinator-api.env
# Set CIRCUITS_DIR=/var/lib/aitbc/circuits_staging
```

### Phase 5: Integration Testing

**1. Test ZK proof verification**
```bash
# Test Groth16 verification
curl -X POST http://localhost:8001/zk/verify \
  -H "Content-Type: application/json" \
  -d '{"proof": {...}, "public_signals": [...]}'
```

**2. Test disabled demo endpoints**
```bash
# Set DEMO_MODE_ENABLED=false in staging config
systemctl restart aitbc-coordinator-api

# Test that demo endpoints return 503
curl -X POST http://localhost:8001/zk/membership/verify \
  -H "Content-Type: application/json" \
  -d '{"group_id":"miners","nullifier":"0x...","proof":"test"}'
# Expected: 503 Service Unavailable
```

**3. Test enabled demo endpoints**
```bash
# Set DEMO_MODE_ENABLED=true in staging config
systemctl restart aitbc-coordinator-api

# Test that demo endpoints work
curl -X POST http://localhost:8001/zk/membership/verify \
  -H "Content-Type: application/json" \
  -d '{"group_id":"miners","nullifier":"0x...","proof":"test"}'
# Expected: 200 OK
```

## Rollback Plan

If deployment fails:

**1. Python Services**
```bash
# Rollback code changes
git checkout HEAD~1 -- apps/coordinator-api/src/app/services/
systemctl restart aitbc-coordinator-api
```

**2. Smart Contract**
```bash
# Smart contract cannot be rolled back, but can be redeployed
# Keep old contract address for reference
```

**3. Circom Circuits**
```bash
# Restore previous circuit versions
rm -rf /var/lib/aitbc/circuits_staging
cp /var/lib/aitbc/circuits_backup/* /var/lib/aitbc/circuits_staging/ -r
```

## Verification Checklist

- [ ] Staging environment file created
- [ ] Staging database created and accessible
- [ ] Python virtual environment created
- [ ] Coordinator-api deployed with security fixes
- [ ] AIToken.sol deployed to testnet
- [ ] AIToken.sol supply cap tested
- [ ] AIToken.sol cooldown tested
- [ ] Circom circuits copied to staging
- [ ] ZK proof Groth16 verification tested
- [ ] Demo endpoints tested (both enabled and disabled)
- [ ] Integration tests passing
- [ ] Rollback plan documented

## Post-Deployment

**1. Monitor staging environment**
```bash
# Check service logs
journalctl -u aitbc-coordinator-api -f

# Check health endpoints
curl http://localhost:8001/health
```

**2. Document deployment**
- Record deployment timestamp
- Record deployed versions
- Record any issues encountered
- Update deployment documentation

**3. Prepare for production deployment**
- Review staging test results
- Address any issues found
- Update production deployment plan
- Schedule production deployment window

## Timeline Estimate

- Phase 1 (Environment Preparation): 1-2 hours
- Phase 2 (Python Services): 1 hour
- Phase 3 (Smart Contract): 1-2 hours
- Phase 4 (Circom Circuits): 30 minutes
- Phase 5 (Integration Testing): 2-3 hours

**Total Estimated Time:** 5.5-8.5 hours

## Dependencies

- Staging server access
- Database admin access
- Testnet RPC endpoint
- Testnet account with ETH for gas
- API keys for staging services

## Notes

- This deployment is for testing only
- Do not use staging credentials in production
- Smart contract changes require governance approval for mainnet
- Circom circuit `receipt.circom` has pre-existing issue, not included in deployment
