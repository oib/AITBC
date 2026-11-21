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
> `--secret-key` forms stay excluded, as do the password-file/stdin forms
> on leaves tagged `unplayable:` (`scripts/ops/option-coverage-exclusions.json`
> — dead flags, swallowed fallbacks, pre-guard writes).
>
> **Gate order (#2450):** every secret-bearing leaf now checks the wallet
> before the password source — a nonexistent wallet refuses with the
> wallet error even when `--password-file`/`--password-stdin` is also bad.
> To reach the password-file/stdin refusals the wallet must resolve, so
> the plays below create a throwaway `sp85-a` wallet first (zero funds,
> local file only). The old `sp-final-1` fixture is gone; `sp85-a` replaces
> it. Form B cannot be played through the MCP — `run_aitbc_cli` has no
> stdin channel — CLI only.
>
> Played on node0 + node2 (`aitbc 0.25.9`), `logger -t coderA`. Zero records
> written.

## Play patterns

```bash
# Setup — throwaway encrypted wallet for the password-gate plays
printf 'sp85-pw\n' > /tmp/sp85.pw && chmod 600 /tmp/sp85.pw
aitbc wallet create --name sp85-a --password-file /tmp/sp85.pw

# Form A — resolvable wallet + nonexistent password file
aitbc <leaf> --wallet sp85-a --password-file /tmp/sp85-nosuch.pw
# Form A' — nonexistent wallet + nonexistent password file: the wallet
# gate wins on every leaf (this is the #2450 unified order)
aitbc <leaf> --wallet nosuch85 --password-file /tmp/sp85-nosuch.pw
# Form B — empty stdin + nonexistent wallet (CLI only; MCP has no stdin)
aitbc <leaf> --wallet nosuch85 --password-stdin </dev/null
# Form B' — empty stdin + resolvable wallet reaches the stdin refusal
aitbc <leaf> --wallet sp85-a --password-stdin </dev/null
```

**Expected refusals:** Form A `Cannot read password file
'/tmp/sp85-nosuch.pw'` once the wallet resolves; Form B' `No password on
stdin`; Form A'/B `Wallet 'nosuch85' not found` — the wallet gate fires
first everywhere. Wallet/file refusals exit 2 (`NotFoundError`), the
empty-stdin refusal exits 1; every refusal emits a JSON error object
under `--output json`, before the command's write path.

## Result

Census after merge: **1 non-secret uncovered** (`crosschain bridge
--wait`, exclusions-tagged) + **120 secret** — inline `--password`/
`--private-key`/`--secret-key`/`--access-secret`/`--decode-seed`/
`--show-secrets` forms *plus* the file/stdin forms on the ~20
`unplayable:`-tagged leaves (which stay unexercised by rule) → full CLI
option surface classified.
