# Security Setup

**Level**: Beginner
**Prerequisites**: [Scenario 18 Analytics Collection](./18_analytics_collection.md)
**Estimated Time**: 15 minutes
**Last Updated**: 2026-06-25
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Security Setup

---

## See Also

- **Previous Scenario**: [Scenario 18 Analytics Collection](./18_analytics_collection.md)
- **Next Scenario**: [Scenario 20 Cross-Chain Transfer](./20_cross_chain_transfer.md)
- **Agent SDK**: [Agent SDK Documentation](../agent-sdk/README.md)
- **Feature Documentation**: [Security Reference](../security/README.md)

---

## Scenario Overview

This scenario demonstrates how to run security audits, perform security scans, and apply security patches using the `aitbc security` command group. These commands help maintain the security posture of an AITBC deployment.

### Use Case

A node operator wants to verify the security of their AITBC deployment by running an audit to assess the overall security score, scanning for vulnerabilities, and applying any available security patches.

### What You'll Learn

- How to run a security audit with `aitbc security audit`
- How to perform a security scan with `aitbc security scan`
- How to apply security patches with `aitbc security patch`
- How to integrate security checks into an agent's operational workflow

---

## Prerequisites

### Knowledge Required

- Basic familiarity with the `aitbc` CLI (see [Scenario 01 Wallet Basics](./01_wallet_basics.md))
- Understanding of security audits and vulnerability scanning concepts

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`

### Setup Required

- A running AITBC deployment (blockchain node, coordinator, and services)
- Appropriate permissions to run security operations

---

## Step-by-Step Workflow

### Step 1: Run a Security Audit

The `audit` subcommand produces a security score, a vulnerability count, and a list of recommendations. It takes no additional options beyond the global output format.

```bash
aitbc security audit
```

**Expected output:**
```
Security Audit

Security Score      A+
Vulnerabilities     0
Recommendations     []
```

### Step 2: Perform a Security Scan

The `scan` subcommand runs a security scan that reports the action taken, completion status, and number of issues found.

```bash
aitbc security scan
```

**Expected output:**
```
Security Scan

Action            security_scan
Status            completed
Issues Found      0
```

### Step 3: Apply Security Patches

The `patch` subcommand applies available security patches and reports the completion status.

```bash
aitbc security patch
```

**Expected output:**
```
Security Patch

Action            security_patch
Status            completed
```

### Step 4: Full Security Workflow

Run all three security commands in sequence as part of a regular maintenance routine.

```bash
# Step 1: Audit to assess current security posture
echo "=== Running Security Audit ==="
aitbc security audit

# Step 2: Scan for vulnerabilities
echo "=== Running Security Scan ==="
aitbc security scan

# Step 3: Apply any available patches
echo "=== Applying Security Patches ==="
aitbc security patch

echo "=== Security workflow complete ==="
```

**Expected output:**
```
=== Running Security Audit ===
Security Audit

Security Score      A+
Vulnerabilities     0
Recommendations     []

=== Running Security Scan ===
Security Scan

Action            security_scan
Status            completed
Issues Found      0

=== Applying Security Patches ===
Security Patch

Action            security_patch
Status            completed

=== Security workflow complete ===
```

---

## Code Examples Using Agent SDK

### Example 1: Agent Runs Security Checks via CLI Subprocess

The `aitbc_agent` SDK does not expose a direct security API, but agents can run security operations by invoking the real `aitbc` CLI through subprocess calls.

```python
import asyncio
import subprocess
from aitbc_agent import Agent, AgentCapabilities

async def run_security_audit() -> dict:
    """Run a security audit via the real aitbc CLI."""
    result = subprocess.run(
        ["aitbc", "security", "audit"],
        capture_output=True, text=True,
    )
    return {
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }

async def run_security_scan() -> dict:
    """Run a security scan via the real aitbc CLI."""
    result = subprocess.run(
        ["aitbc", "security", "scan"],
        capture_output=True, text=True,
    )
    return {
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }

async def apply_security_patches() -> dict:
    """Apply security patches via the real aitbc CLI."""
    result = subprocess.run(
        ["aitbc", "security", "patch"],
        capture_output=True, text=True,
    )
    return {
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }

async def main():
    agent = Agent.create(
        name="Security Agent",
        agent_type="processing",
        capabilities={"compute_type": "processing", "max_concurrent_jobs": 1},
    )
    await agent.register()

    # Run the full security workflow
    print("=== Security Audit ===")
    audit = await run_security_audit()
    print(audit["stdout"])

    print("=== Security Scan ===")
    scan = await run_security_scan()
    print(scan["stdout"])

    print("=== Security Patch ===")
    patch = await apply_security_patches()
    print(patch["stdout"])

asyncio.run(main())
```

### Example 2: Scheduled Security Maintenance

An agent can schedule periodic security checks and alert on issues.

```python
import subprocess
import time

def run_full_security_check() -> dict:
    """Run audit, scan, and patch in sequence."""
    results = {}

    audit = subprocess.run(
        ["aitbc", "security", "audit"],
        capture_output=True, text=True,
    )
    results["audit"] = audit.stdout.strip()

    scan = subprocess.run(
        ["aitbc", "security", "scan"],
        capture_output=True, text=True,
    )
    results["scan"] = scan.stdout.strip()

    patch = subprocess.run(
        ["aitbc", "security", "patch"],
        capture_output=True, text=True,
    )
    results["patch"] = patch.stdout.strip()

    return results

def scheduled_security_check(interval_seconds: int = 3600):
    """Run security checks on a schedule."""
    while True:
        print(f"\n--- Security check at {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
        results = run_full_security_check()
        for step, output in results.items():
            print(f"[{step}] {output}")
        time.sleep(interval_seconds)

# Run hourly security checks (Ctrl+C to stop)
# scheduled_security_check(interval_seconds=3600)
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Run a security audit to assess the overall security score with `aitbc security audit`
- Perform a security scan to detect issues with `aitbc security scan`
- Apply security patches with `aitbc security patch`
- Integrate security checks into an agent's automated maintenance workflow

---

## Validation

Verify that all security commands complete successfully:

```bash
# Confirm audit returns a security score
aitbc security audit

# Confirm scan completes without errors
aitbc security scan

# Confirm patch applies successfully
aitbc security patch

# Run all three and check exit codes
aitbc security audit && echo "audit OK" && \
aitbc security scan && echo "scan OK" && \
aitbc security patch && echo "patch OK"
```

---

## Related Resources

- [Security Documentation](../security/README.md)
- [Agent SDK Quick Start](../agent-sdk/QUICK_START_GUIDE.md)
- [Next Scenario: Cross-Chain Transfer](./20_cross_chain_transfer.md)

---

*Last updated: 2026-06-25*
*Version: 1.0*
