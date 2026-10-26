# Secret-Form Option Coverage — password-file/stdin refusals

**Level**: Advanced
**Prerequisites**: Scenario 84 Last Uncovered Options
**Estimated Time**: 15 minutes
**Last Updated**: 2026-10-26
**Version**: 1.0

breadcrumb: Home > Scenarios > Secret-Form Coverage

## Scenario Overview

> **COVERAGE-FINAL-1 (issue #554).** Exercises the `--password-file` and
> `--password-stdin` forms of the shared wallet-secret trio across ~100
> command leaves. Refusal happens at `wallet_secret.py:84` ("Cannot read
> password file") or `:153` ("No password on stdin") — always before
> signing and before any write/POST. The inline `--password`/`--private-key`/
> `--secret-key` forms stay excluded; dead/inert leaves are tagged
> `unplayable:` in `scripts/ops/option-coverage-exclusions.json`.
>
> Played on node0 + node2 (`aitbc 0.25.9`), test wallet `sp-final-1`
> (empty, encrypted, scenario artifact), `logger -t coderA`. Zero records
> written.

## Play patterns

```bash
# Form A — nonexistent password file, real empty test wallet
aitbc <leaf> --wallet sp-final-1 --password-file /tmp/sp554-nosuch.pw
# Form B — empty stdin + nonexistent wallet
aitbc <leaf> --wallet nosuch554 --password-stdin </dev/null
```

**Expected refusals:** `Cannot read password file '/tmp/sp554-nosuch.pw'`
(exit 4, or 1 where the wallet daemon is consulted first) /
`Wallet 'nosuch554' not found` / `No password on stdin` — all before the
command's write path.

## Result

Census after merge: **1 non-secret uncovered** (`crosschain bridge
--wait`, exclusions-tagged) + **120 secret** (inline `--password`,
`--private-key`, `--secret-key`, `--access-secret`, `--decode-seed`,
`--show-secrets`) → full CLI option surface classified.
