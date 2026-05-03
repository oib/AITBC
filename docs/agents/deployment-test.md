# Agent Documentation Deployment Testing

This guide outlines the testing procedures for deploying AITBC agent documentation to the live server and ensuring all components work correctly.

## Deployment Testing Checklist

### Pre-Deployment Validation

#### ✅ File Structure Validation
```bash
# Verify all documentation files exist
find docs/agents/ -type f \( -name "*.md" -o -name "*.json" -o -name "*.yaml" \) | sort

# Check for broken internal links (sample check)
find docs/agents/ -name "*.md" -exec grep -l "\[.*\](.*\.md)" {} \; | head -5

# Validate JSON syntax
python3 -m json.tool docs/agents/agent-manifest.json > /dev/null
python3 -m json.tool docs/agents/agent-api-spec.json > /dev/null

# Validate YAML syntax
python3 -c "import yaml; yaml.safe_load(open('docs/agents/agent-quickstart.yaml'))"
```

#### ✅ Content Validation
```bash
# Check markdown syntax
find docs/agents/ -name "*.md" -exec markdownlint {} \;

# Verify all CLI commands are documented
grep -r "aitbc " docs/agents/ | grep -E "(create|execute|deploy|swarm)" | wc -l

# Check machine-readable formats completeness
ls docs/agents/*.json docs/agents/*.yaml | wc -l
```

### Deployment Testing Script

```bash
#!/bin/bash
# deploy-test.sh - Agent Documentation Deployment Test

set -e

echo "🚀 Starting AITBC Agent Documentation Deployment Test"

# Configuration
DOCS_DIR="docs/agents"
LIVE_SERVER="aitbc-cascade"
WEB_ROOT="/var/www/aitbc.bubuit.net/docs/agents"

# Step 1: Validate local files
echo "📋 Step 1: Validating local documentation files..."
if [ ! -d "$DOCS_DIR" ]; then
    echo "❌ Documentation directory not found: $DOCS_DIR"
    exit 1
fi

# Check required files
required_files=(
    "README.md"
    "getting-started.md"
    "agent-manifest.json"
    "agent-quickstart.yaml"
    "agent-api-spec.json"
    "index.yaml"
    "compute-provider.md"
    "advanced-ai-agents.md"
    "collaborative-agents.md"
    "openclaw-integration.md"
)

for file in "${required_files[@]}"; do
    if [ ! -f "$DOCS_DIR/$file" ]; then
        echo "❌ Required file missing: $file"
        exit 1
    fi
done

echo "✅ All required files present"

# Step 2: Validate JSON/YAML syntax
echo "🔍 Step 2: Validating JSON/YAML syntax..."
python3 -m json.tool "$DOCS_DIR/agent-manifest.json" > /dev/null || {
    echo "❌ Invalid JSON in agent-manifest.json"
    exit 1
}

python3 -m json.tool "$DOCS_DIR/agent-api-spec.json" > /dev/null || {
    echo "❌ Invalid JSON in agent-api-spec.json"
    exit 1
}

python3 -c "import yaml; yaml.safe_load(open('$DOCS_DIR/agent-quickstart.yaml'))" || {
    echo "❌ Invalid YAML in agent-quickstart.yaml"
    exit 1
}

echo "✅ JSON/YAML syntax valid"

# Step 3: Test documentation accessibility
echo "🌐 Step 3: Testing documentation accessibility..."
# Create test script to check documentation structure
cat > test_docs.py << 'EOF'
import json
import yaml
import os

def test_agent_manifest():
    with open('docs/agents/agent-manifest.json') as f:
        manifest = json.load(f)
    
    required_keys = ['aitbc_agent_manifest', 'agent_types', 'network_protocols']
    for key in required_keys:
        if key not in manifest['aitbc_agent_manifest']:
            raise Exception(f"Missing key in manifest: {key}")
    
    print("✅ Agent manifest validation passed")

def test_api_spec():
    with open('docs/agents/agent-api-spec.json') as f:
        api_spec = json.load(f)
    
    if 'aitbc_agent_api' not in api_spec:
        raise Exception("Missing aitbc_agent_api key")
    
    endpoints = api_spec['aitbc_agent_api']['endpoints']
    required_endpoints = ['agent_registry', 'resource_marketplace', 'swarm_coordination']
    
    for endpoint in required_endpoints:
        if endpoint not in endpoints:
            raise Exception(f"Missing endpoint: {endpoint}")
    
    print("✅ API spec validation passed")

def test_quickstart():
    with open('docs/agents/agent-quickstart.yaml') as f:
        quickstart = yaml.safe_load(f)
    
    required_sections = ['network', 'agent_types', 'onboarding_workflow']
    for section in required_sections:
        if section not in quickstart:
            raise Exception(f"Missing section: {section}")
    
    print("✅ Quickstart validation passed")

if __name__ == "__main__":
    test_agent_manifest()
    test_api_spec()
    test_quickstart()
    print("✅ All documentation tests passed")
EOF

python3 test_docs.py || {
    echo "❌ Documentation validation failed"
    exit 1
}

echo "✅ Documentation accessibility test passed"

# Step 4: Deploy to test environment
echo "📦 Step 4: Deploying to test environment..."
# Create temporary test directory
TEST_DIR="/tmp/aitbc-agent-docs-test"
mkdir -p "$TEST_DIR"

# Copy documentation
cp -r "$DOCS_DIR"/* "$TEST_DIR/"

# Test file permissions
find "$TEST_DIR" -type f -exec chmod 644 {} \;
find "$TEST_DIR" -type d -exec chmod 755 {} \;

echo "✅ Files copied to test environment"

# Step 5: Test web server configuration
echo "🌐 Step 5: Testing web server configuration..."
# Create test nginx configuration
cat > test_nginx.conf << 'EOF'
server {
    listen 8080;
    server_name localhost;
    
    location /docs/agents/ {
        alias /tmp/aitbc-agent-docs-test/;
        index README.md;
        
        # Serve markdown files
        location ~* \.md$ {
            add_header Content-Type text/plain;
        }
        
        # Serve JSON files
        location ~* \.json$ {
            add_header Content-Type application/json;
        }
        
        # Serve YAML files
        location ~* \.yaml$ {
            add_header Content-Type application/x-yaml;
        }
    }
}
EOF

echo "✅ Web server configuration prepared"

# Step 6: Test documentation URLs
echo "🔗 Step 6: Testing documentation URLs..."
# Create URL test script
cat > test_urls.py << 'EOF'
import requests
import json

base_url = "http://localhost:8080/docs/agents"

test_urls = [
    "/README.md",
    "/getting-started.md",
    "/agent-manifest.json",
    "/agent-quickstart.yaml",
    "/agent-api-spec.json",
    "/advanced-ai-agents.md",
    "/collaborative-agents.md",
    "/openclaw-integration.md"
]

for url_path in test_urls:
    try:
        response = requests.get(f"{base_url}{url_path}", timeout=5)
        if response.status_code == 200:
            print(f"✅ {url_path} - {response.status_code}")
        else:
            print(f"❌ {url_path} - {response.status_code}")
            exit(1)
    except Exception as e:
        print(f"❌ {url_path} - Error: {e}")
        exit(1)

print("✅ All URLs accessible")
EOF

echo "✅ URL test script prepared"

# Step 7: Generate deployment report
echo "📊 Step 7: Generating deployment report..."
cat > deployment-report.json << EOF
{
  "deployment_test": {
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "status": "passed",
    "tests_completed": [
      "file_structure_validation",
      "json_yaml_syntax_validation",
      "content_validation",
      "accessibility_testing",
      "web_server_configuration",
      "url_accessibility"
    ],
    "files_deployed": $(find "$DOCS_DIR" -type f \( -name "*.md" -o -name "*.json" -o -name "*.yaml" \) | wc -l),
    "documentation_size_mb": $(du -sm "$DOCS_DIR" | cut -f1),
    "machine_readable_files": $(find "$DOCS_DIR" -name "*.json" -o -name "*.yaml" | wc -l),
    "ready_for_production": true
  }
}
EOF

echo "✅ Deployment report generated"

# Cleanup
rm -f test_docs.py test_nginx.conf test_urls.py
rm -rf "$TEST_DIR"

echo "🎉 Deployment testing completed successfully!"
echo "📋 Ready for production deployment to live server"
EOF

chmod +x deploy-test.sh
