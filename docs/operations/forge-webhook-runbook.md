# Forge Ops Runbook — Bitbucket PR Webhook

> **Epic ABS-230 (Phase 2 Ops-Fläche), Story ABS-366.** Operational guide for the inbound
> Bitbucket PR webhook (`POST /webhooks/bitbucket`, ABS-345) that keeps one `pr_mirror` row per
> work item fresh so the board shows PR/CI truth without any agent touching the forge.
>
> **Human-only boundary:** the forge secrets and the repo→project binding below are
> **human-provisioned** (ADR-A-0004). An agent consumes them from the server environment; it
> never generates, stores, or rotates them. Steps marked **[OPERATOR]** must not be executed by
> an autonomous seat.

## Bitbucket signing-proxy requirement

The endpoint authenticates each delivery by HMAC of the **raw request body**. It expects a
GitHub-style header:

```
X-Hub-Signature: sha256=<hex hmac-sha256(rawBody, FORGE_WEBHOOK_SECRET)>
```

**Bitbucket Cloud does not natively HMAC-sign its webhook payloads.** It sends the event body
with no `X-Hub-Signature` header. Therefore a webhook wired straight from Bitbucket Cloud to this
endpoint **fails closed** — every delivery is rejected `401` and **no `pr_mirror` row updates**.

To bridge this gap you MUST place a **signing proxy** in front of the endpoint (or use a
Bitbucket signed-webhook feature/app that emits the header):

```
Bitbucket Cloud  ──POST (unsigned)──▶  Signing proxy  ──POST + X-Hub-Signature──▶  /webhooks/bitbucket
```

The signing proxy:

1. Receives the raw Bitbucket PR event (`pullrequest:created|updated|fulfilled|rejected`).
2. Computes `sha256=hmac-sha256(rawBody, FORGE_WEBHOOK_SECRET)` over the **byte-exact body it will
   forward** (a re-serialized body will not match — forward the bytes unchanged).
3. Sets the `X-Hub-Signature` header and forwards to `POST /webhooks/bitbucket`.

The endpoint verifies the HMAC with a constant-time compare and rejects any body whose bytes do
not match the signature, so the proxy and the endpoint must agree on the exact forwarded bytes.

## Human-provisioned env vars

All values are server-side only and MUST NOT surface in any `/api` or `/agent` response or the
served SPA bundle. They are read once from the process environment in
`backend/packages/forge/config` (`loadForgeConfig`).

| Env var | Consumed | Purpose |
| --- | --- | --- |
| `FORGE_WEBHOOK_SECRET` | server-side, `backend/packages/forge` (`verifyWebhookSignature`) | HMAC key for the `X-Hub-Signature` check. No secret → endpoint returns `503`. |
| `FORGE_BITBUCKET_TOKEN` | server-side, `backend/packages/forge` (REST provider) | Bitbucket app-password/token for the lazy-poll REST refresh + merge. |
| `FORGE_BITBUCKET_WORKSPACE` | server-side, `backend/packages/forge` | Bitbucket workspace slug of the bound repo. |
| `FORGE_BITBUCKET_REPO` | server-side, `backend/packages/forge` | Bitbucket repository slug of the bound repo. |
| `FORGE_BITBUCKET_PROJECT_ID` | server-side, `backend/packages/forge` (ABS-365 repo→project binding) | The `project_id` the `(workspace, repo)` maps to; scopes the webhook write to one tenant. Unset → the webhook write path is unbound and is a clean no-op. |

**[OPERATOR]** Provision these in the deployment environment (never commit them). Rotate
`FORGE_WEBHOOK_SECRET` in lockstep with the signing proxy's copy — a mismatch fails closed.

## Fail-closed behavior (operator diagnosis)

The endpoint never writes on an unauthenticated or misconfigured request. Use the response code to
diagnose a mis-wired proxy:

| Condition | Response | Meaning |
| --- | --- | --- |
| No `FORGE_WEBHOOK_SECRET` configured | `503 webhook_not_configured` | The server has no secret — it refuses all deliveries. Provision the secret and restart. |
| Missing or bad `X-Hub-Signature` | `401 invalid_signature` | The proxy did not sign, signed with the wrong secret, or the forwarded body bytes differ from what was signed. |
| Body is not valid JSON | `400 bad_json` | Signature verified but the payload could not be parsed. |
| Valid signature, key/repo not in the bound project | `202 {matched:false}` | Clean no-op ACK so Bitbucket stops retrying; nothing written (ABS-365). |
| Valid signature, matched work item | `200 {matched:true,...}` | The `pr_mirror` row transitioned to the payload's state. |

A steady stream of `401`s with no `pr_mirror` updates after a live Bitbucket wiring almost always
means the **signing proxy is missing or the shared secret drifted** — start there.

## References

- **Code:** `backend/packages/forge/webhook.ts` (`verifyWebhookSignature`, `applyBitbucketWebhook`),
  `backend/apps/server/src/routes/forge.ts` (route + status codes),
  `backend/packages/forge/config.ts` (env consumption).
- **Related stories:** ABS-345 (the webhook this documents), ABS-365 (repo→project binding /
  tenant isolation).
- **ADR:** ADR-A-0004 — forge secrets + repo binding are human-provisioned.
- **Pattern:** `patterns_library/api/webhook-handler.md`.
