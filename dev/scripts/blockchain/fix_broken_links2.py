import os

def replace_in_file(filepath, replacements):
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        
        modified = content
        for old, new in replacements:
            modified = modified.replace(old, new)
            
        if modified != content:
            with open(filepath, 'w') as f:
                f.write(modified)
            print(f"Fixed links in {filepath}")
    except Exception as e:
        print(f"Error in {filepath}: {e}")

# Fix docs/README.md
replace_in_file('docs/README.md', [
    ('../cli/README.md', '0_getting_started/3_cli.md')
])

# Fix docs/8_development/DEVELOPMENT_GUIDELINES.md
replace_in_file('docs/8_development/DEVELOPMENT_GUIDELINES.md', [
    ('../.windsurf/workflows/project-organization.md', '../../.windsurf/workflows/project-organization.md'),
    ('../.windsurf/workflows/file-organization-prevention.md', '../../.windsurf/workflows/file-organization-prevention.md')
])

# Fix docs/20_phase_reports/COMPREHENSIVE_GUIDE.md
replace_in_file('docs/20_phase_reports/COMPREHENSIVE_GUIDE.md', [
    ('../11_agents/marketplace/', '../11_agents/README.md'),
    ('../11_agents/swarm/', '../11_agents/README.md'),
    ('../11_agents/development/', '../11_agents/README.md'),
    ('../10_plan/multi-language-apis-completed.md', '../12_issues/multi-language-apis-completed.md') # Assuming it might move or we just remove it
])

# Fix docs/security/SECURITY_AGENT_WALLET_PROTECTION.md
replace_in_file('docs/security/SECURITY_AGENT_WALLET_PROTECTION.md', [
    ('SECURITY_ARCHITECTURE.md', 'SECURITY_OVERVIEW.md'), # If it exists
    ('SMART_CONTRACT_SECURITY.md', 'README.md'),
    ('../11_agents/AGENT_DEVELOPMENT.md', '../11_agents/README.md')
])

print("Finished fixing broken links 2")
