# Fleet `IS_HUB` semantics (main vs island)

Parent: #1978 FLEET-CONFIG-DRIFT-1 finding F2; row STALE-IDENTITY-FLAGS-1 (#1987).

`IS_HUB` is the **island membership / P2P discovery** flag on
`BlockchainSettings.is_hub` (`apps/blockchain-node/src/aitbc_chain/config.py`).
It is **not** the main-chain proposer role, `MARKET_ROLE=hub`, or
`NODE_ROLE=hub` (pool-hub CLI still keys off `NODE_ROLE` in
`/etc/aitbc/node.env`).

## Main chain (`blockchain.env`, `node.env`)

| Host | Intended `IS_HUB` | Rationale |
|------|-------------------|-----------|
| **hub** (promoted proposer + island join RPC) | `true` | Directory hub for island join / P2P island bookkeeping |
| **hub1** (demoted follower) | `false` or unset | Follower; stale pre-demotion `true` is drift |
| **node0, node1, node2** | unset | Customer/shop/validator nodes are not island directory hubs |

Loaded by `aitbc-blockchain-node`, RPC, and P2P when those units run on
the main chain.

## Island chain (`blockchain-island.env`, `node-island.env`)

Used only by `aitbc-*-island` units (`%N.env` isolation — see
[companion island deploy](companion-island-deploy.md)).

**`bc-2-island-1`** (hub1 + node1, 2-of-2 PBFT exercise):

- Both validators run island units today with `IS_HUB=true` in
  `blockchain-island.env`. This is a **symmetric two-validator mesh**:
  there is no separate “join-only” follower; P2P tolerates dual-hub when
  both sides advertise `is_hub` (see `p2p_network.py` island-id checks).
- **Do not** copy main-chain `IS_HUB=true` onto hub1’s `blockchain.env` /
  `node.env`; island hub intent lives only under the island env set.

## `EXTRA_SERVICES` vs `DISABLED_SERVICES` (demoted hub1)

`link-systemd.sh` / `update.sh` treat `DISABLED_SERVICES` as authoritative
over `EXTRA_SERVICES` (`scripts/testing/test_disabled_services_guard.sh`).
Demoted **hub1** should not list demoted units in **both** lists:

- Keep `DISABLED_SERVICES` naming units that must stay off (market,
  exchange, coordinator-api, api-gateway, p2p, event-bridge,
  agent-coordinator).
- Trim `EXTRA_SERVICES` to units that **actually run** on hub1 (e.g.
  `aitbc-island-ipfs` only). Overlap is stale residue, not an override
  pattern to preserve long-term.

## Verification

```bash
# Main chain — followers must not advertise hub
grep -h '^IS_HUB=' /etc/aitbc/blockchain.env /etc/aitbc/node.env 2>/dev/null || true

# Island — only under island env files on island hosts
grep '^IS_HUB=' /etc/aitbc/blockchain-island.env 2>/dev/null || true

# hub1 demotion hygiene
grep -E '^(EXTRA_SERVICES|DISABLED_SERVICES)=' /etc/aitbc/node.env
```

After main-chain `IS_HUB` edits on a validator host, restart
`aitbc-blockchain-node` serially (one PBFT validator at a time; heads
equal before the next).
