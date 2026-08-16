# AITBC CLI Testing

**Last updated:** 2026-08-16

The CLI's tests live in `cli/tests/`: 87 tests across seven files. As of V23-84 they run with
everything else — `cli/tests` is in `testpaths` in the root `pyproject.toml`, so a bare
`pytest` from the repository root collects them.

Before that they were collected by nothing. `cli/` carried its own `pytest.ini` whose
`testpaths = cli/tests` resolved against rootdir `cli/`, so it pointed at `cli/cli/tests`,
which does not exist; pytest warned and fell back to searching the working directory. The 87
tests were found by that fallback, and only when the invocation happened to start at `cli/` or
`cli/tests`. The ini file is gone; there is one pytest configuration for the repository.

## Running them

```bash
/opt/aitbc/venv/bin/pytest cli/tests -q
```

From anywhere in the tree, with the root configuration. To run one file or one class:

```bash
/opt/aitbc/venv/bin/pytest cli/tests/test_explorer.py -q
```

```bash
/opt/aitbc/venv/bin/pytest cli/tests/test_cli_comprehensive.py::TestSimulateCommand -v
```

Use `venv/bin/pytest` rather than a system pytest: the root configuration requires
`pytest-rerunfailures` and `pytest-timeout`, which are installed in the virtualenv.

`cd cli && pytest` still runs just these 87. Removing `cli/pytest.ini` did not change that:
rootdir is now the repository root, so the real configuration applies, and pytest skips
`testpaths` when the invocation directory is not the rootdir and collects from where it was
invoked instead.

## What is covered

| file | tests | what it exercises |
|---|---|---|
| `test_explorer.py` | 39 | all 14 `explorer` subcommands, in-process through Click's `CliRunner` with the explorer client mocked — including its error paths (`NetworkError`, an empty result, an unexpected exception) |
| `test_cli_comprehensive.py` | 25 | the command tree end to end, by running the launcher as a subprocess: `simulate`, `blockchain`, `network`, `market`, `ai`, `resource`, output formats, and the argument errors each group should reject |
| `test_cli_basic.py` | 8 | that the launcher starts, that `--help` lists the top-level groups, and that an invalid command exits non-zero |
| `test_gpu_marketplace.py` | 7 | that `gpu` and the six `market` subcommands are registered and their help text is what the docs claim — help-text checks, not behaviour |
| `test_exchange_island.py` | 5 | argument validation on `exchange buy`, `sell` and `orderbook`: invalid amounts, currencies and trading pairs are rejected |
| `test_island_credentials.py` | 2 | loading island credentials, including the missing-file and malformed-file paths |
| `test_wallet_creation.py` | 1 | that a file-backed wallet is created with a real private key rather than a placeholder |

## Two kinds of test in here

**In-process** (`test_explorer.py`, `test_gpu_marketplace.py`, `test_exchange_island.py`) —
Click's `CliRunner` invokes the command object directly with its client mocked. Fast,
deterministic, and able to assert on what the command sent as well as what it printed.

**Subprocess** (`test_cli_basic.py`, `test_cli_comprehensive.py`) — these run
`scripts/aitbc-cli`, the launcher that `/usr/local/bin/aitbc` symlinks to. Shallow by
comparison, mostly `--help` and exit codes, but they are the only tests that would catch a
CLI that fails to start at all: a bad import in any command module is invisible to every
in-process test that does not import that module.

Both files derive their paths from `__file__` rather than hard-coding `/opt/aitbc` and
`/usr/local/bin/aitbc`, so a checkout elsewhere, or one without the symlink installed, runs
them against its own tree.

## What is not covered

- No command that writes to a chain, submits a job, or moves funds is exercised against a live
  service, by design. The subprocess tests stop at `--help` and argument validation for those.
- `network test --peer localhost` is attempted twice and its result is asserted as
  `returncode in (0, 1, 2)`, which accepts every outcome the command can produce. It is a
  crash check, not a connectivity check.
- `cli/tests/run_cli_tests.py` is a standalone runner script, not a pytest module, and nothing
  collects it.

## Adding tests

Put them in `cli/tests/`; they are collected automatically. Markers must be registered in the
root `pyproject.toml` — `--strict-markers` is on, and an unregistered marker fails collection
rather than being ignored.
