# Mission Control — Release-Toggle (Freigabe) Guide

> Covers the board S9 `release-toggle` control in `TicketDrawer.tsx`.
> Security-flagged feature (ABS-241 `#EXPORT_CRITICAL`); bug fix landed in ABS-446.

## What the Toggle Does

The release-toggle (data-testid `release-toggle`) appears in the human-action
drawer for board S9 tickets. Checking it adds the `orchestrator-ready` label via
the server, which signals the orchestrator that a human has approved the item for
release (Freigabe). Unchecking it removes that label.

## How State Binding Works

The toggle uses **optimistic state** so the checkbox flips immediately on click
while the async server write completes in the background.

```
click → setReleaseOverride(next)   ← DOM flips here (synchronous)
      → api.setLabels(…)           ← PATCH /api/v1/…/labels (async)
          success → onChanged() → setReleaseOverride(null)   (server truth is now authoritative)
          failure → setReleaseOverride(null) + show error note (reverts to eligible)
```

The displayed state is `releaseChecked = releaseOverride ?? eligible`:

- While a write is in flight: `releaseOverride` holds the optimistic value.
- After a successful write and reload: `releaseOverride` is cleared; `eligible`
  (from the reloaded labels) becomes authoritative.
- After a failed write: `releaseOverride` is cleared and the control reverts to
  the pre-click server value.

## Security Model (`#EXPORT_CRITICAL`)

The server remains the authorization boundary — the client controls only DOM state.

| Layer | Detail |
| --- | --- |
| **Client write** | `api.setLabels` → `sendJSON("PATCH", …/labels, …, { credentials: "include" })` |
| **Session gate** | HttpOnly cookie (`via === "session"`); bearer tokens rejected with 403 (ABS-413) |
| **Role gate** | `requireHuman` enforces a writer-role allowlist (`admin`/`maintainer`) before any write |
| **Actor** | `HUMAN_ACTOR` is set server-side in `updateItem()`; client cannot supply or spoof it |
| **Fail-safe** | `!res.ok` (incl. 403) reverts to server truth, surfaces a note; no silent false-positive |

Non-writer sessions see a read-only notice; the toggle is never in their DOM.

## Why the Pre-Fix Behavior Failed

Before ABS-446, the checkbox was `checked={eligible}`. `eligible` derives from the
ticket labels returned by the last reload. A click triggered a server write and
then `onChanged()` (async), so the DOM checkbox never observed a synchronous
state change — Playwright's `.check()` reported "did not change its state"
(`board.spec.ts:74`, S9). The fix adds `releaseOverride` so the DOM flips on the
click event itself.

## Verification

`backend/apps/web/e2e/board.spec.ts` S9 self-seeds a human-action card in
`beforeAll` and asserts the full flow:

1. Open the drawer for the S9 card.
2. `.check()` the `release-toggle` — asserts the control is now checked.
3. Poll `GET /agent/v1/projects/{project}/items?label=orchestrator-ready` and
   assert the card appears — confirms the server write succeeded.

Reverting `checked={releaseChecked}` back to `checked={eligible}` reproduces the
failure at `board.spec.ts:93`.

## References

- **ABS-241** — original Freigabe/release-toggle delivery (actor=human, S9 board)
- **ABS-446** — bug fix (optimistic state binding); commit `9079607`; MR !96
- **ABS-410** — Mission Control UX epic
- **ABS-413** — `via === "session"` bearer-token 403 defence-in-depth
