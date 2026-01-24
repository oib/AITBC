---
name: blockchain-operations
description: Comprehensive blockchain node management and operations for AITBC
version: 1.0.0
author: Cascade
tags: [blockchain, node, mining, transactions, aitbc, operations]
---

# Blockchain Operations Skill

This skill provides standardized procedures for managing AITBC blockchain nodes, verifying transactions, and optimizing mining operations.

## Overview

The blockchain operations skill ensures reliable management of all blockchain-related components including node synchronization, transaction processing, mining operations, and network health monitoring.

## Capabilities

### Node Management
- Node deployment and configuration
- Sync status monitoring
- Peer management
- Network diagnostics

### Transaction Operations
- Transaction verification and debugging
- Gas optimization
- Batch processing
- Mempool management

### Mining Operations
- Mining performance optimization
- Pool management
- Reward tracking
- Hash rate optimization

### Network Health
- Network connectivity checks
- Block propagation monitoring
- Fork detection and resolution
- Consensus validation

## Common Workflows

### 1. Node Health Check
- Verify node synchronization
- Check peer connections
- Validate consensus rules
- Monitor resource usage

### 2. Transaction Debugging
- Trace transaction lifecycle
- Verify gas usage
- Check receipt status
- Debug failed transactions

### 3. Mining Optimization
- Analyze mining performance
- Optimize GPU settings
- Configure mining pools
- Monitor profitability

### 4. Network Diagnostics
- Test connectivity to peers
- Analyze block propagation
- Detect network partitions
- Validate consensus state

## Supporting Files

- `node-health.sh` - Comprehensive node health monitoring
- `tx-tracer.py` - Transaction tracing and debugging tool
- `mining-optimize.sh` - GPU mining optimization script
- `network-diag.py` - Network diagnostics and analysis
- `sync-monitor.py` - Real-time sync status monitor

## Usage

This skill is automatically invoked when you request blockchain-related operations such as:
- "check node status"
- "debug transaction"
- "optimize mining"
- "network diagnostics"

## Safety Features

- Automatic backup of node data before operations
- Validation of all transactions before processing
- Safe mining parameter adjustments
- Rollback capability for configuration changes

## Prerequisites

- AITBC node installed and configured
- GPU drivers installed (for mining operations)
- Proper network connectivity
- Sufficient disk space for blockchain data
