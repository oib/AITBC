# Dependency Audit Report

**Date**: 2026-07-29
**Scope**: Python dependency security audit (`pip-audit`) + static security lint (`bandit`)
**Tools**: pip-audit 2.10.1, bandit 1.9.4. `safety` 3.7.0 could not run (see Tooling Notes).

## Executive Summary

- Packages scanned: 168 pinned (`requirements.txt`, local editable `aitbc-shared` excluded — see notes)
- Security issues (pip-audit): 6 known vulnerabilities across 4 packages, 0 without triage guidance
- Static lint (bandit): 107 medium-confidence/severity findings, 0 high-severity, across 5 rule categories, over 212k LOC
- Tickets filed: 9 (4 CVE remediation, 5 bandit rule-category triage)

## Findings

### 1. Security Issues (pip-audit, real CVEs/GHSA advisories)

| Package | Installed | Advisory | Fix | Notes |
|---|---|---|---|---|
| `ecdsa` | 0.19.2 | PYSEC-2026-1325 | **none available** | Minerva timing attack on P-256 curve via `sign_digest()` — can leak the private key's internal nonce. No upstream fix; needs a mitigation decision, not just a version bump. |
| `msgpack` | 1.1.2 | GHSA-6v7p-g79w-8964 | 1.2.1 | Re-using an `Unpacker` after an error can crash (SEGV) or enable a DoS if unpacking untrusted external input. |
| `pydantic-settings` | 2.14.1 | GHSA-4xgf-cpjx-pc3j | 2.14.2 | `NestedSecretsSettingsSource` follows symlinks pointing *outside* `secrets_dir` when `secrets_nested_subdir=True`, reading secrets from an unintended location. |
| `starlette` | 1.2.1 | PYSEC-2026-248 | 1.3.0 | `request.url` is reconstructed from the raw HTTP path without validation — a crafted path can produce a URL pointing at an unintended scheme/host. |
| `starlette` | 1.2.1 | PYSEC-2026-249 | 1.3.1 | `request.form()`'s `max_fields`/`max_part_size` limits are enforced for `multipart/form-data` but silently ignored for `application/x-www-form-urlencoded`, bypassing the resource-consumption bound. |

### 2. Static Security Lint (bandit, `-ll` = medium+ only)

No HIGH-severity findings. 107 MEDIUM findings, grouped by rule (bandit confidence, not exploitation likelihood — each category needs manual triage, most are probably intentional/safe but unreviewed):

| Rule | Count | Description | Representative locations |
|---|---|---|---|
| B608 `hardcoded_sql_expressions` | 23 | Possible SQL injection via string-built queries | `apps/blockchain-explorer/routers/analytics.py:39`, `apps/bridge-monitor/src/bridge_monitor/storage.py:168`, `apps/coordinator-api/scripts/migrate_complete.py` (multiple) |
| B108 `hardcoded_tmp_directory` | 41 | Hardcoded `/tmp` paths (symlink/race risk) | `apps/coordinator-api/.../agent_coordination/services/security.py` (multiple), test fixtures |
| B104 `hardcoded_bind_all_interfaces` | 31 | Binding to `0.0.0.0` | `aitbc/config/hierarchical_config.py` (multiple) |
| B310 `blacklist` (url open) | 11 | `urlopen`-family calls not scheme-restricted | `aitbc/oracles/price_oracle.py:194`, `apps/coordinator-api/.../alerting.py:109`, `apps/exchange/simple_exchange/handlers/*.py` |
| B113 `request_without_timeout` | 1 | `requests` call with no timeout (can hang indefinitely) | `apps/pool-hub/src/poolhub/services/validation.py:70` |

## Recommendations

### Immediate Actions (High Priority)

1. `pydantic-settings` → 2.14.2 (secrets-directory symlink escape)
2. `starlette` → >=1.3.1 (two real CVEs; also the shared ASGI framework across most services)
3. Decide a mitigation for `ecdsa`'s unfixed Minerva timing attack (constant-time alternative, isolate usage, or accept risk with justification)

### Short-term (Medium Priority)

4. `msgpack` → 1.2.1
5. Triage the 23 B608 SQL-injection-shaped findings — confirm parameterization or fix

### Long-term (Low Priority)

6. Review B310 (URL-scheme restriction), B104 (bind-all-interfaces — likely intentional for containerized services, confirm), B108 (temp-file hygiene), B113 (single timeout fix)

## Tooling Notes

- `safety` 3.7.0 requires SaaS auth (`safety auth login`) for `scan`, and additionally crashed with an internal `typer`/`click` traceback on Python 3.13.5 in this environment — not usable without further dependency-compatibility work. Not run.
- `pip-audit` was run against `requirements.txt` with the local editable install line (`-e file:///opt/aitbc/packages/aitbc-shared`, a stale/mismatched-case path) stripped, since it broke pip-audit's dependency resolution. Only third-party pinned packages were scanned; the local package itself was not.
- `poetry show --outdated` was not run — `poetry` is not installed in this environment (only a bare venv with the audit tools themselves).
- Node/JS per-app audits (`apps/explorer-web`, `contracts/`) were out of scope for this pass.

## Implementation Tickets

Filed in the active tracker (Gitea Issues, `oib/aitbc`), grouped under one epic:

- **AITBC-60** (epic): Dependency/security audit remediation (2026-07-29)
  - AITBC-51: ecdsa 0.19.2 Minerva timing attack (PYSEC-2026-1325) — no fix available, needs mitigation
  - AITBC-52: msgpack 1.1.2 DoS on repeated Unpacker error (GHSA-6v7p-g79w-8964) — upgrade to 1.2.1
  - AITBC-53: pydantic-settings 2.14.1 secrets-dir symlink escape (GHSA-4xgf-cpjx-pc3j) — upgrade to 2.14.2
  - AITBC-54: starlette 1.2.1 — two CVEs (PYSEC-2026-248, PYSEC-2026-249) — upgrade to >=1.3.1
  - AITBC-55: bandit B608 triage — 23 possible SQL-injection-shaped queries
  - AITBC-56: bandit B108 triage — 41 hardcoded /tmp usages
  - AITBC-57: bandit B104 triage — 31 bind-all-interfaces findings
  - AITBC-58: bandit B310 triage — 11 unrestricted urlopen scheme findings
  - AITBC-59: bandit B113 fix — 1 requests call without a timeout
