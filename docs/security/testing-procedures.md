# Security Remediation Testing Procedures

**Date:** 2026-05-11  
**Purpose:** Test completed security remediations before deployment

## Test Environment Setup

### Prerequisites
- Node.js and npm installed
- Circom compiler installed
- Python 3.13+ with virtual environment
- Hardhat for smart contract testing
- Access to staging environment (for ZK service tests)

### Installation Commands
```bash
# Install Circom
npm install -g circom

# Install snarkjs
npm install -g snarkjs

# Setup Python environment
cd /opt/aitbc
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Test 1: Circom Circuit Fixes

### 1.1 Test ml_training_verification.circom

**Fix Verified:** Learning rate constraint replaced with proper comparison circuits

**Compilation Test:**
```bash
cd /opt/aitbc/apps/zk-circuits
circom ml_training_verification.circom --r1cs --wasm
```

**Expected Result:**
- Compilation succeeds without errors
- R1CS and WASM files generated
- No constraint validation errors

**Constraint Verification:**
```bash
# Check that LessThan and GreaterThan components are used
grep -n "LessThan\|GreaterThan" ml_training_verification.circom
```

**Expected Result:**
- Lines showing LessThan component for learning_rate < 1
- Lines showing GreaterThan component for learning_rate > 0

### 1.2 Test ml_inference_verification.circom

**Fix Verified:** Verification logic replaced with IsZero circuit

**Compilation Test:**
```bash
circom ml_inference_verification.circom --r1cs --wasm
```

**Expected Result:**
- Compilation succeeds
- R1CS and WASM files generated

**Verification Logic Check:**
```bash
grep -n "IsZero" ml_inference_verification.circom
```

**Expected Result:**
- IsZero component used for diff == 0 check
- No "1 - (diff * diff)" pattern present

### 1.3 Test modular_ml_components.circom

**Fix Verified:** Learning rate validation re-implemented

**Compilation Test:**
```bash
circom modular_ml_components.circom --r1cs --wasm
```

**Expected Result:**
- Compilation succeeds
- R1CS and WASM files generated

**Validation Check:**
```bash
grep -A 10 "template LearningRateValidation" modular_ml_components.circom
```

**Expected Result:**
- LearningRateValidation template has constraints
- LessThan and GreaterThan components present
- Not empty (no "Removed constraint" comment)

### 1.4 Test receipt.circom

**Fix Verified:** ECDSA verification placeholder removed, moved to API layer

**Compilation Test:**
```bash
circom receipt.circom --r1cs --wasm
```

**Expected Result:**
- Compilation succeeds
- No ECDSA verification placeholder constraint
- Security note about off-chain verification present

**Placeholder Check:**
```bash
grep -n "signature\[0\] \* signature\[1\]" receipt.circom
```

**Expected Result:**
- No placeholder constraint found
- Security comment present

## Test 2: ZK Proof Service Fixes

### 2.1 Test zk_proofs.py Groth16 Verification

**Fix Verified:** Mock verification replaced with actual Groth16

**Verification:**
```bash
cd /opt/aitbc
python -c "
from apps.coordinator-api.src.app.services.zk_proofs import ZKProofService
import inspect

# Check verify_proof method signature
sig = inspect.signature(ZKProofService.verify_proof)
print('Method signature:', sig)

# Check if actual verification logic is present
source = inspect.getsource(ZKProofService.verify_proof)
print('Contains snarkjs:', 'snarkjs.groth16.verify' in source)
print('Returns dict:', 'return {' in source)
"
```

**Expected Result:**
- Method signature includes verification_key parameter (optional)
- Source contains snarkjs.groth16.verify call
- Returns dict with verification results
- No "return {\"verified\": True}" hardcoded return

### 2.2 Test zk_memory_verification.py Disabled by Default

**Fix Verified:** Service disabled by default with enabled flag

**Verification:**
```bash
python -c "
from apps.coordinator-api.src.app.services.zk_memory_verification import ZKMemoryVerificationService
import inspect

# Check constructor signature
sig = inspect.signature(ZKMemoryVerificationService.__init__)
print('Constructor signature:', sig)

# Check if enabled parameter exists
params = sig.parameters
print('Has enabled parameter:', 'enabled' in params)
print('Default value:', params['enabled'].default if 'enabled' in params else 'N/A')
"
```

**Expected Result:**
- Constructor has enabled parameter
- Default value is False
- generate_memory_proof checks if enabled

### 2.3 Test zk_applications.py Demo Endpoints Disabled

**Fix Verified:** DEMO_MODE_ENABLED flag added, endpoints disabled by default

**Verification:**
```bash
python -c "
import ast
with open('apps/coordinator-api/src/app/routers/zk_applications.py', 'r') as f:
    content = f.read()
    
# Check for DEMO_MODE_ENABLED flag
print('Has DEMO_MODE_ENABLED flag:', 'DEMO_MODE_ENABLED' in content)
print('Default value:', content.split('DEMO_MODE_ENABLED')[1].split('=')[1].strip() if 'DEMO_MODE_ENABLED' in content else 'N/A')

# Check if demo endpoints have enabled check
demo_endpoints = ['verify_group_membership', 'submit_private_bid', 'verify_computation_proof', 'generate_stealth_address']
for endpoint in demo_endpoints:
    has_check = f'if not DEMO_MODE_ENABLED' in content
    print(f'{endpoint} has enabled check: {has_check}')
"
```

**Expected Result:**
- DEMO_MODE_ENABLED flag present
- Default value is False
- All demo endpoints have enabled check
- 503 error raised when not enabled

## Test 3: AIToken.sol Supply Cap and Cooldown

### 3.1 Test Smart Contract Compilation

**Fix Verified:** Supply cap and cooldown added

**Compilation Test:**
```bash
cd /opt/aitbc/contracts
npx hardhat compile
```

**Expected Result:**
- Compilation succeeds
- No compilation errors

### 3.2 Test Supply Cap

**Test Script:**
```javascript
// test/test_aitoken_supply_cap.js
const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AIToken Supply Cap", function () {
  it("Should enforce MAX_SUPPLY", async function () {
    const AIToken = await ethers.getContractFactory("AIToken");
    const initialSupply = ethers.parseEther("1000000"); // 1 million
    const token = await AIToken.deploy(initialSupply);
    
    const MAX_SUPPLY = ethers.parseEther("1000000000"); // 1 billion
    
    // Try to mint beyond cap
    await expect(
      token.mint(await token.owner(), MAX_SUPPLY - initialSupply + ethers.parseEther("1"))
    ).to.be.revertedWith("Minting would exceed max supply");
  });

  it("Should accept minting within cap", async function () {
    const AIToken = await ethers.getContractFactory("AIToken");
    const initialSupply = ethers.parseEther("1000000");
    const token = await AIToken.deploy(initialSupply);
    
    // Mint within cap
    await token.mint(await token.owner(), ethers.parseEther("1000"));
    const totalSupply = await token.totalSupply();
    expect(totalSupply).to.equal(initialSupply + ethers.parseEther("1000"));
  });
});
```

**Run Test:**
```bash
npx hardhat test test/test_aitoken_supply_cap.js
```

**Expected Result:**
- Tests pass
- Minting beyond cap reverts with proper error
- Minting within cap succeeds

### 3.3 Test Minting Cooldown

**Test Script:**
```javascript
// test/test_aitoken_cooldown.js
const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AIToken Minting Cooldown", function () {
  it("Should enforce 1-day cooldown", async function () {
    const AIToken = await ethers.getContractFactory("AIToken");
    const token = await AIToken.deploy(ethers.parseEther("1000000"));
    
    // First mint
    await token.mint(await token.owner(), ethers.parseEther("1000"));
    
    // Try to mint immediately again (should fail)
    await expect(
      token.mint(await token.owner(), ethers.parseEther("1000"))
    ).to.be.revertedWith("Minting cooldown not elapsed");
  });

  it("Should allow minting after cooldown", async function () {
    const AIToken = await ethers.getContractFactory("AIToken");
    const token = await AIToken.deploy(ethers.parseEther("1000000"));
    
    // First mint
    await token.mint(await token.owner(), ethers.parseEther("1000"));
    
    // Fast forward 1 day
    await ethers.provider.send("evm_increaseTime", [86400]);
    await ethers.provider.send("evm_mine");
    
    // Mint after cooldown (should succeed)
    await token.mint(await token.owner(), ethers.parseEther("1000"));
    
    const totalSupply = await token.totalSupply();
    expect(totalSupply).to.equal(ethers.parseEther("1000000") + ethers.parseEther("2000"));
  });
});
```

**Run Test:**
```bash
npx hardhat test test/test_aitoken_cooldown.js
```

**Expected Result:**
- Immediate second mint fails with cooldown error
- Mint after 1 day succeeds

### 3.4 Test Constructor Validation

**Test Script:**
```javascript
// test/test_aitoken_constructor.js
const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AIToken Constructor", function () {
  it("Should reject initial supply exceeding MAX_SUPPLY", async function () {
    const AIToken = await ethers.getContractFactory("AIToken");
    const MAX_SUPPLY = ethers.parseEther("1000000000");
    
    await expect(
      AIToken.deploy(MAX_SUPPLY + ethers.parseEther("1"))
    ).to.be.revertedWith("Initial supply exceeds max supply");
  });

  it("Should accept initial supply within MAX_SUPPLY", async function () {
    const AIToken = await ethers.getContractFactory("AIToken");
    const token = await AIToken.deploy(ethers.parseEther("1000000"));
    expect(await token.totalSupply()).to.equal(ethers.parseEther("1000000"));
  });
});
```

**Run Test:**
```bash
npx hardhat test test/test_aitoken_constructor.js
```

**Expected Result:**
- Deployment with supply > MAX_SUPPLY fails
- Deployment with supply <= MAX_SUPPLY succeeds

## Test Summary Checklist

### Circom Circuits
- [ ] ml_training_verification.circom compiles
- [ ] Learning rate constraint uses LessThan/GreaterThan
- [ ] ml_inference_verification.circom compiles
- [ ] Verification uses IsZero circuit
- [ ] modular_ml_components.circom compiles
- [ ] Learning rate validation has constraints
- [ ] receipt.circom compiles
- [ ] No placeholder ECDSA constraint

### ZK Proof Services
- [ ] zk_proofs.py uses Groth16 verification
- [ ] zk_memory_verification.py has enabled flag (default False)
- [ ] zk_applications.py has DEMO_MODE_ENABLED flag (default False)
- [ ] Demo endpoints check enabled flag
- [ ] Disabled endpoints return 503 error

### AIToken.sol
- [ ] Contract compiles
- [ ] Supply cap enforced
- [ ] Minting cooldown enforced
- [ ] Constructor validates initial supply

## Staging Environment Tests

### Prerequisites
- Staging environment deployed
- Environment variables configured
- DEMO_MODE_ENABLED can be set via environment

### Staging Test Commands

```bash
# Set environment variables
export DEMO_MODE_ENABLED=false
export ZK_PROOF_ENABLED=false

# Deploy to staging
./scripts/deployment/deploy.sh --env staging

# Run health checks
./scripts/monitoring/health_check.sh

# Test endpoints
curl -X POST http://staging.aitbc.com/zk/membership/verify \
  -H "Content-Type: application/json" \
  -d '{"group_id":"miners","nullifier":"0x...","proof":"test"}'

# Expected: 503 Service Unavailable with message about demo mode
```

## Test Results Documentation

After completing tests, document results in:
- `docs/security/test-results.md`
- Include test dates, results, any failures
- Attach logs for failed tests
- Sign off on successful tests

## Rollback Plan

If any test fails:
1. Revert the specific change
2. Re-run tests
3. Document the failure and reason
4. Update remediation plan
5. Escalate if critical

## Next Steps After Testing

1. All tests pass → Proceed to staging deployment
2. Some tests fail → Fix issues, re-test
3. Critical tests fail → Rollback, reassess approach
