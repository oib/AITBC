---
description: GitHub CLI operations for authentication status and API interaction in AITBC context
title: github-cli-operations-skill
version: 1.2
---

# GitHub CLI Operations Skill

## Purpose
Test and validate GitHub CLI (gh) authentication status and API interaction capabilities for AITBC repository operations, CI/CD integration, Gitea compatibility checks, and security alert management (Dependabot and CodeQL code scanning).

## Activation
Trigger when user requests GitHub CLI operations: authentication verification, API testing, repository interaction, Gitea API compatibility checks, Dependabot alert management, or CodeQL code scanning alert management.

## Input
```json
{
  "operation": "check-auth|api-request|repo-info|workflow-status|gitea-check|dependabot-alerts|code-scanning-alerts|comprehensive",
  "api_endpoint": "string (optional for api-request, default: /user)",
  "api_method": "GET|POST|PUT|DELETE|PATCH (optional, default: GET)",
  "api_headers": "object (optional for api-request)",
  "api_body": "object (optional for api-request)",
  "repo_owner": "string (optional for repo-info, default: current)",
  "repo_name": "string (optional for repo-info)",
  "workflow_id": "string (optional for workflow-status)",
  "gitea_host": "string (optional for gitea-check, default: gitea.bubuit.net:3000)",
  "alert_state": "string (optional for dependabot-alerts/code-scanning-alerts, default: open)",
  "alert_ids": "array of numbers (optional for dependabot-alerts/code-scanning-alerts)",
  "dismissal_reason": "string (optional for dependabot-alerts/code-scanning-alerts)",
  "dismissal_comment": "string (optional for dependabot-alerts/code-scanning-alerts)",
  "timeout": "number (optional, default: 30 seconds)"
}
```

## Output
```json
{
  "summary": "GitHub CLI operations completed",
  "operation": "check-auth|api-request|repo-info|workflow-status|gitea-check|dependabot-alerts|code-scanning-alerts|comprehensive",
  "auth_status": {
    "authenticated": "boolean",
    "username": "string",
    "token_scopes": "array of strings",
    "github_enterprise": "boolean",
    "gitea_compatible": "boolean"
  },
  "api_response": {
    "status_code": "number",
    "response_body": "object",
    "success": "boolean"
  },
  "repo_info": {
    "name": "string",
    "owner": "string",
    "url": "string",
    "default_branch": "string",
    "visibility": "string"
  },
  "workflow_status": {
    "id": "string",
    "state": "string",
    "conclusion": "string",
    "created_at": "string",
    "updated_at": "string"
  },
  "gitea_status": {
    "reachable": "boolean",
    "version": "string",
    "api_compatible": "boolean"
  },
  "dependabot_alerts": {
    "total_count": "number",
    "open_count": "number",
    "dismissed_count": "number",
    "alerts": [
      {
        "number": "number",
        "dependency": "string",
        "severity": "string",
        "state": "string",
        "url": "string"
      }
    ],
    "dismissed_ids": "array of numbers"
  },
  "code_scanning_alerts": {
    "total_count": "number",
    "open_count": "number",
    "dismissed_count": "number",
    "alerts": [
      {
        "number": "number",
        "rule": "string",
        "severity": "string",
        "state": "string",
        "path": "string",
        "url": "string"
      }
    ],
    "dismissed_ids": "array of numbers"
  },
  "issues": [],
  "recommendations": [],
  "confidence": 1.0,
  "execution_time": "number",
  "validation_status": "success|partial|failed"
}
```

## Process

### 1. Analyze
- Validate GitHub CLI installation and version
- Check authentication status and token validity
- Verify API endpoint accessibility
- Assess Gitea compatibility if requested
- Review repository access permissions

### 2. Plan
- Define authentication verification steps
- Prepare API request parameters and headers
- Set up repository information retrieval strategy
- Configure workflow status monitoring
- Plan Gitea compatibility checks

### 3. Execute

#### Check Authentication
```bash
# Verify GitHub CLI authentication
gh auth status

# Get current authentication details
gh auth token
gh config get github.com
gh config get gitea.bubuit.net
```

#### API Requests
```bash
# Basic API request
gh api /user

# API request with method
gh api /repos/oib/aitbc

# API request with custom headers
gh api /user -H "Accept: application/vnd.github.v3+json"

# POST request with body
gh api /repos/oib/aitbc/issues -X POST -f title="Test Issue" -f body="Description"

# API request to Gitea
gh api /api/v1/user --hostname gitea.bubuit.net:3000
```

#### Repository Information
```bash
# Get repository information
gh repo view oib/aitbc

# Get repository details via API
gh api /repos/oib/aitbc

# Get repository issues
gh api /repos/oib/aitbc/issues

# Get repository workflows
gh api /repos/oib/aitbc/actions/workflows
```

#### Workflow Status
```bash
# List recent workflow runs
gh run list --repo oib/aitbc

# Get specific workflow run details
gh run view <run_id> --repo oib/aitbc

# Get workflow status via API
gh api /repos/oib/aitbc/actions/runs/<run_id>
```

#### Gitea Compatibility
```bash
# Check Gitea authentication
gh auth status --hostname gitea.bubuit.net:3000

# Test Gitea API
gh api /api/v1/user --hostname gitea.bubuit.net:3000

# Check Gitea version
gh api /api/v1/version --hostname gitea.bubuit.net:3000
```

#### Dependabot Alert Management
```bash
# List all Dependabot alerts
gh api repos/oib/AITBC/dependabot/alerts

# List open Dependabot alerts
gh api repos/oib/AITBC/dependabot/alerts --jq '.[] | select(.state == "open")'

# Get specific alert details
gh api repos/oib/AITBC/dependabot/alerts/<alert_number>

# Dismiss a single alert
gh api -X PATCH repos/oib/AITBC/dependabot/alerts/<alert_number> \
  -f state=dismissed \
  -f dismissed_reason=fix_started \
  -f dismissed_comment="Fixed by dependency update in commit <commit_hash>"

# Dismiss multiple alerts (batch)
for alert in 542 541 540 537 536; do
  gh api -X PATCH "repos/oib/AITBC/dependabot/alerts/$alert" \
    -f state=dismissed \
    -f dismissed_reason=fix_started \
    -f dismissed_comment="Fixed by dependency update"
done

# Valid dismissal reasons: fix_started, inaccurate, no_bandwidth, not_used, tolerable_risk
```

#### CodeQL Code Scanning Alert Management
```bash
# List all code scanning alerts
gh api repos/oib/AITBC/code-scanning/alerts

# List open code scanning alerts
gh api repos/oib/AITBC/code-scanning/alerts --jq '.[] | select(.state == "open")'

# Get specific alert details
gh api repos/oib/AITBC/code-scanning/alerts/<alert_number>

# Dismiss a single alert
gh api -X PATCH repos/oib/AITBC/code-scanning/alerts/<alert_number> \
  -f state=dismissed \
  -f dismissed_reason="false positive" \
  -f dismissed_comment="Fixed in commit <commit_hash> - vulnerability no longer present in code"

# Dismiss multiple alerts (batch)
for alert in 2974 2973 2972 2971; do
  gh api -X PATCH "repos/oib/AITBC/code-scanning/alerts/$alert" \
    -f state=dismissed \
    -f dismissed_reason="false positive" \
    -f dismissed_comment="Fixed in commit <commit_hash>"
done

# Valid dismissal reasons: false positive, won't fix, used in tests
```

### 4. Validate
- Confirm authentication is valid and has required scopes
- Verify API responses return expected data structures
- Check repository access permissions are sufficient
- Validate workflow status information is accurate
- Confirm Gitea API compatibility for CI/CD operations
- Verify Dependabot alert dismissal operations completed successfully
- Verify CodeQL code scanning alert dismissal operations completed successfully
- Confirm alert state changes are reflected in GitHub UI

### 5. Report
- Summarize authentication status and token scopes
- Report API response data and success indicators
- Provide repository information and access details
- Display workflow status and recent runs
- Indicate Gitea compatibility status
- List Dependabot alerts and dismissal status
- List CodeQL code scanning alerts and dismissal status
- List any issues or recommendations

## Common Use Cases

### CI/CD Integration
```bash
# Check authentication before CI operations
gh auth status

# Trigger workflow via API
gh api /repos/oib/aitbc/actions/workflows/<workflow_id>/dispatches \
  -X POST -f ref=main -f inputs='{"param":"value"}'
```

### Repository Management
```bash
# Get repository statistics
gh api /repos/oib/aitbc

# List branches
gh api /repos/oib/aitbc/branches

# Get commit history
gh api /repos/oib/aitbc/commits
```

### Issue and PR Operations
```bash
# List open issues
gh api /repos/oib/aitbc/issues?state=open

# Create issue
gh api /repos/oib/aitbc/issues -X POST \
  -f title="Test Issue" -f body="Description"

# List pull requests
gh api /repos/oib/aitbc/pulls
```

### Gitea Operations
```bash
# Check Gitea authentication
gh auth status --hostname gitea.bubuit.net:3000

# Get Gitea user info
gh api /api/v1/user --hostname gitea.bubuit.net:3000

# Get Gitea repository info
gh api /api/v1/repos/oib/aitbc --hostname gitea.bubuit.net:3000
```

### Dependabot Alert Management
```bash
# List open Dependabot alerts
gh api repos/oib/AITBC/dependabot/alerts \
  --jq '.[] | select(.state == "open") | {number, dependency: .dependency.package.name, severity: .security_advisory.severity, url: .html_url}'

# Dismiss alerts after dependency update
for alert in 542 541 540 537 536; do
  gh api -X PATCH "repos/oib/AITBC/dependabot/alerts/$alert" \
    -f state=dismissed \
    -f dismissed_reason=fix_started \
    -f dismissed_comment="Fixed by dependency update in commit <commit_hash>"
done

# Get alert details before dismissal
gh api repos/oib/AITBC/dependabot/alerts/<alert_number> \
  --jq '{number, dependency, severity, vulnerable_version_range, first_patched_version}'
```

### CodeQL Code Scanning Alert Management
```bash
# List open code scanning alerts
gh api repos/oib/AITBC/code-scanning/alerts \
  --jq '.[] | select(.state == "open") | {number, rule: .rule.id, severity: .rule.security_severity_level, path: .most_recent_instance.location.path, url: .html_url}'

# Dismiss alerts after code fixes
for alert in 2974 2973 2972 2971; do
  gh api -X PATCH "repos/oib/AITBC/code-scanning/alerts/$alert" \
    -f state=dismissed \
    -f dismissed_reason="false positive" \
    -f dismissed_comment="Fixed in commit <commit_hash> - vulnerability no longer present in code"
done

# Get alert details before dismissal
gh api repos/oib/AITBC/code-scanning/alerts/<alert_number> \
  --jq '{number, rule, severity, path, line: .most_recent_instance.location.start_line}'
```

## Error Handling

### Authentication Issues
- If `gh auth status` fails: Prompt user to run `gh auth login`
- If token lacks required scopes: Prompt user to re-authenticate with correct scopes
- If Gitea authentication fails: Check hostname and credentials

### API Request Issues
- If API endpoint returns 404: Verify endpoint path and repository access
- If API returns 403: Check token permissions and rate limits
- If API returns 500: Check service availability and retry

### Gitea Compatibility Issues
- If Gitea API version incompatible: Note compatibility limitations
- If Gitea endpoint structure differs: Adjust API calls accordingly

### Dependabot Alert Issues
- If alert dismissal fails with 422: Check dismissal_reason is valid (fix_started, inaccurate, no_bandwidth, not_used, tolerable_risk)
- If alert not found: Verify alert number and repository
- If token lacks repo write permissions: Prompt user to re-authenticate with correct scopes
- If batch dismissal fails: Process alerts individually to identify specific failures

### CodeQL Code Scanning Alert Issues
- If alert dismissal fails with 422: Check dismissal_reason is valid (false positive, won't fix, used in tests)
- If alert not found: Verify alert number and repository
- If token lacks repo write permissions: Prompt user to re-authenticate with correct scopes
- If batch dismissal fails: Process alerts individually to identify specific failures
- Note: Code scanning alerts should auto-close when GitHub CodeQL re-scans and detects fixes

## Notes
- GitHub CLI supports both GitHub and Gitea via hostname configuration
- Gitea API endpoints typically use `/api/v1/` prefix vs GitHub's `/api/v3/`
- Authentication tokens should have appropriate scopes for intended operations
- Rate limits apply differently between GitHub and Gitea
- Some GitHub-specific features may not work with Gitea
- Dependabot dismissal reasons: fix_started, inaccurate, no_bandwidth, not_used, tolerable_risk
- CodeQL code scanning dismissal reasons: false positive, won't fix, used in tests
- Code scanning alerts should auto-close when GitHub CodeQL re-scans and detects fixes
- Dependabot alerts should auto-close when dependencies are updated to patched versions

## Related Skills
- `aitbc-ci-debug-skill`: CI/CD workflow debugging
- `gitea-runner-log-debugger`: Gitea runner log analysis
- `aitbc-ai-operations-skill`: AI operations testing
