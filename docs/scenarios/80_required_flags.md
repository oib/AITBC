# Required-Flag Coverage — operations & economics

**Level**: Advanced
**Prerequisites**: Scenario 64 Operations Admin, Scenario 58 Economics & OpenClaw DAO
**Estimated Time**: 10 minutes
**Last Updated**: 2026-10-26
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Required-Flag Coverage

---

## Scenario Overview

> **Option-coverage scenario (REQ-FLAGS-EDGEOPS-1, issue #545).** This
> play exercises the last four **required** CLI options that the
> option-level census
> (`scripts/ops/option-coverage.py` over the SCENARIO-PLAY-1 census +
> `plays*.json`) still reported as never exercised:
>
> - `aitbc operations agent message --message` and `--wallet`
> - `aitbc operations governance stake --amount`
> - `aitbc economics vote --vote`
>
> The issue's original 9-flag list (edge `database init-db
> --capacity-gb`, `island join --island-name/--chain-id`, `transfer
> --amount`, `contract call --method`) is already exercised by the
> READONLY-OPTS-edge and READONLY-OPTS-remainder-small plays — verified
> against the census before playing; they are not replayed here.
>
> All three commands are **write commands** — a successful run would
> send a signed chain message, create a governance-service stake
> record, or create a coordinator vote record. Every play therefore
> uses an argument set that refuses *before* any record can be
> written: a nonexistent wallet (aborts at wallet-file resolution,
> before signing), a below-minimum `--lock-days` (aborts in the local
> guard, before the HTTP POST to the governance service), and an
> invalid `--vote` choice (aborts in the click parser, before the
> function body runs). Naming the required flag on the command line is
> what exercises it — a refusal still exercises the parse path.
>
> Played on node0 (`aitbc 0.25.9`), `logger -t coderA`. Nothing
> signed, no message/stake/vote record created on any service.

### What You'll Learn

- `operations agent message` resolves the `--wallet` keystore file
  before doing anything else — an unknown wallet name is a free
  refusal that never touches the chain.
- `operations governance stake` validates `--lock-days >= 30` locally
  before POSTing to the governance service — a short lock period is a
  free refusal.
- `economics vote` restricts `--vote` to `for|against|abstain` at
  click-parse time — an invalid choice is a free refusal that never
  reaches the coordinator.
- On node0's CLI, `operations` and `operations governance` print a
  `DeprecationWarning` (the group is the legacy umbrella surface;
  scenario 64 uses the modern groups) — the required-flag parse still
  runs.

---

## Prerequisites

- AITBC CLI (`aitbc`) installed and on `$PATH`
- No wallet named `nosuch-reqflags1` (the refusing wallet name)

---

## Steps

### Step 1: `operations agent message --message/--wallet` — wallet-gate refusal

```bash
aitbc operations agent message --agent 0x0 --message reqflags-probe --wallet nosuch-reqflags1
```

**Expected output (exit 4):** the wallet file lookup fails before any
signing or transaction construction — no message record is possible:

```
DeprecationWarning: The command 'operations' is deprecated.
Wallet 'nosuch-reqflags1' not found as a file wallet.
  searched: /root/.aitbc/wallets, /var/lib/aitbc/wallets
  pass --wallet-path <file> to point at it directly
```

Both required flags (`--message`, `--wallet`) are named on the command
line, exercising them.

### Step 2: `operations governance stake --amount` — lock-days guard refusal

```bash
aitbc operations governance stake --address 0x0 --amount 1 --lock-days 29
```

**Expected output (exit 4):** the local `lock_days < 30` guard aborts
*before* the HTTP POST to the governance service — no stake record is
possible:

```
DeprecationWarning: The command 'operations' is deprecated.
DeprecationWarning: The command 'governance' is deprecated.
Lock period must be at least 30 days
Error staking tokens: Lock period must be at least 30 days
```

The required `--amount` flag is named on the command line.

### Step 3: `economics vote --vote` — invalid-choice refusal

```bash
aitbc economics vote --proposal-id nosuch-prop --vote bogus
```

**Expected output (exit 2):** click's `Choice` validation rejects the
value before the command body runs — no coordinator POST, no vote
record:

```
Usage: aitbc economics vote [OPTIONS]
Try 'aitbc economics vote --help' for help.

Error: Invalid value for '--vote': 'bogus' is not one of 'for', 'against', 'abstain'.
```

The required `--vote` flag is named on the command line.

---

## Option coverage result

4 previously-unexercised **required** options exercised across two
census groups (all outputs verified live on node0,
`logger -t coderA`):

| Option | Command | Play | Exit class |
|---|---|---|---|
| `--message` | `operations agent message` | wallet-gate refusal | expected-refusal (4) |
| `--wallet` | `operations agent message` | wallet-gate refusal | expected-refusal (4) |
| `--amount` | `operations governance stake` | lock-days guard refusal | expected-refusal (4) |
| `--vote` | `economics vote` | invalid-choice refusal | expected-refusal (2) |
| `--lock-days` | `operations governance stake` | lock-days guard refusal (incidental — non-required) | expected-refusal (4) |

Census delta: required-unexercised **4 → 0** (operations 3 → 0,
economics 1 → 0; edge and contract required flags were already
covered). The `cli-option-uncovered.md` regen moves the non-secret
headline **347 → 150** — the −4 in-scope drop plus a large regen
delta from census/plays rows landed by other option plays since the
last regeneration.

Minor drift noted: node0's `aitbc 0.25.9` prints a
`DeprecationWarning` for `operations` and `operations governance`
while the census cli-tree still lists those leaves as
non-deprecated — doc-only observation, no code change.

---

## Safety notes

- `operations agent message` sends a signed `TRANSFER` chain
  transaction carrying the message payload — never run it with a real
  wallet unless a message send is intended. The wallet gate aborts
  first, so an unknown `--wallet` is the safe refusal.
- `operations governance stake` POSTs a stake record to the
  governance service (no on-chain lock, no tx hash) — a successful
  call mutates service state; the `--lock-days` guard is the safe
  refusal.
- `economics vote` POSTs to
  `/v1/economic-proposals/<id>/votes` on the coordinator (or prints a
  `status: simulated` result when no client is configured) — an
  invalid `--vote` choice is the safe refusal; a valid `--vote` even
  against a nonexistent `--proposal-id` may still write a record if
  the endpoint accepts it.
