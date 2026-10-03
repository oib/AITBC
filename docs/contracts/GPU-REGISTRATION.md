# GPU registration on the AITBC chain

> Moved out of `contracts/contracts/GPURegistry.sol` (SC-14). That file contained no
> Solidity — only this guidance — but sat in the compiled contracts tree, where it read as
> a deployable contract and could be picked up by a deploy script by mistake.

AITBC does not use an Ethereum-style smart contract for GPU registration. The chain uses a
custom transaction system with typed transactions, so registration belongs there rather
than in a contract.

Register GPUs as a `GPU_REGISTER` transaction type with an appropriate payload.

See `apps/blockchain-node/src/aitbc_chain/rpc/transactions.py` for the transaction types
already defined (`TRANSFER`, `GPU_REGISTER`, …).

## To enable blockchain GPU registration

1. Add the `GPU_REGISTER` transaction type to the blockchain node.
2. Update the GPU service to submit `GPU_REGISTER` transactions.
3. Change the CLI to use the blockchain transaction for GPU registration.

## Taking a registration out of service

A GPU's registrant removes it from the market with a `GPU_DEREGISTER` transaction
(`aitbc gpu-onchain deregister --gpu-id <id> --wallet <registrant wallet>`). The payload is
`{"gpu_id": "<id>"}`, the value is 0, and the fee is the default transaction fee.

- It sets the registration's `status` to `deactivated` and keeps the row, so `registered_by`
  still stops anyone else from taking the id over and the sealed `GPU_REGISTER` history stays
  joined to it. The registrant re-registers the same `gpu_id` to reactivate it.
- Only the registrant can send it. A GPU that is unknown, already deactivated, or recorded
  without a registrant is refused.
- A deactivated GPU takes no new `GPU_ALLOCATE`. Existing allocations are not touched and are
  not a precondition (nothing completes an allocation today).
- The market service's default offer listing leaves deactivated GPUs out; `status=deactivated`
  lists them.
- Active only from `STATE_TRANSITION_V10_HEIGHT` (see
  [ENVIRONMENT_CONFIGURATION.md](../blockchain/ENVIRONMENT_CONFIGURATION.md)); the height is
  baked into `config.py` as the default 32100 since the fleet-wide activation on
  2026-10-02, and an env value only overrides that default. Below the height the node
  refuses the transaction at admission, and a copy sealed below it replays as a plain
  transfer. Every node must run a build that knows the type before the height, or
  `gpu_registration` diverges between nodes.
- `aitbc gpu unregister` is a different command: it edits the local GPU service and does not
  touch the chain. The coordinator API's own GPU registry (`/v1/market/gpu/*`) is a separate
  table and is not affected by a chain deactivation.
