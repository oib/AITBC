# MONEYPATH-OPTS-2 — operations / transactions / eth option coverage

**Level**: Advanced
**Prerequisites**: Scenario 64 Operations Admin
**Estimated Time**: 15 minutes
**Last Updated**: 2026-10-26
**Version**: 1.0

breadcrumb: Home > Scenarios > Moneypath Option Coverage

**Legs**: 4

## Scenario Overview

> **Option-coverage scenario (issue #548).** Exercises the 25 non-secret
> uncovered options in the `operations`, `transactions`, and `eth` groups.
> Plays ran on node0 (`logger -t coderA`). Read-only flags were played
> live; signed/money paths stopped at free refusals (wallet-not-found,
> no-TTY password, client-side validation, click parse, dead-endpoint, or
> server 4xx on `nosuch`/`0x0` ids). Nothing signed, no record created.

## Steps

Read-only and refusal legs only — nothing signed, no record created.
Placeholder `nosuch` ids and `0x0`-style dead addresses throughout.

### Step 1: operations agent message (wallet-gate refusal)

```bash
aitbc operations agent message --agent 0x0000000000000000000000000000000000000001 --message 'mo2 probe' --wallet nosuch-mo2 --rpc-url http://127.0.0.1:9
```

**Expected output (exit 4):** wallet-not-found refusal before any RPC.

### Step 2: operations governance reads and guards

```bash
aitbc operations governance delegate --delegator 0x0000000000000000000000000000000000000001 --delegate 0x0000000000000000000000000000000000000002 --amount 1 --wallet nosuch-mo2 --format bogus
```

**Expected output (exit 2):** click `Choice` parse refusal on `--format`.

```bash
aitbc operations governance execute --proposal-id nosuch --format json
aitbc operations governance get-proposal --proposal-id nosuch --format json
```

**Expected output (exit 2, each):** server refusal — `execute` answers
403, `get-proposal` answers 404.

```bash
aitbc operations governance proposal --proposal-id p-mo2 --title t --description d --params '{}' --wallet nosuch-mo2 --format json
aitbc operations governance stake --address 0x0000000000000000000000000000000000000001 --amount 1 --lock-days 0 --format json
aitbc operations governance vote --proposal-id nosuch --vote for --wallet nosuch-mo2 --reason mo2 --format json
```

**Expected output (exit 4, each):** free refusals — nosuch wallet for
`proposal`/`vote`, the `lock_days < 30` guard for `stake`.

```bash
aitbc operations governance voting-power --address 0x0000000000000000000000000000000000000000 --format json
```

**Expected output (exit 0):** a single JSON document with the address's
voting power (the `--format json` drift is fixed — JSON, not a table).

### Step 3: transactions reads and send guards

```bash
aitbc transactions search --recipient 0x0000000000000000000000000000000000000000
aitbc transactions search --address 0x0000000000000000000000000000000000000000 --rpc-url http://127.0.0.1:9
aitbc transactions status --tx-hash 0x00 --rpc-url http://127.0.0.1:9
```

**Expected output:** `search --recipient` prints live rows (exit 0);
the dead `--rpc-url` legs fail (exit 2) on connect.

```bash
aitbc transactions send --from nosuch-mo2 --to 0x0000000000000000000000000000000000000001 --amount 1 --fee 0.01 --type TRANSFER --payload '{}' --use-explorer --rpc-url http://127.0.0.1:9
```

**Expected output (exit 1):** password/wallet refusal before any send.

### Step 4: eth transfers reads

```bash
aitbc eth transfers -a 0x0000000000000000000000000000000000000000 --since 0 --json --no-log
aitbc eth transfers -a 0x0000000000000000000000000000000000000000 --rpc-url http://127.0.0.1:9 --explorer-url http://127.0.0.1:9 --log /tmp/mo2-transfers.jsonl
```

**Expected output:** the first leg prints/filters rows and exits 1 on
the nonce cross-check pagination cap when the RPC data is incomplete;
the dead-endpoint leg refuses before writing the log (exit 2).

## Option → exit-class table

| Option | Play | Exit |
|---|---|---|
| `operations agent message --rpc-url` | dead rpc + nosuch wallet | 4 free refusal |
| `operations governance delegate --format` | `--format bogus` | 2 parse refusal |
| `operations governance execute --format` | proposal `nosuch` | 2 server 403 |
| `operations governance get-proposal --format` | proposal `nosuch` | 2 server 404 |
| `operations governance proposal --params/--format` | nosuch wallet | 4 free refusal |
| `operations governance stake --format` | `--lock-days 0` | 4 free refusal |
| `operations governance vote --reason/--format` | nosuch wallet | 4 free refusal |
| `operations governance voting-power --format` | 0x0 address | 0 live (json — drift fixed) |
| `transactions search --recipient` | 0x0 recipient | 0 live rows |
| `transactions search --rpc-url` | 127.0.0.1:9 | 2 |
| `transactions send --fee/--type/--payload/--use-explorer/--rpc-url` | `--from nosuch` | 1 password refusal |
| `transactions status --rpc-url` | 127.0.0.1:9 | 2 |
| `eth transfers -a/--since/--json/--no-log` | 0x0 addr | 1 pagination cap |
| `eth transfers --rpc-url/--explorer-url/--log` | 127.0.0.1:9 | 2 pre-write refusal |

Census delta: operations 10→0, transactions 8→0, eth 7→0 of the uncovered set.

**Drift resolved:** `operations governance voting-power --format json`
now emits a JSON document (was: table output despite the flag). The
round-5 replay also showed this doc had no replayable commands — the
Steps section above restores leg-by-leg coverage.
