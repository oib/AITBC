# blockchain-rpc

## Status

**active**

## Description

Blockchain RPC API service exposing the blockchain node's JSON-RPC interface on port 8202. Separate systemd unit from blockchain-node for independent scaling and restart. Source code lives within `apps/blockchain-node/src/aitbc_chain/app.py`. Other services depend on this for chain queries (blockchain-explorer, bridge-monitor, blockchain-sync).

## Node Type

hub, island

## GPU Required

no

## Service

`aitbc-blockchain-rpc.service` — enabled and running. Exec: `uvicorn aitbc_chain.app:app --host 127.0.0.1 --port 8202`.

## Core Service

yes

## Source

Bundled inside `apps/blockchain-node/src/`. This directory is a placeholder for future code separation.

## Notes

- **Not legacy** — actively depended on by blockchain-explorer, bridge-monitor, and blockchain-sync.
- `aitbc-blockchain-rpc.service` is a separate unit that starts after `aitbc-blockchain-node.service`.

---
*Last updated: 2026-06-17*
