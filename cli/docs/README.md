# AITBC CLI Technical Documentation

**Level**: Intermediate<br>
**Prerequisites**: Basic CLI familiarity, shell usage, and AITBC project context<br>
**Estimated Time**: 10-15 minutes<br>
**Last Updated**: 2026-06-22<br>
**Version**: 2.1.0 (CLI runtime)

## Navigation Path
**Home** → **CLI Technical** → *You are here*

---

## What lives here

This directory holds the CLI-internal technical documentation. The user-facing CLI reference lives one level up:

- [`../README.md`](../README.md) — user-facing CLI overview, command groups, and quick start
- [`../CLI_USAGE_GUIDE.md`](../CLI_USAGE_GUIDE.md) — detailed usage guide with workflows
- [`../FILE_ORGANIZATION_SUMMARY.md`](../FILE_ORGANIZATION_SUMMARY.md) — full directory tree of `cli/`

Files in this directory:

- `README.md` — this landing page
- `DISABLED_COMMANDS_CLEANUP.md` — historical analysis of previously disabled commands (now re-enabled)
- `FILE_ORGANIZATION_SUMMARY.md` — older organization summary (superseded by the top-level one)

---

## Quick Start

### Installation

The CLI is installed by `scripts/deployment/setup.sh` as an editable package into `/opt/aitbc/venv`:

```bash
cd /opt/aitbc/cli
/opt/aitbc/venv/bin/pip install -e .
```

A wrapper at `/usr/local/bin/aitbc` invokes `/opt/aitbc/venv/bin/python -m aitbc_cli.core.main "$@"`, so `aitbc` works from any shell.

### Usage

```bash
aitbc --help          # list all 50+ command groups
aitbc --version       # aitbc, version 2.1.0
aitbc wallet --help   # subcommand help for any group
```

---

## CLI Architecture (summary)

- **Entry point**: `aitbc_cli.core.main:main` (Click group)
- **Command groups**: 50+ top-level groups registered in `aitbc_cli/core/main.py`
- **Modular subpackages**: `exchange/`, `market/`, `node/`, `wallet/` under `aitbc_cli/commands/`
- **Output formats**: `table` (default), `json`, `yaml`, `csv` via global `--output` flag
- **Config**: `/etc/aitbc/blockchain.env`, `/etc/aitbc/node.env`, `~/.aitbc/config`, env vars (`AITBC_RPC_URL`, `AITBC_COORDINATOR_URL`, ...)

See [`../FILE_ORGANIZATION_SUMMARY.md`](../FILE_ORGANIZATION_SUMMARY.md) for the full directory tree.

---

## Related Resources

- [CLI README](../README.md) — user-facing overview and command reference
- [CLI Usage Guide](../CLI_USAGE_GUIDE.md) — detailed workflows
- [File Organization Summary](../FILE_ORGANIZATION_SUMMARY.md) — directory structure
- [Disabled Commands Cleanup](DISABLED_COMMANDS_CLEANUP.md) — historical analysis

### Help & Support
- **Documentation Issues**: [Report Issues](https://github.com/oib/AITBC/issues)
- **Community Forum**: [AITBC Forum](https://forum.aitbc.net)
- **Technical Support**: [AITBC Support](https://support.aitbc.net)

---

*Last updated: 2026-06-22*<br>
*Version: 2.1.0 (CLI runtime)*<br>
*Status: Active index for CLI technical documentation*
