# QA Validation Report — DEMO-2

## Scope
Harden island credentials file permissions in `cli/aitbc_cli/utils/island_credentials.py`.

## Commit under test
`0bdaeaa68d5026b1cbd21a0cfc00101b4e7e8a2d` on `origin/DEMO-2-auto`

## Validation commands

### Lint
```bash
/tmp/qas-venv/bin/ruff check cli/aitbc_cli/utils/island_credentials.py tests/cli/test_island_credentials.py tests/cli/test_utils_island_credentials.py
```
Result: `All checks passed!`

### Unit / integration tests (targeted)
```bash
PYTHONPATH=/tmp/qas-fake:cli /tmp/qas-venv/bin/python -m pytest tests/cli/test_island_credentials.py tests/cli/test_utils_island_credentials.py -q --confcutdir=tests/cli
```
Result: `41 passed` (0 failed)

Note: the full monorepo dependency tree is not installed in this sandbox, so the CLI package was stub-shimmed for `get_logger` only; the source file under test and both test files were executed unmodified.

## Acceptance-criteria check

- [x] `load_island_credentials` checks that the credentials file is owned by the effective user (`file_stat.st_uid != os.geteuid()`).
- [x] `load_island_credentials` checks the file mode and rejects world-readable or otherwise too-permissive files (`file_stat.st_mode & 0o777 > 0o600`).
- [x] A `PermissionError` is raised with a one-line, actionable message when permissions are invalid.
- [x] A unit test (`test_load_island_credentials_world_readable`) covers a file with mode `0o644` and asserts the permission check raises.
- [x] Existing happy-path tests for `load_island_credentials` still pass.
- [x] The change is minimal and does not refactor unrelated credential logic.

## Verdict

PASS — all acceptance criteria met; targeted lint and test suites green. Approved for RTE.
