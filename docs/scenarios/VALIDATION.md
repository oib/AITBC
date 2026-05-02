# Scenario Validation Guide

**Scope**: All scenario documents in `docs/scenarios/`  
**Goal**: Ensure every scenario is tested with scripts that exercise all 3 nodes: `aitbc1`, `aitbc`, and `gitea-runner`.

## 🧭 Node Roles

- **`aitbc1`**
  - Genesis authority node
  - Primary blockchain node for genesis, sync, and chain-state validation

- **`aitbc`**
  - Follower / local integration node
  - Used for cross-node transaction, wallet, and application-flow checks

- **`gitea-runner`**
  - CI / automation node
  - Used to verify the scenario can run in the same environment as the workflows

## 🧪 Canonical Validation Scripts

Use these scripts as the baseline when validating scenarios:

- **Bootstrap the multi-node environment**
  - `scripts/workflow/setup_multinode_blockchain.sh`

- **Two-node blockchain smoke tests**
  - `scripts/workflow/25_comprehensive_testing.sh`
  - `scripts/workflow/31_consensus_testing.sh`

- **Full 3-node scenario harness**
  - `scripts/workflow/44_comprehensive_multi_node_scenario.sh`

- **Multi-Chain Island Architecture test**
  - `scripts/workflow/46_multi_chain_island_test.sh`

## ✅ Validation Rule for Scenario Docs

Every scenario document should include a short validation section that answers:

- **Which script validates this scenario?**
- **Which of the 3 nodes are exercised?**
- **What success criteria should be checked?**

If a scenario is node-specific, note where each step runs:

- **`aitbc1`** for genesis, primary chain, or authority actions
- **`aitbc`** for local/follower actions
- **`gitea-runner`** for CI-side execution or third-node coverage

## 📝 Recommended Scenario Validation Block

Add a section like this to each scenario document:

````markdown
## 🧪 Validation

Validate this scenario with the 3-node harness:

```bash
bash scripts/workflow/44_comprehensive_multi_node_scenario.sh
```

**Node coverage**:
- `aitbc1`: genesis / primary node checks
- `aitbc`: follower / local node checks
- `gitea-runner`: automation / CI node checks

**Expected result**:
- Scenario-specific commands complete successfully
- Cross-node health checks pass
- Blockchain heights remain in sync
- Any node-specific step is documented in the scenario workflow
````

## 🔁 Workflow for Scenario Testing

1. Bring up the multi-node environment.
2. Run the scenario-specific commands from the document.
3. Execute the 3-node validation harness.
4. Confirm the scenario behaves consistently on all 3 nodes.
5. Record any node-specific exceptions in the scenario document.

## 📌 Notes

- The 3-node script is the preferred canonical validation path.
- The smaller blockchain scripts are still useful for focused smoke tests.
- Scenario docs should link back here so the validation approach stays consistent.
