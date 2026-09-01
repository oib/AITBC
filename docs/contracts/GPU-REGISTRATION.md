# GPU registration on the AITBC chain

> Moved out of `contracts/contracts/GPURegistry.sol` (SC-14). That file contained no
> Solidity — only this guidance — but sat in the compiled contracts tree, where it read as
> a deployable contract and could be picked up by a deploy script by mistake.

AITBC does not use an Ethereum-style smart contract for GPU registration. The chain uses a
custom transaction system with typed transactions, so registration belongs there rather
than in a contract.

Register GPUs as a `GPU_REGISTER` transaction type with an appropriate payload.

See `apps/blockchain-node/src/aitbc_chain/rpc/transactions.py` for the transaction types
already defined (`TRANSFER`, `FAUCET`, `GPU_REGISTER`, …).

## To enable blockchain GPU registration

1. Add the `GPU_REGISTER` transaction type to the blockchain node.
2. Update the GPU service to submit `GPU_REGISTER` transactions.
3. Change the CLI to use the blockchain transaction for GPU registration.
