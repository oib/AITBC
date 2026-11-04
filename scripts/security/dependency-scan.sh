#!/bin/bash
# Local dependency security scanning script
# Run this script to check for security vulnerabilities in dependencies
#
# pip-audit is the only scanner (SEC-19): the previous second scanner was
# removed from the repo on 2026-09-05 (SEC-15) and is never installed here.
#
# Scan tools live outside the project venv so a scan cannot change the
# project's dependency set:
#   1. pip-audit already on PATH (dev tier)  -> used as-is
#   2. $AITBC_SCAN_TOOLS_VENV with pip-audit -> used as-is, kept
#   3. otherwise a throwaway venv at $AITBC_SCAN_TOOLS_VENV or mktemp -d,
#      removed on exit via trap
# The script never creates or installs into $REPO_ROOT/venv — the project
# venv is created by scripts/ci/setup-python-venv.sh / setup.sh.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== AITBC Dependency Security Scan ===${NC}"
echo ""

PIP_AUDIT=""
CREATED_TOOLS_VENV=""

_cleanup() {
    if [ -n "$CREATED_TOOLS_VENV" ]; then
        rm -rf "$CREATED_TOOLS_VENV"
    fi
}
trap _cleanup EXIT

if command -v pip-audit >/dev/null 2>&1; then
    PIP_AUDIT="pip-audit"
    echo -e "${GREEN}✓ Using pip-audit from PATH${NC}"
elif [ -n "${AITBC_SCAN_TOOLS_VENV:-}" ] && [ -x "${AITBC_SCAN_TOOLS_VENV}/bin/pip-audit" ]; then
    PIP_AUDIT="${AITBC_SCAN_TOOLS_VENV}/bin/pip-audit"
    echo -e "${GREEN}✓ Using tools venv at ${AITBC_SCAN_TOOLS_VENV}${NC}"
else
    TOOLS_VENV="${AITBC_SCAN_TOOLS_VENV:-$(mktemp -d)}"
    echo -e "${BLUE}Creating throwaway tools venv at ${TOOLS_VENV}${NC}"
    python3 -m venv "$TOOLS_VENV"
    "$TOOLS_VENV/bin/pip" install --quiet pip-audit
    PIP_AUDIT="$TOOLS_VENV/bin/pip-audit"
    CREATED_TOOLS_VENV="$TOOLS_VENV"
fi
echo ""

# Run pip-audit against the requirements files and each app's declared
# dependencies ([project].dependencies + [tool.poetry.dependencies]).
# Any non-zero pip-audit run — vulnerabilities or an audit error — is
# recorded and fails the script at the summary.
AUDIT_FAILED=0
APP_REQS="$(mktemp)"
trap 'rm -f "$APP_REQS"; _cleanup' EXIT

echo -e "${BLUE}=== Running pip-audit ===${NC}"
req_found=0
for reqs in requirements*.txt; do
    [ -f "$reqs" ] || continue
    req_found=1
    echo "--- $reqs ---"
    "$PIP_AUDIT" -r "$reqs" --desc || AUDIT_FAILED=1
done
[ "$req_found" = 1 ] || echo -e "${YELLOW}No requirements*.txt found${NC}"
for pyproject in apps/*/pyproject.toml; do
    [ -e "$pyproject" ] || continue
    app="$(basename "$(dirname "$pyproject")")"
    python3 - "$pyproject" > "$APP_REQS" <<'PY'
import sys, tomllib
d = tomllib.load(open(sys.argv[1], "rb"))
lines = list(d.get("project", {}).get("dependencies", []))
for name, spec in d.get("tool", {}).get("poetry", {}).get("dependencies", {}).items():
    if name.lower() == "python":
        continue
    if isinstance(spec, dict):
        if any(k in spec for k in ("path", "git", "url")):
            continue
        extras = f"[{','.join(spec['extras'])}]" if spec.get("extras") else ""
        spec = spec.get("version", "")
        name = f"{name}{extras}"
    if not isinstance(spec, str) or spec in ("", "*"):
        lines.append(name)
    elif spec[0] in "^~" or spec[0].isdigit():
        lines.append(f"{name}>={spec.lstrip('^~')}")
    else:
        lines.append(f"{name}{spec}")
print("\n".join(lines))
PY
    [ -s "$APP_REQS" ] || continue
    echo "--- apps/$app/pyproject.toml ---"
    "$PIP_AUDIT" -r "$APP_REQS" || AUDIT_FAILED=1
done
echo ""

# Check for outdated packages (skip due to cache issues)
echo -e "${BLUE}=== Checking for outdated packages ===${NC}"
echo -e "${YELLOW}Skipping outdated package check due to pip cache issues${NC}"
echo -e "${YELLOW}Run manually: pip list --outdated${NC}"
echo ""

# Check package versions — from the project venv only when it already
# exists; the tools venv carries nothing but pip-audit.
echo -e "${BLUE}=== Critical Package Versions ===${NC}"
if [ -x "venv/bin/pip" ]; then
    echo "Cryptography: $(venv/bin/pip show cryptography 2>/dev/null | grep Version || echo 'Not installed')"
    echo "PyJWT: $(venv/bin/pip show pyjwt 2>/dev/null | grep Version || echo 'Not installed')"
    echo "Requests: $(venv/bin/pip show requests 2>/dev/null | grep Version || echo 'Not installed')"
    echo "SQLAlchemy: $(venv/bin/pip show sqlalchemy 2>/dev/null | grep Version || echo 'Not installed')"
else
    echo -e "${YELLOW}No project venv at ./venv — skipping installed-version listing${NC}"
    echo -e "${YELLOW}(the project venv is created by setup.sh / scripts/ci/setup-python-venv.sh, not by a scan)${NC}"
fi
echo ""

# Generate summary report
echo -e "${BLUE}=== Security Scan Summary ===${NC}"
if [ "$AUDIT_FAILED" -ne 0 ]; then
    echo -e "${YELLOW}✗ pip-audit reported vulnerabilities or audit errors — scan FAILED${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Security scan completed — no known vulnerabilities${NC}"
echo ""
echo "Primary security scan (pip-audit) completed successfully."
echo "Note: pip-audit is the only dependency scanner — no other scan tools"
echo "are installed, and nothing is installed into the project venv."
echo "For comprehensive scanning, consider: pip-audit --audit-log <output-file>"
echo ""
echo "Recommendations:"
echo "  1. Review any vulnerabilities found above"
echo "  2. Update affected packages: pip install --upgrade <package>"
echo "  3. Test thoroughly after updates"
echo "  4. Commit updated requirements.txt"
echo ""
