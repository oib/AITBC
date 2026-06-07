---
description: Autonomous skill for SSH-based investigation of gitea-runner CI logs, runner health, and root-cause-oriented debug guidance
title: Gitea Runner Log Debugger
version: 1.1
---

# Gitea Runner Log Debugger Skill

## Purpose
Use this skill to diagnose failed Gitea Actions runs by connecting to `gitea-runner`, reading CI log files, correlating them with runner health, and producing targeted debug suggestions.

## Activation
Activate this skill when:
- a Gitea workflow fails and the UI log is incomplete or inconvenient
- Windsurf needs direct access to runner-side CI logs
- you need to distinguish workflow failures from runner failures
- you need evidence-backed debug suggestions instead of generic guesses
- a job appears to fail because of OOM, restart loops, path mismatches, or missing dependencies

## Known Environment Facts
- Runner host: `ssh gitea-runner`
- Runner service: `gitea-runner.service`
- Runner binary: `/opt/gitea-runner/act_runner`
- Persistent CI logs: `/opt/gitea-runner/logs`
- Indexed log manifest: `/opt/gitea-runner/logs/index.tsv`
- Latest log symlink: `/opt/gitea-runner/logs/latest.log`
- Gitea Actions on this runner exposes GitHub-compatible runtime variables, so `GITHUB_RUN_ID` is the correct run identifier to prefer over `GITEA_RUN_ID`

## Inputs

### Minimum Input
- failing workflow name, job name, or pasted error output

### Best Input
```json
{
  "workflow_name": "Staking Tests",
  "job_name": "test-staking-service",
  "run_id": "1787",
  "symptoms": [
    "ModuleNotFoundError: No module named click"
  ],
  "needs_runner_health_check": true
}
```

## Expected Outputs
```json
{
  "failure_class": "workflow_config | dependency_packaging | application_test | service_readiness | runner_infrastructure | unknown",
  "root_cause": "string",
  "evidence": ["string"],
  "minimal_fix": "string",
  "follow_up_checks": ["string"],
  "confidence": "low | medium | high"
}
```

## Investigation Sequence

### 1. Connect and Verify Runner
```bash
ssh gitea-runner 'hostname; whoami; systemctl is-active gitea-runner'
```

### 2. Locate Relevant CI Logs
Prefer indexed job logs first.

```bash
ssh gitea-runner 'tail -n 20 /opt/gitea-runner/logs/index.tsv'
ssh gitea-runner 'tail -n 200 /opt/gitea-runner/logs/latest.log'
```

If a run id is known:

```bash
ssh gitea-runner "awk -F '\t' '\$2 == \"1787\" {print}' /opt/gitea-runner/logs/index.tsv"
```

If only workflow/job names are known:

```bash
ssh gitea-runner 'grep -i "production tests" /opt/gitea-runner/logs/index.tsv | tail -n 20'
ssh gitea-runner 'grep -i "test-production" /opt/gitea-runner/logs/index.tsv | tail -n 20'
```

### 3. Read the Job Log Before the Runner Log
```bash
ssh gitea-runner 'tail -n 200 /opt/gitea-runner/logs/<resolved-log>.log'
```

### 4. Correlate With Runner State
```bash
ssh gitea-runner 'systemctl status gitea-runner --no-pager'
ssh gitea-runner 'journalctl -u gitea-runner -n 200 --no-pager'
ssh gitea-runner 'tail -n 200 /opt/gitea-runner/runner.log'
```

### 5. Check for Resource Exhaustion Only if Indicated
```bash
ssh gitea-runner 'free -h; df -h /opt /var /tmp'
ssh gitea-runner 'dmesg -T | grep -i -E "oom|out of memory|killed process" | tail -n 50'
```

## Classification Rules

### Workflow Config Failure
Evidence patterns:
- script path not found
- wrong repo path
- wrong service/unit name
- wrong import target or startup command
- missing environment export

Default recommendation:
- patch the workflow with the smallest targeted fix

### Dependency / Packaging Failure
Evidence patterns:
- `ModuleNotFoundError`
- `ImportError`
- failed editable install
- Poetry package discovery failure
- missing pip/Node dependency in lean CI setup

Default recommendation:
- add only the missing dependency when truly required
- otherwise fix the import chain or packaging metadata root cause

### Application / Test Failure
Evidence patterns:
- normal environment setup completes
- tests collect and run
- failure is an assertion or application traceback

Default recommendation:
- patch code or tests, not the runner

### Service Readiness Failure
Evidence patterns:
- health endpoint timeout
- process exits immediately
- server log shows startup/config exception

Default recommendation:
- inspect service startup logs and verify host/path/port assumptions

### Runner / Infrastructure Failure
Evidence patterns:
- `oom-kill` in `journalctl`
- runner daemon restart loop
- truncated logs across unrelated workflows
- disk exhaustion or temp space errors

Default recommendation:
- treat as runner capacity/stability issue only when evidence is direct

## Decision Heuristics
- Prefer the job log over `journalctl` for code/workflow failures
- Prefer the smallest fix that explains all evidence
- Do not suggest restarting the runner unless the user asks or the runner is clearly unhealthy
- Ignore internal `task <id>` values for workflow naming or file lookup
- If `/opt/gitea-runner/logs` is missing a run, check whether the workflow had the logging initializer at that time

## Debug Suggestion Template
When reporting back, use this structure:

### Failure Class
`<workflow_config | dependency_packaging | application_test | service_readiness | runner_infrastructure | unknown>`

### Root Cause
One sentence describing the most likely issue.

### Evidence
- `<specific log line>`
- `<specific log line>`
- `<runner health correlation if relevant>`

### Minimal Fix
One focused change that addresses the root cause.

### Optional Follow-up
- `<verification step>`
- `<secondary diagnostic if needed>`

### Confidence
`low | medium | high`

## Safety Constraints
- Read-only first
- No service restarts without explicit user approval
- No deletion of runner files during diagnosis
- Do not conflate application tracebacks with runner instability

## Fast First-Pass Bundle
```bash
ssh gitea-runner '
  echo "=== latest runs ===";
  tail -n 10 /opt/gitea-runner/logs/index.tsv 2>/dev/null || true;
  echo "=== latest log ===";
  tail -n 120 /opt/gitea-runner/logs/latest.log 2>/dev/null || true;
  echo "=== runner service ===";
  systemctl status gitea-runner --no-pager | tail -n 40 || true;
  echo "=== runner journal ===";
  journalctl -u gitea-runner -n 80 --no-pager || true
'
```

## Related Assets
- `.windsurf/workflows/gitea-runner-ci-debug.md`
- `scripts/ci/setup-job-logging.sh`
