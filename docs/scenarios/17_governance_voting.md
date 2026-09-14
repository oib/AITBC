# Governance Voting

**Level**: Beginner
**Prerequisites**: [Scenario 16 Agent Registration](./16_agent_registration.md)
**Estimated Time**: 20 minutes
**Last Updated**: 2026-08-21
**Version**: 1.3

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Governance Voting

---

## See Also

- **Previous Scenario**: [Scenario 16 Agent Registration](./16_agent_registration.md)
- **Next Scenario**: [Scenario 18 Analytics Collection](./18_analytics_collection.md)
- **Agent SDK**: [Agent SDK Documentation](../agent-sdk/README.md)
- **Feature Documentation**: [Governance Reference](../governance/README.md)

---

## Scenario Overview

This scenario demonstrates two real CLI surfaces:

- `aitbc governance` — talks to the **governance service** on port 8105 (`propose`, `vote`, `close`, `execute`, `list`, `get`, `status`). This is the canonical group.
- `aitbc operations governance` — talks to **blockchain RPC** `/rpc/governance/*` for a wallet-signed path. The `aitbc operations` group is **deprecated and hidden** from `aitbc --help`; it is kept here only for `voting-power`/`stake`/`delegate`, which have no `aitbc governance` equivalent.

Live two-node validation so far has proven `aitbc governance status`. Treat propose/vote/execute as command-shaped plays against a running governance service; they are not yet a closed on-chain parameter-change cycle (see [DESIGN_CYCLE.md](../DESIGN_CYCLE.md) P1.7).

### Use Case

A network participant wants to propose a parameter change (e.g., adjusting the block gas limit), gather votes from stakeholders during the voting period, and execute the proposal once it passes.

### What You'll Learn

- How to inspect the live governance service with `aitbc governance status`
- How to propose, vote, and execute through `aitbc governance` (canonical service path)
- How to stake and delegate voting power via the deprecated `aitbc operations governance` RPC path (no canonical equivalent)
- How to execute a passed proposal

### Live operator setup

On the live two-node deployment, generate and store a client JWT, set the governance service URL, and ensure `GOVERNANCE_REQUIRE_EXECUTION_TIMELOCK` is not disabled in production. See CLI live setup documentation.

---

## Prerequisites

### Knowledge Required

- Basic familiarity with the `aitbc` CLI (see [Scenario 01 Wallet Basics](./01_wallet_basics.md))
- A wallet created in the AITBC keystore (see [Scenario 01](./01_wallet_basics.md))

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`

### Setup Required

- A running blockchain node reachable at `http://localhost:8202` (RPC)
- A wallet JSON file in `~/.aitbc/wallets/<wallet_name>.json`
- The governance service reachable at `http://localhost:8105`

---

## Step-by-Step Workflow

### Step 0: Check the governance service

```bash
aitbc governance status
aitbc governance list
```

**Expected output:** an operational summary from port 8105 (live on the hub). An empty proposal list is fine.

### Step 1: Create a Governance Proposal

Create a new proposal via the governance service. `aitbc governance propose` takes a title, description, and a proposer profile ID; the service assigns the proposal ID. The category defaults to `general` and the voting period defaults to 7 days.

```bash
aitbc governance propose \
    --title "Increase Block Gas Limit to 30M" \
    --description "Proposal to raise the block gas limit from 15M to 30M to support higher throughput" \
    --type "parameter_change" \
    --category "parameter_change" \
    --proposer-id mywallet \
    --proposer-address 0xabc123... \
    --voting-days 7
```

**Expected output** (the returned `proposal_id` is used by all later steps):

```
Proposal ID          prop-001
Title                Increase Block Gas Limit to 30M
Category             parameter_change
Type                 parameter_change
Voting Starts        2026-06-25T10:00:00Z
Voting Ends          2026-07-02T10:00:00Z
Status               active
```

### Step 2: Retrieve Proposal Details

Check the current state of a proposal, including vote tallies and status.

```bash
aitbc governance get --proposal-id prop-001
```

**Expected output:**

```
Proposal ID          prop-001
Title                Increase Block Gas Limit to 30M
Description          Proposal to raise the block gas limit from 15M to 30M...
Category             parameter_change
Status               active
Voting Starts        2026-06-25T10:00:00Z
Voting Ends          2026-07-02T10:00:00Z
Votes For            0
Votes Against        0
Votes Abstain        0
Total Voting Power   0
```

### Step 3: Cast a Vote

Vote on a proposal through the governance service. The `--vote` option accepts `for`, `against`, or `abstain`; `--voter-address` binds the vote to an on-chain wallet for voting power.

```bash
# Vote in favor of the proposal
aitbc governance vote \
    --proposal-id prop-001 \
    --voter-id mywallet \
    --voter-address 0xabc123... \
    --vote for \
    --reason "Higher gas limit improves throughput for AI workloads"
```

**Expected output:**

```
Vote 'for' cast for proposal prop-001

Proposal ID       prop-001
Voter ID          mywallet
Voter Address     0xabc123...
Vote Type         for
Reason            Higher gas limit improves throughput for AI workloads
Status            accepted
```

```bash
# Vote against the proposal with a different voter
aitbc governance vote \
    --proposal-id prop-001 \
    --voter-id otherwallet \
    --voter-address 0xdef456... \
    --vote against \
    --reason "Concerned about state bloat"
```

### Step 4: Check Voting Power

> **Deprecated group:** steps 4–6 use `aitbc operations governance`, which is deprecated and hidden from `aitbc --help`. `voting-power`, `stake`, and `delegate` have no `aitbc governance` equivalent; they talk to the blockchain RPC directly.

Query the voting power for a specific address before casting a vote.

```bash
aitbc operations governance voting-power --address 0xabc123def456...
```

**Expected output:**

```
Address             0xabc123def456...
Voting Power        1500
Delegated Power     0
Staked Tokens       1500
Lock Period Days    60
```

### Step 5: Stake Tokens for Enhanced Voting Power

Stake tokens to increase your voting power. The lock period must be at least 30 days.

```bash
aitbc operations governance stake \
    --address 0xabc123def456... \
    --amount 2000 \
    --lock-days 90
```

**Expected output:**

```
Staked 2000 tokens for 90 days

Staker Address      0xabc123def456...
Amount              2000
Lock Period Days    90
Voting Power Gain   2000
Status              staked
```

### Step 6: Delegate Voting Power

Delegate your voting power to another address if you prefer not to vote directly.

```bash
aitbc operations governance delegate \
    --delegator 0xabc123def456... \
    --delegate 0xdelegate789... \
    --amount 1000
```

**Expected output:**

```
Delegated 1000 voting power from 0xabc123def456... to 0xdelegate789...

Delegator Address   0xabc123def456...
Delegate Address    0xdelegate789...
Amount              1000
Status              delegated
```

### Step 7: Close the Proposal and Tally Votes

After the voting period ends (or quorum and approval are reached early), close the proposal so it transitions to `succeeded` or `defeated`:

```bash
aitbc governance close --proposal-id prop-001
```

**Expected output:**

```
Proposal closed: prop-001

Proposal ID         prop-001
Status              succeeded
Yes Votes           1000
No Votes            500
Abstain Votes       100
```

### Step 8: Execute a Passed Proposal

Once the voting period ends and the proposal passes, execute it to enact the changes.

```bash
aitbc governance execute --proposal-id prop-001
```

**Expected output:**

```
Executed proposal prop-001

Proposal ID         prop-001
Status              executed
Execution Result    success
Transaction Hash    0xexec123...
```

---

## Code Examples Using Agent SDK

### Example 1: Agent Participates in Governance via CLI Subprocess

The `aitbc_agent` SDK does not expose a direct governance API, but agents can participate in governance by invoking the real `aitbc` CLI through subprocess calls. This approach keeps the agent aligned with the canonical CLI command surface.

```python
import asyncio
import subprocess
import json
from aitbc_agent import Agent, AgentCapabilities

async def main():
    agent = Agent.create(
        name="Governance Agent",
        agent_type="processing",
        capabilities={"compute_type": "processing", "max_concurrent_jobs": 1},
    )

    # Register the agent first
    await agent.register()

    # Create a governance proposal via the real aitbc CLI (service assigns the ID)
    result = subprocess.run(
        [
            "aitbc", "governance", "propose",
            "--title", "Reduce Transaction Fee to 0.001 AIT",
            "--description", "Lower fees to encourage microtransactions",
            "--type", "parameter_change",
            "--proposer-id", "mywallet",
            "--voting-days", "5",
            "--format", "json",
        ],
        capture_output=True, text=True,
    )
    print("Proposal created:", result.stdout)
    proposal_id = json.loads(result.stdout)["proposal_id"]

    # Cast a vote via the real aitbc CLI
    vote_result = subprocess.run(
        [
            "aitbc", "governance", "vote",
            "--proposal-id", proposal_id,
            "--voter-id", "mywallet",
            "--vote", "for",
            "--reason", "Lower fees benefit AI microtransactions",
            "--format", "json",
        ],
        capture_output=True, text=True,
    )
    print("Vote cast:", vote_result.stdout)

asyncio.run(main())
```

### Example 2: Monitor Proposal Status

An agent can poll proposal status to decide when to execute a passed proposal.

```python
import subprocess
import json
import time

def get_proposal_status(proposal_id: str) -> dict:
    """Fetch proposal details via the real aitbc CLI."""
    result = subprocess.run(
        [
            "aitbc", "governance", "get",
            "--proposal-id", proposal_id, "--format", "json",
        ],
        capture_output=True, text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return json.loads(result.stdout)
    return {}

def wait_for_proposal_pass(proposal_id: str, timeout: int = 300) -> bool:
    """Poll until the proposal status is 'passed' or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        proposal = get_proposal_status(proposal_id)
        status = proposal.get("status", "unknown")
        print(f"Proposal {proposal_id} status: {status}")
        if status == "passed":
            return True
        if status in ("rejected", "failed"):
            return False
        time.sleep(10)
    return False

# Usage
if wait_for_proposal_pass("prop-002"):
    subprocess.run(["aitbc", "governance", "execute", "--proposal-id", "prop-002"])
    print("Proposal executed!")
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Inspect the live governance service with `aitbc governance status` / `list`
- Create proposals and cast votes with `aitbc governance propose` / `vote` (canonical service path)
- Stake tokens and delegate voting power via the deprecated `aitbc operations governance` RPC path
- Execute a passed proposal

---

## Validation

Verify that the governance workflow completed successfully:

```bash
aitbc governance status
aitbc governance list
aitbc governance get --proposal-id prop-001
```

---

## Related Resources

- [Governance Documentation](../governance/README.md)
- [Agent SDK Quick Start](../agent-sdk/QUICK_START_GUIDE.md)
- [Next Scenario: Analytics Collection](./18_analytics_collection.md)

---

*Last updated: 2026-08-21*
*Version: 1.3*
