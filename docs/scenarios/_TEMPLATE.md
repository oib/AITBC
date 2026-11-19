# [SCENARIO TITLE]

**Level**: Beginner
**Prerequisites**: [List prerequisites, e.g. "Scenario 01 Wallet Basics"]
**Estimated Time**: [X minutes]
**Last Updated**: 2026-08-21
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > [Scenario Name]

---

## See Also

- **Previous Scenario**: Link to previous scenario
- **Next Scenario**: Link to next scenario
- **Agent SDK**: [Agent SDK Documentation](../agent-sdk/README.md)
- **Feature Documentation**: [Link to relevant feature docs]

---

## Scenario Overview

[Brief description of what this scenario demonstrates and what the agent will accomplish.]

### Use Case

[Describe the real-world use case this scenario addresses.]

### What You'll Learn

- [Learning objective 1]
- [Learning objective 2]
- [Learning objective 3]

---

## Prerequisites

### Knowledge Required

- [Prerequisite knowledge 1]
- [Prerequisite knowledge 2]

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`
- [Any other tools]

### Setup Required

- [Setup step 1]
- [Setup step 2]

---

## Amount units — check before every money flag

AITBC mixes three amount conventions; **verify the flag's `--help` text
before writing an amount into a play** — the docs have shipped both
wrong readings before (#2280):

| Convention | `--help` signature | Example commands |
|---|---|---|
| AIT decimal | `type=DECIMAL`, "Amount of AIT" | `wallet send/stake/liquidity-stake/earn/request-payment/spend/multisig-propose`, `exchange add-liquidity`, `ipfs island subscribe`, `stake`/`unstake`, `market exchange deposit-eth/withdraw-eth` |
| Raw compute units | `type=int`, "compute-units" | `bridge lock --amount`, `trade create --amount`, `crosschain` amounts (`UNITS_PER_AIT = 36_000_000`) |
| Free-form / service-side | `type=TEXT`/`INTEGER` | `bond create/top-up`, `agent-wallet stake`, `operations governance stake/delegate` (deprecated path) |

Never copy a `36_000_000`-style raw-unit literal into an AIT-decimal flag —
it attempts a 36-million-AIT spend.

## Step-by-Step Workflow

Every operator step uses the `aitbc` CLI. Curl, `journalctl`, and `pytest` belong only under **Validation**.

### Step 1: [Step Title]

[Description of step 1]

```bash
# Command examples using the real `aitbc` CLI
aitbc <command> <subcommand> [options]
```

**Expected output:**

```
[Sample output]
```

### Step 2: [Step Title]

[Description of step 2]

```bash
# Command examples
```

[Continue with additional steps as needed]

---

## Code Examples Using Agent SDK

### Example 1: [Title]

```python
from aitbc_agent import Agent, AgentIdentity, AgentCapabilities

# Real SDK usage grounded in the current aitbc_agent package
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- [Outcome 1]
- [Outcome 2]
- [Outcome 3]

---

## Validation

[How to validate the scenario succeeded — commands to check state]

```bash
# Validation commands
```

---

## Related Resources

- [Related docs/resources]
- [Next scenarios]

---

*Last updated: 2026-08-21*
*Version: 1.0*
