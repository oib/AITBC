# Retired HTLC Settlement

The Python-native HTLC wrapper was removed after the inter-chain settlement
rail was retired in #2385. Node settlement mutations and the trading
`lock-escrow` and `settle` endpoints still return HTTP 410. Legacy settlement
reads and historical replay remain supported.

The separate [CrossChainAtomicSwap Solidity contract](../../contracts/contracts/CrossChainAtomicSwap.sol)
remains in the repository. It is not a replacement for the retired AITBC
node and trading settlement endpoints.

## Python SDK compatibility

The public `aitbc.settlement.htlc` helpers are deprecated for new
integrations but remain importable. Use `SettlementClient` to inspect
legacy escrow status and proofs. Its remaining write wrappers are
compatibility shims for routes that return HTTP 410.
