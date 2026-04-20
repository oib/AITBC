---
description: SSH to gitea-runner, inspect CI job logs, correlate runner health, and produce root-cause-focused debug suggestions
---

# Gitea Runner CI Debug Workflow

## Purpose
Use this workflow when a Gitea Actions job fails and you need Windsurf to:
- SSH to `gitea-runner`
- locate the most relevant CI log files
- inspect runner health and runner-side failures
- separate workflow/application failures from runner/infrastructure failures
- produce actionable debug suggestions with evidence

## Key Environment Facts
- The actual runner host is reachable via `ssh gitea-runner`
- The runner service is `gitea-runner.service`
- The runner binary is `/opt/gitea-runner/act_runner`
- Gitea Actions on this runner behaves like a GitHub-compatibility layer
- Prefer `GITHUB_RUN_ID` and `GITHUB_RUN_NUMBER`, not `GITEA_RUN_ID`
- Internal runner `task <id>` messages in `journalctl` are useful for runner debugging, but are not stable workflow-facing identifiers
- CI job logs created by the reusable logging wrapper live under `/opt/gitea-runner/logs`

## Safety Rules
- Start with read-only inspection only
- Do not restart the runner or mutate files unless the user explicitly asks
- Prefer scoped log reads over dumping entire files
- If a failure is clearly application-level, stop proposing runner changes

## Primary Log Sources

### Job Logs
- `/opt/gitea-runner/logs/index.tsv`
- `/opt/gitea-runner/logs/latest.log`
- `/opt/gitea-runner/logs/latest-<workflow>.log`
- `/opt/gitea-runner/logs/latest-<workflow>-<job>.log`

### Runner Logs
- `journalctl -u gitea-runner`
- `/opt/gitea-runner/runner.log`
- `systemctl status gitea-runner --no-pager`

## Workflow Steps

### Step 1: Confirm Runner Reachability
```bash
ssh gitea-runner 'hostname; whoami; systemctl is-active gitea-runner'
```

Expected outcome:
- host is `gitea-runner`
- user is usually `root`
- service is `active`

### Step 2: Find Candidate CI Logs
If you know the workflow or job name, start there.

```bash
ssh gitea-runner 'ls -lah /opt/gitea-runner/logs'
ssh gitea-runner 'tail -n 20 /opt/gitea-runner/logs/index.tsv'
ssh gitea-runner 'tail -n 200 /opt/gitea-runner/logs/latest.log'
```

If you know the run id:

```bash
ssh gitea-runner "awk -F '\t' '\$2 == \"1787\" {print}' /opt/gitea-runner/logs/index.tsv"
```

If you know the workflow/job name:

```bash
ssh gitea-runner 'grep -i "staking tests" /opt/gitea-runner/logs/index.tsv | tail -n 20'
ssh gitea-runner 'grep -i "test-staking-service" /opt/gitea-runner/logs/index.tsv | tail -n 20'
```

### Step 3: Read the Most Relevant Job Log
After identifying the file path from `index.tsv`, inspect the tail first.

```bash
ssh gitea-runner 'tail -n 200 /opt/gitea-runner/logs/<resolved-log-file>.log'
```

If `latest.log` already matches the failing run:

```bash
ssh gitea-runner 'tail -n 200 /opt/gitea-runner/logs/latest.log'
```

### Step 4: Correlate With Runner Health
Only do this after reading the job log, so you do not confuse test failures with runner failures.

```bash
ssh gitea-runner 'systemctl status gitea-runner --no-pager'
ssh gitea-runner 'journalctl -u gitea-runner -n 200 --no-pager'
ssh gitea-runner 'tail -n 200 /opt/gitea-runner/runner.log'
```

### Step 5: Check for Infrastructure Pressure
Use these when the log suggests abrupt termination, hanging setup, missing containers, or unexplained exits.

```bash
ssh gitea-runner 'free -h; df -h /opt /var /tmp'
ssh gitea-runner 'dmesg -T | grep -i -E "oom|out of memory|killed process" | tail -n 50'
ssh gitea-runner 'journalctl -u gitea-runner --since "2 hours ago" --no-pager | grep -i -E "oom|killed|failed|panic|error"'
```

### Step 6: Classify the Failure
Use the evidence to classify the failure into one of these buckets.

#### A. Workflow / Config Regression
Typical evidence:
- missing script path
- wrong workspace path
- wrong import target
- wrong service name
- bad YAML logic

Typical fixes:
- patch the workflow
- correct repo-relative paths
- fix `PYTHONPATH`, script invocation, or job dependencies

#### B. Dependency / Packaging Failure
Typical evidence:
- `ModuleNotFoundError`
- editable install failure
- Poetry/pyproject packaging errors
- missing test/runtime packages

Typical fixes:
- add the minimal missing dependency
- avoid broadening installs unnecessarily
- fix package metadata only if the install is actually required

#### C. Application / Test Failure
Typical evidence:
- assertion failures
- application tracebacks after setup completes
- service starts but endpoint behavior is wrong

Typical fixes:
- patch code or tests
- address the real failing import chain or runtime logic

#### D. Service Readiness / Integration Failure
Typical evidence:
- health-check timeout
- `curl` connection refused
- server never starts
- dependent services unavailable

Typical fixes:
- inspect service logs
- fix startup command or environment
- ensure readiness probes hit the correct host/path

#### E. Runner / Infrastructure Failure
Typical evidence:
- `oom-kill` in `journalctl`
- runner daemon restart loop
- disk full or temp space exhaustion
- SSH reachable but job logs end abruptly

Typical fixes:
- reduce CI memory footprint
- split large jobs
- investigate runner/container resource limits
- only restart runner if explicitly requested

## Analysis Heuristics

### Prefer the Smallest Plausible Root Cause
Do not blame the runner for a clean Python traceback in a job log.

### Use Job Logs Before Runner Logs
Job logs usually explain application/workflow failures better than runner logs.

### Treat OOM as a Runner Problem Only With Evidence
Look for `oom-kill`, `killed process`, or abrupt job termination without a normal traceback.

### Distinguish Missing Logs From Missing Logging
If `/opt/gitea-runner/logs` does not contain the run you want, verify whether the workflow had the logging initializer yet.

## Recommended Windsurf Output Format
When the investigation is complete, report findings in this structure:

```text
Failure class:
Root cause:
Evidence:
- <log line or command result>
- <log line or command result>
Why this is the likely cause:
Minimal fix:
Optional follow-up checks:
Confidence: <low|medium|high>
```

## Quick Command Bundle
Use this bundle when you need a fast first pass.

```bash
ssh gitea-runner '
  echo "=== service ===";
  systemctl is-active gitea-runner;
  echo "=== latest indexed runs ===";
  tail -n 10 /opt/gitea-runner/logs/index.tsv 2>/dev/null || true;
  echo "=== latest job log ===";
  tail -n 120 /opt/gitea-runner/logs/latest.log 2>/dev/null || true;
  echo "=== runner journal ===";
  journalctl -u gitea-runner -n 80 --no-pager || true
'
```

## Escalation Guidance
Escalate to a deeper infrastructure review when:
- the runner repeatedly shows `oom-kill`
- job logs are truncated across unrelated workflows
- the runner daemon is flapping
- disk or tmp space is exhausted
- the same failure occurs across multiple independent workflows without a shared code change

## Related Files
- `/opt/aitbc/scripts/ci/setup-job-logging.sh`
- `/opt/aitbc/.gitea/workflows/staking-tests.yml`
- `/opt/aitbc/.gitea/workflows/production-tests.yml`
- `/opt/aitbc/.gitea/workflows/systemd-sync.yml`
