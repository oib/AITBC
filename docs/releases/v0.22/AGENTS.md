# v0.22 Open Tasks — Agent Split

This document records the remaining open findings from the v0.22 re-verification
pass and assigns them to Agent A or Agent B for continued work.

See [`release.log`](./release.log) for the full ledger, evidence, and verification
commands.

## Agent A — Core / Shared / Bridge / Infrastructure

Focus: `aitbc/`, `apps/blockchain-node`, `apps/blockchain-event-bridge`,
`apps/blockchain-explorer`, `contracts/`, ops/scripts, shared packages, and
infrastructure-wide findings.

- **CORE** — CORE-02/04/08/09/10/11/12/13/15/16/18/19/20/21/22/25/26/28/29
- **APP-64** — `blockchain-event-bridge` checkpoint reset and reorg handling
- **Contracts** — SC-05/06/08/09/10/11/12/14
- **Ops** — OPS-03/04/06/07/08/09/10/12/14/15/16/17/18
- **Packages** — PKG-01 through PKG-14
- **Tests/docs** — TEST-02 through TEST-08; DOC-02 through DOC-07

## Agent B — Apps / CLI / Service Layer

Focus: `apps/*` (except core blockchain/bridge/explorer), `cli/`, and
service-level auth/endpoint findings.

- **APP-54** — `simple_exchange` on stdlib `http.server` and fail-open API key
- **CLI** — CLI-02/03/05/06/07/08/09/10/13

## Notes

- APP-54 and APP-64 are the only remaining concrete application-level findings.
- All other APP findings tracked in `v0.22/release.log` are closed as of this
  re-verification pass.
- Cross-area items (e.g. CLI-13, TEST-08) may require both agents to coordinate.
