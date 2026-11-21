# Contract Deploy & Call

**Level**: Intermediate
**Prerequisites**: Scenario 02 Transaction Sending
**Estimated Time**: 15 minutes
**Last Updated**: 2026-11-21
**Version**: 1.1

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Contract Deploy & Call

---

## See Also

- **Previous Scenario**: [Developer Registry](./72_developer_registry.md)
- **Next Scenario**: [Confidential Payments](./74_confidential_payments.md)
- **Feature Documentation**: `cli/aitbc_cli/commands/contract.py`

---

## Scenario Overview

> **Registry write, not a chain transaction:** `contract deploy` does
> **not** submit a transaction — it inserts a `SmartContract` row into
> the serving node's chain database and derives a deterministic address
> (`hash(deployer:name:timestamp)`). No gas is spent, no block is
> produced, and the row is **node-local**: it does not replicate to
> other fleet nodes. `contract call` reads that row's stored `state`
> blob — there is no EVM execution, no method dispatch, and no revert
> path. Both go through the blockchain RPC (`--rpc-url`, default
> `http://localhost:8202`).

This scenario covers the generic `aitbc contract` escape hatch for
registering and reading contract entries by name/address. Treat it as a
node-local contract registry, not as EVM deployment — real contract
deployment on this fleet is the Sepolia `AIPowerRental` path
(Scenario 59), not this surface.

### Use Case

An operator registers a contract entry on a node or reads back stored
state during debugging, without writing a bespoke script.

### What You'll Learn

- `contract deploy` — register a named contract entry through the node RPC
- `contract call` — read a stored state value by method name
- `contract list` — enumerate entries visible on the serving node

---

## Prerequisites

- A reachable blockchain RPC (`8202`)
- No funded account is needed: the CLI sends only the contract name, so
  the RPC defaults `deployer` to `0x0000000000000000000000000000000000000000`
- For `call`: the contract address as returned by `deploy`/`list`

---

## Steps

### 1. Register an entry

```bash
aitbc contract deploy --contract-name MyContract --rpc-url http://localhost:8202
```

Returns a deterministic `contract_address` and `status: deployed`. The
entry exists only in the serving node's chain DB — `contract list` on
any other node will not show it.

### 2. Read stored state

```bash
aitbc contract call --contract-address 0x<contract> --method 'balanceOf' \
    --args '["0x<account>"]'
```

`--args` is accepted but does not affect the result: `call` returns
`contract.state[method]` verbatim (`null` when the method was never
written) plus the ABI entry if one was stored. `state` is populated only
by paths that write it — `deploy` stores `{}`, so a fresh entry answers
`result: null` for every method.

### 3. List entries on this node

```bash
aitbc contract list
```

---

## Cost Table

| Step | Spend |
|---|---|
| `contract deploy` | 0 AIT — DB row only, no transaction |
| `contract call` | 0 AIT — state read only |
| `contract list` | 0 AIT |

---

## Verification

- `deploy` returns `success: true` with a deterministic address; the
  same name on the same node at a different timestamp yields a different
  address.
- `contract list` on the **serving node** shows the new entry; other
  nodes show nothing (no replication).
- `call` returns `success: true` with `result` equal to the stored
  state value (`null` for a fresh entry); an unknown address returns
  `Contract not found`.

## Troubleshooting

- `Contract not found` — the address is not in this node's registry, or
  you are querying a different node than the one that served `deploy`.
- `RPC unreachable` — wrong `--rpc-url` or node stopped.
