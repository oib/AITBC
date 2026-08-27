# Bug Fixes - v0.4.6

**Release**: v0.4.6
**Date**: June 4, 2026
**Status**: ✅ Implemented

## Overview

AITBC v0.4.6 resolves critical issues in test scripts, blockchain RPC endpoints, and agent coordinator polling.

## Test Script Fixes

- ✅ Fixed hardcoded `FOLLOWER_NODE="aitbc"` in `25_comprehensive_testing.sh` to respect environment configuration
- ✅ Removed `set -e` from `25_comprehensive_testing.sh` to allow script to continue on test failures
- ✅ Fixed emoji UTF-8 bytes in `39_agent_communication_testing.sh` causing bash parsing errors
- ✅ Replaced heredocs with direct JSON strings in `39_agent_communication_testing.sh` to avoid nested heredoc issues
- ✅ Added localhost GPU tests to `25_comprehensive_testing.sh` for single-node setups with local GPU
- ✅ Fixed file paths in `25_comprehensive_testing.sh` (bulk sync, health monitoring, security scripts)
- ✅ Fixed database path in `25_comprehensive_testing.sh` to match `ait-hub.aitbc.bubuit.net` chain directory
- ✅ Removed firewall status test from `25_comprehensive_testing.sh` (neither ufw nor iptables installed)
- ✅ Fixed RPC endpoint paths in `25_comprehensive_testing.sh`:
  - `/rpc/getBalance/{address}` → `/rpc/balance/{address}`
  - `/rpc/sendTx` → `/rpc/transaction`
- ✅ Fixed transaction payload in `25_comprehensive_testing.sh` to include required `signature` field and correct field names (`from`/`to`)

## Blockchain RPC Fixes

- ✅ Added `/rpc/info` endpoint to return blockchain information (chain_id, height, total_transactions, total_accounts, genesis_params)
- ✅ Fixed transaction endpoint to accept proper `TransactionRequest` schema with required fields

## Agent Coordinator Fixes

- ✅ Fixed Hermes polling daemon endpoint from `/api/v1/agent/messages/{agent_id}` to `/api/v1/agent/messages/inbox?agent_id={agent_id}`
- ✅ Resolved 404 errors in agent-coordinator polling logs

---

*Last Updated: 2026-06-04*
