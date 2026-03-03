# Phase 1: OpenClaw Autonomous Economics

## Overview
This phase aims to give OpenClaw agents complete financial autonomy within the AITBC ecosystem. Currently, users must manually fund and approve GPU rentals. By implementing autonomous agent wallets and bidding strategies, agents can negotiate their own compute power dynamically based on the priority of the task they are given.

## Objectives
1. **Agent Wallet & Micro-Transactions**: Equip every OpenClaw agent profile with a secure, isolated smart contract wallet (`AgentWallet.sol`).
2. **Bid-Strategy Engine**: Develop Python services that allow agents to assess the current marketplace queue and bid optimally for GPU time.
3. **Multi-Agent Orchestration**: Allow a single user prompt to spin up a "Master Agent" that delegates sub-tasks to "Worker Agents", renting optimal hardware for each specific sub-task.

## Implementation Steps

### Step 1.1: Smart Contract Upgrades
- Create `AgentWallet.sol` derived from OpenZeppelin's `ERC2771Context` for meta-transactions.
- Allow users to set daily spend limits (allowances) for their agents.
- Update `AIPowerRental.sol` to accept signatures directly from `AgentWallet` contracts.

### Step 2.1: Bid-Strategy Engine (Python)
- Create `src/app/services/agent_bidding_service.py`.
- Implement a reinforcement learning model (based on our existing `advanced_reinforcement_learning.py`) to predict the optimal bid price based on network congestion.
- Integrate with the `MarketplaceGPUOptimizer` to read real-time queue depths.

### Step 3.1: Task Delegation & Orchestration
- Update the `OpenClaw Enhanced Service` to parse complex prompts into DAGs (Directed Acyclic Graphs) of sub-tasks.
- Implement parallel execution of sub-tasks by spawning multiple containerized agent instances that negotiate independently in the marketplace.

## Expected Outcomes
- Agents can run 24/7 without user approval prompts for every transaction.
- 30% reduction in average task completion time due to optimal sub-task hardware routing (e.g., using cheap CPUs for text formatting, expensive GPUs for image generation).
- Higher overall utilization of the AITBC marketplace as agents automatically fill idle compute slots with low-priority background tasks.
