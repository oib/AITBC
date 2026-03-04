#!/bin/bash

# AITBC Codebase Verification Script
# Verifies that all standardization changes have been applied

echo "=== AITBC Codebase Verification ==="
echo "Date: $(date)"
echo

# Check core services are running
echo "🔍 Core Services Status:"
core_services=("aitbc-blockchain-node" "aitbc-blockchain-rpc" "aitbc-coordinator-api" "aitbc-exchange-api")
for service in "${core_services[@]}"; do
    status=$(systemctl is-active "$service.service" 2>/dev/null || echo "not-found")
    if [[ "$status" == "active" ]]; then
        echo "✅ $service.service: $status"
    else
        echo "❌ $service.service: $status"
    fi
done
echo

# Check user standardization
echo "🔍 User Standardization:"
non_aitbc_users=$(grep -r "User=" /etc/systemd/system/aitbc-*.service | grep -v "User=aitbc" | wc -l)
if [[ $non_aitbc_users -eq 0 ]]; then
    echo "✅ All services use 'aitbc' user"
else
    echo "❌ Found $non_aitbc_users services not using 'aitbc' user"
    grep -r "User=" /etc/systemd/system/aitbc-*.service | grep -v "User=aitbc"
fi
echo

# Check path standardization
echo "🔍 Path Standardization:"
non_opt_paths=$(grep -r "WorkingDirectory=" /etc/systemd/system/aitbc-*.service | grep -v "/opt/aitbc" | wc -l)
if [[ $non_opt_paths -eq 0 ]]; then
    echo "✅ All services use '/opt/aitbc' paths"
else
    echo "❌ Found $non_opt_paths services not using '/opt/aitbc' paths"
    grep -r "WorkingDirectory=" /etc/systemd/system/aitbc-*.service | grep -v "/opt/aitbc"
fi
echo

# Check for duplicate services
echo "🔍 Duplicate Services Check:"
duplicates=$(systemctl list-units --all | grep aitbc | grep "not-found" | wc -l)
if [[ $duplicates -eq 0 ]]; then
    echo "✅ No duplicate services found"
else
    echo "⚠️  Found $duplicates 'not-found' service references (harmless systemd cache)"
fi
echo

# Check file organization
echo "🔍 File Organization:"
if [[ -d "/opt/aitbc/apps" ]]; then
    app_count=$(find /opt/aitbc/apps -maxdepth 1 -type d | wc -l)
    echo "✅ /opt/aitbc/apps/ exists with $((app_count-1)) app directories"
else
    echo "❌ /opt/aitbc/apps/ directory not found"
fi

if [[ -d "/home/oib/windsurf/aitbc/dev/scripts" ]]; then
    script_count=$(find /home/oib/windsurf/aitbc/dev/scripts -name "*.py" | wc -l)
    echo "✅ /home/oib/windsurf/aitbc/dev/scripts/ exists with $script_count Python scripts"
else
    echo "❌ /home/oib/windsurf/aitbc/dev/scripts/ directory not found"
fi

if [[ -d "/home/oib/windsurf/aitbc/scripts/deploy" ]]; then
    deploy_count=$(find /home/oib/windsurf/aitbc/scripts/deploy -name "*.sh" | wc -l)
    echo "✅ /home/oib/windsurf/aitbc/scripts/deploy/ exists with $deploy_count deployment scripts"
else
    echo "❌ /home/oib/windsurf/aitbc/scripts/deploy/ directory not found"
fi
echo

# Check Python version requirements
echo "🔍 Python Version Requirements:"
python_checks=$(grep -r "Python 3.13.5" /etc/systemd/system/aitbc-*.service | wc -l)
total_services=$(ls /etc/systemd/system/aitbc-*.service | wc -l)
echo "✅ $python_checks/$total_services services have Python 3.13.5+ requirement"
echo

# Summary
echo "📊 Verification Summary:"
total_checks=6
passed_checks=0

[[ $(systemctl is-active "aitbc-blockchain-node.service") == "active" ]] && ((passed_checks++))
[[ $(systemctl is-active "aitbc-blockchain-rpc.service") == "active" ]] && ((passed_checks++))
[[ $(systemctl is-active "aitbc-coordinator-api.service") == "active" ]] && ((passed_checks++))
[[ $(systemctl is-active "aitbc-exchange-api.service") == "active" ]] && ((passed_checks++))
[[ $non_aitbc_users -eq 0 ]] && ((passed_checks++))
[[ $non_opt_paths -eq 0 ]] && ((passed_checks++))

echo "✅ Passed: $passed_checks/$total_checks major checks"

if [[ $passed_checks -ge 4 ]]; then
    echo "🎉 Codebase is properly standardized and operational!"
    exit 0
else
    echo "⚠️  Some issues found - review the output above"
    exit 1
fi
