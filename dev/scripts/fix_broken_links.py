import os
import re

def replace_in_file(filepath, replacements):
    with open(filepath, 'r') as f:
        content = f.read()
    
    modified = content
    for old, new in replacements:
        modified = modified.replace(old, new)
        
    if modified != content:
        with open(filepath, 'w') as f:
            f.write(modified)
        print(f"Fixed links in {filepath}")

# Fix docs/README.md
replace_in_file('docs/README.md', [
    ('../3_miners/1_quick-start.md', '3_miners/1_quick-start.md'),
    ('../2_clients/1_quick-start.md', '2_clients/1_quick-start.md'),
    ('../8_development/', '8_development/'),
    ('../11_agents/', '11_agents/'),
    ('../cli/README.md', '../cli/README.md') # Actually, this should probably point to docs/5_reference/ or somewhere else, let's just make it a relative link up one dir
])

# Fix docs/0_getting_started/3_cli.md
replace_in_file('docs/0_getting_started/3_cli.md', [
    ('../11_agents/swarm/', '../11_agents/swarm.md') # Link to the file instead of directory
])

# Fix docs/0_getting_started/ENHANCED_SERVICES_IMPLEMENTATION_GUIDE.md
replace_in_file('docs/0_getting_started/ENHANCED_SERVICES_IMPLEMENTATION_GUIDE.md', [
    ('docs/', '../')
])

# Fix docs/18_explorer/EXPLORER_FINAL_STATUS.md
replace_in_file('docs/18_explorer/EXPLORER_FINAL_STATUS.md', [
    ('../apps/blockchain-explorer/README.md', '../../apps/blockchain-explorer/README.md')
])

# Fix docs/20_phase_reports/COMPREHENSIVE_GUIDE.md
replace_in_file('docs/20_phase_reports/COMPREHENSIVE_GUIDE.md', [
    ('docs/11_agents/', '../11_agents/'),
    ('docs/2_clients/', '../2_clients/'),
    ('docs/6_architecture/', '../6_architecture/'),
    ('docs/10_plan/', '../10_plan/'),
    ('LICENSE', '../../LICENSE')
])

# Fix docs/security/SECURITY_AGENT_WALLET_PROTECTION.md
replace_in_file('docs/security/SECURITY_AGENT_WALLET_PROTECTION.md', [
    ('../docs/SECURITY_ARCHITECTURE.md', 'SECURITY_ARCHITECTURE.md'),
    ('../docs/SMART_CONTRACT_SECURITY.md', 'SMART_CONTRACT_SECURITY.md'),
    ('../docs/AGENT_DEVELOPMENT.md', '../11_agents/AGENT_DEVELOPMENT.md')
])

print("Finished fixing broken links")
