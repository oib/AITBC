# Preflight Checklist (Before Implementation)

Use this checklist before starting Stage 20 development work.

## Tools & Versions
- [x] Circom v2.2.3+ installed (`circom --version`)
- [x] snarkjs installed globally (`snarkjs --help`)
- [x] Node.js + npm aligned with repo version (`node -v`, `npm -v`)
- [x] Vitest available for JS SDK tests (`npx vitest --version`)
- [ ] Python 3.13+ with pytest (`python --version`, `pytest --version`)
- [ ] NVIDIA drivers + CUDA installed (`nvidia-smi`, `nvcc --version`)
- [ ] Ollama installed and running (`ollama list`)

## Environment Sanity
- [x] `.env` files present/updated for coordinator API
- [x] Virtualenvs active (`.venv` for Python services)
- [x] npm/yarn install completed in `packages/js/aitbc-sdk`
- [x] GPU available and visible via `nvidia-smi`
- [x] Network access for model pulls (Ollama)

## Baseline Health Checks
- [ ] `npm test` in `packages/js/aitbc-sdk` passes
- [ ] `pytest` in `apps/coordinator-api` passes
- [ ] `pytest` in `apps/blockchain-node` passes
- [ ] `pytest` in `apps/wallet-daemon` passes
- [ ] `pytest` in `apps/pool-hub` passes
- [x] Circom compile sanity: `circom apps/zk-circuits/receipt_simple.circom --r1cs -o /tmp/zkcheck`

## Data & Backup
- [ ] Backup current `.env` files (coordinator, wallet, blockchain-node)
- [ ] Snapshot existing ZK artifacts (ptau/zkey) if any
- [ ] Note current npm package version for JS SDK

## Scope & Branching
- [ ] Create feature branch for Stage 20 work
- [ ] Confirm scope limited to 01–04 task files plus testing/deployment updates
- [ ] Review success metrics in `00_nextMileston.md`

## Hardware Notes
- [ ] Target consumer GPU list ready (e.g., RTX 3060/4070/4090)
- [ ] Test host has CUDA drivers matching target GPUs

## Rollback Ready
- [ ] Plan for reverting npm publish if needed
- [ ] Alembic downgrade path verified (if new migrations)
- [ ] Feature flags identified for new endpoints

Mark items as checked before starting implementation to avoid mid-task blockers.
