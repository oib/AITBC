# MCP tools for the agent-economics RPC surfaces (Refs #657)

> **Status: IMPLEMENTED** — all nine tools land in
> `mcp-server/aitbc_mcp_rpc_tools.py` (`create_agent_stake`,
> `add_agent_stake`, `unbond_agent_stake`, `complete_agent_stake`,
> `deploy_bounty`, `submit_bounty`, `verify_bounty`, `dispute_bounty`,
> `expire_bounty`), thin typed wrappers over the node RPC routes below.
> REST on the node RPC is the canonical surface (operator decision 8B);
> the tools are not a second implementation.

The v17 revival (BNT-1) restored the agent-staking and bounty routes on
the chain node's RPC: they refuse with HTTP 410 while
`state_transition_v17_height` is unset or unreached
(`raise_for_unarmed`, `rpc/retired.py:54`), and every handler requires an
operator signature over the whole request body
(`require_operator_signature`, `rpc/agent_economics_auth.py:32`).

## Route map

One router is mounted at both `/rpc` and `/v1` (`app.py:464-467`);
`/v1/*` is the canonical spelling (`docs/reference/all-routes.md`). The
MCP `blockchain-rpc` service base already ends in `/rpc`
(`cli/aitbc_cli/commands/http.py:36`), so tools pass the bare path — it
lands on the same handlers either way.

| Tool | `blockchain-rpc` path (canonical `/v1/…`) | Seals |
|---|---|---|
| `create_agent_stake` | `agent-staking/stake` | `STAKE_LOCK` |
| `add_agent_stake` | `agent-staking/stake/{stake_id}/add` | `STAKE_LOCK` (top-up) |
| `unbond_agent_stake` | `agent-staking/stake/{stake_id}/unbond` | record → `unbonding` |
| `complete_agent_stake` | `agent-staking/stake/{stake_id}/complete` | `STAKE_RELEASE` |
| `deploy_bounty` | `bounty/deploy` | `BOUNTY_LOCK` |
| `submit_bounty` | `bounty/{bounty_id}/submit` | submission record |
| `verify_bounty` | `bounty/{bounty_id}/verify` | `BOUNTY_PAYOUT` when `verified` |
| `dispute_bounty` | `bounty/{bounty_id}/dispute` | status memo |
| `expire_bounty` | `bounty/{bounty_id}/expire` | `BOUNTY_REFUND` |

Required fields, the signed-`stake_id`/`bounty_id`-must-match-path
bindings, and the 409-until-the-lock-is-funded payout gate live in
`rpc/agent_staking.py` / `rpc/bounty.py` — the tools mirror them as
typed parameters. The three memo routes (`performance`,
`agents/{wallet}/distribute`, `claim-rewards`) are out of scope for this
pass: record-only, no escrow movement.

## Signing — whole-payload keccak canonical-JSON

Every route takes a JSON body whose top-level `signature` authorizes
the rest. The recipe is identical on both sides
(`agent_economics_auth.py:27-29,66-71`; coordinator
`contexts/blockchain/services/blockchain.py:53-70`):

1. Strip `signature` from the body (`signed_body`).
2. `canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))`.
3. `digest = keccak256(canonical)`; sign via eth_keys
   `pk.sign_msg_hash(digest)` with `AGENT_ECONOMICS_OPERATOR_KEY`.
4. Attach `sig.to_hex()` as `signature` and POST.

The node re-verifies against `AGENT_ECONOMICS_OPERATOR_ADDRESS`
(`verify_request_signature`, `rpc/utils.py:213`): 403 on a missing or
bad signature, 503 while the operator address is unset. Reference
implementation: `hub:/root/v17-bounty_cycle.py` (operator-held, not in
the repo).

**Tool shape:** each tool takes the route's unsigned fields as typed
params plus a required `signature: str` — the same shape as
`create_escrow`'s `lock_signature`/`lock_tx`
(`aitbc_mcp_rpc_tools.py:1920-1968`). The tool assembles the body,
attaches the caller's signature, and forwards; producing the signature
stays outside the MCP process (see Key custody).

## Write gate — the existing dry_run/confirm convention

Match `aitbc_mcp_rpc_tools.py` exactly; read-only tools are the default
(`read_only_hint=True`), mutating tools are gated:

- `@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))`
- Params:
  `dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True`,
  `confirm: Annotated[bool, Field(description="Confirm the destructive action.")] = False`,
  plus the usual `role` / `host` overrides.
- The body ends in
  `return _http_write_tool(role, host, "blockchain-rpc", path, body, dry_run, confirm, auth="rpc")`.

`_http_write_tool` (`aitbc_mcp_rpc_tools.py:41-76`) then does the
gating: `dry_run=True` returns `_build_dry_run("Set dry_run=false and
confirm=true to execute.", command)` — the exact `aitbc http call` line
and nothing is sent; `confirm` unset returns
`{"error": "Confirmation required", "command": …, "note": "This is a
destructive RPC call. Pass dry_run=false and confirm=true to
execute."}`; only with both does `_run_http` POST on the target host.

## Key custody

No key material in the MCP process — the existing split stays as
designed (`chain-reset-runbook.md` §9 item 4): signing-side
`AGENT_ECONOMICS_OPERATOR_KEY` lives only in the hub coordinator env
(`config.py:337`, consumed at `services/blockchain.py:61`);
verifying-side `AGENT_ECONOMICS_OPERATOR_ADDRESS` lives in
`aitbc-blockchain-rpc.env` on every node. Verifiers run where the key
must never exist — do not consolidate the pair and do not add a third
store. The tools accept a ready-made `signature`; minting it is the
operator-signing path's job, not the tool's.

## Acceptance

- Every route in the map has a typed tool, each forwarded through
  `_http_write_tool` — no bespoke request code.
- Signing proven against the canonical-JSON recipe: a test vector signs
  a body (strip → canonical JSON → keccak → `sign_msg_hash`) and a node
  accepts it through `require_operator_signature` — sign/verify
  round-trip on a live rpc unit.
- `dry_run` coverage on every tool: the default call returns the command
  only; `dry_run=false` without `confirm=true` returns the
  Confirmation-required error.
- No keys in the MCP process env: nothing in `mcp-server/` reads
  `AGENT_ECONOMICS_OPERATOR_KEY` and the server process env stays clean.

Refs: #657 · `docs/scenarios/86_bounty_lifecycle.md`,
`87_agent_staking.md` — the same recipe by hand ·
`docs/design/v9-unsigned-protocol-transfers.md` — why these revived.
