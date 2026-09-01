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
- [CLI click overview (CLICK_CLI.md)](CLICK_CLI.md) — command-tree and group catalog
- [CLI developer guide (CLI_DEVELOPER_GUIDE.md)](CLI_DEVELOPER_GUIDE.md) — extending and packaging the CLI
- [CLI testing notes (testing.md)](testing.md) — validation and test conventions
- [Package README (cli/README.md)](../../cli/README.md) — source-level overview and group catalog

## What lives here

This directory contains user-facing and technical CLI documentation. Implementation code lives in `cli/aitbc_cli/`.
