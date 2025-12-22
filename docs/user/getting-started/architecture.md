---
title: Architecture
description: Technical architecture of the AITBC platform
---

# Architecture

## Overview

AITBC consists of several interconnected components that work together to provide a secure and efficient AI computing platform.

## Components

### Coordinator API
The central service managing jobs, marketplace operations, and coordination.

### Blockchain Nodes
Maintain the distributed ledger and execute smart contracts.

### Wallet Daemon
Manages cryptographic keys and transactions.

### Miners/Validators
Execute AI computations and secure the network.

### Explorer
Browse blockchain data and transactions.

## Data Flow

```mermaid
sequenceDiagram
    participant U as User
    participant C as Coordinator
    participant M as Marketplace
    participant B as Blockchain
    participant V as Miner
    
    U->>C: Submit Job
    C->>M: Find Offer
    M->>B: Create Transaction
    V->>B: Execute Job
    V->>C: Submit Results
    C->>U: Return Results
```

## Security Model

- Cryptographic proofs for all computations
- Multi-signature validation
- Secure enclave support
- Privacy-preserving techniques
