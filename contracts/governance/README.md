# AITBC Governance Contracts

Foundry project containing the AITBC governance and agent-coordination
contract set. This is a standalone subproject of the AITBC monorepo — its
dependencies are vendored under `lib/` (git submodules: `forge-std` and
`openzeppelin-contracts`, pinned in `foundry.lock`).

## Contracts

| Contract | File | Purpose |
|----------|------|---------|
| `AITBCGovernanceToken` | `src/AITBCGovernanceToken.sol` | ERC-20 governance token with staking-based voting power |
| `AITBCVoting` | `src/AITBCVoting.sol` | Simple proposal/voting contract on top of the governance token |
| `AgentDAO` | `src/AgentDAO.sol` | OpenZeppelin Governor-based DAO (settings, counting, votes, quorum fraction, timelock) with agent-wallet registry, proposal bonds, voting snapshots and multi-sig gates for critical proposal types |
| `GPUStaking` | `src/GPUStaking.sol` | GPU resource staking pools with reward distribution and provider reputation |
| `GovernanceAgentWallet` | `src/GovernanceAgentWallet.sol` | Smart wallet letting AI agents register with the `AgentDAO` and vote autonomously per a configurable strategy |
| `SafeMath` | `src/SafeMath.sol` | Vendored OpenZeppelin v4 SafeMath library (removed upstream in v5; kept for `GPUStaking`/`AgentDAO` arithmetic) |

## Build & test

Requires [Foundry](https://book.getfoundry.sh/). From this directory:

```shell
forge build    # compile (solc 0.8.24, via_ir, evm cancun — see foundry.toml)
forge test     # run test/*.t.sol suites
```

If `lib/` is empty (fresh clone), populate the pinned submodules first:

```shell
forge install   # or: git submodule update --init --recursive
```

OpenZeppelin contracts resolve via the remapping in `foundry.toml`
(`@openzeppelin/contracts/=lib/openzeppelin-contracts/contracts/`).
