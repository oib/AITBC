# Node-held wallet access for agents (SEC-1)

Status: **implemented behind a flag** (SEC-2, 2026-10-13). The wrapper
service lives in `apps/ops-signer/` (`python -m aitbc_ops_signer`,
`AITBC_OPS_SIGNER_ENABLED` off by default, nothing installed on any
host); the operator runbook is
[../ops/ops-signer-runbook.md](../ops/ops-signer-runbook.md). Caps and
the initial allow-list follow the operator's 12-Oct decisions (1 AIT/tx,
5 AIT/day, shop + S-10 payee). Companion to
[key-custody-proposal.md](key-custody-proposal.md) (which covers at-rest
custody; this covers *use*).

Problem being solved: recurring operator-gated steps (pay a payee,
re-sign a market offer, send a canary) are stalled today because the
only signing path is a human operator with a plaintext key. This design
lets an agent initiate a spend from a wallet that lives on a node while
the agent never sees the password or the key — and every spend is
bounded, allow-listed, and individually approved by the operator.

## 1. Dedicated ops wallet

A single new wallet, `aitbc-ops`, created by the operator on the node
where agent-signed sends should originate (initially hub, since most
gated flows land there). It is a *new* account — deliberately **not**
the treasury, **not** a validator identity, and **not** any authority
address — so a compromise touches nothing else. Funding: a small,
operator-chosen float (order of hundreds of AIT, enough for the flows in
§6). Hard caps enforced by the signer wrapper (§2):

- `OPS_MAX_PER_TX` — ceiling on a single transfer.
- `OPS_MAX_PER_DAY` — ceiling on the rolling 24 h sum.

Both bounds are conservative defaults the operator sets at creation and
can change only by editing the wrapper config as root. The wallet file
itself lives under the node's keystore dir, mode 600, owner root.

## 2. Allow-list enforced in a node-side signer wrapper

A small root-owned signer service on the node — call it
`aitbc-ops-signer` — is the *only* component that can open the wallet.
It exposes a minimal local endpoint (a root-only unix socket, e.g.
`/run/aitbc-ops-signer.sock` with `SocketMode=0660` for a dedicated
`aitbc-ops` group) accepting exactly one request shape:

```
sign_payment(to=<address>, amount_units=<int>, memo=<task-id>)
```

The wrapper enforces **all** policy locally, in code the agent cannot
influence:

- recipient must be on a static allow-list
  (`/etc/aitbc/ops-signer.allow`, root-owned 600 — the S-10 payee
  address, a market-offer sink, a burn/canary address, etc.);
- `amount_units <= OPS_MAX_PER_TX` and the rolling-day total stays
  within `OPS_MAX_PER_DAY` (counter kept in a small local sqlite);
- `memo` is required and is echoed into the audit record — a send
  without a task reference is refused.

The agent submits a request; the wrapper either signs-and-broadcasts or
refuses. **The agent never learns a key, a password, or a signed blob.**

## 3. Root-only credential via systemd credentials

The wallet's decrypt password is stored as a **systemd credential**, not
in an env file:

```
# /etc/systemd/system/aitbc-ops-signer.service
[Service]
Type=simple
User=root
LoadCredentialEncrypted=ops-wallet-pass:/etc/aitbc/credentials/ops-wallet-pass
ExecStart=/opt/aitbc/venv/bin/python -m aitbc_ops_signer
```

- `LoadCredentialEncrypted=` (or `SetCredentialEncrypted=`) makes
  systemd place the decrypted value in `$CREDENTIALS_DIRECTORY/` as an
  in-memory file visible only to the service. The password never lands
  in argv, environment dumps (`/proc/*/environ`), `systemctl show`
  output, or journald.
- The on-disk credential file `/etc/aitbc/credentials/ops-wallet-pass`
  is root-owned mode 600; it can itself be TPM/host-bound so a copied
  file is useless off the node.
- Side benefit vs `EnvironmentFile=`: no `.env` world-readable accident
  can ever leak it, and the KC-class cleanups (removing unused secrets
  from env files) cannot disturb it.

## 4. Per-use approval through ask-user-question

Policy caps are the *floor*, not the trigger. Before the agent calls the
socket it must ask the operator via `ask_user_question`:

- **Shown in the question:** recipient address (full), amount, the
  task id it serves, and what it changes (e.g. "S-10 payee payment,
  360,000 units").
- **Options:** "Approve (send now)" / "Approve (queue for batch)" /
  "Refuse". The agent must quote the chosen answer verbatim in its
  reply and the TOPOLOGY record.
- A refusal is final for that request — the agent does not retry with a
  rephrased question.

This keeps the human decision *per use* while the caps and allow-list
make a mistaken approval cheap rather than catastrophic.

## 5. Audit trail — tx hashes and addresses only

Every request (approved or refused) appends one line to
`/var/lib/aitbc/ops-signer-audit.log` (root-owned, append-only from the
service's view):

```
<iso-time> task=<memo> to=<addr> amount=<units> result=<signed|refused> tx=<hash|->
```

The trail contains **only** tx hashes, addresses, amounts, and the task
reference — no key material, no password, no request body. It is the
single place to answer "did the agent ever send X to Y" and doubles as
the fleet-check data source for the ops wallet's expected balance.

## 6. How S-10 and M-2 run under it

- **S-10 (operator payment).** Agent prepares the transfer request,
  asks via `ask_user_question` naming the payee address + 360,000
  units + "S-10". Operator approves once; the wrapper signs, broadcasts,
  writes the audit line. The operator's earlier decision ("I will pay
  now") becomes one click instead of a manual wallet session. The
  payee must already be in the allow-list — the operator adds it as root
  before the ask.
- **M-2 (market re-listing).** Offer creation needs a signed envelope.
  Same shape: agent prepares `plugin_id/price/capacity/description`,
  the ask shows each offer; the wrapper signs each approved offer and
  returns the tx hashes for the read-only registry query. Node2's shop
  wallet can stay the provider on-chain while the *signing* happens
  under the ops policy — the offers remain attributable to the shop.

## 7. Out of scope, deliberately

- **Treasury spends.** The treasury (`0x34FFfAd1…`, ~1M AIT) never
  becomes an ops-wallet source. Its custody is the K-4 offline-copy
  procedure; a signer wrapper that could touch it would move the blast
  radius from bounded to total.
- **Rotations.** Key/password rotation stays a standalone operator
  ceremony (the 12-Oct rule). The wrapper never generates, replaces, or
  exports key material.
- **Validator and authority keys.** `kr0/` keys stay in the custody
  tiers from the companion paper; consensus/authority signatures are a
  separate trust domain that no agent-initiated path may touch.

Reason, stated once: the point of the ops wallet is that the worst
possible agent bug — a wrong request — is capped at a small float, not
a fleet-identity or treasury event.

## 8. Rollout plan + rollback

Rollout (each step states who does it):

1. **Operator:** create `aitbc-ops` wallet on hub; fund it with the
   chosen float from treasury (normal send).
2. **Operator:** write `/etc/aitbc/credentials/ops-wallet-pass` (mode
   600, root) containing the wallet password — this is the only step
   that handles a passphrase.
3. **Agent (repo):** land `apps/ops-signer/` — the wrapper service,
   its unit file, the allow-list format, fixture tests for caps +
   allow-list + audit line. Code lands on main behind a flag; nothing
   installed.
4. **Operator:** install the unit on hub, `systemctl daemon-reload`,
   write the allow-list, start `aitbc-ops-signer`. Verify with one
   1-unit canary to a canary address (testnet-style check on the live
   island is fine at that size).
5. **Agent:** wire `ask_user_question`-gated sends into the S-10/M-2
   flows as a *new* path; the manual-wallet path stays as fallback.
6. **Verify:** audit log line + on-chain tx + balance drop match.

Rollback: `systemctl stop aitbc-ops-signer` plus removing the unit.
The wallet file stays put (no deletion needed — it's just a file);
the audit log is kept. If the wallet itself is compromised, sweep its
balance back to treasury (operator send) and rotate to a fresh
`aitbc-ops-2`.

## Open decisions for the operator

- Float size + the two cap values.
- Whether node2 gets its own ops-signer later (M-2 convenience) or all
  agent sends funnel through hub's.
- Allow-list initial contents.
