#!/bin/bash
# deploy-agent-docs.sh - Test deployment of AITBC agent documentation

set -e

echo "🚀 Starting AITBC Agent Documentation Deployment Test"

# Configuration
DOCS_DIR="docs/11_agents"
LIVE_SERVER="aitbc-cascade"
WEB_ROOT="/var/www/aitbc.bubuit.net/docs/agents"
TEST_DIR="/tmp/aitbc-agent-docs-test"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Step 1: Validate local files
echo "📋 Step 1: Validating local documentation files..."
if [ ! -d "$DOCS_DIR" ]; then
    print_error "Documentation directory not found: $DOCS_DIR"
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
    "project-structure.md"
    "MERGE_SUMMARY.md"
)

missing_files=()
for file in "${required_files[@]}"; do
    if [ ! -f "$DOCS_DIR/$file" ]; then
        missing_files+=("$file")
    fi
done

if [ ${#missing_files[@]} -gt 0 ]; then
    print_error "Required files missing:"
    for file in "${missing_files[@]}"; do
        echo "  - $file"
    done
    exit 1
fi

print_status "All required files present ($(echo ${#required_files[@]} files)"

# Step 2: Validate JSON/YAML syntax
echo "🔍 Step 2: Validating JSON/YAML syntax..."

# Validate JSON files
json_files=("agent-manifest.json" "agent-api-spec.json")
for json_file in "${json_files[@]}"; do
    if ! python3 -m json.tool "$DOCS_DIR/$json_file" > /dev/null 2>&1; then
        print_error "Invalid JSON in $json_file"
        exit 1
    fi
    print_status "JSON valid: $json_file"
done

# Validate YAML files
yaml_files=("agent-quickstart.yaml" "index.yaml")
for yaml_file in "${yaml_files[@]}"; do
    if ! python3 -c "import yaml; yaml.safe_load(open('$DOCS_DIR/$yaml_file'))" 2>/dev/null; then
        print_error "Invalid YAML in $yaml_file"
        exit 1
    fi
    print_status "YAML valid: $yaml_file"
done

print_status "All JSON/YAML syntax valid"

# Step 3: Test documentation structure
echo "🏗️  Step 3: Testing documentation structure..."

# Create Python test script
cat > /tmp/test_docs_structure.py << 'EOF'
import json
import yaml
import os
import sys

def test_agent_manifest():
    try:
        with open('docs/11_agents/agent-manifest.json') as f:
            manifest = json.load(f)
        
        required_keys = ['aitbc_agent_manifest']
        for key in required_keys:
            if key not in manifest:
                raise Exception(f"Missing key in manifest: {key}")
        
        # Check agent types
        agent_types = manifest['aitbc_agent_manifest'].get('agent_types', {})
        required_agent_types = ['compute_provider', 'compute_consumer', 'platform_builder', 'swarm_coordinator']
        
        for agent_type in required_agent_types:
            if agent_type not in agent_types:
                raise Exception(f"Missing agent type: {agent_type}")
        
        print("✅ Agent manifest validation passed")
        return True
    except Exception as e:
        print(f"❌ Agent manifest validation failed: {e}")
        return False

def test_api_spec():
    try:
        with open('docs/11_agents/agent-api-spec.json') as f:
            api_spec = json.load(f)
        
        if 'aitbc_agent_api' not in api_spec:
            raise Exception("Missing aitbc_agent_api key")
        
        endpoints = api_spec['aitbc_agent_api'].get('endpoints', {})
        required_endpoints = ['agent_registry', 'resource_marketplace', 'swarm_coordination', 'reputation_system']
        
        for endpoint in required_endpoints:
            if endpoint not in endpoints:
                raise Exception(f"Missing endpoint: {endpoint}")
        
        print("✅ API spec validation passed")
        return True
    except Exception as e:
        print(f"❌ API spec validation failed: {e}")
        return False

def test_quickstart():
    try:
        with open('docs/11_agents/agent-quickstart.yaml') as f:
            quickstart = yaml.safe_load(f)
        
        required_sections = ['network', 'agent_types', 'onboarding_workflow']
        for section in required_sections:
            if section not in quickstart:
                raise Exception(f"Missing section: {section}")
        
        print("✅ Quickstart validation passed")
        return True
    except Exception as e:
        print(f"❌ Quickstart validation failed: {e}")
        return False

def test_index_structure():
    try:
        with open('docs/11_agents/index.yaml') as f:
            index = yaml.safe_load(f)
        
        required_sections = ['network', 'agent_types', 'documentation_structure']
        for section in required_sections:
            if section not in index:
                raise Exception(f"Missing section in index: {section}")
        
        print("✅ Index structure validation passed")
        return True
    except Exception as e:
        print(f"❌ Index structure validation failed: {e}")
        return False

if __name__ == "__main__":
    tests = [
        test_agent_manifest,
        test_api_spec,
        test_quickstart,
        test_index_structure
    ]
    
    passed = 0
    for test in tests:
        if test():
            passed += 1
        else:
            sys.exit(1)
    
    print(f"✅ All {passed} documentation tests passed")
EOF

if ! python3 /tmp/test_docs_structure.py; then
    print_error "Documentation structure validation failed"
    rm -f /tmp/test_docs_structure.py
    exit 1
fi

rm -f /tmp/test_docs_structure.py
print_status "Documentation structure validation passed"

# Step 4: Create test deployment
echo "📦 Step 4: Creating test deployment..."

# Clean up previous test
rm -rf "$TEST_DIR"
mkdir -p "$TEST_DIR"

# Copy documentation files
cp -r "$DOCS_DIR"/* "$TEST_DIR/"

# Set proper permissions
find "$TEST_DIR" -type f -exec chmod 644 {} \;
find "$TEST_DIR" -type d -exec chmod 755 {} \;

# Calculate documentation size
doc_size=$(du -sm "$TEST_DIR" | cut -f1)
file_count=$(find "$TEST_DIR" -type f | wc -l)
json_count=$(find "$TEST_DIR" -name "*.json" | wc -l)
yaml_count=$(find "$TEST_DIR" -name "*.yaml" | wc -l)
md_count=$(find "$TEST_DIR" -name "*.md" | wc -l)

print_status "Test deployment created"
echo "   📊 Size: ${doc_size}MB"
echo "   📄 Files: $file_count total"
echo "   📋 JSON: $json_count files"
echo "   📋 YAML: $yaml_count files"
echo "   📋 Markdown: $md_count files"

# Step 5: Test file accessibility
echo "🔍 Step 5: Testing file accessibility..."

# Test key files can be read
test_files=(
    "$TEST_DIR/README.md"
    "$TEST_DIR/agent-manifest.json"
    "$TEST_DIR/agent-quickstart.yaml"
    "$TEST_DIR/agent-api-spec.json"
)

for file in "${test_files[@]}"; do
    if [ ! -r "$file" ]; then
        print_error "Cannot read file: $file"
        exit 1
    fi
done

print_status "All test files accessible"

# Step 6: Test content integrity
echo "🔐 Step 6: Testing content integrity..."

# Test JSON files can be parsed
for json_file in "$TEST_DIR"/*.json; do
    if [ -f "$json_file" ]; then
        if ! python3 -m json.tool "$json_file" > /dev/null 2>&1; then
            print_error "JSON file corrupted: $(basename $json_file)"
            exit 1
        fi
    fi
done

# Test YAML files can be parsed
for yaml_file in "$TEST_DIR"/*.yaml; do
    if [ -f "$yaml_file" ]; then
        if ! python3 -c "import yaml; yaml.safe_load(open('$yaml_file'))" 2>/dev/null; then
            print_error "YAML file corrupted: $(basename $yaml_file)"
            exit 1
        fi
    fi
done

print_status "Content integrity verified"

# Step 7: Generate deployment report
echo "📊 Step 7: Generating deployment report..."

report_file="$TEST_DIR/deployment-report.json"
cat > "$report_file" << EOF
{
  "deployment_test": {
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "status": "passed",
    "tests_completed": [
      "file_structure_validation",
      "json_yaml_syntax_validation",
      "documentation_structure_testing",
      "test_deployment_creation",
      "file_accessibility_testing",
      "content_integrity_verification"
    ],
    "statistics": {
      "total_files": $file_count,
      "json_files": $json_count,
      "yaml_files": $yaml_count,
      "markdown_files": $md_count,
      "total_size_mb": $doc_size
    },
    "required_files": {
      "count": ${#required_files[@]},
      "all_present": true
    },
    "ready_for_production": true,
    "next_steps": [
      "Deploy to live server",
      "Update web server configuration",
      "Test live URLs",
      "Monitor performance"
    ]
  }
}
EOF

print_status "Deployment report generated"

# Step 8: Cleanup
echo "🧹 Step 8: Cleanup..."
rm -rf "$TEST_DIR"

print_status "Test cleanup completed"

# Final summary
echo ""
echo "🎉 DEPLOYMENT TESTING COMPLETED SUCCESSFULLY!"
echo ""
echo "📋 TEST SUMMARY:"
echo "   ✅ File structure validation"
echo "   ✅ JSON/YAML syntax validation"
echo "   ✅ Documentation structure testing"
echo "   ✅ Test deployment creation"
echo "   ✅ File accessibility testing"
echo "   ✅ Content integrity verification"
echo ""
echo "📊 STATISTICS:"
echo "   📄 Total files: $file_count"
echo "   📋 JSON files: $json_count"
echo "   📋 YAML files: $yaml_count"
echo "   📋 Markdown files: $md_count"
echo "   💾 Total size: ${doc_size}MB"
echo ""
echo "🚀 READY FOR PRODUCTION DEPLOYMENT!"
echo ""
echo "Next steps:"
echo "1. Deploy to live server: ssh $LIVE_SERVER"
echo "2. Copy files to: $WEB_ROOT"
echo "3. Test live URLs"
echo "4. Monitor performance"
