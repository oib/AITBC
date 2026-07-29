# Secrets / Credential Access Adapter — Interface

> _Adapted from the clean-room blueprint. Inline `.agentic/…` names below are design-record concepts; their live homes are in the [crosswalk](../../../blueprint/CROSSWALK.md). Treat this file as the capability contract._

Mandatory **when agents need access to protected systems**. Governs how agents interact with
credentials without seeing them. Policy: [`blueprint/governance/security.md`](../../../blueprint/governance/security.md).

## The mediation principle

Prefer operations where **the adapter performs the privileged action** and returns the outcome —
the agent never holds the credential value.

## Operations

| Operation | Semantics |
|-----------|-----------|
| `list_secrets()` | Names and purposes only — never values. |
| `perform(action, secret_name, params)` | **Preferred path.** The adapter executes the action (call the API, connect to the DB, trigger the job) using the named credential internally; returns the result + an audit event. |
| `request_raw_access(secret_name, task_ref, justification)` | **Exception path.** Creates a `raw-secret-access` human gate on the ticket. Only after explicit per-task human approval does `read_raw` become available, scoped to that task and logged. |
| `read_raw(grant_token)` | Valid only against an approved grant; single task scope; audited. |

## Audit contract

Every `perform`, `request_raw_access`, and `read_raw` emits an audit event recorded as a
structured ticket comment: actor role, secret name (never value), action, outcome, timestamp.

## Providers (v1 reference)

- `env` — secrets from the runtime environment; mediation via wrapper commands.
- vault-style — named-secret store with server-side action execution.

Provider selection: `config.security.secrets_adapter`. With
`config.security.mediated_access_only: true` (default), `request_raw_access` is the only route
to a value — there is no configuration that silently hands agents raw secrets.
