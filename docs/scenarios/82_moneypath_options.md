# MONEYPATH-OPTS-2 — operations / transactions / eth option coverage

**Level**: Advanced
**Prerequisites**: Scenario 64 Operations Admin
**Estimated Time**: 15 minutes
**Last Updated**: 2026-10-26
**Version**: 1.0

breadcrumb: Home > Scenarios > Moneypath Option Coverage

## Scenario Overview

> **Option-coverage scenario (issue #548).** Exercises the 25 non-secret
> uncovered options in the `operations`, `transactions`, and `eth` groups.
> Plays ran on node0 (`logger -t coderA`). Read-only flags were played
> live; signed/money paths stopped at free refusals (wallet-not-found,
> no-TTY password, client-side validation, click parse, dead-endpoint, or
> server 4xx on `nosuch`/`0x0` ids). Nothing signed, no record created.

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
| `operations governance voting-power --format` | 0x0 address | 0 live (drift: table despite json) |
| `transactions search --recipient` | 0x0 recipient | 0 live rows |
| `transactions search --rpc-url` | 127.0.0.1:9 | 2 |
| `transactions send --fee/--type/--payload/--use-explorer/--rpc-url` | `--from nosuch` | 1 password refusal |
| `transactions status --rpc-url` | 127.0.0.1:9 | 2 |
| `eth transfers -a/--since/--json/--no-log` | 0x0 addr | 1 pagination cap |
| `eth transfers --rpc-url/--explorer-url/--log` | 127.0.0.1:9 | 2 pre-write refusal |

Census delta: operations 10→0, transactions 8→0, eth 7→0 of the uncovered set.
