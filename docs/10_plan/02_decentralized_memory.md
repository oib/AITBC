# Phase 2: Decentralized AI Memory & Storage

## Overview
OpenClaw agents require persistent memory to provide long-term value, maintain context across sessions, and continuously learn. Storing large vector embeddings and knowledge graphs on-chain is prohibitively expensive. This phase integrates decentralized storage solutions (IPFS/Filecoin) tightly with the AITBC blockchain to provide verifiable, persistent, and scalable agent memory.

## Objectives
1. **IPFS/Filecoin Integration**: Implement a storage adapter service to offload vector databases (RAG data) to IPFS/Filecoin.
2. **On-Chain Data Anchoring**: Link the IPFS CIDs (Content Identifiers) to the agent's smart contract profile ensuring verifiable data lineage.
3. **Shared Knowledge Graphs**: Enable an economic model where agents can buy/sell access to high-value, curated knowledge graphs.

## Implementation Steps

### Step 2.1: Storage Adapter Service (Python)
- Integrate `ipfshttpclient` or `web3.storage` into the existing Python services.
- Update `AdaptiveLearningService` to periodically batch and upload recent agent experiences and learned policy weights to IPFS.
- Store the returned CID.

### Step 2.2: Smart Contract Updates for Data Anchoring
- Update `GovernanceProfile` or create a new `AgentMemory.sol` contract.
- Add functions to append new CIDs representing the latest memory state of the agent.
- Implement ZK-Proofs (using the existing `ZKReceiptVerifier`) to prove that a given CID contains valid, non-tampered data without uploading the data itself to the chain.

### Step 2.3: Knowledge Graph Marketplace
- Create `KnowledgeGraphMarket.sol` to allow agents to list their CIDs for sale.
- Implement access control where paying the fee via `AITBCPaymentProcessor` grants decryption keys to the buyer agent.
- Integrate with `MultiModalFusionEngine` so agents can fuse newly purchased knowledge into their existing models.

## Expected Outcomes
- Infinite, scalable memory for OpenClaw agents without bloating the AITBC blockchain state.
- A new revenue stream for "Data Miner" agents who specialize in crawling, indexing, and structuring high-quality datasets for others to consume.
- Faster agent spin-up times, as new agents can initialize by purchasing and downloading a pre-trained knowledge graph instead of starting from scratch.
