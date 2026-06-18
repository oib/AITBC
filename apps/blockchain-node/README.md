# blockchain-node

## Status

**active**

## Description

Core blockchain node implementing consensus (PoA/PBFT), P2P networking, RPC API, and sync. The foundational layer of the AITBC network. Requires PostgreSQL and Redis.

## Node Type

hub, island

## GPU Required

no

## Service

4 systemd service(s): aitbc-blockchain-node.service, aitbc-blockchain-p2p.service, aitbc-blockchain-rpc.service, aitbc-blockchain-sync.service

## Core Service

yes

## Source

`src/` directory with 89 Python file(s)

---
*Last updated: 2026-06-17*
