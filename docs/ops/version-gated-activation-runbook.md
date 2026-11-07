# Version-gated state-transition activation runbook (v21/v22 pattern)

> Generalizes the v14–v18 activation runbooks for the current
> `STATE_TRANSITION_V*_HEIGHT` mechanism. Live pins observed 2026-11-07
> (hub `/etc/aitbc/blockchain.env`): `V20_HEIGHT=18200`,
> `V21_HEIGHT=22000`, `V22_HEIGHT=20100`. Chain `bc-2`, head ~h20140 —
> **v22 activates at h20100 (already crossed); v21 arms at h22000**
> (~30h out at ~67s cadence).

## What a version gate is

`state_transition_vN_height` in `apps/blockchain-node/src/aitbc_chain/config.py`
(default `None` = unarmed). At/after the height, new apply/validate rules
activate **inside the same consensus transition** — every validator must
agree or `aux_state_root` diverges (v18 lesson: committed-set changes are
absolute-pin territory).

## Pre-activation checklist (all five hosts)

1. Code carrying the rule is on `origin/main` and ff'd fleet-wide —
   `git log --oneline -1` identical on hub, hub1, node0, node1, node2.
2. `STATE_TRANSITION_VN_HEIGHT=<H>` present in `/etc/aitbc/blockchain.env`
   on **every** host, identical value — a mixed set applies different
   rules at the same height and forks.
3. Height H is comfortably ahead of current head (≥ several hours at
   observed cadence) so the env edit + serial restart wave completes
   before activation.
4. `fleet-config-check` / env drift check clean.
5. Restart wave per `fleet-wave-runbook.md`: hold-check each host,
   serial restarts, readback `ExecMainStartTimestamp`/`MainPID`,
   head-equality between hosts.
6. Pre-activation snapshot: latest `aitbc-backup.timer` generation < 26h
   old on every host (R13-00 verified daily coverage).

## At activation

- Watch head cross H; verify block production continues (no stall, no
  fork — compare block hashes across hosts at H and H+5).
- Verify the new rule's observable behavior on a canary tx where one
  exists (e.g. v21 agent-spend session grant path).
- Confirm `aux_state_root` agreement — any mismatch = mixed-fleet bug,
  halt and reconcile before further txs.

## Abort / rollback

- **Before H**: remove/adjust the env pin and re-wave if needed — code
  without the height stays dormant (rules are height-gated, not
  code-gated).
- **After H**: there is no clean rollback — activated consensus rules
  are in chain history. Forward-fix only; this is why the pre-checks
  exist. Do not attempt env rollback post-activation.
- `V13_HEIGHT_NOT_ARMED = 2**62` pattern exists for parking rules as
  dead code during development — not a post-activation tool.

## Special notes

- **v21 (AGENT-SPEND-B-1, #1142 + #1223 default-deny)**: session-bound
  senders must name a live `payload.session_id`; `AGENT_BOUND_ALLOWED_TX_TYPES`
  default-deny live since the #1223 wave. Activation at h22000 — verify
  the deny matrix behaves (unknown-type-with-value refused) immediately
  post-activation.
- **v22 (BOND-RELEASE-001, #1166/#1167)**: bond ownership/provider binding,
  3650-day lock ceiling (`PROTOCOL_MAX_LOCK_DURATION` compile-time —
  never env). Activated h20100 — confirm bond release/top-up edge cases
  post-activation.
- Island chains (`bc-2-island-1`, transitions=1) apply equivalent rules
  from genesis — out of scope for height pins.
