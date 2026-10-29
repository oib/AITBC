# AITBC CLI

The `aitbc` command-line interface is the primary operator and agent entry point for the AITBC network.

## Installation

From the repository root:

```bash
cd cli
pip install -e .
```

Or install the published package:

```bash
pip install aitbc-cli
```

## Quick start

```bash
aitbc --help           # list all command groups
aitbc --version        # show CLI version
aitbc wallet --help    # subcommand help for any group
aitbc genesis init --create-wallet --register-service
```

## Further reading

- [CLI command reference (cli/CLI_USAGE_GUIDE.md)](../../cli/CLI_USAGE_GUIDE.md) — detailed command and workflow reference
- [Per-command reference (commands/)](commands/README.md) — generated page per `aitbc` command: options, examples, related scenarios/features
- [CLI click overview (CLICK_CLI.md)](CLICK_CLI.md) — command-tree and group catalog
- [CLI developer guide (CLI_DEVELOPER_GUIDE.md)](CLI_DEVELOPER_GUIDE.md) — extending and packaging the CLI
- [CLI testing notes (testing.md)](testing.md) — validation and test conventions
- [Package README (cli/README.md)](../../cli/README.md) — source-level overview and group catalog

## Wallet password input (all signing commands)

Every `aitbc` command that signs a transaction or unlocks an encrypted
wallet accepts the same three password options, with identical help text:

- `--password-stdin` — read **one line** from stdin (the trailing newline
  is stripped; other whitespace is kept). This is the recommended form for
  agents and scripts: `printf '%s\n' "$PASS" | aitbc …`.
- `--password-file <path>` — read the password from a file. The file must
  be a regular file (symlinks are resolved), owned by the **calling user**
  (`st_uid == geteuid` — a file owned by anyone else, including root when
  the caller is not root, is refused), **not group- or world-readable**
  (`chmod 0600`), and at most 4 KiB. Exactly one trailing newline is
  stripped.
- `--password <value>` — **deprecated**: the value is visible in process
  lists (`ps`) and shell history. Still accepted for compatibility; a
  one-line warning is printed to stderr. Use the file or stdin form.

Two environment variables are also honoured (kept for compatibility; the
environment is inherited by child processes, so prefer stdin or a file):

- `AITBC_WALLET_PASSWORD_FILE` — same rules as `--password-file`.
- `AITBC_WALLET_PASSWORD` — the password value itself.
  `AITBC_WALLET_PASSWORD_<WALLET_NAME>` (upper-cased, `-` → `_`) is checked
  per wallet first.

Resolution order, highest first: `--password-stdin` → `--password-file` →
`--password` (deprecated; any explicit flag beats inherited state) →
`AITBC_WALLET_PASSWORD_FILE` → `AITBC_WALLET_PASSWORD[_<NAME>]` →
system keyring → interactive `getpass` prompt (only when a TTY exists).
Passing two explicit sources at once (e.g. `--password` together with
`--password-file`) is an error, not a guess. With no source and no TTY the
command fails with a message listing the supported inputs — agents on
headless hosts must always pass `--password-stdin` or `--password-file`.

The password file belongs on the node that owns the wallet, mode `0600`,
owned by the user that runs the CLI. Never commit it to the repository and
never copy it to another node.

## What lives here

This directory contains user-facing and technical CLI documentation. Implementation code lives in `cli/aitbc_cli/`.
